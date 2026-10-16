from __future__ import annotations

import io
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict

import polars as pl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.dataset import (
    Dataset,
    DatasetTable,
    DatasetVersion,
    DatasetVersionStatus,
    Transformation,
)
from app.services.profiling import ParsingError, parse_upload, profile_table
from app.services.storage import ObjectStorage
from app.services.upload_validation import UploadValidationError, validate_upload


class DatasetServiceError(Exception):
    """Raised for client-facing errors (bad upload, not found, etc). The
    router translates this to an HTTP error response."""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "sheet"


async def _next_version_number(db: AsyncSession, dataset_id: str) -> int:
    result = await db.execute(
        select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)
    )
    current_max = result.scalar_one_or_none()
    return (current_max or 0) + 1


def _profile_to_dict(table_profile) -> dict:
    data = asdict(table_profile)
    return data


async def ingest_upload(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    workspace_id: str,
    dataset: Dataset | None,
    dataset_name: str,
    filename: str,
    content: bytes,
    user_id: str,
) -> DatasetVersion:
    """Validate, parse and profile an uploaded file, then persist it as a
    new DatasetVersion (creating the parent Dataset if one wasn't passed
    in). Raises DatasetServiceError on any validation/parsing failure —
    nothing is written to the database or object storage in that case."""

    settings = get_settings()

    try:
        validated = validate_upload(filename, content, settings.max_upload_size_bytes)
    except UploadValidationError as exc:
        raise DatasetServiceError(str(exc)) from exc

    try:
        tables, invalid_value_counts = parse_upload(validated.extension, validated.content)
    except ParsingError as exc:
        raise DatasetServiceError(str(exc)) from exc

    profiles = {
        sheet_name: profile_table(sheet_name, df, invalid_value_counts.get(sheet_name))
        for sheet_name, df in tables.items()
    }

    if dataset is None:
        dataset = Dataset(workspace_id=workspace_id, name=dataset_name, created_by_user_id=user_id)
        db.add(dataset)
        await db.flush()

    version_number = await _next_version_number(db, dataset.id)
    version_id = str(uuid.uuid4())

    source_key = f"workspaces/{workspace_id}/datasets/{dataset.id}/versions/{version_id}/source/{filename}"
    storage.write(source_key, content)

    version = DatasetVersion(
        id=version_id,
        dataset_id=dataset.id,
        version_number=version_number,
        status=DatasetVersionStatus.READY,
        source_filename=filename,
        storage_key=source_key,
        file_size_bytes=len(content),
        created_by_user_id=user_id,
    )
    db.add(version)
    await db.flush()

    for sheet_name, df in tables.items():
        table_profile = profiles[sheet_name]
        parquet_buffer = io.BytesIO()
        df.write_parquet(parquet_buffer)
        data_key = (
            f"workspaces/{workspace_id}/datasets/{dataset.id}/versions/{version_id}/"
            f"tables/{_slugify(sheet_name)}.parquet"
        )
        storage.write(data_key, parquet_buffer.getvalue())

        db.add(
            DatasetTable(
                dataset_version_id=version.id,
                sheet_name=sheet_name,
                row_count=table_profile.row_count,
                column_count=table_profile.column_count,
                profile=_profile_to_dict(table_profile),
                data_storage_key=data_key,
            )
        )

    await db.commit()
    await db.refresh(version)
    return version


async def get_dataset_table_dataframe(storage: ObjectStorage, table: DatasetTable) -> pl.DataFrame:
    content = storage.read(table.data_storage_key)
    return pl.read_parquet(io.BytesIO(content))


async def get_table_for_version(
    db: AsyncSession, dataset_id: str, version_number: int, sheet_name: str | None
) -> DatasetTable:
    """Resolves the DatasetTable for a given dataset's version_number +
    optional sheet_name — shared by any endpoint that needs to address a
    specific historical snapshot (currently: version comparison)."""
    version_result = await db.execute(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.version_number == version_number
        )
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise DatasetServiceError(f"Version {version_number} not found for this dataset.")

    tables_result = await db.execute(select(DatasetTable).where(DatasetTable.dataset_version_id == version.id))
    tables = list(tables_result.scalars().all())
    if not tables:
        raise DatasetServiceError(f"Version {version_number} has no tables.")

    if sheet_name is not None:
        matching = [t for t in tables if t.sheet_name == sheet_name]
        if not matching:
            available = ", ".join(t.sheet_name for t in tables)
            raise DatasetServiceError(
                f"Version {version_number} has no sheet named '{sheet_name}'. Available: {available}."
            )
        return matching[0]

    if len(tables) > 1:
        available = ", ".join(t.sheet_name for t in tables)
        raise DatasetServiceError(
            f"Version {version_number} has multiple sheets ({available}) — specify sheet_name."
        )
    return tables[0]


async def _apply_table_transformation(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    operation_type: str,
    mutate: Callable[[pl.DataFrame], tuple[pl.DataFrame, dict]],
) -> DatasetVersion:
    """Shared machinery behind every cleaning operation (deduplicate,
    fill-missing-values, normalize-text, filter-rows, calculated-field):
    produces a new DatasetVersion carrying every sheet from the source
    version forward (only the targeted sheet is actually transformed —
    the rest are copied through unchanged), and records a Transformation
    audit entry. The source version is never mutated.

    `mutate` receives the target sheet's DataFrame and returns
    `(new_df, extra_parameters)` — extra_parameters is merged into the
    Transformation's audit record (e.g. rows_removed, fill_value). It
    runs against every sibling table's DataFrame loaded into memory
    first, and BEFORE any new version/table/storage write happens — so
    an invalid operation (unknown column, wrong dtype, ...) raises
    cleanly with nothing persisted, not a half-written version."""

    source_version = await db.get(DatasetVersion, source_table.dataset_version_id)
    if source_version is None:
        raise DatasetServiceError("Source dataset version not found.")
    dataset_id = source_version.dataset_id

    # Load every table in the source version so the new version is a
    # complete, independently-readable snapshot (not just the one sheet
    # that changed).
    result = await db.execute(
        select(DatasetTable).where(DatasetTable.dataset_version_id == source_version.id)
    )
    sibling_tables = list(result.scalars().all())

    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise DatasetServiceError("Dataset not found.")
    workspace_id = dataset.workspace_id

    dataframes: dict[str, pl.DataFrame] = {}
    for table in sibling_tables:
        dataframes[table.id] = await get_dataset_table_dataframe(storage, table)

    new_df, extra_parameters = mutate(dataframes[source_table.id])
    dataframes[source_table.id] = new_df

    version_number = await _next_version_number(db, dataset_id)
    version_id = str(uuid.uuid4())

    new_version = DatasetVersion(
        id=version_id,
        dataset_id=dataset_id,
        version_number=version_number,
        status=DatasetVersionStatus.READY,
        derived_from_version_id=source_version.id,
        created_by_user_id=user_id,
    )
    db.add(new_version)
    await db.flush()

    for table in sibling_tables:
        df = dataframes[table.id]
        table_profile = profile_table(table.sheet_name, df)
        parquet_buffer = io.BytesIO()
        df.write_parquet(parquet_buffer)
        data_key = (
            f"workspaces/{workspace_id}/datasets/{dataset_id}/versions/{version_id}/"
            f"tables/{_slugify(table.sheet_name)}.parquet"
        )
        storage.write(data_key, parquet_buffer.getvalue())

        db.add(
            DatasetTable(
                dataset_version_id=new_version.id,
                sheet_name=table.sheet_name,
                row_count=table_profile.row_count,
                column_count=table_profile.column_count,
                profile=_profile_to_dict(table_profile),
                confirmed_schema=table.confirmed_schema,
                confirmed_field_mapping=table.confirmed_field_mapping,
                data_storage_key=data_key,
            )
        )

    db.add(
        Transformation(
            dataset_id=dataset_id,
            source_version_id=source_version.id,
            result_version_id=new_version.id,
            operation_type=operation_type,
            parameters={"table_sheet_name": source_table.sheet_name, **extra_parameters},
            performed_by_user_id=user_id,
        )
    )

    await db.commit()
    await db.refresh(new_version)
    return new_version


async def apply_deduplicate(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
) -> DatasetVersion:
    """The first real cleaning operation: remove exact-duplicate rows."""

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        before = df.height
        df = df.unique(keep="first", maintain_order=True)
        return df, {"rows_removed": before - df.height}

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="deduplicate", mutate=mutate
    )


def _require_column(df: pl.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise DatasetServiceError(
            f"Unknown column: {column!r}. Available: {', '.join(df.columns)}."
        )


FILL_STRATEGIES = {"drop_rows", "constant", "mean", "median", "mode"}


async def apply_fill_missing_values(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    column: str,
    strategy: str,
    constant_value: object = None,
) -> DatasetVersion:
    """Handle missing values in one column: drop rows with a null, fill
    with a given constant, or fill with the column's mean/median/mode.
    mean/median require a numeric column; mode works for any dtype
    (picks the single most frequent non-null value)."""

    if strategy not in FILL_STRATEGIES:
        raise DatasetServiceError(f"Unknown strategy: {strategy!r}. Valid: {', '.join(sorted(FILL_STRATEGIES))}.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, column)
        before = df.height
        series = df[column]
        nulls_before = series.null_count()

        if strategy == "drop_rows":
            new_df = df.filter(pl.col(column).is_not_null())
            return new_df, {"column": column, "strategy": strategy, "rows_removed": before - new_df.height}

        if strategy == "constant":
            if constant_value is None:
                raise DatasetServiceError("constant_value is required for the 'constant' strategy.")
            try:
                new_df = df.with_columns(pl.col(column).fill_null(pl.lit(constant_value)))
            except Exception as exc:  # polars raises its own dtype-mismatch errors
                raise DatasetServiceError(
                    f"Could not fill column {column!r} with {constant_value!r}: {exc}"
                ) from exc
            return new_df, {"column": column, "strategy": strategy, "constant_value": constant_value, "values_filled": nulls_before}

        if strategy in ("mean", "median"):
            if not series.dtype.is_numeric():
                raise DatasetServiceError(
                    f"Column {column!r} is not numeric (dtype: {series.dtype}) — "
                    f"'{strategy}' only applies to numeric columns."
                )
            fill_value = series.mean() if strategy == "mean" else series.median()
            if fill_value is None:
                raise DatasetServiceError(f"Column {column!r} has no non-null values to compute a {strategy} from.")
            new_df = df.with_columns(pl.col(column).fill_null(fill_value))
            return new_df, {"column": column, "strategy": strategy, "fill_value": fill_value, "values_filled": nulls_before}

        # mode
        non_null = series.drop_nulls()
        if non_null.len() == 0:
            raise DatasetServiceError(f"Column {column!r} has no non-null values to compute a mode from.")
        fill_value = non_null.mode()[0]
        new_df = df.with_columns(pl.col(column).fill_null(pl.lit(fill_value)))
        return new_df, {"column": column, "strategy": strategy, "fill_value": fill_value, "values_filled": nulls_before}

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="fill_missing_values", mutate=mutate
    )


async def apply_normalize_text(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    column: str,
    case: str | None = None,
    trim: bool = True,
    collapse_whitespace: bool = True,
) -> DatasetVersion:
    """Normalize a text column: trim surrounding whitespace, collapse
    repeated internal whitespace to single spaces, and/or change case.
    Only applies to text (Utf8) columns — a numeric/date/boolean column
    is rejected rather than silently stringified."""

    valid_cases = {None, "lower", "upper", "title"}
    if case not in valid_cases:
        raise DatasetServiceError(f"Unknown case: {case!r}. Valid: lower, upper, title, or omit it.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, column)
        if df[column].dtype != pl.Utf8:
            raise DatasetServiceError(
                f"Column {column!r} is not a text column (dtype: {df[column].dtype}) — "
                "normalize-text only applies to text columns."
            )

        expr = pl.col(column)
        if trim:
            expr = expr.str.strip_chars()
        if collapse_whitespace:
            expr = expr.str.replace_all(r"\s+", " ")
        if case == "lower":
            expr = expr.str.to_lowercase()
        elif case == "upper":
            expr = expr.str.to_uppercase()
        elif case == "title":
            expr = expr.str.to_titlecase()

        new_df = df.with_columns(expr.alias(column))
        return new_df, {"column": column, "case": case, "trim": trim, "collapse_whitespace": collapse_whitespace}

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="normalize_text", mutate=mutate
    )


FILTER_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "is_null", "not_null"}
_UNARY_FILTER_OPERATORS = {"is_null", "not_null"}


async def apply_filter_rows(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    column: str,
    operator: str,
    value: object = None,
) -> DatasetVersion:
    """Keep only the rows matching a condition on one column — produces a
    new, filtered version rather than a read-only query result (unlike
    the Phase 3 analytics tools, this is a persisted cleaning step with
    its own audit trail, the same as deduplicate)."""

    if operator not in FILTER_OPERATORS:
        raise DatasetServiceError(f"Unknown operator: {operator!r}. Valid: {', '.join(sorted(FILTER_OPERATORS))}.")
    if operator not in _UNARY_FILTER_OPERATORS and value is None:
        raise DatasetServiceError(f"value is required for operator {operator!r}.")
    if operator == "contains" and not isinstance(value, str):
        raise DatasetServiceError("value must be a string for the 'contains' operator.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, column)
        before = df.height
        col = pl.col(column)

        if operator == "is_null":
            condition = col.is_null()
        elif operator == "not_null":
            condition = col.is_not_null()
        elif operator == "contains":
            if df[column].dtype != pl.Utf8:
                raise DatasetServiceError(
                    f"Column {column!r} is not a text column (dtype: {df[column].dtype}) — "
                    "'contains' only applies to text columns."
                )
            condition = col.str.contains(str(value), literal=True)
        else:
            try:
                literal = pl.lit(value)
                condition = {
                    "eq": col == literal,
                    "ne": col != literal,
                    "gt": col > literal,
                    "gte": col >= literal,
                    "lt": col < literal,
                    "lte": col <= literal,
                }[operator]
            except Exception as exc:
                raise DatasetServiceError(f"Could not compare column {column!r} to {value!r}: {exc}") from exc

        try:
            new_df = df.filter(condition)
        except Exception as exc:
            raise DatasetServiceError(f"Could not filter column {column!r}: {exc}") from exc

        return new_df, {
            "column": column,
            "operator": operator,
            "value": value,
            "rows_removed": before - new_df.height,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="filter_rows", mutate=mutate
    )


ARITHMETIC_OPERATORS = {"add", "subtract", "multiply", "divide"}
CALCULATED_FIELD_OPERATORS = ARITHMETIC_OPERATORS | {"concat"}


async def apply_calculated_field(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    new_column_name: str,
    left_column: str,
    operator: str,
    right_column: str | None = None,
    right_value: object = None,
    separator: str = "",
) -> DatasetVersion:
    """Add a new column computed from existing ones: arithmetic
    (add/subtract/multiply/divide) between two numeric columns or a
    numeric column and a constant, or text concatenation between two
    text columns or a text column and a constant. Exactly one of
    right_column/right_value must be given."""

    if operator not in CALCULATED_FIELD_OPERATORS:
        raise DatasetServiceError(
            f"Unknown operator: {operator!r}. Valid: {', '.join(sorted(CALCULATED_FIELD_OPERATORS))}."
        )
    if (right_column is None) == (right_value is None):
        raise DatasetServiceError("Provide exactly one of right_column or right_value.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, left_column)
        if new_column_name in df.columns:
            raise DatasetServiceError(f"Column {new_column_name!r} already exists.")
        if right_column is not None:
            _require_column(df, right_column)
            right_expr = pl.col(right_column)
            right_dtype = df[right_column].dtype
        else:
            right_expr = pl.lit(right_value)
            right_dtype = None

        left_dtype = df[left_column].dtype

        if operator in ARITHMETIC_OPERATORS:
            if not left_dtype.is_numeric():
                raise DatasetServiceError(f"Column {left_column!r} is not numeric (dtype: {left_dtype}).")
            if right_column is not None:
                if not right_dtype.is_numeric():
                    raise DatasetServiceError(f"Column {right_column!r} is not numeric (dtype: {right_dtype}).")
            elif not isinstance(right_value, (int, float)):
                raise DatasetServiceError(f"right_value must be a number for operator {operator!r}.")

            left_expr = pl.col(left_column)
            expr = {
                "add": left_expr + right_expr,
                "subtract": left_expr - right_expr,
                "multiply": left_expr * right_expr,
                "divide": left_expr / right_expr,
            }[operator]
        else:  # concat
            if left_dtype != pl.Utf8:
                raise DatasetServiceError(f"Column {left_column!r} is not a text column (dtype: {left_dtype}).")
            if right_column is not None:
                if right_dtype != pl.Utf8:
                    raise DatasetServiceError(f"Column {right_column!r} is not a text column (dtype: {right_dtype}).")
            elif not isinstance(right_value, str):
                raise DatasetServiceError("right_value must be a string for operator 'concat'.")
            expr = pl.col(left_column) + pl.lit(separator) + right_expr

        try:
            new_df = df.with_columns(expr.alias(new_column_name))
        except Exception as exc:
            raise DatasetServiceError(f"Could not compute {new_column_name!r}: {exc}") from exc

        return new_df, {
            "new_column_name": new_column_name,
            "left_column": left_column,
            "operator": operator,
            "right_column": right_column,
            "right_value": right_value,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="calculated_field", mutate=mutate
    )


async def apply_merge_columns(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    columns: list[str],
    new_column_name: str,
    separator: str = " ",
    drop_source_columns: bool = True,
) -> DatasetVersion:
    """Combine two or more columns into one new text column — each
    source value is cast to text first, so this works across mixed
    column types (e.g. merging a numeric "year" column with a text
    "quarter" column into a "period" column), not just text-on-text."""

    if len(columns) < 2:
        raise DatasetServiceError("merge-columns needs at least 2 source columns.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        for col in columns:
            _require_column(df, col)
        if new_column_name in df.columns:
            raise DatasetServiceError(f"Column {new_column_name!r} already exists.")

        parts = [pl.col(c).cast(pl.Utf8) for c in columns]
        expr = parts[0]
        for part in parts[1:]:
            expr = expr + pl.lit(separator) + part

        new_df = df.with_columns(expr.alias(new_column_name))
        if drop_source_columns:
            new_df = new_df.drop(columns)

        return new_df, {
            "columns": columns,
            "new_column_name": new_column_name,
            "separator": separator,
            "drop_source_columns": drop_source_columns,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="merge_columns", mutate=mutate
    )


async def apply_split_column(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    column: str,
    delimiter: str,
    new_column_names: list[str] | None = None,
    drop_source_column: bool = True,
) -> DatasetVersion:
    """Split one text column into several, by a literal delimiter (not a
    regex). The number of resulting columns is however many parts the
    row with the most delimiter occurrences produces — rows with fewer
    parts get null in the extra columns, rather than the split failing.
    If new_column_names is given, its length must exactly match that
    count (computed from the actual data, so it can't be known upfront)
    — rather than silently truncating or padding a mismatched list."""

    if not delimiter:
        raise DatasetServiceError("delimiter must not be empty.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, column)
        if df[column].dtype != pl.Utf8:
            raise DatasetServiceError(
                f"Column {column!r} is not a text column (dtype: {df[column].dtype}) — "
                "split-column only applies to text columns."
            )

        parts_col = pl.col(column).str.split(delimiter)
        parts_series = df.select(parts_col.alias("_parts"))["_parts"]
        max_parts = parts_series.list.len().max() or 0
        if max_parts < 2:
            raise DatasetServiceError(
                f"No value in column {column!r} contains the delimiter {delimiter!r} — nothing to split."
            )

        if new_column_names is not None:
            if len(new_column_names) != max_parts:
                raise DatasetServiceError(
                    f"new_column_names has {len(new_column_names)} name(s), but splitting on {delimiter!r} "
                    f"produces {max_parts} column(s) for this data. Provide exactly {max_parts} name(s)."
                )
            result_names = new_column_names
        else:
            result_names = [f"{column}_{i + 1}" for i in range(max_parts)]

        for name in result_names:
            if name in df.columns and name != column:
                raise DatasetServiceError(f"Column {name!r} already exists.")
        if len(set(result_names)) != len(result_names):
            raise DatasetServiceError("new_column_names must be unique.")

        new_df = df.with_columns(parts_col.alias("_parts"))
        new_df = new_df.with_columns(
            [pl.col("_parts").list.get(i, null_on_oob=True).alias(name) for i, name in enumerate(result_names)]
        )
        new_df = new_df.drop("_parts")
        if drop_source_column:
            new_df = new_df.drop(column)

        return new_df, {
            "column": column,
            "delimiter": delimiter,
            "result_columns": result_names,
            "drop_source_column": drop_source_column,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="split_column", mutate=mutate
    )


STANDARDIZE_KINDS = {"date", "currency"}
_CURRENCY_SYMBOL_PATTERN = r"[£$€,%]"


async def apply_standardize_column(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    column: str,
    kind: str,
    date_format: str | None = None,
) -> DatasetVersion:
    """Fixes the two things app/services/profiling.py's data-quality
    profiler only *detects* and flags (numeric_stored_as_text,
    date_stored_as_text) but never corrected on its own:

    - kind="date": parses a text column against one explicit strptime
      format (e.g. "%Y-%m-%d", "%d/%m/%Y") into a real Date column.
      Deliberately requires the caller to state the format rather than
      guessing — the same DD/MM vs MM/DD ambiguity documented in
      profiling.py's _DATE_PATTERNS applies here, and guessing wrong
      silently corrupts every date in the column. A value that doesn't
      match the given format becomes null (reported as values_unparsed)
      rather than failing the whole operation — real spreadsheets mix
      a few typos into otherwise-consistent columns.
    - kind="currency": strips currency symbols (£$€), thousands
      separators, and a trailing %, then parses as a float. "12.5%"
      becomes 12.5, not 0.125 — deliberately not guessing a percentage
      should become a fraction.
    """

    if kind not in STANDARDIZE_KINDS:
        raise DatasetServiceError(f"Unknown kind: {kind!r}. Valid: {', '.join(sorted(STANDARDIZE_KINDS))}.")
    if kind == "date" and not date_format:
        raise DatasetServiceError("date_format is required when kind='date' (e.g. '%Y-%m-%d', '%d/%m/%Y').")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        _require_column(df, column)
        if df[column].dtype != pl.Utf8:
            raise DatasetServiceError(
                f"Column {column!r} is not a text column (dtype: {df[column].dtype}) — nothing to standardize."
            )
        nulls_before = df[column].null_count()

        if kind == "date":
            try:
                new_df = df.with_columns(pl.col(column).str.strptime(pl.Date, format=date_format, strict=False))
            except Exception as exc:
                raise DatasetServiceError(f"Invalid date_format {date_format!r}: {exc}") from exc
        else:
            cleaned = pl.col(column).str.strip_chars().str.replace_all(_CURRENCY_SYMBOL_PATTERN, "")
            new_df = df.with_columns(cleaned.cast(pl.Float64, strict=False))

        nulls_after = new_df[column].null_count()
        return new_df, {
            "column": column,
            "kind": kind,
            "date_format": date_format,
            "values_unparsed": nulls_after - nulls_before,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="standardize_column", mutate=mutate
    )


PIVOT_AGGREGATE_FUNCTIONS = {"min", "max", "first", "last", "sum", "mean", "median", "len"}
MAX_PIVOT_COLUMNS = 50  # guard against an unreasonable column explosion from a high-cardinality pivot column


async def apply_pivot(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    index_columns: list[str],
    pivot_column: str,
    value_column: str,
    aggregate_function: str = "sum",
) -> DatasetVersion:
    """Long-to-wide reshape: one row per distinct combination of
    index_columns, one new column per distinct value in pivot_column,
    populated by aggregating value_column. Unlike every other cleaning
    operation, this REPLACES the table's column set entirely rather than
    adding to or filtering it — any column not named in index_columns,
    pivot_column, or value_column is dropped, which is inherent to what
    "pivot" means (the row grouping itself changes), not a limitation of
    this implementation.

    An aggregate_function is always required (defaults to "sum") rather
    than letting polars raise when more than one source row shares the
    same index+pivot-value combination — real spreadsheet data routinely
    has duplicates (e.g. two expense rows in the same month/category),
    and erroring on that would make this unusable for exactly the
    messy-data case it needs to handle."""

    if not index_columns:
        raise DatasetServiceError("pivot needs at least one index column.")
    if aggregate_function not in PIVOT_AGGREGATE_FUNCTIONS:
        raise DatasetServiceError(
            f"Unknown aggregate_function: {aggregate_function!r}. Valid: {', '.join(sorted(PIVOT_AGGREGATE_FUNCTIONS))}."
        )

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        for col in [*index_columns, pivot_column, value_column]:
            _require_column(df, col)
        if value_column in index_columns or value_column == pivot_column:
            raise DatasetServiceError("value_column must be different from index_columns and pivot_column.")
        if pivot_column in index_columns:
            raise DatasetServiceError("pivot_column must not also be one of index_columns.")

        distinct_count = df[pivot_column].n_unique()
        if distinct_count > MAX_PIVOT_COLUMNS:
            raise DatasetServiceError(
                f"Column {pivot_column!r} has {distinct_count} distinct values — pivoting would create "
                f"that many new columns (max {MAX_PIVOT_COLUMNS}). Filter the data first to reduce this."
            )

        try:
            new_df = df.pivot(
                on=pivot_column, index=index_columns, values=value_column, aggregate_function=aggregate_function
            )
        except Exception as exc:
            raise DatasetServiceError(f"Could not pivot: {exc}") from exc

        return new_df, {
            "index_columns": index_columns,
            "pivot_column": pivot_column,
            "value_column": value_column,
            "aggregate_function": aggregate_function,
            "result_columns": new_df.columns,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="pivot", mutate=mutate
    )


async def apply_unpivot(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    id_columns: list[str],
    value_columns: list[str],
    variable_name: str = "variable",
    value_name: str = "value",
) -> DatasetVersion:
    """Wide-to-long reshape: for each row, one output row per column
    named in value_columns, carrying that column's name (in
    variable_name) and its value (in value_name) alongside the
    unchanged id_columns. Unlike pivot, the resulting column count is
    always fixed (len(id_columns) + 2) — only the row count grows,
    which is why this is the simpler direction of the two."""

    if not id_columns:
        raise DatasetServiceError("unpivot needs at least one id column.")
    if not value_columns:
        raise DatasetServiceError("unpivot needs at least one value column.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        for col in [*id_columns, *value_columns]:
            _require_column(df, col)
        overlap = set(id_columns) & set(value_columns)
        if overlap:
            raise DatasetServiceError(f"Column(s) in both id_columns and value_columns: {', '.join(sorted(overlap))}.")
        # The output schema is id_columns + [variable_name, value_name] —
        # value_columns themselves are consumed by the reshape, so only a
        # collision against a *surviving* id column (or between the two
        # new names) is actually a problem.
        if variable_name in id_columns:
            raise DatasetServiceError(f"variable_name {variable_name!r} collides with an id column.")
        if value_name in id_columns:
            raise DatasetServiceError(f"value_name {value_name!r} collides with an id column.")
        if variable_name == value_name:
            raise DatasetServiceError("variable_name and value_name must be different.")

        try:
            new_df = df.unpivot(
                index=id_columns, on=value_columns, variable_name=variable_name, value_name=value_name
            )
        except Exception as exc:
            raise DatasetServiceError(f"Could not unpivot: {exc}") from exc

        return new_df, {
            "id_columns": id_columns,
            "value_columns": value_columns,
            "variable_name": variable_name,
            "value_name": value_name,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="unpivot", mutate=mutate
    )


GROUP_BY_FUNCTIONS = {"sum", "mean", "min", "max", "median", "count"}


async def apply_group_by(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    source_table: DatasetTable,
    user_id: str,
    group_by_columns: list[str],
    aggregations: list[dict],
) -> DatasetVersion:
    """Persisted group-by: one row per distinct combination of
    group_by_columns, with one or more named aggregate columns
    (sum/mean/min/max/median/count) — the version-producing counterpart
    to the read-only `group_aggregate` analytics tool (Phase 3), which
    only ever returns a single aggregation as a query result, never a
    new table. Each entry in `aggregations` is
    {column, function, output_name} — `column` is omitted for "count"
    (it counts rows per group, not values in a specific column)."""

    if not group_by_columns:
        raise DatasetServiceError("group-by needs at least one group_by column.")
    if not aggregations:
        raise DatasetServiceError("group-by needs at least one aggregation.")

    def mutate(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
        for col in group_by_columns:
            _require_column(df, col)

        agg_exprs = []
        used_names = set(group_by_columns)
        for agg in aggregations:
            function = agg.get("function")
            output_name = agg.get("output_name")
            column = agg.get("column")

            if function not in GROUP_BY_FUNCTIONS:
                raise DatasetServiceError(
                    f"Unknown aggregation function: {function!r}. Valid: {', '.join(sorted(GROUP_BY_FUNCTIONS))}."
                )
            if not output_name:
                raise DatasetServiceError("Every aggregation needs an output_name.")
            if output_name in used_names:
                raise DatasetServiceError(f"Duplicate or colliding output_name: {output_name!r}.")
            used_names.add(output_name)

            if function == "count":
                agg_exprs.append(pl.len().alias(output_name))
                continue

            if not column:
                raise DatasetServiceError(f"column is required for aggregation function {function!r}.")
            _require_column(df, column)
            if function in ("sum", "mean", "median") and not df[column].dtype.is_numeric():
                raise DatasetServiceError(
                    f"Column {column!r} is not numeric (dtype: {df[column].dtype}) — "
                    f"'{function}' requires a numeric column."
                )
            expr = {
                "sum": pl.col(column).sum(),
                "mean": pl.col(column).mean(),
                "min": pl.col(column).min(),
                "max": pl.col(column).max(),
                "median": pl.col(column).median(),
            }[function]
            agg_exprs.append(expr.alias(output_name))

        try:
            new_df = df.group_by(group_by_columns, maintain_order=True).agg(agg_exprs)
        except Exception as exc:
            raise DatasetServiceError(f"Could not group by: {exc}") from exc

        return new_df, {
            "group_by_columns": group_by_columns,
            "aggregations": aggregations,
            "result_row_count": new_df.height,
        }

    return await _apply_table_transformation(
        db, storage, source_table=source_table, user_id=user_id, operation_type="group_by", mutate=mutate
    )

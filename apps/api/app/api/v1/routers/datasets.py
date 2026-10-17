import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_http_client, get_object_storage
from app.api.resolvers import get_dataset_or_404, get_table_chain_or_404, get_workspace_or_404
from app.db.session import get_db, get_session_factory
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.schemas.dataset import (
    CalculatedFieldRequest,
    ConfirmSchemaRequest,
    DatasetDetailOut,
    DatasetOut,
    DatasetTableOut,
    DatasetVersionOut,
    FillMissingValuesRequest,
    FilterRowsRequest,
    GroupByRequest,
    MergeColumnsRequest,
    NormalizeTextRequest,
    PivotRequest,
    SplitColumnRequest,
    StandardizeColumnRequest,
    UnpivotRequest,
)
from app.schemas.version_compare import CompareVersionsRequest, CompareVersionsResponse
from app.services import billing
from app.services.authz import require_workspace_access, require_workspace_write_access
from app.services.datasets import (
    DatasetServiceError,
    apply_calculated_field,
    apply_deduplicate,
    apply_fill_missing_values,
    apply_filter_rows,
    apply_group_by,
    apply_merge_columns,
    apply_normalize_text,
    apply_pivot,
    apply_split_column,
    apply_standardize_column,
    apply_unpivot,
    finish_ingest_upload,
    get_dataset_table_dataframe,
    get_table_for_version,
    ingest_upload,
)
from app.services.malware_scanning import MalwareDetectedError, MalwareScanningUnavailableError
from app.services.storage import ObjectStorage
from app.services.version_compare import compare_tables
from app.services.webhooks import dispatch_event

router = APIRouter(tags=["datasets"])

VALID_COLUMN_TYPES = {"integer", "float", "boolean", "date", "datetime", "text"}


@router.post(
    "/workspaces/{workspace_id}/datasets",
    response_model=DatasetVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dataset_id: str | None = Form(default=None),
    name: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> DatasetVersion:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    dataset: Dataset | None = None
    if dataset_id is not None:
        dataset = await get_dataset_or_404(db, dataset_id)
        if dataset.workspace_id != workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found in this workspace")
    elif not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name is required when creating a new dataset")

    content = await file.read()

    subscription = await billing.get_subscription_for_workspace(db, workspace)
    try:
        await billing.check_upload_allowed(db, subscription, len(content))
    except billing.QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc

    try:
        version, extension = await ingest_upload(
            db,
            storage,
            workspace_id=workspace_id,
            dataset=dataset,
            dataset_name=name or (file.filename or "Untitled dataset"),
            filename=file.filename or "upload",
            content=content,
            user_id=current_user.id,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except MalwareDetectedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except MalwareScanningUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    # The file is safely stored and the version row exists (status
    # PROCESSING) by this point — parsing and profiling (the expensive
    # part for a large file) happen after this response is sent, not
    # before it. The client sees status="processing" and an empty
    # tables list, and is expected to re-fetch once it flips to "ready"
    # (or "failed", with error_message set).
    background_tasks.add_task(
        finish_ingest_upload,
        version_id=version.id,
        workspace_id=workspace_id,
        dataset_id=version.dataset_id,
        extension=extension,
        storage=storage,
        session_factory=session_factory,
    )

    await dispatch_event(
        db,
        http_client,
        event_type="dataset.uploaded",
        workspace_id=workspace_id,
        payload={"dataset_id": version.dataset_id, "version_id": version.id, "version_number": version.version_number},
    )

    return await _load_version_with_tables(db, version.id)


@router.get("/workspaces/{workspace_id}/datasets", response_model=list[DatasetOut])
async def list_datasets(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Dataset]:
    workspace = await get_workspace_or_404(db, workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    result = await db.execute(select(Dataset).where(Dataset.workspace_id == workspace_id))
    return list(result.scalars().all())


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailOut)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id)
        .options(selectinload(Dataset.versions).selectinload(DatasetVersion.tables))
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")

    workspace = await get_workspace_or_404(db, dataset.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)
    return dataset


@router.post("/datasets/{dataset_id}/compare-versions", response_model=CompareVersionsResponse)
async def compare_versions(
    dataset_id: str,
    payload: CompareVersionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> CompareVersionsResponse:
    dataset = await get_dataset_or_404(db, dataset_id)
    workspace = await get_workspace_or_404(db, dataset.workspace_id)
    await require_workspace_access(db, current_user.id, workspace)

    try:
        table_a = await get_table_for_version(db, dataset_id, payload.version_a, payload.sheet_name)
        table_b = await get_table_for_version(db, dataset_id, payload.version_b, payload.sheet_name)
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if table_a.sheet_name != table_b.sheet_name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Sheet mismatch: version {payload.version_a} resolved to '{table_a.sheet_name}' but "
            f"version {payload.version_b} resolved to '{table_b.sheet_name}'. Specify sheet_name explicitly.",
        )

    df_a = await get_dataset_table_dataframe(storage, table_a)
    df_b = await get_dataset_table_dataframe(storage, table_b)

    result = compare_tables(df_a, df_b)
    return CompareVersionsResponse(
        version_a=payload.version_a,
        version_b=payload.version_b,
        sheet_name=table_a.sheet_name,
        **result,
    )


async def _load_version_with_tables(db: AsyncSession, version_id: str) -> DatasetVersion:
    result = await db.execute(
        select(DatasetVersion)
        .where(DatasetVersion.id == version_id)
        .options(selectinload(DatasetVersion.tables))
    )
    return result.scalar_one()


@router.get("/dataset-tables/{table_id}", response_model=DatasetTableOut)
async def get_dataset_table(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetTableOut:
    """A single table's profile (columns, types, quality issues) by id.
    Not a new capability — every other /dataset-tables/{id}/* endpoint
    already loads this same row — just the first one that returns the
    table itself rather than acting on it. Added for the dashboard
    add-widget UI to list real column names instead of asking a user to
    type one from memory."""
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_access(db, current_user.id, workspace)
    return table


@router.patch("/dataset-tables/{table_id}/schema", response_model=DatasetVersionOut)
async def confirm_schema(
    table_id: str,
    payload: ConfirmSchemaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersion:
    table, version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    known_columns = {col["name"] for col in table.profile["columns"]}
    unknown = set(payload.column_types) - known_columns
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown column(s): {', '.join(sorted(unknown))}")

    invalid_types = {t for t in payload.column_types.values() if t not in VALID_COLUMN_TYPES}
    if invalid_types:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid type(s): {', '.join(sorted(invalid_types))}. Valid: {', '.join(sorted(VALID_COLUMN_TYPES))}",
        )

    table.confirmed_schema = payload.column_types
    await db.commit()
    return await _load_version_with_tables(db, version.id)


@router.post("/dataset-tables/{table_id}/deduplicate", response_model=DatasetVersionOut)
async def deduplicate_table(
    table_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    new_version = await apply_deduplicate(db, storage, source_table=table, user_id=current_user.id)
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/fill-missing-values", response_model=DatasetVersionOut)
async def fill_missing_values(
    table_id: str,
    payload: FillMissingValuesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_fill_missing_values(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            column=payload.column,
            strategy=payload.strategy,
            constant_value=payload.constant_value,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/normalize-text", response_model=DatasetVersionOut)
async def normalize_text(
    table_id: str,
    payload: NormalizeTextRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_normalize_text(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            column=payload.column,
            case=payload.case,
            trim=payload.trim,
            collapse_whitespace=payload.collapse_whitespace,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/filter-rows", response_model=DatasetVersionOut)
async def filter_rows(
    table_id: str,
    payload: FilterRowsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_filter_rows(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            column=payload.column,
            operator=payload.operator,
            value=payload.value,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/calculated-field", response_model=DatasetVersionOut)
async def calculated_field(
    table_id: str,
    payload: CalculatedFieldRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_calculated_field(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            new_column_name=payload.new_column_name,
            left_column=payload.left_column,
            operator=payload.operator,
            right_column=payload.right_column,
            right_value=payload.right_value,
            separator=payload.separator,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/merge-columns", response_model=DatasetVersionOut)
async def merge_columns(
    table_id: str,
    payload: MergeColumnsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_merge_columns(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            columns=payload.columns,
            new_column_name=payload.new_column_name,
            separator=payload.separator,
            drop_source_columns=payload.drop_source_columns,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/split-column", response_model=DatasetVersionOut)
async def split_column(
    table_id: str,
    payload: SplitColumnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_split_column(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            column=payload.column,
            delimiter=payload.delimiter,
            new_column_names=payload.new_column_names,
            drop_source_column=payload.drop_source_column,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/standardize-column", response_model=DatasetVersionOut)
async def standardize_column(
    table_id: str,
    payload: StandardizeColumnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_standardize_column(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            column=payload.column,
            kind=payload.kind,
            date_format=payload.date_format,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/pivot", response_model=DatasetVersionOut)
async def pivot_table(
    table_id: str,
    payload: PivotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_pivot(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            index_columns=payload.index_columns,
            pivot_column=payload.pivot_column,
            value_column=payload.value_column,
            aggregate_function=payload.aggregate_function,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/unpivot", response_model=DatasetVersionOut)
async def unpivot_table(
    table_id: str,
    payload: UnpivotRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_unpivot(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            id_columns=payload.id_columns,
            value_columns=payload.value_columns,
            variable_name=payload.variable_name,
            value_name=payload.value_name,
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)


@router.post("/dataset-tables/{table_id}/group-by", response_model=DatasetVersionOut)
async def group_by_table(
    table_id: str,
    payload: GroupByRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DatasetVersion:
    table, _version, _dataset, workspace = await get_table_chain_or_404(db, table_id)
    await require_workspace_write_access(db, current_user.id, workspace)

    try:
        new_version = await apply_group_by(
            db,
            storage,
            source_table=table,
            user_id=current_user.id,
            group_by_columns=payload.group_by_columns,
            aggregations=[a.model_dump() for a in payload.aggregations],
        )
    except DatasetServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _load_version_with_tables(db, new_version.id)

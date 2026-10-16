"""Matches a dataset's actual column headers against an industry pack's
canonical fields — real-world spreadsheets never use the exact column
names a pack's authors picked ("Rent (PCM)" vs "rent_amount" vs "Monthly
Rent"), so this does two passes:

1. Exact match: the column header, normalized (lowercased, punctuation
   stripped), equals one of the field's known aliases exactly.
2. Token-subset match: the column's word tokens and an alias's word
   tokens are subsets of each other either way (so "Monthly Rent Amount"
   matches alias "rent", and "Rent" matches alias "rent amount"). This
   deliberately uses whole-word tokens, not raw substrings, so "Parent
   Company" doesn't false-match the alias "rent".

This is a heuristic, not a certified parser — ambiguous short aliases
(e.g. "status") can still mismatch on real-world data. It's good enough
to drive a schema-confirmation step (same pattern as Phase 2's column
type confirmation), not to silently trust without the option to review.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.industry_packs import IndustryPack

if TYPE_CHECKING:
    from app.models.dataset import DatasetTable


def _normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return set(_normalize(value).split())


def resolve_field_mapping(pack: IndustryPack, column_names: list[str]) -> dict[str, str | None]:
    """Returns {canonical_field: matched_column_name_or_None}. Each
    actual column is used for at most one canonical field."""
    mapping: dict[str, str | None] = {ca.canonical_field: None for ca in pack.column_aliases}
    used: set[str] = set()

    # Pass 1: exact normalized match.
    for ca in pack.column_aliases:
        alias_variants = {_normalize(a) for a in ca.aliases} | {_normalize(ca.canonical_field)}
        for col in column_names:
            if col in used:
                continue
            if _normalize(col) in alias_variants:
                mapping[ca.canonical_field] = col
                used.add(col)
                break

    # Pass 2: token-subset match for anything still unmapped.
    for ca in pack.column_aliases:
        if mapping[ca.canonical_field] is not None:
            continue
        alias_token_sets = [_tokens(a) for a in ca.aliases if a]
        for col in column_names:
            if col in used:
                continue
            col_tokens = _tokens(col)
            if not col_tokens:
                continue
            if any(a_tokens and (a_tokens <= col_tokens or col_tokens <= a_tokens) for a_tokens in alias_token_sets):
                mapping[ca.canonical_field] = col
                used.add(col)
                break

    return mapping


def missing_required_fields(pack: IndustryPack, mapping: dict[str, str | None]) -> list[str]:
    return [ca.canonical_field for ca in pack.column_aliases if ca.required_for_pack and mapping.get(ca.canonical_field) is None]


def get_effective_field_mapping(
    table: "DatasetTable", pack: IndustryPack, column_names: list[str]
) -> dict[str, str | None]:
    """The mapping every KPI/report/scenario/dashboard-widget call site
    should actually use: the user-confirmed mapping
    (DatasetTable.confirmed_field_mapping) when one has been saved via
    PATCH /dataset-tables/{id}/field-mapping, falling back to the
    automatic alias/token matching otherwise — same "trust the review,
    not just the guess" pattern as Phase 2's confirmed_schema for column
    types. A stored mapping is used as-is, even if it references a
    column that no longer exists in `column_names` (e.g. a later
    cleaning operation renamed or dropped it) — the same edge case
    confirmed_schema already has, not a new one; the KPI engine treats a
    mapped-but-missing column the same as an unmapped one."""
    if table.confirmed_field_mapping is not None:
        return table.confirmed_field_mapping
    return resolve_field_mapping(pack, column_names)

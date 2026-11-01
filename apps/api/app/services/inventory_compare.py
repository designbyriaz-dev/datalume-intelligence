"""Compares two inventories for the same tenancy — the brief's
"check-in/check-out inventory records with a diff view". Matches items
by (room, item_name) rather than by row id, since a check-in and a
check-out inventory are two independent sets of rows describing the same
physical items, not two versions of the same rows. Deterministic, no AI
involved — mirrors app/services/version_compare.py's "pure function over
two already-loaded things, dict-shaped output" approach for the same
testability reason that module's own docstring gives.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.inventory import Inventory, InventoryItem


@dataclass
class ItemDiff:
    room: str
    item_name: str
    status: str  # unchanged | changed | added | removed
    condition_before: str | None = None
    condition_after: str | None = None
    notes_before: str | None = None
    notes_after: str | None = None


@dataclass
class InventoryComparison:
    items: list[ItemDiff]
    added_count: int
    removed_count: int
    changed_count: int
    unchanged_count: int


def _key(item: InventoryItem) -> tuple[str, str]:
    return (item.room, item.item_name)


def compare_inventories(before: Inventory, after: Inventory) -> InventoryComparison:
    """before/after must have their `.items` already loaded (e.g. via a
    query that already fetched them, or an ORM relationship access)."""
    before_by_key = {_key(item): item for item in before.items}
    after_by_key = {_key(item): item for item in after.items}

    diffs: list[ItemDiff] = []
    added_count = removed_count = changed_count = unchanged_count = 0

    for key, before_item in before_by_key.items():
        after_item = after_by_key.get(key)
        if after_item is None:
            diffs.append(
                ItemDiff(
                    room=before_item.room,
                    item_name=before_item.item_name,
                    status="removed",
                    condition_before=before_item.condition,
                    notes_before=before_item.notes,
                )
            )
            removed_count += 1
            continue

        condition_changed = before_item.condition != after_item.condition
        notes_changed = (before_item.notes or "") != (after_item.notes or "")
        if condition_changed or notes_changed:
            diffs.append(
                ItemDiff(
                    room=before_item.room,
                    item_name=before_item.item_name,
                    status="changed",
                    condition_before=before_item.condition,
                    condition_after=after_item.condition,
                    notes_before=before_item.notes,
                    notes_after=after_item.notes,
                )
            )
            changed_count += 1
        else:
            diffs.append(
                ItemDiff(
                    room=before_item.room,
                    item_name=before_item.item_name,
                    status="unchanged",
                    condition_before=before_item.condition,
                    condition_after=after_item.condition,
                    notes_before=before_item.notes,
                    notes_after=after_item.notes,
                )
            )
            unchanged_count += 1

    for key, after_item in after_by_key.items():
        if key not in before_by_key:
            diffs.append(
                ItemDiff(
                    room=after_item.room,
                    item_name=after_item.item_name,
                    status="added",
                    condition_after=after_item.condition,
                    notes_after=after_item.notes,
                )
            )
            added_count += 1

    diffs.sort(key=lambda d: (d.room, d.item_name))

    return InventoryComparison(
        items=diffs,
        added_count=added_count,
        removed_count=removed_count,
        changed_count=changed_count,
        unchanged_count=unchanged_count,
    )

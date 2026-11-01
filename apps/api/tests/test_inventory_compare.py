from app.models.inventory import Inventory, InventoryItem, InventoryType, ItemCondition
from app.services.inventory_compare import compare_inventories


def _inventory(items: list[InventoryItem]) -> Inventory:
    inv = Inventory(
        tenancy_id="t1",
        inventory_type=InventoryType.CHECK_IN.value,
        inspection_date="2026-01-01",
    )
    inv.items = items
    return inv


def _item(room: str, name: str, condition: str, notes: str | None = None) -> InventoryItem:
    return InventoryItem(room=room, item_name=name, condition=condition, notes=notes)


def test_identical_inventories_are_all_unchanged() -> None:
    before = _inventory([_item("Kitchen", "Oven", ItemCondition.GOOD.value)])
    after = _inventory([_item("Kitchen", "Oven", ItemCondition.GOOD.value)])

    result = compare_inventories(before, after)

    assert result.unchanged_count == 1
    assert result.changed_count == 0
    assert result.added_count == 0
    assert result.removed_count == 0
    assert result.items[0].status == "unchanged"


def test_condition_change_is_flagged() -> None:
    before = _inventory([_item("Living room", "Carpet", ItemCondition.GOOD.value)])
    after = _inventory([_item("Living room", "Carpet", ItemCondition.DAMAGED.value)])

    result = compare_inventories(before, after)

    assert result.changed_count == 1
    diff = result.items[0]
    assert diff.status == "changed"
    assert diff.condition_before == ItemCondition.GOOD.value
    assert diff.condition_after == ItemCondition.DAMAGED.value


def test_notes_only_change_is_flagged_even_if_condition_matches() -> None:
    before = _inventory([_item("Bedroom", "Wardrobe", ItemCondition.GOOD.value, notes="No issues")])
    after = _inventory([_item("Bedroom", "Wardrobe", ItemCondition.GOOD.value, notes="Small scratch on door")])

    result = compare_inventories(before, after)

    assert result.changed_count == 1
    assert result.items[0].notes_after == "Small scratch on door"


def test_item_missing_at_checkout_is_removed() -> None:
    before = _inventory([_item("Kitchen", "Toaster", ItemCondition.GOOD.value)])
    after = _inventory([])

    result = compare_inventories(before, after)

    assert result.removed_count == 1
    assert result.items[0].status == "removed"
    assert result.items[0].condition_after is None


def test_new_item_at_checkout_is_added() -> None:
    before = _inventory([])
    after = _inventory([_item("Garden", "Shed", ItemCondition.FAIR.value)])

    result = compare_inventories(before, after)

    assert result.added_count == 1
    assert result.items[0].status == "added"
    assert result.items[0].condition_before is None


def test_mixed_comparison_counts_each_category_correctly() -> None:
    before = _inventory(
        [
            _item("Kitchen", "Oven", ItemCondition.GOOD.value),
            _item("Kitchen", "Fridge", ItemCondition.EXCELLENT.value),
            _item("Hallway", "Rug", ItemCondition.FAIR.value),
        ]
    )
    after = _inventory(
        [
            _item("Kitchen", "Oven", ItemCondition.GOOD.value),  # unchanged
            _item("Kitchen", "Fridge", ItemCondition.POOR.value),  # changed
            # Hallway Rug missing -> removed
            _item("Garden", "Table", ItemCondition.GOOD.value),  # added
        ]
    )

    result = compare_inventories(before, after)

    assert result.unchanged_count == 1
    assert result.changed_count == 1
    assert result.removed_count == 1
    assert result.added_count == 1
    assert len(result.items) == 4

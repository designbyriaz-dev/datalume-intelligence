from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.inventory import InventoryType, ItemCondition


class InventoryItemCreate(BaseModel):
    room: str = Field(min_length=1, max_length=255)
    item_name: str = Field(min_length=1, max_length=255)
    condition: ItemCondition
    notes: str | None = Field(default=None, max_length=2000)


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inventory_id: str
    room: str
    item_name: str
    condition: str
    notes: str | None


class InventoryCreate(BaseModel):
    inventory_type: InventoryType
    inspection_date: date
    notes: str | None = Field(default=None, max_length=2000)
    items: list[InventoryItemCreate] = Field(default_factory=list)


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenancy_id: str
    inventory_type: str
    inspection_date: date
    notes: str | None
    created_by_user_id: str | None
    items: list[InventoryItemOut]


class InventoryItemDiff(BaseModel):
    room: str
    item_name: str
    status: str = Field(description="unchanged | changed | added | removed")
    condition_before: str | None = None
    condition_after: str | None = None
    notes_before: str | None = None
    notes_after: str | None = None


class InventoryComparisonOut(BaseModel):
    before_inventory_id: str
    after_inventory_id: str
    items: list[InventoryItemDiff]
    added_count: int
    removed_count: int
    changed_count: int
    unchanged_count: int

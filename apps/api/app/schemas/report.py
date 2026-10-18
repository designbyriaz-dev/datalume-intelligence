from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_table_id: str
    report_type: str
    file_size_bytes: int
    generated_by_user_id: str | None

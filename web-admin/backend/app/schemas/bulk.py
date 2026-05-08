from pydantic import BaseModel


class BulkDeleteRequest(BaseModel):
    ids: list[int]


class BulkStatusUpdateRequest(BaseModel):
    ids: list[int]
    status: str

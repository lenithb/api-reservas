from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

PageItem = TypeVar("PageItem")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[PageItem]):
    items: list[PageItem]
    page: int
    limit: int
    total: int

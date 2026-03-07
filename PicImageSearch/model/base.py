from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class BaseSearchItem(ABC):
    def __init__(self, data: Any, **kwargs: Any):
        self.origin: Any = data
        self.url: str = ""
        self.thumbnail: str = ""
        self.title: str = ""
        self.similarity: float = 0.0
        self._parse_data(data, **kwargs)

    @abstractmethod
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        pass


class BaseSearchResponse(ABC, Generic[T]):
    def __init__(self, resp_data: Any, resp_url: str, **kwargs: Any):
        self.origin: Any = resp_data
        self.url: str = resp_url
        self.raw: list[T] = []
        self._parse_response(resp_data, resp_url=resp_url, **kwargs)

    @abstractmethod
    def _parse_response(self, resp_data: Any, **kwargs: Any) -> None:
        pass

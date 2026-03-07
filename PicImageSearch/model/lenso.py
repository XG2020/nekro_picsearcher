from typing import Any

from typing_extensions import override

from ..utils import deep_get
from .base import BaseSearchItem, BaseSearchResponse


class LensoURLItem:
    def __init__(self, data: dict[str, Any]) -> None:
        self.origin: dict[str, Any] = data
        self.image_url: str = data.get("imageUrl", "")
        self.source_url: str = data.get("sourceUrl", "")
        self.title: str = data.get("title") or ""
        self.lang: str = data.get("lang", "")


class LensoResultItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.url_list: list[LensoURLItem] = []
        self.width: int = 0
        self.height: int = 0
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.origin: dict[str, Any] = data
        self.title: str = deep_get(data, "urlList[0].title") or ""
        self.url: str = deep_get(data, "urlList[0].sourceUrl") or ""
        self.hash: str = data.get("hash", "")
        distance: float = data.get("distance", 0.0)
        self.similarity: float = round(distance * 100, 2)
        self.thumbnail: str = data.get("proxyUrl", "")
        self.url_list = [LensoURLItem(url_data) for url_data in data.get("urlList", [])]
        self.width = data.get("width", 0)
        self.height = data.get("height", 0)


class LensoResponse(BaseSearchResponse[LensoResultItem]):
    def __init__(self, resp_data: dict[str, Any], resp_url: str, **kwargs: Any) -> None:
        self.raw: list[LensoResultItem] = []
        self.duplicates: list[LensoResultItem] = []
        self.similar: list[LensoResultItem] = []
        self.places: list[LensoResultItem] = []
        self.related: list[LensoResultItem] = []
        self.people: list[LensoResultItem] = []
        self.detected_faces: list[Any] = []
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        self.detected_faces = resp_data.get("detectedFaces", [])
        results_data = resp_data.get("results", {})
        result_types = {
            "duplicates": self.duplicates,
            "similar": self.similar,
            "places": self.places,
            "related": self.related,
            "people": self.people,
        }
        for result_type, result_list in result_types.items():
            result_list.extend(LensoResultItem(item) for item in results_data.get(result_type, []))
            self.raw.extend(result_list)

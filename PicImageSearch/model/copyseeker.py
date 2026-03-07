from typing import Any

from typing_extensions import override

from .base import BaseSearchItem, BaseSearchResponse


class CopyseekerItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.url: str = data["url"]
        self.title: str = data["title"]
        self.thumbnail: str = data.get("mainImage", "")
        self.thumbnail_list: list[str] = data.get("otherImages", [])
        self.website_rank: float = data.get("rank", 0.0)


class CopyseekerResponse(BaseSearchResponse[CopyseekerItem]):
    def __init__(self, resp_data: dict[str, Any], resp_url: str, **kwargs: Any) -> None:
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        self.id: str = resp_data["id"]
        self.image_url: str = resp_data["imageUrl"]
        self.best_guess_label: str | None = resp_data.get("bestGuessLabel")
        self.entities: str | None = resp_data.get("entities")
        self.total: int = resp_data["totalLinksFound"]
        self.exif: dict[str, Any] = resp_data.get("exif", {})
        self.raw: list[CopyseekerItem] = [CopyseekerItem(page) for page in resp_data.get("pages", [])]
        self.similar_image_urls: list[str] = resp_data.get("visuallySimilarImages", [])

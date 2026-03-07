from typing import Any

from typing_extensions import override

from ..types import DomainInfo
from .base import BaseSearchItem, BaseSearchResponse


class TineyeItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.thumbnail: str = data["image_url"]
        self.image_url: str = data["backlinks"][0]["url"]
        self.url: str = data["backlinks"][0]["backlink"]
        self.domain: str = data["domain"]
        self.size: list[int] = [data["width"], data["height"]]
        self.crawl_date: str = data["backlinks"][0]["crawl_date"]


class TineyeResponse(BaseSearchResponse[TineyeItem]):
    def __init__(
        self,
        resp_data: dict[str, Any],
        resp_url: str,
        domains: list[DomainInfo],
        page_number: int = 1,
    ):
        super().__init__(
            resp_data,
            resp_url,
            domains=domains,
            page_number=page_number,
        )
        self.domains: list[DomainInfo] = domains
        self.page_number: int = page_number

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        self.query_hash: str = resp_data["query_hash"]
        self.status_code: int = resp_data["status_code"]
        self.total_pages: int = resp_data["total_pages"]
        matches = resp_data["matches"]
        self.raw: list[TineyeItem] = [TineyeItem(i) for i in matches] if matches else []

from json import loads as json_loads
from typing import Any

from typing_extensions import override

from ..exceptions import ParsingError
from ..utils import deep_get, parse_html
from .base import BaseSearchItem, BaseSearchResponse


class YandexItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.url: str = data["url"]
        self.title: str = data["title"]
        thumb_url: str = data["thumb"]["url"]
        self.thumbnail: str = f"https:{thumb_url}" if thumb_url.startswith("//") else thumb_url
        self.source: str = data["domain"]
        self.content: str = data["description"]
        original_image = data["originalImage"]
        self.size: str = f"{original_image['width']}x{original_image['height']}"


class YandexResponse(BaseSearchResponse[YandexItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        data = parse_html(resp_data)
        self.origin: Any = data
        data_div = data.find('div.Root[id^="ImagesApp-"]')
        data_state = data_div.attr("data-state")

        if not data_state:
            raise ParsingError(
                message="Failed to find critical DOM attribute 'data-state'",
                engine="yandex",
                details="This usually indicates a change in the page structure or an unexpected response.",
            )

        data_json = json_loads(str(data_state))
        if sites := deep_get(data_json, "initialState.cbirSites.sites"):
            self.raw: list[YandexItem] = [YandexItem(site) for site in sites]
        else:
            raise ParsingError(
                message="Failed to extract search results from 'data-state'",
                engine="yandex",
                details="This usually indicates a change in the page structure or an unexpected response.",
            )

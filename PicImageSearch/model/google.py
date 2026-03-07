from re import compile
from typing import Any

from typing_extensions import override

from ..exceptions import ParsingError
from ..utils import parse_html
from .base import BaseSearchItem, BaseSearchResponse


class GoogleItem(BaseSearchItem):
    def __init__(self, data: Any, thumbnail: str | None):
        super().__init__(data, thumbnail=thumbnail)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        self.title: str = data("h3").text()
        self.url: str = data("a").eq(0).attr("href")
        self.thumbnail: str = kwargs.get("thumbnail") or ""
        self.content: str = data("div.VwiC3b").text()


class GoogleResponse(BaseSearchResponse[GoogleItem]):
    def __init__(
        self,
        resp_data: str,
        resp_url: str,
        page_number: int = 1,
        pages: list[str] | None = None,
    ):
        super().__init__(resp_data, resp_url, page_number=page_number, pages=pages)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        data = parse_html(resp_data)
        self.origin: Any = data
        self.page_number: int = kwargs["page_number"]

        if pages := kwargs.get("pages"):
            self.pages: list[str] = pages
        else:
            self.pages = [f"https://www.google.com{i.attr('href')}" for i in data.find('a[aria-label~="Page"]').items()]
            self.pages.insert(0, kwargs["resp_url"])

        script_list = list(data.find("script").items())
        thumbnail_dict: dict[str, str] = self.create_thumbnail_dict(script_list)

        search_items = data.find("#search .wHYlTd")
        self.raw: list[GoogleItem] = [
            GoogleItem(i, thumbnail_dict.get(i('img[id^="dimg_"]').attr("id"))) for i in search_items.items()
        ]

        if thumbnail_dict and not self.raw:
            raise ParsingError(
                message="Failed to extract search results despite finding thumbnails",
                engine="google",
                details="This usually indicates a change in the page structure.",
            )

    @staticmethod
    def create_thumbnail_dict(script_list: list[Any]) -> dict[str, str]:
        thumbnail_dict = {}
        base_64_regex = compile(r"data:image/(?:jpeg|jpg|png|gif);base64,[^'\"]+")
        id_regex = compile(r"dimg_[^'\"]+")

        for script in script_list:
            st = script.text() or ""
            base_64_match = base_64_regex.findall(st)
            if not base_64_match:
                continue
            base64: str = base_64_match[0]
            id_list: list[str] = id_regex.findall(st)

            for _id in id_list:
                thumbnail_dict[_id] = base64.replace(r"\x3d", "=")

        return thumbnail_dict

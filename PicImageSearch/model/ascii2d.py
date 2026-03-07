from typing import Any, NamedTuple

from typing_extensions import override

from ..utils import parse_html
from .base import BaseSearchItem, BaseSearchResponse

BASE_URL = "https://ascii2d.net"
SUPPORTED_SOURCES = [
    "fanbox",
    "fantia",
    "misskey",
    "pixiv",
    "twitter",
    "ニコニコ静画",
    "ニジエ",
]


class URL(NamedTuple):
    href: str
    text: str


class Ascii2DItem(BaseSearchItem):
    def __init__(self, data: Any, **kwargs: Any) -> None:
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        self.hash: str = data("div.hash").eq(0).text()
        self.detail: str = data("small").eq(0).text()
        image_source = data("img").eq(0).attr("src")
        self.thumbnail: str = f"{BASE_URL}{image_source}" if image_source.startswith("/") else image_source
        self.url_list: list[URL] = []
        self.author: str = ""
        self.author_url: str = ""
        self._arrange(data)

    def _arrange(self, data: Any) -> None:
        if infos := data.find("div.detail-box.gray-link"):
            links = infos.find("a")
            self.url_list = [URL(i.attr("href"), i.text()) for i in links.items()] if links else []
            mark = next(
                (small.text() for small in infos("small").items() if small.text() in SUPPORTED_SOURCES),
                "",
            )
            self._arrange_links(infos, links, mark)
            self._arrange_title(infos)
        self._normalize_url_list()
        if not self.url_list:
            self._arrange_backup_links(data)

    def _arrange_links(self, infos: Any, links: Any, mark: str) -> None:
        if links:
            link_items = list(links.items())
            if len(link_items) > 1 and mark in SUPPORTED_SOURCES:
                self.title: str = link_items[0].text()
                self.url: str = link_items[0].attr("href")
                self.author_url = link_items[1].attr("href")
                self.author = link_items[1].text()
            elif links.eq(0).parents("small"):
                infos.remove("small")
                self.title = infos.text()

    def _arrange_title(self, infos: Any) -> None:
        if not self.title:
            self.title = self._extract_external_text(infos) or infos.find("h6").text()
        if self.title and any(i in self.title for i in {"詳細掲示板のログ", "2ちゃんねるのログ"}):
            self.title = ""

    @staticmethod
    def _extract_external_text(infos: Any) -> str:
        external = infos.find(".external")
        external.remove("a")
        return "\n".join(i.text() for i in external.items() if i.text()) or ""

    def _normalize_url_list(self) -> None:
        self.url_list = [
            URL(BASE_URL + url.href, url.text) if url.href.startswith("/") else url for url in self.url_list
        ]

    def _arrange_backup_links(self, data: Any) -> None:
        if links := data.find("div.pull-xs-right > a"):
            self.url = links.eq(0).attr("href")
            self.url_list = [URL(self.url, links.eq(0).text())]


class Ascii2DResponse(BaseSearchResponse[Ascii2DItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        data = parse_html(resp_data)
        self.origin: Any = data
        self.raw: list[Ascii2DItem] = [Ascii2DItem(i) for i in data.find("div.row.item-box").items()]

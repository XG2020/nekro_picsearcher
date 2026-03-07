from typing import Any

from typing_extensions import override

from ..utils import parse_html
from .base import BaseSearchItem, BaseSearchResponse


class EHentaiItem(BaseSearchItem):
    def __init__(self, data: Any, **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        self._arrange(data)

    def _arrange(self, data: Any) -> None:
        glink = data.find(".glink")
        self.title: str = glink.text()
        if glink.parent("div"):
            self.url: str = glink.parent("div").parent("a").attr("href")
        else:
            self.url = glink.parent("a").attr("href")
        thumbnail = data.find(".glthumb img") or data.find(".gl1e img") or data.find(".gl3t img")
        self.thumbnail: str = thumbnail.attr("data-src") or thumbnail.attr("src")
        _type = data.find(".cs") or data.find(".cn")
        self.type: str = _type.eq(0).text() or ""
        self.date: str = data.find("[id^='posted']").eq(0).text() or ""
        self.tags: list[str] = []
        for i in data.find("div[class=gt],div[class=gtl]").items():
            if tag := i.attr("title"):
                self.tags.append(tag)


class EHentaiResponse(BaseSearchResponse[EHentaiItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        data = parse_html(resp_data)
        self.origin: Any = data
        if "No unfiltered results" in resp_data:
            self.raw: list[EHentaiItem] = []
        elif tr_items := data.find(".itg").children("tr").items():
            self.raw = [EHentaiItem(i) for i in tr_items if i.children("td")]
        else:
            gl1t_items = data.find(".itg").children(".gl1t").items()
            self.raw = [EHentaiItem(i) for i in gl1t_items]

from typing import Any

from typing_extensions import override

from ..utils import parse_html
from .base import BaseSearchItem, BaseSearchResponse


class IqdbItem(BaseSearchItem):
    def __init__(self, data: Any, **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        self.content: str = ""
        self.source: str = ""
        self.other_source: list[dict[str, str]] = []
        self.size: str = ""
        self._arrange(data)

    def _arrange(self, data: Any) -> None:
        tr_list = list(data("tr").items())
        if len(tr_list) >= 5:
            self.content = tr_list[0]("th").text()
            if self.content == "No relevant matches":
                return
            tr_list = tr_list[1:]
        self.url: str = self._get_url(tr_list[0]("td > a").attr("href"))
        self.thumbnail: str = "https://iqdb.org" + tr_list[0]("td > a > img").attr("src")
        source_list = [i.tail.strip() for i in tr_list[1]("img")]
        self.source = source_list[0]
        if other_source := tr_list[1]("td > a"):
            self.other_source.append(
                {
                    "source": source_list[1],
                    "url": self._get_url(other_source.attr("href")),
                }
            )
        self.size = tr_list[2]("td").text()
        similarity_raw = tr_list[3]("td").text()
        self.similarity: float = float(similarity_raw.removesuffix("% similarity"))

    @staticmethod
    def _get_url(url: str) -> str:
        return url if url.startswith("http") else f"https:{url}"


class IqdbResponse(BaseSearchResponse[IqdbItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        data = parse_html(resp_data)
        self.origin: Any = data
        self.raw: list[IqdbItem] = []
        self.more: list[IqdbItem] = []
        self.saucenao_url: str = ""
        self.ascii2d_url: str = ""
        self.google_url: str = ""
        self.tineye_url: str = ""
        self._arrange(data)

    def _arrange(self, data: Any) -> None:
        host = "https://iqdb.org" if data('a[href^="//3d.iqdb.org"]') else "https://3d.iqdb.org"
        tables = list(data("#pages > div > table").items())
        self.url: str = f"{host}/?url=https://iqdb.org{tables[0].find('img').attr('src')}"
        if len(tables) > 1:
            tables = tables[1:]
            self.raw.extend([IqdbItem(i) for i in tables])
        if tables[0].find("th").text() == "No relevant matches":
            self._get_other_urls(tables[0].find("a"))
        else:
            self._get_other_urls(data("#show1 > a"))
        self._get_more(data("#more1 > div.pages > div > table"))

    def _get_more(self, data: Any) -> None:
        self.more.extend([IqdbItem(i) for i in data.items()])

    def _get_other_urls(self, data: Any) -> None:
        urls_with_name = {
            "SauceNao": ["https:", "saucenao"],
            "ascii2d.net": ["", "ascii2d"],
            "Google Images": ["https:", "google"],
            "TinEye": ["https:", "tineye"],
        }
        for link in data.items():
            href = link.attr("href")
            text = link.text()
            if href == "#":
                continue
            if text in urls_with_name:
                prefix, attr_name = urls_with_name[text]
                full_url = href if href.startswith("https:") else prefix + href
                setattr(self, f"{attr_name}_url", full_url)

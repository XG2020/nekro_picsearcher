from typing import Any
from urllib.parse import urlparse
from typing_extensions import override

from ..utils import parse_html
from .base import BaseSearchItem, BaseSearchResponse


def get_site_name(url: str | None) -> str:
    if not url:
        return ""
    parsed_url = urlparse(url)
    return parsed_url.netloc.replace("www.", "") if parsed_url.netloc else ""


def parse_image_size(html: Any) -> str | None:
    info_spans = html("div.oYQBg.Zn52Me > span")
    for span in info_spans.items():
        text = span.text()
        if text and "x" in text:
            return text
    return None


def extract_ldi_images(script_text: str, image_url_map: dict[str, str]) -> None:
    import re
    from ast import literal_eval
    ldi_match = re.search(r"google\.ldi\s*=\s*({[^}]+})", script_text)
    if not ldi_match:
        return
    try:
        ldi_dict = literal_eval(ldi_match[1])
        for key, value in ldi_dict.items():
            if key.startswith("dimg_"):
                image_url_map[key] = value.replace("\\u003d", "=").replace("\\u0026", "&")
    except (SyntaxError, ValueError):
        pass


def extract_base64_images(script_text: str, base64_image_map: dict[str, str]) -> None:
    import re
    if "_setImagesSrc" not in script_text:
        return
    image_ids_match = re.search(r"var ii=\[([^]]*)];", script_text)
    base64_match = re.search(r"var s='(data:image/[^;]+;base64,[^']+)';", script_text)
    if not (image_ids_match and base64_match):
        return
    image_ids_str = image_ids_match[1]
    image_ids = [img_id.strip().strip("'") for img_id in image_ids_str.split(",") if img_id.strip()]
    base64_str = base64_match[1]
    if image_ids and base64_str:
        for img_id in image_ids:
            base64_image_map[img_id] = base64_str


def extract_image_maps(html: Any) -> tuple[dict[str, str], dict[str, str]]:
    base64_image_map: dict[str, str] = {}
    image_url_map: dict[str, str] = {}
    try:
        from pyquery import PyQuery as PQ  # type: ignore
    except Exception as e:
        raise RuntimeError(
            f"Missing dependency 'pyquery': {e}. Install with 'pip install pyquery lxml cssselect'."
        )
    for script_element in html("script[nonce]"):
        if script_text := PQ(script_element).text():
            extract_ldi_images(script_text, image_url_map)
            extract_base64_images(script_text, base64_image_map)
    return image_url_map, base64_image_map


class GoogleLensBaseItem(BaseSearchItem):
    def __init__(
        self,
        data: Any,
        image_url_map: dict[str, str],
        base64_image_map: dict[str, str],
        **kwargs: Any,
    ):
        self.image_url_map: dict[str, str] = image_url_map
        self.base64_image_map: dict[str, str] = base64_image_map
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        pass

    def _extract_image_url(self, image_element: Any) -> str:
        if not image_element:
            return ""
        if image_id := image_element.attr("data-iid") or image_element.attr("id"):
            if image_id in self.image_url_map:
                return self.image_url_map[image_id]
            if image_id in self.base64_image_map:
                return self.base64_image_map[image_id]
        if data_src := image_element.attr("data-src"):
            return data_src
        return src if (src := image_element.attr("src")) else ""


class GoogleLensItem(GoogleLensBaseItem):
    def __init__(
        self,
        data: Any,
        image_url_map: dict[str, str],
        base64_image_map: dict[str, str],
        **kwargs: Any,
    ):
        super().__init__(data, image_url_map, base64_image_map, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        link_element = data("a.LBcIee")
        title_element = data("a.LBcIee .Yt787")
        site_name_element = data("a.LBcIee .R8BTeb.q8U8x.LJEGod.du278d.i0Rdmd")
        image_element = data(".gdOPf.q07dbf.uhHOwf.ez24Df img")
        self.url: str = link_element.attr("href") if link_element else ""
        self.title: str = title_element.text() if title_element else ""
        if site_name_element:
            self.site_name: str = site_name_element.text()
        else:
            self.site_name = get_site_name(self.url)
        self.thumbnail: str = self._extract_image_url(image_element)


class GoogleLensRelatedSearchItem(GoogleLensBaseItem):
    def __init__(
        self,
        data: Any,
        image_url_map: dict[str, str],
        base64_image_map: dict[str, str],
        **kwargs: Any,
    ):
        super().__init__(data, image_url_map, base64_image_map, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        url_el = data("a.Kg0xqe")
        image_element = data("img")
        if url_el and url_el.attr("href"):
            self.url: str = f"https://www.google.com{url_el.attr('href')}"
        self.title: str = data(".I9S4yc").text()
        self.thumbnail: str = self._extract_image_url(image_element)


class GoogleLensResponse(BaseSearchResponse[GoogleLensItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    def _parse_search_items(
        self, html: Any, image_url_map: dict[str, str], base64_image_map: dict[str, str]
    ) -> None:
        items_elements = html(".vEWxFf.RCxtQc.my5z3d")
        for el in items_elements:
            try:
                from pyquery import PyQuery as PQ  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    f"Missing dependency 'pyquery': {e}. Install with 'pip install pyquery lxml cssselect'."
                )
            item = GoogleLensItem(PQ(el), image_url_map, base64_image_map)
            self.raw.append(item)

    def _parse_related_searches(
        self, html: Any, image_url_map: dict[str, str], base64_image_map: dict[str, str]
    ) -> None:
        related_searches_elements = html(".Kg0xqe")
        for el in related_searches_elements:
            try:
                from pyquery import PyQuery as PQ  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    f"Missing dependency 'pyquery': {e}. Install with 'pip install pyquery lxml cssselect'."
                )
            related_item = GoogleLensRelatedSearchItem(PQ(el), image_url_map, base64_image_map)
            self.related_searches.append(related_item)

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        html = parse_html(resp_data)
        self.origin: Any = html
        self.url: str = kwargs.get("resp_url", "")
        self.raw: list[GoogleLensItem] = []
        self.related_searches: list[GoogleLensRelatedSearchItem] = []
        image_url_map, base64_image_map = extract_image_maps(html)
        self._parse_search_items(html, image_url_map, base64_image_map)
        self._parse_related_searches(html, image_url_map, base64_image_map)


class GoogleLensExactMatchesItem(GoogleLensBaseItem):
    def __init__(
        self,
        data: Any,
        image_url_map: dict[str, str],
        base64_image_map: dict[str, str],
        **kwargs: Any,
    ):
        super().__init__(data, image_url_map, base64_image_map, **kwargs)

    @override
    def _parse_data(self, data: Any, **kwargs: Any) -> None:
        link_element = data("a.ngTNl")
        title_element = data(".ZhosBf")
        image_element = data(".GmoL0c .zVq10e img")
        site_name_element = data(".XC18Gb .LbKnXb .xuPcX")
        info_div = data(".oYQBg.Zn52Me")
        self.url: str = link_element.attr("href") if link_element else ""
        self.title: str = title_element.text() if title_element else ""
        if site_name_element:
            self.site_name: str = site_name_element.text()
        else:
            self.site_name = get_site_name(self.url)
        self.size: str | None = parse_image_size(info_div)
        self.thumbnail: str = self._extract_image_url(image_element)


class GoogleLensExactMatchesResponse(BaseSearchResponse[GoogleLensExactMatchesItem]):
    def __init__(self, resp_data: str, resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @staticmethod
    def _parse_search_items(
        html: Any,
        image_url_map: dict[str, str],
        base64_image_map: dict[str, str],
    ) -> list[GoogleLensExactMatchesItem]:
        items = []
        try:
            from pyquery import PyQuery as PQ  # type: ignore
        except Exception as e:
            raise RuntimeError(
                f"Missing dependency 'pyquery': {e}. Install with 'pip install pyquery lxml cssselect'."
            )
        items_elements = html(".YxbOwd")
        for el in items_elements:
            item = GoogleLensExactMatchesItem(PQ(el), image_url_map, base64_image_map)
            items.append(item)
        return items

    @override
    def _parse_response(self, resp_data: str, **kwargs: Any) -> None:
        html = parse_html(resp_data)
        self.origin: Any = html
        self.url: str = kwargs.get("resp_url", "")
        self.raw: list[GoogleLensExactMatchesItem] = []
        image_url_map, base64_image_map = extract_image_maps(html)
        self.raw = self._parse_search_items(html, image_url_map, base64_image_map)

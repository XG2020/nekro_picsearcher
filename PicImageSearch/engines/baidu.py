from json import loads as json_loads
from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.baidu import BaiDuResponse
from ..utils import deep_get, read_file, parse_html
from .base import BaseSearchEngine


class BaiDu(BaseSearchEngine[BaiDuResponse]):
    def __init__(self, **request_kwargs: Any):
        base_url = "https://graph.baidu.com"
        super().__init__(base_url, **request_kwargs)

    @staticmethod
    def _extract_card_data(data: Any) -> list[dict[str, Any]]:
        for script in data("script").items():
            script_text = script.text()
            if script_text and "window.cardData" in script_text:
                start = script_text.find("[")
                end = script_text.rfind("]") + 1
                return json_loads(script_text[start:end])
        return []

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> BaiDuResponse:
        data = {"from": "pc"}
        if url:
            files = {"image": await self.download(url)}
        elif file:
            files = {"image": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        resp = await self._send_request(
            method="post",
            endpoint="upload",
            headers={"Acs-Token": ""},
            data=data,
            files=files,
        )
        data_url = deep_get(json_loads(resp.text), "data.url")
        if not data_url:
            return BaiDuResponse({}, resp.url)
        resp = await self._send_request(method="get", url=data_url)
        data = parse_html(resp.text)
        card_data = self._extract_card_data(data)
        same_data = None
        for card in card_data:
            if card.get("cardName") == "noresult":
                return BaiDuResponse({}, data_url)
            if card.get("cardName") == "same":
                same_data = card["tplData"]
            if card.get("cardName") == "simipic":
                next_url = card["tplData"]["firstUrl"]
                resp = await self._send_request(method="get", url=next_url)
                resp_data = json_loads(resp.text)
                if same_data:
                    resp_data["same"] = same_data
                return BaiDuResponse(resp_data, data_url)
        return BaiDuResponse({}, data_url)

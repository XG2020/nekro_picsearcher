from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.yandex import YandexResponse
from ..utils import read_file
from .base import BaseSearchEngine


class Yandex(BaseSearchEngine[YandexResponse]):
    def __init__(
        self,
        base_url: str = "https://yandex.com",
        **request_kwargs: Any,
    ):
        base_url = f"{base_url}/images/search"
        super().__init__(base_url, **request_kwargs)

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> YandexResponse:
        params = {"rpt": "imageview", "cbir_page": "sites"}

        if url:
            params["url"] = url
            resp = await self._send_request(method="get", params=params)
        elif file:
            files = {"upfile": read_file(file)}
            resp = await self._send_request(
                method="post",
                params=params,
                data={"prg": 1},
                files=files,
            )
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        return YandexResponse(resp.text, resp.url)

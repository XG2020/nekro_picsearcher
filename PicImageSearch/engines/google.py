from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.google import GoogleResponse
from ..utils import read_file
from .base import BaseSearchEngine


class Google(BaseSearchEngine[GoogleResponse]):
    def __init__(
        self,
        base_url: str = "https://www.google.com",
        **request_kwargs: Any,
    ):
        base_url = f"{base_url}/searchbyimage"
        super().__init__(base_url, **request_kwargs)

    async def _navigate_page(self, resp: GoogleResponse, offset: int) -> GoogleResponse | None:
        next_page_number = resp.page_number + offset
        if next_page_number < 1 or next_page_number > len(resp.pages):
            return None
        _resp = await self._send_request(method="get", url=resp.pages[next_page_number - 1])
        return GoogleResponse(_resp.text, _resp.url, next_page_number, resp.pages)

    async def pre_page(self, resp: GoogleResponse) -> GoogleResponse | None:
        return await self._navigate_page(resp, -1)

    async def next_page(self, resp: GoogleResponse) -> GoogleResponse | None:
        return await self._navigate_page(resp, 1)

    async def _ensure_thumbnail_data(self, resp: GoogleResponse) -> GoogleResponse:
        if resp and resp.raw:
            selected = next((i for i in resp.raw if i.thumbnail), resp.raw[0])
            if not selected.thumbnail and len(resp.raw) > 1:
                _resp = await self._send_request(method="get", url=resp.url)
                return GoogleResponse(_resp.text, _resp.url)
        return resp

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> GoogleResponse:
        params: dict[str, Any] = {"sbisrc": 1, "safe": "off"}

        if url:
            params["image_url"] = url
            resp = await self._send_request(method="get", params=params)
        elif file:
            files = {"encoded_image": read_file(file)}
            resp = await self._send_request(
                method="post",
                endpoint="upload",
                data=params,
                files=files,
            )
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        initial_resp = GoogleResponse(resp.text, resp.url)
        return await self._ensure_thumbnail_data(initial_resp)

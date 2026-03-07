from json import loads as json_loads
from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.tracemoe import TraceMoeMe, TraceMoeResponse
from ..utils import read_file
from .base import BaseSearchEngine


class TraceMoe(BaseSearchEngine[TraceMoeResponse]):
    def __init__(
        self,
        base_url: str = "https://trace.moe",
        base_url_api: str = "https://api.trace.moe",
        mute: bool = False,
        size: str | None = None,
        **request_kwargs: Any,
    ):
        base_url = f"{base_url_api}/search"
        super().__init__(base_url, **request_kwargs)
        self.me_url: str = f"{base_url_api}/me"
        self.mute: bool = mute
        self.size: str | None = size

    async def me(self, key: str | None = None) -> TraceMoeMe:
        params = {"key": key} if key else None
        resp = await self._send_request(method="get", url=self.me_url, params=params)
        return TraceMoeMe(json_loads(resp.text))

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        key: str | None = None,
        anilist_id: int | None = None,
        chinese_title: bool = True,
        cut_borders: bool = True,
        **kwargs: Any,
    ) -> TraceMoeResponse:
        headers = {"x-trace-key": key} if key else None
        files: dict[str, Any] | None = None
        params: dict[str, bool | int | str] = {"anilistInfo": ""}
        if cut_borders:
            params["cutBorders"] = "true"
        if anilist_id:
            params["anilistID"] = anilist_id

        if url:
            params["url"] = url
        elif file:
            files = {"file": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        resp = await self._send_request(
            method="post",
            headers=headers,
            params=params,
            files=files,
        )

        result = TraceMoeResponse(
            resp_data=json_loads(resp.text),
            resp_url=resp.url,
            mute=self.mute,
            size=self.size,
        )

        return result

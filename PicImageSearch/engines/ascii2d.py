from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.ascii2d import Ascii2DResponse
from ..utils import read_file
from .base import BaseSearchEngine


class Ascii2D(BaseSearchEngine[Ascii2DResponse]):
    def __init__(
        self,
        base_url: str = "https://ascii2d.net",
        bovw: bool = False,
        **request_kwargs: Any,
    ):
        base_url = f"{base_url}/search"
        super().__init__(base_url, **request_kwargs)
        self.bovw: bool = bovw

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> Ascii2DResponse:
        data: dict[str, Any] | None = None
        files: dict[str, Any] | None = None
        endpoint: str = "uri" if url else "file"

        if url:
            data = {"uri": url}
        elif file:
            files = {"file": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        resp = await self._send_request(
            method="post",
            endpoint=endpoint,
            data=data,
            files=files,
        )

        if self.bovw:
            resp = await self._send_request(method="get", url=resp.url.replace("/color/", "/bovw/"))

        return Ascii2DResponse(resp.text, resp.url)

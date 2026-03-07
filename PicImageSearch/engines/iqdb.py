from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model.iqdb import IqdbResponse
from ..utils import read_file
from .base import BaseSearchEngine


class Iqdb(BaseSearchEngine[IqdbResponse]):
    def __init__(
        self,
        is_3d: bool = False,
        **request_kwargs: Any,
    ):
        base_url = "https://3d.iqdb.org" if is_3d else "https://iqdb.org"
        super().__init__(base_url, **request_kwargs)

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        force_gray: bool = False,
        **kwargs: Any,
    ) -> IqdbResponse:
        data: dict[str, Any] = {}
        files: dict[str, Any] | None = None

        if force_gray:
            data["forcegray"] = "on"

        if url:
            data["url"] = url
        elif file:
            files = {"file": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")

        resp = await self._send_request(
            method="post",
            data=data,
            files=files,
        )

        return IqdbResponse(resp.text, resp.url)

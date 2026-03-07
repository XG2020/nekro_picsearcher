from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model import EHentaiResponse
from ..utils import read_file
from .base import BaseSearchEngine


class EHentai(BaseSearchEngine[EHentaiResponse]):
    def __init__(
        self,
        is_ex: bool = False,
        covers: bool = False,
        similar: bool = True,
        exp: bool = False,
        **request_kwargs: Any,
    ):
        base_url = "https://upld.exhentai.org" if is_ex else "https://upld.e-hentai.org"
        super().__init__(base_url, **request_kwargs)
        self.is_ex: bool = is_ex
        self.covers: bool = covers
        self.similar: bool = similar
        self.exp: bool = exp

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> EHentaiResponse:
        endpoint = "upld/image_lookup.php" if self.is_ex else "image_lookup.php"
        data: dict[str, Any] = {"f_sfile": "File Search"}
        if url:
            files = {"sfile": await self.download(url)}
        elif file:
            files = {"sfile": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")
        if self.covers:
            data["fs_covers"] = "on"
        if self.similar:
            data["fs_similar"] = "on"
        if self.exp:
            data["fs_exp"] = "on"
        resp = await self._send_request(
            method="post",
            endpoint=endpoint,
            data=data,
            files=files,
        )
        return EHentaiResponse(resp.text, resp.url)

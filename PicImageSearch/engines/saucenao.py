from json import loads as json_loads
from pathlib import Path
from typing import Any

from httpx import QueryParams
from typing_extensions import override

from ..model import SauceNAOResponse
from ..utils import read_file
from .base import BaseSearchEngine


class SauceNAO(BaseSearchEngine[SauceNAOResponse]):
    def __init__(
        self,
        base_url: str = "https://saucenao.com",
        api_key: str | None = None,
        numres: int = 5,
        hide: int = 0,
        minsim: int = 30,
        output_type: int = 2,
        testmode: int = 0,
        dbmask: int | None = None,
        dbmaski: int | None = None,
        db: int = 999,
        dbs: list[int] | None = None,
        **request_kwargs: Any,
    ):
        base_url = f"{base_url}/search.php"
        super().__init__(base_url, **request_kwargs)
        params: dict[str, Any] = {
            "testmode": testmode,
            "numres": numres,
            "output_type": output_type,
            "hide": hide,
            "db": db,
            "minsim": minsim,
        }
        if api_key is not None:
            params["api_key"] = api_key
        if dbmask is not None:
            params["dbmask"] = dbmask
        if dbmaski is not None:
            params["dbmaski"] = dbmaski
        self.params: QueryParams = QueryParams(params)
        if dbs is not None:
            self.params = self.params.remove("db")
            for i in dbs:
                self.params = self.params.add("dbs[]", i)

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> SauceNAOResponse:
        params = self.params
        files: dict[str, Any] | None = None
        if url:
            params = params.add("url", url)
        elif file:
            files = {"file": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")
        resp = await self._send_request(
            method="post",
            params=params,
            files=files,
        )
        resp_json = json_loads(resp.text)
        resp_json.update({"status_code": resp.status_code})
        return SauceNAOResponse(resp_json, resp.url)

from json import loads as json_loads
from pathlib import Path
from typing import Any

from typing_extensions import override

from ..model import TineyeResponse
from ..types import DomainInfo
from ..utils import deep_get, read_file
from .base import BaseSearchEngine


class Tineye(BaseSearchEngine[TineyeResponse]):
    def __init__(self, base_url: str = "https://tineye.com", **request_kwargs: Any):
        super().__init__(base_url, **request_kwargs)

    async def _get_domains(self, query_hash: str) -> list[DomainInfo]:
        resp = await self._send_request(method="get", endpoint=f"api/v1/search/get_domains/{query_hash}")
        resp_json = json_loads(resp.text)
        return [DomainInfo.from_raw_data(domain_data) for domain_data in resp_json.get("domains", [])]

    async def _navigate_page(self, resp: TineyeResponse, offset: int) -> TineyeResponse | None:
        next_page_number = resp.page_number + offset
        if next_page_number < 1 or next_page_number > resp.total_pages:
            return None
        api_url = resp.url.replace("search/", "api/v1/result_json/").replace(
            f"page={resp.page_number}", f"page={next_page_number}"
        )
        _resp = await self._send_request(method="get", url=api_url)
        resp_json = json_loads(_resp.text)
        resp_json.update({"status_code": _resp.status_code})
        return TineyeResponse(
            resp_json,
            _resp.url,
            resp.domains,
            next_page_number,
        )

    async def pre_page(self, resp: TineyeResponse) -> TineyeResponse | None:
        return await self._navigate_page(resp, -1)

    async def next_page(self, resp: TineyeResponse) -> TineyeResponse | None:
        return await self._navigate_page(resp, 1)

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        show_unavailable_domains: bool = False,
        domain: str = "",
        sort: str = "score",
        order: str = "desc",
        tags: str = "",
        **kwargs: Any,
    ) -> TineyeResponse:
        files: dict[str, Any] | None = None
        params: dict[str, Any] = {
            "sort": sort,
            "order": order,
            "page": 1,
            "show_unavailable_domains": show_unavailable_domains or "",
            "tags": tags,
            "domain": domain,
        }
        params = {k: v for k, v in params.items() if v}
        if url:
            params["url"] = url
        elif file:
            files = {"image": read_file(file)}
        else:
            raise ValueError("Either 'url' or 'file' must be provided")
        resp = await self._send_request(
            method="post",
            endpoint="api/v1/result_json/",
            data=params,
            files=files,
        )
        resp_json = json_loads(resp.text)
        resp_json["status_code"] = resp.status_code
        _url = resp.url
        domains = []
        if query_hash := deep_get(resp_json, "query.key"):
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            _url = f"{self.base_url}/search/{query_hash}?{query_string}"
            domains = await self._get_domains(resp_json["query"]["hash"])
        return TineyeResponse(resp_json, _url, domains)

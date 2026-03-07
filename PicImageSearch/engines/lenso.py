import base64
import warnings
from json import loads as json_loads
from pathlib import Path
from typing import Any, Literal, get_args

from typing_extensions import override

from ..model import LensoResponse
from ..utils import read_file
from .base import BaseSearchEngine


class Lenso(BaseSearchEngine[LensoResponse]):
    SEARCH_TYPES = Literal["", "duplicates", "similar", "places", "related"]  # pyright: ignore[reportUnannotatedClassAttribute]
    SORT_TYPES = Literal[  # pyright: ignore[reportUnannotatedClassAttribute]
        "SMART",
        "RANDOM",
        "QUALITY_DESCENDING",
        "QUALITY_ASCENDING",
        "DATE_DESCENDING",
        "DATE_ASCENDING",
    ]

    def __init__(
        self,
        base_url: str = "https://lenso.ai",
        **request_kwargs: Any,
    ):
        warnings.warn(
            (
                "The Lenso engine is deprecated as the website now uses Cloudflare turnstile protection "
                "which prevents this client from working properly."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(base_url, **request_kwargs)

    async def _upload_image(self, image_base64: str) -> str:
        endpoint = "api/upload"
        payload = {"image": f"data:image/jpeg;base64,{image_base64}"}
        resp = await self._send_request(method="post", endpoint=endpoint, json=payload)
        resp_json = json_loads(resp.text)
        if result_hash := resp_json.get("id"):
            return result_hash
        raise RuntimeError(
            f"Lenso Upload failed or ID not found. Status Code: {resp.status_code}, Response: {resp.text}"
        )

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        search_type: SEARCH_TYPES = "",
        sort_type: SORT_TYPES = "SMART",
        **kwargs: Any,
    ) -> LensoResponse:
        warnings.warn(
            (
                "The Lenso engine is deprecated as the website now uses Cloudflare turnstile protection "
                "which prevents this client from working properly."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if search_type and search_type not in get_args(self.SEARCH_TYPES):
            valid_types = '", "'.join(t for t in get_args(self.SEARCH_TYPES) if t)
            raise ValueError(f'Invalid search_type. Must be empty or one of: "{valid_types}"')
        if sort_type not in get_args(self.SORT_TYPES):
            valid_sorts = '", "'.join(get_args(self.SORT_TYPES))
            raise ValueError(f'Invalid sort_type. Must be one of: "{valid_sorts}"')
        if url:
            image_bytes = await self.download(url)
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            result_hash = await self._upload_image(image_base64)
        elif file:
            image_bytes = read_file(file)
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            result_hash = await self._upload_image(image_base64)
        else:
            raise ValueError("Either 'url' or 'file' must be provided")
        search_endpoint = "api/search"
        search_payload = {
            "image": {
                "id": result_hash,
                "data": f"data:image/jpeg;base64,{image_base64}",
            },
            "effects": {},
            "selection": {},
            "domain": "",
            "text": "",
            "page": 0,
            "type": search_type,
            "sort": sort_type,
            "seed": 0,
            "facial_search_consent": 0,
        }
        resp = await self._send_request(method="post", endpoint=search_endpoint, json=search_payload)
        resp_json = json_loads(resp.text)
        resp_url = f"{self.base_url}/en/results/{result_hash}"
        return LensoResponse(resp_json, resp_url)

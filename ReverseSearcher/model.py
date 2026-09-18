"""基于参考插件请求/解析模块的 Nekro 搜图模型。

这里保留 AstrBot 版本的统一请求生命周期和引擎参数分发，但不依赖
AstrBot 的消息、卡片或日志 API。上层插件拿到响应对象后自行转换为统一结果。
"""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image

from .utils import Network
from .utils.api_request import AnimeTrace, EHentai, GoogleLens, SauceNAO, Yandex
from .utils.response_parser.base_parser import BaseSearchResponse
from .utils.security import is_safe_image_ref

ENGINE_MAP: dict[str, type] = {
    "animetrace": AnimeTrace,
    "anime_trace": AnimeTrace,
    "yandex": Yandex,
    "saucenao": SauceNAO,
    "google": GoogleLens,
    "google_lens": GoogleLens,
    "ehentai": EHentai,
    "exhentai": EHentai,
}


class BaseSearchModel:
    """统一执行 AnimeTrace、SauceNAO、Yandex、Google Lens、E-Hentai。"""

    def __init__(
        self,
        proxies: str | None = None,
        cookies: str | None = None,
        timeout: int = 60,
        default_params: dict[str, dict[str, Any]] | None = None,
        allow_third_party_image_host: bool = True,
    ) -> None:
        self.proxies = proxies
        self.cookies = cookies
        self.timeout = timeout
        self.default_params = default_params or {}
        self.allow_third_party_image_host = allow_third_party_image_host

    @staticmethod
    def _is_gif(file: str | bytes | Path) -> bool:
        if isinstance(file, bytes):
            return file.startswith((b"GIF87a", b"GIF89a"))
        return str(file).lower().endswith(".gif")

    async def _convert_gif_to_jpeg(self, file: str | bytes | Path) -> bytes:
        def convert() -> bytes:
            raw = file if isinstance(file, bytes) else Path(file).read_bytes()
            image = Image.open(io.BytesIO(raw))
            image.seek(0)
            output = io.BytesIO()
            image.convert("RGB").save(output, "JPEG", quality=85)
            return output.getvalue()

        return await asyncio.to_thread(convert)

    def _prepare_engine_params(self, api: str, values: dict[str, Any]) -> dict[str, Any]:
        if api in {"animetrace", "anime_trace"}:
            return {
                "is_multi": values.pop("is_multi", None),
                "ai_detect": values.pop("ai_detect", None),
            }
        if api in {"ehentai", "exhentai"}:
            return {
                "is_ex": api == "exhentai" or values.pop("is_ex", False),
                "covers": values.pop("covers", False),
                "similar": values.pop("similar", True),
                "exp": values.pop("exp", False),
                "cookies": values.pop("cookies", None),
            }
        if api == "saucenao":
            return {
                "api_key": values.pop("api_key", None),
                "hide": values.pop("hide", 0),
                "numres": values.pop("numres", 5),
                "minsim": values.pop("minsim", 30),
                "output_type": values.pop("output_type", 2),
                "testmode": values.pop("testmode", 0),
                "dbmask": values.pop("dbmask", None),
                "dbmaski": values.pop("dbmaski", None),
                "db": values.pop("db", 999),
                "dbs": values.pop("dbs", None),
            }
        if api in {"google", "google_lens"}:
            api_keys = values.pop("api_keys", {}) or {}
            return {
                "serpapi_key": values.pop("serpapi_key", None) or api_keys.get("serpapi"),
                "zenserp_key": values.pop("zenserp_key", None) or api_keys.get("zenserp"),
                "country": values.pop("country", "HK"),
                "hl": values.pop("hl", "zh-CN"),
                "max_results": values.pop("max_results", 10),
            }
        if api == "yandex":
            return {
                "max_results": values.pop("max_results", 10),
                "use_ru_fallback": values.pop("use_ru_fallback", True),
                "cookies": values.pop("cookies", None),
            }
        return {}

    async def _search_engine(
        self,
        api: str,
        file: str | bytes | Path | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> BaseSearchResponse[Any]:
        normalized = api.lower()
        if normalized not in ENGINE_MAP:
            raise ValueError(f"不支持的参考搜索引擎: {api}")
        if not file and not url:
            raise ValueError("必须提供 file 或 url 参数")
        if file and url:
            raise ValueError("file 和 url 参数不能同时提供")
        if url and not await asyncio.to_thread(is_safe_image_ref, url):
            raise ValueError("图片地址不安全：仅支持公网图片 URL")
        if file and self._is_gif(file):
            file = await self._convert_gif_to_jpeg(file)

        params = {**self.default_params.get(normalized, {}), **kwargs}
        engine_params = self._prepare_engine_params(normalized, params)
        effective_cookies = engine_params.get("cookies") or self.cookies
        if normalized in {"google", "google_lens", "yandex"} and file and not self.allow_third_party_image_host:
            raise ValueError("当前配置禁止本地图上传到第三方图床，无法使用该参考引擎")

        network_kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self.proxies:
            network_kwargs["proxies"] = self.proxies
        if effective_cookies:
            network_kwargs["cookies"] = effective_cookies

        if params.get("base64") and normalized not in {"animetrace", "anime_trace"}:
            file = base64.b64decode(params.pop("base64"))

        async with Network(**network_kwargs) as network:
            request_cls = ENGINE_MAP[normalized]
            request = request_cls(network=network, **engine_params)
            if normalized in {"animetrace", "anime_trace"} and params.get("base64"):
                return await request.search(
                    base64=params.pop("base64"),
                    model=params.pop("model", None),
                    **params,
                )
            return await request.search(file=file, url=url, **params)

    async def search(
        self,
        api: str,
        file: str | bytes | Path | None = None,
        url: str | None = None,
        **kwargs: Any,
    ) -> BaseSearchResponse[Any]:
        return await self._search_engine(api, file=file, url=url, **kwargs)


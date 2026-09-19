from typing import Any

from typing_extensions import override

from ..ext_tools import read_file
from ..response_parser.yandex_parser import YandexResponse
from ..types import FileContent
from .base_req import BaseSearchReq


class Yandex(BaseSearchReq[YandexResponse]):
    """
    Yandex 搜索请求类
    """

    def __init__(
        self,
        base_url: str = "https://yandex.ru",
        **request_kwargs: Any,
    ):
        # Yandex's .com endpoint may redirect or present a different regional
        # search page for mainland Chinese clients. Keep the request on .ru.
        base_url = base_url.replace("yandex.com", "yandex.ru")
        base_url = f"{base_url}/images/search"
        request_kwargs.pop("use_ru_fallback", None)
        # max_results 在 search() 阶段使用，不会传给底层 httpx 客户端，这里先弹出避免报错
        request_kwargs.pop("max_results", None)

        super().__init__(base_url, **request_kwargs)

    @override
    async def search(
        self,
        url: str | None = None,
        file: FileContent = None,
        **kwargs: Any,
    ) -> YandexResponse:
        target_url = url
        if file:
            # 本地文件先上传到临时图床（Litterbox），再以 URL 形式搜索
            file_bytes = file if isinstance(file, bytes) else read_file(file)
            target_url = await self._upload_image(file_bytes)

        if not target_url:
            raise ValueError("Must provide url or file")

        # Yandex 通过 .ru URL 搜索：https://yandex.ru/images/search?rpt=imageview&url={target_url}
        params = {"rpt": "imageview", "url": target_url}

        # 用浏览器 UA 头，降低被风控的概率
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        resp = await self._send_request(
            method="get", params=params, headers=headers, timeout=30
        )

        return YandexResponse(resp.text, resp.url, **kwargs)

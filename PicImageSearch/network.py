from types import TracebackType
from typing import Any, NamedTuple

from httpx import AsyncClient, QueryParams, create_ssl_context

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.82 Safari/537.36"
    )
}


class Network:
    def __init__(
        self,
        internal: bool = False,
        proxies: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: str | None = None,
        timeout: float = 30,
        verify_ssl: bool = True,
        http2: bool = False,
    ):
        self.internal: bool = internal
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        self.cookies: dict[str, str] = {}
        if cookies:
            for line in cookies.split(";"):
                key, value = line.strip().split("=", 1)
                self.cookies[key] = value

        ssl_context = create_ssl_context(verify=verify_ssl)
        ssl_context.set_ciphers("DEFAULT")
        self.client: AsyncClient = AsyncClient(
            headers=headers,
            cookies=self.cookies,
            verify=ssl_context,
            http2=http2,
            proxy=proxies,
            timeout=timeout,
            follow_redirects=True,
        )

    def start(self) -> AsyncClient:
        return self.client

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self.client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        await self.client.aclose()


class ClientManager:
    def __init__(
        self,
        client: AsyncClient | None = None,
        proxies: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: str | None = None,
        timeout: float = 30,
        verify_ssl: bool = True,
        http2: bool = False,
    ):
        self.client: Network | AsyncClient = client or Network(
            internal=True,
            proxies=proxies,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            verify_ssl=verify_ssl,
            http2=http2,
        )

    async def __aenter__(self) -> AsyncClient:
        return self.client.start() if isinstance(self.client, Network) else self.client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if isinstance(self.client, Network) and self.client.internal:
            await self.client.close()


class RESP(NamedTuple):
    text: str
    url: str
    status_code: int


class HandOver:
    def __init__(
        self,
        client: AsyncClient | None = None,
        proxies: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: str | None = None,
        timeout: float = 30,
        verify_ssl: bool = True,
        http2: bool = False,
    ):
        self.client: AsyncClient | None = client
        self.proxies: str | None = proxies
        self.headers: dict[str, str] | None = headers
        self.cookies: str | None = cookies
        self.timeout: float = timeout
        self.verify_ssl: bool = verify_ssl
        self.http2: bool = http2

    async def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> RESP:
        async with ClientManager(
            self.client,
            self.proxies,
            self.headers,
            self.cookies,
            self.timeout,
            self.verify_ssl,
            self.http2,
        ) as client:
            resp = await client.get(url, params=params, headers=headers, **kwargs)
            return RESP(resp.text, str(resp.url), resp.status_code)

    async def post(
        self,
        url: str,
        params: dict[str, Any] | QueryParams | None = None,
        headers: dict[str, str] | None = None,
        data: dict[Any, Any] | None = None,
        files: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> RESP:
        async with ClientManager(
            self.client,
            self.proxies,
            self.headers,
            self.cookies,
            self.timeout,
            self.verify_ssl,
            self.http2,
        ) as client:
            resp = await client.post(
                url,
                params=params,
                headers=headers,
                data=data,
                files=files,
                json=json,
                **kwargs,
            )
            return RESP(resp.text, str(resp.url), resp.status_code)

    async def download(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        async with ClientManager(
            self.client,
            self.proxies,
            self.headers,
            self.cookies,
            self.timeout,
            self.verify_ssl,
            self.http2,
        ) as client:
            resp = await client.get(url, headers=headers)
            return resp.read()

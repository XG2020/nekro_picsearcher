import re
from base64 import b64decode, b64encode
from json import dumps as json_dumps
from json import loads as json_loads
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from typing_extensions import override

from ..model import BingResponse
from ..utils import read_file
from .base import BaseSearchEngine


def _decrypt_signature_segment(encrypted_segment: str) -> str:
    ENCRYPTION_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIGd3gMN2v1KRLBGmotz7jbQYF8PaB+Jpe6iVf2YIeN5b"
    CHAR_OFFSET = 3
    try:
        decoded_bytes = b64decode(encrypted_segment)
    except Exception:
        return encrypted_segment
    decrypted_chars = []
    for i, cipher_byte in enumerate(decoded_bytes):
        key_char_code = ord(ENCRYPTION_KEY[i % len(ENCRYPTION_KEY)])
        xor_result = cipher_byte ^ key_char_code
        original_char_code = xor_result - CHAR_OFFSET
        decrypted_chars.append(chr(original_char_code))
    return "".join(decrypted_chars)


def _parse_signature(raw_signature: str) -> str:
    parts = raw_signature.split("|")
    if len(parts) == 3:
        version, encrypted_data, timestamp = parts
        decrypted_data = _decrypt_signature_segment(encrypted_data)
        return f"{version}|{decrypted_data}|{timestamp}"
    return raw_signature


class Bing(BaseSearchEngine[BingResponse]):
    def __init__(self, **request_kwargs: Any):
        base_url = "https://www.bing.com"
        super().__init__(base_url, **request_kwargs)
        self._session_key: str | None = None
        self._image_signature: str | None = None

    async def _upload_image(self, file: str | bytes | Path) -> tuple[str, str]:
        endpoint = "images/search?view=detailv2&iss=sbiupload"
        image_base64 = b64encode(read_file(file)).decode("utf-8")
        files = {
            "cbir": "sbi",
            "imageBin": image_base64,
        }
        resp = await self._send_request(method="post", endpoint=endpoint, files=files)
        self._session_key = re.search(r"skey=([^&]+)", resp.text)[1]
        self._image_signature = re.search(r"imageSignature&quot;:&quot;(.+?)&quot;", resp.text)[1]
        if match := re.search(r"(bcid_[A-Za-z0-9-.]+)", resp.text):
            return match[1], str(resp.url)
        raise ValueError("BCID not found on page.")

    async def _get_insights(self, bcid: str | None = None, image_url: str | None = None) -> dict[str, Any]:
        endpoint = "images/api/custom/knowledge"
        params: dict[str, Any] = {
            "rshighlight": "true",
            "textDecorations": "true",
            "internalFeatures": "similarproducts,share",
            "nbl": "1",
            "skey": self._session_key,
            "safeSearch": "off",
            "mkt": "en-us",
            "setLang": "en-us",
            "iss": "SBIUPLOADGET",
            "IID": "idpins",
            "SFX": "1",
        }
        if image_url:
            referer = (
                f"{self.base_url}/images/search?"
                f"view=detailv2&iss=sbi&FORM=SBIHMP&sbisrc=UrlPaste"
                f"&q=imgurl:{quote_plus(image_url)}&idpbck=1"
            )
            image_info = {"imageInfo": {"url": image_url, "source": "Url"}}
        else:
            params["insightsToken"] = bcid
            referer = f"{self.base_url}/images/search?insightsToken={bcid}"
            image_info = {"imageInfo": {"imageInsightsToken": bcid, "source": "Gallery"}}
            if self.client:
                self.client.cookies.clear()
        headers = {"Referer": referer}
        if self._image_signature:
            headers["X-Image-Knowledge-Signature"] = _parse_signature(self._image_signature)
        files = {
            "knowledgeRequest": (
                None,
                json_dumps(image_info),
                "application/json",
            )
        }
        resp = await self._send_request(method="post", endpoint=endpoint, headers=headers, params=params, files=files)
        return json_loads(resp.text)

    @override
    async def search(
        self,
        url: str | None = None,
        file: str | bytes | Path | None = None,
        **kwargs: Any,
    ) -> BingResponse:
        if url:
            resp_url = (
                f"{self.base_url}/images/search?"
                f"view=detailv2&iss=sbi&FORM=SBIHMP&sbisrc=UrlPaste"
                f"&q=imgurl:{url}&idpbck=1"
            )
            resp = await self._send_request(method="GET", url=resp_url)
            self._image_signature = re.search(r"imageSignature&quot;:&quot;(.+?)&quot;", resp.text)[1]
            resp_json = await self._get_insights(image_url=url)
        elif file:
            bcid, resp_url = await self._upload_image(file)
            resp_json = await self._get_insights(bcid=bcid)
        else:
            raise ValueError("Either 'url' or 'file' must be provided")
        return BingResponse(resp_json, resp_url)

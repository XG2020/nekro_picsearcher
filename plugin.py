import asyncio
import html
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from nekro_agent.api.plugin import ConfigBase, ExtraField, NekroPlugin, SandboxMethodType
from nekro_agent.api.schemas import AgentCtx
from pydantic import Field
from nekro_agent.api import core

from .PicImageSearch.engines.ascii2d import Ascii2D
from .PicImageSearch.engines.anime_trace import AnimeTrace
from .PicImageSearch.engines.bing import Bing
from .PicImageSearch.engines.saucenao import SauceNAO
from .PicImageSearch.engines.tineye import Tineye
from .PicImageSearch.engines.tracemoe import TraceMoe
from .PicImageSearch.engines.yandex import Yandex
from .PicImageSearch.engines.google import Google
from .PicImageSearch.engines.iqdb import Iqdb
from .PicImageSearch.engines.baidu import BaiDu
from .PicImageSearch.engines.google_lens import GoogleLens
from .PicImageSearch.engines.lenso import Lenso
from .PicImageSearch.engines.copyseeker import Copyseeker
from .PicImageSearch.engines.ehentai import EHentai


plugin = NekroPlugin(
    name="以图搜图",
    module_name="nekro_picsearcher",
    description="基于 PicImageSearch 的多引擎图片反向搜索工具",
    author="XGGM",
    version="1.1.0",
    url="https://github.com/XG2020/nekro_picsearcher",
)


@plugin.mount_config()
class PicSearcherConfig(ConfigBase):
    saucenao_api_key: str = Field(
        default="",
        title="SauceNAO API Key",
        description="可选，用于提升 SauceNAO 查询额度与稳定性",
        json_schema_extra=ExtraField(is_secret=True, required=False).model_dump(),
    )
    exhentai_cookie_member_id: str = Field(
        default="",
        title="ExHentai Cookie ipb_member_id",
        description="用于 ExHentai 登录态（ipb_member_id）",
        json_schema_extra=ExtraField(is_secret=True, required=False).model_dump(),
    )
    exhentai_cookie_pass_hash: str = Field(
        default="",
        title="ExHentai Cookie ipb_pass_hash",
        description="用于 ExHentai 登录态（ipb_pass_hash）",
        json_schema_extra=ExtraField(is_secret=True, required=False).model_dump(),
    )
    exhentai_cookie_igneous: str = Field(
        default="",
        title="ExHentai Cookie igneous",
        description="用于 ExHentai 登录态（igneous，可选）",
        json_schema_extra=ExtraField(is_secret=True, required=False).model_dump(),
    )
    ascii2d_bovw: bool = Field(
        default=False,
        title="Ascii2D 特征搜索",
        description="开启后使用特征搜索（bovw），默认颜色聚合搜索",
    )
    enable_yandex: bool = Field(default=True, title="启用 Yandex")
    enable_baidu: bool = Field(default=True, title="启用 Baidu")
    enable_google: bool = Field(default=False, title="启用 Google")
    enable_bing: bool = Field(default=False, title="启用 Bing")
    enable_ascii2d: bool = Field(default=False, title="启用 Ascii2D")
    enable_anime_trace: bool = Field(default=False, title="启用 AnimeTrace")
    enable_tracemoe: bool = Field(default=False, title="启用 TraceMoe")
    enable_iqdb: bool = Field(default=False, title="启用 IQDB")
    enable_google_lens: bool = Field(default=False, title="启用 Google Lens")
    enable_lenso: bool = Field(default=False, title="启用 Lenso")
    enable_copyseeker: bool = Field(default=False, title="启用 Copyseeker")
    enable_saucenao: bool = Field(default=False, title="启用 SauceNAO")
    enable_tineye: bool = Field(default=False, title="启用 Tineye")
    enable_ehentai: bool = Field(default=False, title="启用 EHentai")
    enable_exhentai: bool = Field(default=False, title="启用 ExHentai")
    max_results: int = Field(
        default=3,
        title="单引擎返回条数",
        description="每个引擎返回的最大结果条数",
    )
    trusted_results: int = Field(
        default=5,
        title="可信结果增强数量",
        description="从所有搜索结果中筛选并抓取正文的高可信结果数量",
    )
    webpage_fetch_timeout: int = Field(
        default=12,
        title="网页抓取超时秒数",
        description="抓取搜索结果来源网页时的请求超时时间",
    )
    webpage_content_chars: int = Field(
        default=3500,
        title="网页正文最大字符数",
        description="每个可信网页最多返回的清洗正文字符数",
    )
    webpage_max_bytes: int = Field(
        default=1048576,
        title="网页抓取最大字节数",
        description="限制单个来源网页最多读取的响应字节数，避免超大页面占用上下文和内存",
    )
    webpage_cache_ttl: int = Field(
        default=1800,
        title="网页内容缓存秒数",
        description="同一来源网页在缓存有效期内复用抓取与总结结果，减少重复请求和模型消耗",
    )
    allow_private_webpage_fetch: bool = Field(
        default=False,
        title="允许抓取私网地址",
        description="默认禁止抓取 localhost、内网 IP 等私有地址，防止搜索结果链接触发内网访问",
    )


_WEBPAGE_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}
_PYQUERY_READY = False


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _get_proxy() -> Optional[str]:
    try:
        proxy = getattr(core.config, "DEFAULT_PROXY", None)
    except Exception:
        proxy = None
    if proxy:
        if isinstance(proxy, str) and proxy.startswith(("http://", "https://")):
            return proxy
        return f"http://{proxy}"
    return None


def _get_cfg() -> "PicSearcherConfig":
    try:
        cfg = getattr(plugin, "config", None)
        if cfg:
            return cfg
    except Exception:
        pass
    return PicSearcherConfig()

def _ensure_pyquery() -> None:
    global _PYQUERY_READY
    if _PYQUERY_READY:
        return
    try:
        from nekro_agent.services.plugin.packages import dynamic_import_pkg
        dynamic_import_pkg("pyquery", "pyquery")
        dynamic_import_pkg("lxml", "lxml")
        dynamic_import_pkg("cssselect", "cssselect")
        import pyquery  # noqa: F401
        import lxml  # noqa: F401
        _PYQUERY_READY = True
    except Exception as ee:
        raise RuntimeError(
            f"缺少依赖 pyquery/lxml：{ee}. 请确保 dynamic_import_pkg 可用，或手动执行 pip install pyquery lxml cssselect"
        )


def _build_file_arg(image: str, ctx: AgentCtx) -> Dict[str, Any]:
    if _is_url(image):
        return {"url": image}
    host_path = ctx.fs.get_file(image)
    return {"file": str(host_path)}


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _is_private_host(hostname: str) -> bool:
    if not hostname:
        return True
    host = hostname.strip("[]").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return True
    except Exception:
        return False
    return False


def _validate_fetch_url(url: str, cfg: PicSearcherConfig) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持抓取 http/https 网页")
    if not parsed.hostname:
        raise ValueError("来源链接缺少有效域名")
    if not cfg.allow_private_webpage_fetch and _is_private_host(parsed.hostname):
        raise ValueError("已阻止抓取私网或本机地址")


def _cache_key(url: str, cfg: PicSearcherConfig) -> str:
    return f"{cfg.webpage_content_chars}:{url}"


def _get_cached_webpage(url: str, cfg: PicSearcherConfig) -> Optional[Dict[str, str]]:
    ttl = max(0, cfg.webpage_cache_ttl)
    if ttl <= 0:
        return None
    key = _cache_key(url, cfg)
    cached = _WEBPAGE_CACHE.get(key)
    if not cached:
        return None
    created_at, value = cached
    if time.time() - created_at > ttl:
        _WEBPAGE_CACHE.pop(key, None)
        return None
    return value


def _set_cached_webpage(url: str, cfg: PicSearcherConfig, value: Dict[str, str]) -> None:
    if cfg.webpage_cache_ttl <= 0:
        return
    if len(_WEBPAGE_CACHE) > 256:
        oldest_key = min(_WEBPAGE_CACHE, key=lambda key: _WEBPAGE_CACHE[key][0])
        _WEBPAGE_CACHE.pop(oldest_key, None)
    _WEBPAGE_CACHE[_cache_key(url, cfg)] = (time.time(), value)


def _detect_result_consensus(entries: List[Dict[str, Any]]) -> List[str]:
    if not entries:
        return []
    domain_count: Dict[str, int] = {}
    title_count: Dict[str, int] = {}
    engine_count: Dict[str, int] = {}
    for entry in entries:
        domain = _domain_of(entry["url"])
        if domain:
            domain_count[domain] = domain_count.get(domain, 0) + 1
        title = _clean_text(entry["item"].get("title") or entry["item"].get("source") or entry["item"].get("site_name") or "").lower()
        if title:
            title_count[title] = title_count.get(title, 0) + 1
        engine = str(entry.get("engine") or "")
        if engine:
            engine_count[engine] = engine_count.get(engine, 0) + 1
    hints: List[str] = []
    repeated_domains = [f"{domain}×{count}" for domain, count in sorted(domain_count.items(), key=lambda item: item[1], reverse=True) if count > 1]
    repeated_titles = [f"{title}×{count}" for title, count in sorted(title_count.items(), key=lambda item: item[1], reverse=True) if count > 1]
    if repeated_domains:
        hints.append(f"多个结果指向相同域名：{', '.join(repeated_domains[:3])}")
    if repeated_titles:
        hints.append(f"多个结果标题/来源相近：{', '.join(repeated_titles[:3])}")
    if len(engine_count) > 1:
        hints.append(f"共有 {len(engine_count)} 个引擎给出可访问来源，可优先采纳跨引擎一致的信息")
    if not hints:
        hints.append("未发现明显跨结果共识，请保留不确定性并避免把单一网页结论当作事实")
    return hints


def _classify_source_type(url: str, item: Dict[str, Any], page_text: str) -> Tuple[str, str, float]:
    domain = _domain_of(url)
    path = urlparse(url).path.lower()
    title = _clean_text(
        item.get("title")
        or item.get("source")
        or item.get("site_name")
        or item.get("author")
        or ""
    ).lower()
    text = _clean_text(page_text).lower()
    merged = " ".join([domain, path, title, text[:1500]])
    text_head = text[:300]

    official_title_keywords = ["official", "official site", "官网", "官方", "公式サイト", "official website", "官方网站"]
    official_head_keywords = ["official website", "官方网站", "官方页面", "公式サイト", "official site"]
    official_domain_tokens = ["official", ".gov", ".edu"]
    original_domains = [
        "pixiv.net",
        "artstation.com",
        "deviantart.com",
        "fanbox.cc",
        "skeb.jp",
        "nijie.info",
        "patreon.com",
    ]
    social_domains = [
        "x.com",
        "twitter.com",
        "weibo.com",
        "instagram.com",
        "bilibili.com",
        "youtube.com",
        "tiktok.com",
    ]
    discussion_domains = [
        "reddit.com",
        "tieba.baidu.com",
        "zhihu.com",
        "forum",
        "bbs",
        "stackexchange.com",
        "quora.com",
    ]
    ecommerce_domains = [
        "taobao.com",
        "tmall.com",
        "jd.com",
        "amazon.",
        "ebay.",
        "etsy.com",
        "aliexpress.com",
    ]
    wiki_news_domains = [
        "wikipedia.org",
        "wikimedia.org",
        "fandom.com",
        "news",
        "press",
        "blog",
        "medium.com",
    ]
    aggregator_domains = [
        "pinterest.",
        "yande.re",
        "konachan.",
        "zerochan.net",
        "danbooru.donmai.us",
        "gelbooru.com",
    ]

    negative_domain_hit = any(token in domain for token in [*discussion_domains, *ecommerce_domains, *aggregator_domains])
    official_title_hit = any(keyword in title for keyword in official_title_keywords)
    official_domain_hit = any(token in domain for token in official_domain_tokens)
    official_path_hit = any(token in path for token in ["/official", "/official-site", "/officialsite", "/about", "/brand"])
    official_head_hit = any(keyword in text_head for keyword in official_head_keywords)
    if official_domain_hit or official_title_hit or (official_path_hit and official_head_hit):
        if not negative_domain_hit:
            reason_parts: List[str] = []
            if official_domain_hit:
                reason_parts.append("域名包含强官方信号")
            if official_title_hit:
                reason_parts.append("标题包含官方标识")
            if official_path_hit and official_head_hit:
                reason_parts.append("路径与正文开头同时出现官方标识")
            return "官方/权威页", "；".join(reason_parts), 18.0
    if any(token in domain for token in original_domains):
        return "原始发布页", "命中常见创作者原始发布平台", 14.0
    if any(token in domain for token in ecommerce_domains) or any(
        keyword in merged for keyword in ["price", "buy", "sale", "商品", "购买", "店铺", "加入购物车"]
    ):
        return "电商商品页", "页面更像商品销售或店铺展示", -4.0
    if any(token in domain for token in discussion_domains) or any(
        keyword in merged for keyword in ["forum", "thread", "帖子", "评论", "问答", "discussion", "回复"]
    ):
        return "讨论社区页", "页面更像讨论、帖子或问答内容", -2.0
    if any(token in domain for token in aggregator_domains) or any(
        keyword in merged for keyword in ["repost", "collection", "curation", "转载", "合集", "图片库", "similar images"]
    ):
        return "聚合转载页", "页面更像图片聚合、转载或索引页", -6.0
    if any(token in domain for token in wiki_news_domains) or any(
        keyword in merged for keyword in ["百科", "新闻", "报道", "wiki", "press release", "article"]
    ):
        return "资讯/资料页", "页面更像百科、资料或资讯报道", 6.0
    if any(token in domain for token in social_domains) or any(
        keyword in merged for keyword in ["post", "status", "tweet", "微博", "动态", "视频主页"]
    ):
        return "社交媒体页", "页面更像社交平台发布内容", 4.0
    return "未识别", "暂未命中明显来源类型特征", 0.0


def _score_result(engine: str, item: Dict[str, Any]) -> Tuple[float, List[str], Dict[str, float]]:
    score_detail: Dict[str, float] = {}
    reasons: List[str] = []
    similarity = item.get("similarity")
    if similarity is not None:
        try:
            sim_value = float(str(similarity).rstrip("%"))
            score_detail["similarity"] = min(max(sim_value, 0.0), 100.0) * 1.2
            reasons.append(f"相似度 {sim_value:g}%")
        except Exception:
            pass
    if item.get("title"):
        score_detail["title"] = 12
        reasons.append("含标题")
    if item.get("source") or item.get("site_name") or item.get("author") or item.get("index_name"):
        score_detail["source"] = 8
        reasons.append("含来源信息")
    if item.get("size"):
        score_detail["size"] = 4
    if item.get("url"):
        score_detail["url"] = 10
        domain = _domain_of(str(item.get("url")))
        if domain:
            reasons.append(f"来源域名 {domain}")
    engine_weight = {
        "saucenao": 35,
        "ascii2d": 28,
        "iqdb": 26,
        "tracemoe": 26,
        "google_lens": 22,
        "lenso": 22,
        "tineye": 20,
        "copyseeker": 18,
        "yandex": 16,
        "google": 15,
        "bing": 12,
        "baidu": 10,
        "ehentai": 16,
        "exhentai": 16,
        "anime_trace": 10,
    }.get(engine, 8)
    score_detail["engine"] = float(engine_weight)
    reasons.append(f"{engine} 引擎权重")
    score = sum(score_detail.values())
    score_detail["total"] = score
    return score, reasons, score_detail


def _score_detail_text(score_detail: Dict[str, float]) -> str:
    ordered_keys = [
        ("engine", "引擎"),
        ("similarity", "相似度"),
        ("title", "标题"),
        ("source", "来源字段"),
        ("source_type", "来源类型"),
        ("size", "尺寸"),
        ("url", "链接"),
        ("webpage", "网页内容"),
        ("consensus", "跨结果共识"),
    ]
    parts = [
        f"{label} {score_detail[key]:.1f}"
        for key, label in ordered_keys
        if score_detail.get(key)
    ]
    total = score_detail.get("total", 0.0)
    parts.append(f"总分 {total:.1f}")
    return "；".join(parts)


def _flatten_ranked_results(search_results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for result in search_results:
        engine = str(result.get("engine") or "")
        for item in result.get("items", []):
            url = str(item.get("url") or item.get("video") or item.get("image") or "").strip()
            if not _is_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            score, reasons, score_detail = _score_result(engine, item)
            ranked.append(
                {
                    "engine": engine,
                    "item": item,
                    "url": url,
                    "score": score,
                    "reasons": reasons,
                    "score_detail": score_detail,
                }
            )
    ranked.sort(key=lambda entry: entry["score"], reverse=True)
    return ranked[: max(0, limit)]


def _extract_html_text(raw_html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "header", "footer", "nav"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        metas = []
        for meta_name in ["description", "og:description", "twitter:description"]:
            meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
            content = meta.get("content") if meta else ""
            if content:
                metas.append(content)
        body = soup.get_text("\n", strip=True)
        return _clean_text("\n".join([title, *metas, body]))
    except Exception:
        text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw_html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return _clean_text(text)


async def _fetch_webpage_text(url: str, cfg: PicSearcherConfig) -> str:
    _validate_fetch_url(url, cfg)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    }
    proxies = _get_proxy()
    client_kwargs: Dict[str, Any] = {
        "timeout": cfg.webpage_fetch_timeout,
        "follow_redirects": True,
        "headers": headers,
    }
    if proxies:
        client_kwargs["proxy"] = proxies
    try:
        client = httpx.AsyncClient(**client_kwargs)
    except TypeError:
        if proxies:
            client_kwargs.pop("proxy", None)
            client_kwargs["proxies"] = proxies
        client = httpx.AsyncClient(**client_kwargs)
    async with client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "image/" in content_type or "video/" in content_type or "audio/" in content_type:
                return ""
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max(1, cfg.webpage_max_bytes):
                raise ValueError(f"网页过大，已跳过：{content_length} bytes")
            chunks: List[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max(1, cfg.webpage_max_bytes):
                    raise ValueError(f"网页超过最大读取限制：{cfg.webpage_max_bytes} bytes")
                chunks.append(chunk)
            encoding = response.encoding or "utf-8"
            raw_text = b"".join(chunks).decode(encoding, errors="ignore")
            return _extract_html_text(raw_text)


async def _enrich_ranked_result(entry: Dict[str, Any], cfg: PicSearcherConfig) -> Dict[str, Any]:
    cached = _get_cached_webpage(entry["url"], cfg)
    if cached:
        page_text = cached.get("page_text_for_type", "")
        source_type, source_type_reason, source_type_weight = _classify_source_type(entry["url"], entry["item"], page_text)
        return {
            **entry,
            **cached,
            "cache_hit": "true",
            "source_type": source_type,
            "source_type_reason": source_type_reason,
            "source_type_weight": source_type_weight,
        }
    try:
        text = await _fetch_webpage_text(entry["url"], cfg)
        if not text:
            value = {
                "page_summary": "网页不是可读取正文内容或正文为空",
                "page_error": "empty",
                "page_text_for_type": "",
            }
            _set_cached_webpage(entry["url"], cfg, value)
            source_type, source_type_reason, source_type_weight = _classify_source_type(entry["url"], entry["item"], value["page_summary"])
            return {
                **entry,
                **value,
                "cache_hit": "false",
                "source_type": source_type,
                "source_type_reason": source_type_reason,
                "source_type_weight": source_type_weight,
            }
        value = {
            "page_summary": text[: max(500, cfg.webpage_content_chars)],
            "page_error": "",
            "page_text_for_type": text[:2000],
        }
        _set_cached_webpage(entry["url"], cfg, value)
        source_type, source_type_reason, source_type_weight = _classify_source_type(entry["url"], entry["item"], text)
        return {
            **entry,
            **value,
            "cache_hit": "false",
            "source_type": source_type,
            "source_type_reason": source_type_reason,
            "source_type_weight": source_type_weight,
        }
    except Exception as ex:
        source_type, source_type_reason, source_type_weight = _classify_source_type(entry["url"], entry["item"], "")
        return {
            **entry,
            "page_summary": "",
            "page_error": str(ex),
            "cache_hit": "false",
            "source_type": source_type,
            "source_type_reason": source_type_reason,
            "source_type_weight": source_type_weight,
        }


async def _enrich_trusted_results(search_results: List[Dict[str, Any]], cfg: PicSearcherConfig) -> List[Dict[str, Any]]:
    ranked = _flatten_ranked_results(search_results, cfg.trusted_results)
    if not ranked:
        return []
    enriched = await asyncio.gather(*[_enrich_ranked_result(entry, cfg) for entry in ranked])
    domain_count: Dict[str, int] = {}
    title_count: Dict[str, int] = {}
    for entry in enriched:
        domain = _domain_of(entry["url"])
        if domain:
            domain_count[domain] = domain_count.get(domain, 0) + 1
        title = _clean_text(
            entry["item"].get("title")
            or entry["item"].get("source")
            or entry["item"].get("site_name")
            or entry["item"].get("author")
            or ""
        ).lower()
        if title:
            title_count[title] = title_count.get(title, 0) + 1
    finalized: List[Dict[str, Any]] = []
    for entry in enriched:
        score_detail = dict(entry.get("score_detail") or {})
        score_detail["source_type"] = float(entry.get("source_type_weight") or 0.0)
        webpage_bonus = 0.0
        if entry.get("page_summary"):
            webpage_bonus = 12.0 if not entry.get("page_error") else 6.0
        score_detail["webpage"] = webpage_bonus
        consensus_bonus = 0.0
        domain = _domain_of(entry["url"])
        if domain_count.get(domain, 0) > 1:
            consensus_bonus += 8.0
        title = _clean_text(
            entry["item"].get("title")
            or entry["item"].get("source")
            or entry["item"].get("site_name")
            or entry["item"].get("author")
            or ""
        ).lower()
        if title_count.get(title, 0) > 1:
            consensus_bonus += 6.0
        score_detail["consensus"] = consensus_bonus
        total = sum(value for key, value in score_detail.items() if key != "total")
        score_detail["total"] = total
        finalized.append({**entry, "score": total, "score_detail": score_detail})
    finalized.sort(key=lambda entry: entry["score"], reverse=True)
    return finalized


def _build_final_assessment(trusted: List[Dict[str, Any]]) -> List[str]:
    if not trusted:
        return ["暂无可形成结论的可信来源。"]
    best = trusted[0]
    best_item = best["item"]
    best_title = _clean_text(
        best_item.get("title")
        or best_item.get("source")
        or best_item.get("site_name")
        or best_item.get("author")
        or best["url"]
    )
    lines = [
        f"最优候选：{best_title}",
        f"最优候选链接：{best['url']}",
        f"最优候选来源类型：{best.get('source_type', '未识别')}（{best.get('source_type_reason', '无')}）",
        f"最优候选得分：{best['score']:.1f}（{_score_detail_text(best.get('score_detail') or {})}）",
    ]
    if len(trusted) > 1:
        second = trusted[1]
        second_item = second["item"]
        second_title = _clean_text(
            second_item.get("title")
            or second_item.get("source")
            or second_item.get("site_name")
            or second_item.get("author")
            or second["url"]
        )
        delta = best["score"] - second["score"]
        if delta >= 15:
            lines.append(f"结论倾向：首选结果明显领先，较次选高 {delta:.1f} 分。")
        elif delta >= 5:
            lines.append(f"结论倾向：首选结果略占优，较次选高 {delta:.1f} 分，仍建议核对关键细节。")
        else:
            lines.append(f"结论倾向：前两名接近，仅高 {delta:.1f} 分，应保留不确定性。")
        lines.append(
            f"次选候选：{second_title}（{second.get('source_type', '未识别')}，"
            f"较首选低 {delta:.1f} 分）"
        )
    else:
        lines.append("结论倾向：当前仅有一个高可信候选，请结合正文和视觉内容谨慎判断。")
    if best.get("page_summary"):
        if best.get("source_type") in {"官方/权威页", "原始发布页"}:
            lines.append("建议表述：可优先把首选来源当作主依据；若与视觉观察冲突，明确说明冲突点并保留不确定性。")
        else:
            lines.append("建议表述：首选来源可作重要参考，但仍建议与其他来源或视觉线索交叉验证。")
    return lines


def _fmt_ascii2d(item: Any) -> Dict[str, Any]:
    primary_url = getattr(item, "url", None)
    if not primary_url and getattr(item, "url_list", None):
        try:
            primary_url = item.url_list[0].href
        except Exception:
            primary_url = None
    return {
        "title": getattr(item, "title", ""),
        "author": getattr(item, "author", ""),
        "author_url": getattr(item, "author_url", ""),
        "url": primary_url,
        "thumbnail": getattr(item, "thumbnail", ""),
        "detail": getattr(item, "detail", ""),
    }


def _fmt_tracemoe(item: Any) -> Dict[str, Any]:
    title = item.title_chinese or item.title_romaji or item.title_english or item.title_native
    return {
        "title": title,
        "episode": item.episode,
        "from": item.From,
        "to": item.To,
        "similarity": item.similarity,
        "video": item.video,
        "image": item.image,
        "anilist_id": item.anilist_id,
        "cover_image": item.cover_image,
        "is_adult": item.isAdult,
    }


def _fmt_yandex(item: Any) -> Dict[str, Any]:
    return {
        "title": item.title,
        "url": item.url,
        "thumbnail": item.thumbnail,
        "source": getattr(item, "source", ""),
        "content": getattr(item, "content", ""),
        "size": getattr(item, "size", ""),
    }


def _fmt_google(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "title", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "size": getattr(item, "size", ""),
        "source": getattr(item, "source", ""),
    }


def _fmt_iqdb(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "title", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "size": getattr(item, "size", ""),
        "rating": getattr(item, "rating", ""),
        "similarity": getattr(item, "similarity", None),
    }


def _fmt_baidu(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "title", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
    }


def _fmt_glens(item: Any) -> Dict[str, Any]:
    out = {
        "title": getattr(item, "title", ""),
        "site_name": getattr(item, "site_name", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
    }
    size = getattr(item, "size", None)
    if size:
        out["size"] = size
    return out


def _fmt_ehentai(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "title", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "type": getattr(item, "type", ""),
        "date": getattr(item, "date", ""),
        "tags": getattr(item, "tags", []),
    }


def _fmt_lenso(item: Any) -> Dict[str, Any]:
    size = ""
    w = getattr(item, "width", 0)
    h = getattr(item, "height", 0)
    if w and h:
        size = f"{w}x{h}"
    primary_url = getattr(item, "url", None)
    if not primary_url and getattr(item, "url_list", None):
        try:
            primary_url = item.url_list[0].source_url
        except Exception:
            primary_url = None
    return {
        "title": getattr(item, "title", ""),
        "url": primary_url,
        "thumbnail": getattr(item, "thumbnail", ""),
        "similarity": getattr(item, "similarity", None),
        "size": size,
    }


def _fmt_copyseeker(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "title", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "similarity": None,
    }


def _fmt_bing_pages(item: Any) -> Dict[str, Any]:
    return {
        "title": getattr(item, "name", getattr(item, "title", "")),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "image_url": getattr(item, "image_url", ""),
    }


def _fmt_saucenao(item: Any) -> Dict[str, Any]:
    return {
        "title": item.title,
        "author": item.author,
        "author_url": item.author_url,
        "url": item.url,
        "thumbnail": item.thumbnail,
        "similarity": item.similarity,
        "index_name": item.index_name,
    }


def _fmt_anime_trace(item: Any) -> Dict[str, Any]:
    title = ""
    source = ""
    if getattr(item, "characters", None):
        first = item.characters[0]
        title = getattr(first, "name", "") or ""
        source = getattr(first, "work", "") or ""
    return {
        "title": title,
        "source": source,
        "url": "",
        "thumbnail": "",
    }


def _fmt_tineye(item: Any) -> Dict[str, Any]:
    size = ""
    if getattr(item, "size", None):
        try:
            size = f"{item.size[0]}x{item.size[1]}"
        except Exception:
            size = ""
    return {
        "title": getattr(item, "domain", ""),
        "url": getattr(item, "url", ""),
        "thumbnail": getattr(item, "thumbnail", ""),
        "image_url": getattr(item, "image_url", ""),
        "size": size,
        "source": getattr(item, "domain", ""),
    }


@plugin.mount_prompt_inject_method("picsearcher_image_source_analysis")
async def picsearcher_prompt_inject(_ctx: AgentCtx) -> str:
    return (
        "当用户让你识别、判断、考据图片来源或解释图片内容时，不要只依赖视觉模态。"
        "如果需要确认作品名、作者、出处、角色、事件、原始上下文或图片是否被误传，优先调用 `render_multi_engine_search` 进行反向搜图。"
        "该方法会返回多引擎结果、可信度排序，并对高可信来源网页进行总结或正文清洗；多个结果不一致时，应优先比较可信度高、相似度高、来源字段完整且网页内容可验证的结果，再说明你的判断依据和不确定性。"
    )


async def _do_search_single(
    engine: str,
    cfg: PicSearcherConfig,
    top_k: int,
    file_arg: Dict[str, Any],
    proxy: Optional[str],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    e = engine.lower()
    if options is None:
        options = {}

    if e in {"ascii2d", "asc"}:
        bovw = options.get("bovw", cfg.ascii2d_bovw)
        _ensure_pyquery()
        cli = Ascii2D(bovw=bovw, proxies=proxy)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "ascii2d", "url": resp.url, "items": [_fmt_ascii2d(i) for i in items]}
    if e in {"tracemoe", "trace"}:
        mute = bool(options.get("mute", False))
        size = options.get("size")
        cli = TraceMoe(mute=mute, size=size, proxies=proxy)
        resp = await cli.search(
            key=options.get("key"),
            anilist_id=options.get("anilist_id"),
            chinese_title=options.get("chinese_title", True),
            cut_borders=options.get("cut_borders", True),
            **file_arg,
        )
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "tracemoe", "url": resp.url, "items": [_fmt_tracemoe(i) for i in items]}
    if e in {"yandex", "ydx"}:
        _ensure_pyquery()
        cli = Yandex(proxies=proxy)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "yandex", "url": resp.url, "items": [_fmt_yandex(i) for i in items]}
    if e in {"google", "ggl"}:
        _ensure_pyquery()
        cli = Google(proxies=proxy)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "google", "url": resp.url, "items": [_fmt_google(i) for i in items]}
    if e in {"iqdb"}:
        _ensure_pyquery()
        is_3d = bool(options.get("is_3d", False))
        force_gray = bool(options.get("force_gray", False))
        cli = Iqdb(is_3d=is_3d, proxies=proxy)
        resp = await cli.search(force_gray=force_gray, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "iqdb", "url": resp.url, "items": [_fmt_iqdb(i) for i in items]}
    if e in {"baidu", "bd"}:
        _ensure_pyquery()
        cli = BaiDu(proxies=proxy)
        resp = await cli.search(**file_arg)
        pool = resp.exact_matches or resp.raw
        items = pool[: max(1, top_k)]
        return {"engine": "baidu", "url": resp.url, "items": [_fmt_baidu(i) for i in items]}
    if e in {"saucenao", "nao"}:
        api_key = options.get("api_key") or cfg.saucenao_api_key or None
        saucenao_kwargs: Dict[str, Any] = {}
        for key in ["numres", "hide", "minsim", "output_type", "testmode", "dbmask", "dbmaski", "db", "dbs"]:
            if key in options and options[key] is not None:
                saucenao_kwargs[key] = options[key]
        cli = SauceNAO(api_key=api_key, proxies=proxy, **saucenao_kwargs)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "saucenao", "url": resp.url, "items": [_fmt_saucenao(i) for i in items]}
    if e in {"bing"}:
        cli = Bing(proxies=proxy)
        resp = await cli.search(**file_arg)
        pool = getattr(resp, "pages_including", []) or getattr(resp, "visual_search", [])
        items = pool[: max(1, top_k)]
        return {"engine": "bing", "url": resp.url, "items": [_fmt_bing_pages(i) for i in items]}
    if e in {"google_lens", "lens"}:
        search_type = options.get("lens_type") or options.get("search_type") or "all"
        q = options.get("q")
        hl = options.get("hl", "en")
        country = options.get("country", "US")
        _ensure_pyquery()
        cli = GoogleLens(search_type=search_type, q=q, hl=hl, country=country, proxies=proxy)
        resp = await cli.search(q=q, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "google_lens", "url": resp.url, "items": [_fmt_glens(i) for i in items]}
    if e in {"lenso"}:
        search_type = options.get("search_type", "") if options else ""
        sort_type = options.get("sort_type", "SMART") if options else "SMART"
        cli = Lenso(proxies=proxy)
        resp = await cli.search(search_type=search_type, sort_type=sort_type, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "lenso", "url": resp.url, "items": [_fmt_lenso(i) for i in items]}
    if e in {"copyseeker", "copy"}:
        cli = Copyseeker(proxies=proxy)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "copyseeker", "url": resp.url, "items": [_fmt_copyseeker(i) for i in items]}
    if e in {"anime_trace", "animetrace", "anime"}:
        cli = AnimeTrace(
            is_multi=options.get("is_multi"),
            ai_detect=options.get("ai_detect"),
            proxies=proxy,
        )
        model_name = options.get("model")
        base64_data = options.get("base64")
        if base64_data:
            resp = await cli.search(base64=base64_data, model=model_name)
        else:
            resp = await cli.search(model=model_name, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "anime_trace", "url": resp.url, "items": [_fmt_anime_trace(i) for i in items]}
    if e in {"tineye", "tine"}:
        cli = Tineye(proxies=proxy)
        resp = await cli.search(
            show_unavailable_domains=bool(options.get("show_unavailable_domains", False)),
            domain=options.get("domain", ""),
            sort=options.get("sort", "score"),
            order=options.get("order", "desc"),
            tags=options.get("tags", ""),
            **file_arg,
        )
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "tineye", "url": resp.url, "items": [_fmt_tineye(i) for i in items]}
    if e in {"ehentai", "exhentai", "e-hentai"}:
        is_ex = e in {"exhentai"}
        _ensure_pyquery()
        exhentai_kwargs: Dict[str, Any] = {}
        if is_ex:
            cookies: Dict[str, str] = {}
            if cfg.exhentai_cookie_member_id:
                cookies["ipb_member_id"] = cfg.exhentai_cookie_member_id
            if cfg.exhentai_cookie_pass_hash:
                cookies["ipb_pass_hash"] = cfg.exhentai_cookie_pass_hash
            if cfg.exhentai_cookie_igneous:
                cookies["igneous"] = cfg.exhentai_cookie_igneous
            if cookies:
                exhentai_kwargs["cookies"] = cookies
        cli = EHentai(
            is_ex=is_ex,
            covers=bool(options.get("covers", False)),
            similar=bool(options.get("similar", True)),
            exp=bool(options.get("exp", False)),
            **exhentai_kwargs,
            proxies=proxy,
        )
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "exhentai" if is_ex else "ehentai", "url": resp.url, "items": [_fmt_ehentai(i) for i in items]}
    raise ValueError(f"unsupported engine: {engine}")


async def _do_search_single_safe(
    engine: str,
    cfg: PicSearcherConfig,
    top_k: int,
    file_arg: Dict[str, Any],
    proxy: Optional[str],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        res = await _do_search_single(engine, cfg, top_k, file_arg, proxy, options)
        return {"ok": True, "engine": engine, "result": res}
    except Exception as ex:
        return {"ok": False, "engine": engine, "error": str(ex)}

@plugin.mount_sandbox_method(
    method_type=SandboxMethodType.AGENT,
    name="render_multi_engine_search",
    description="反向搜索图片来源，筛选可信结果并抓取来源网页正文，供 AI 结合来源信息分析图片。",
)
async def render_multi_engine_search(
    _ctx: AgentCtx,
    *args: Any,
    **kwargs: Any,
) -> str:
    """
    在多个引擎上同时进行反向搜索，筛选可信来源并抓取网页正文，给大模型提供图片身份、来源、作者、作品名等参考。

    Args:
        _ctx (AgentCtx): 调用上下文（自动注入）
        image (str): 图片地址（http/https URL 或 AI 沙盒文件路径）
        enable_* (config): 通过配置项控制引擎启用或关闭
        top_k (int | None): 每个引擎返回的最大条数，默认使用配置项 max_results
        options (dict | None): 引擎可选项，示例
            - ascii2d: {"bovw": true}
            - tracemoe: {"key": "...", "anilist_id": 123, "chinese_title": true, "cut_borders": true, "mute": false, "size": "m"}
            - iqdb: {"is_3d": false, "force_gray": false}
            - google_lens: {"search_type": "all|products|visual_matches|exact_matches", "q": "...", "hl": "en", "country": "US"}
            - saucenao: {"api_key": "...", "numres": 5, "hide": 0, "minsim": 30, "output_type": 2}
            - anime_trace: {"model": "anime", "is_multi": 1, "ai_detect": 1, "base64": "..."}
            - ehentai: {"covers": false, "similar": true, "exp": false}
            - tineye: {"show_unavailable_domains": false, "domain": "", "sort": "score", "order": "desc", "tags": ""}

    Returns:
        str: 多引擎聚合结果、可信度排序和高可信来源网页正文。

    Example:
        # 在聊天频道中使用 /exec（无需传入 _ctx）
        /exec render_multi_engine_search(
            image="https://example.com/image.jpg",
            top_k=2,
            options={"bovw": true}
        )
    """
    image: Optional[str] = kwargs.pop("image", None) or (args[0] if len(args) > 0 else None)
    top_k: Optional[int] = kwargs.pop("top_k", None)
    options: Optional[Dict[str, Any]] = kwargs.pop("options", None)
    if not image:
        raise ValueError("缺少参数 image")
    cfg = _get_cfg()
    engs = [
        name
        for name, enabled in [
            ("ascii2d", cfg.enable_ascii2d),
            ("anime_trace", cfg.enable_anime_trace),
            ("tracemoe", cfg.enable_tracemoe),
            ("yandex", cfg.enable_yandex),
            ("google", cfg.enable_google),
            ("iqdb", cfg.enable_iqdb),
            ("baidu", cfg.enable_baidu),
            ("bing", cfg.enable_bing),
            ("google_lens", cfg.enable_google_lens),
            ("lenso", cfg.enable_lenso),
            ("copyseeker", cfg.enable_copyseeker),
            ("saucenao", cfg.enable_saucenao),
            ("tineye", cfg.enable_tineye),
            ("ehentai", cfg.enable_ehentai),
            ("exhentai", cfg.enable_exhentai),
        ]
        if enabled
    ]
    if not engs:
        raise ValueError("未启用任何引擎，请在配置中开启至少一个引擎")
    k = top_k or cfg.max_results
    file_arg = _build_file_arg(image, _ctx)
    proxy = _get_proxy()
    if any(e in {"ascii2d", "yandex", "google", "iqdb", "baidu", "google_lens", "ehentai", "exhentai"} for e in engs):
        _ensure_pyquery()
    search_results: List[Dict[str, Any]] = []
    lines: list[str] = [
        f"Image: {image}",
        "使用建议：不要只依赖视觉模态判断图片含义；请优先结合下方反向搜索来源、可信度排序和网页正文，交叉验证作品名、作者、出处、时间与上下文。",
    ]
    search_tasks = [
        _do_search_single_safe(e, cfg, k, file_arg, proxy, options)
        for e in engs
    ]
    search_outcomes = await asyncio.gather(*search_tasks)
    for outcome in search_outcomes:
        e = outcome["engine"]
        if outcome["ok"]:
            res = outcome["result"]
            search_results.append(res)
            items = res.get("items", [])
            lines.append(f"\n[{res.get('engine','')}] {res.get('url','')}".strip())
            idx = 1
            for it in items:
                parts: list[str] = []
                t = it.get("title") or it.get("source") or it.get("site_name") or ""
                if t:
                    parts.append(t)
                sim = it.get("similarity")
                if sim is not None:
                    parts.append(f"{sim}%")
                sz = it.get("size")
                if sz:
                    parts.append(sz)
                src = it.get("author") or it.get("site_name") or it.get("source")
                if src:
                    parts.append(src)
                url = it.get("url") or it.get("video") or it.get("image") or ""
                line = f"{idx}. " + " | ".join([p for p in parts if p]) + (f" -> {url}" if url else "")
                lines.append(line)
                idx += 1
        else:
            lines.append(f"\n[{e}] error: {outcome['error']}")
    trusted = await _enrich_trusted_results(search_results, cfg)
    if trusted:
        consensus_hints = _detect_result_consensus(trusted)
        final_assessment = _build_final_assessment(trusted)
        lines.append("\n[最终研判摘要]")
        for assessment_line in final_assessment:
            lines.append(assessment_line)
        lines.append("\n[可信结果筛选与网页内容]")
        lines.append("说明：可信度基于引擎权重、相似度、标题/来源字段和可访问 URL 综合排序；多个结果不一致时，请优先比较此列表并给出不确定性判断。")
        lines.append("共识/冲突提示：" + "；".join(consensus_hints))
        for idx, entry in enumerate(trusted, 1):
            item = entry["item"]
            title = _clean_text(item.get("title") or item.get("source") or item.get("site_name") or item.get("author") or "")
            cache_label = " cached" if entry.get("cache_hit") == "true" else ""
            lines.append(f"\n#{idx} score={entry['score']:.1f} engine={entry['engine']}{cache_label} url={entry['url']}")
            if title:
                lines.append(f"标题/来源：{title}")
            lines.append(
                f"来源类型：{entry.get('source_type', '未识别')} | 判断依据："
                f"{entry.get('source_type_reason', '无明显特征')}"
            )
            lines.append(f"可信依据：{'；'.join(entry['reasons'])}")
            lines.append(f"评分明细：{_score_detail_text(entry.get('score_detail') or {})}")
            if entry.get("page_summary"):
                lines.append(f"网页正文：{entry['page_summary']}")
            if entry.get("page_error") and entry.get("page_error") != "empty":
                lines.append(f"网页处理提示：{entry['page_error']}")
            elif entry.get("page_error"):
                lines.append(f"网页内容获取失败：{entry['page_error']}")
    else:
        lines.append("\n[可信结果筛选与网页内容]\n未找到可访问 URL 的可信结果，请基于各引擎原始返回谨慎判断。")
    return "\n".join(lines)

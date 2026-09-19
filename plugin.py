import asyncio
import html
import ipaddress
import re
import socket
import time
import unicodedata
from pathlib import Path
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
from .PicImageSearch.engines.lenso import Lenso
from .PicImageSearch.engines.copyseeker import Copyseeker
from .PicImageSearch.engines.ehentai import EHentai
from .ReverseSearcher.model import BaseSearchModel


plugin = NekroPlugin(
    name="以图搜图",
    module_name="nekro_picsearcher",
    description="基于 PicImageSearch 的多引擎图片反向搜索工具",
    author="XGGM",
    version="1.3.0",
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
    enable_anime_trace: bool = Field(default=True, title="启用 AnimeTrace")
    enable_tracemoe: bool = Field(default=False, title="启用 TraceMoe")
    enable_iqdb: bool = Field(default=False, title="启用 IQDB")
    enable_lenso: bool = Field(default=False, title="启用 Lenso")
    enable_copyseeker: bool = Field(default=False, title="启用 Copyseeker")
    enable_saucenao: bool = Field(default=True, title="启用 SauceNAO")
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
        title="候选结果整理数量",
        description="从所有搜索结果中取前 N 条可访问结果用于网页抓取与证据整理",
    )
    webpage_fetch_timeout: int = Field(
        default=12,
        title="网页抓取超时秒数",
        description="抓取搜索结果来源网页时的请求超时时间",
    )
    webpage_content_chars: int = Field(
        default=3500,
        title="网页正文最大字符数",
        description="每个网页结果最多返回的清洗正文字符数",
    )
    webpage_max_bytes: int = Field(
        default=1048576,
        title="网页抓取最大字节数",
        description="限制单个来源网页最多读取的响应字节数，避免超大页面占用上下文和内存",
    )
    yandex_cookies: str = Field(
        default="",
        title="Yandex Cookie",
        description="可选，Yandex 反爬时填写浏览器 Cookie 以提升稳定性",
        json_schema_extra=ExtraField(is_secret=True, required=False).model_dump(),
    )
    allow_third_party_image_host: bool = Field(
        default=True,
        title="允许第三方临时图床",
        description="本地图搜 Yandex 时允许上传到临时图床；关闭后仅支持公网图片 URL",
    )
    webpage_cache_ttl: int = Field(
        default=900,
        title="网页内容缓存秒数",
        description="相同来源网页在缓存有效期内复用抓取结果，减少重复请求；设为 0 可关闭",
    )
    search_timeout: int = Field(
        default=30,
        title="搜图请求超时秒数",
        description="单个搜索引擎请求的超时时间，避免某个引擎拖慢全部结果",
    )
    allow_private_webpage_fetch: bool = Field(
        default=False,
        title="允许抓取私网地址",
        description="默认禁止抓取 localhost、内网 IP 等私有地址，防止搜索结果链接触发内网访问",
    )
    fetch_webpage_for_top: int = Field(
        default=3,
        title="仅对前 N 条抓取网页",
        description="仅对前 N 条候选结果抓取来源网页，后面结果只保留搜图原始信息与基础证据，可提升响应速度",
    )
    fast_mode: bool = Field(
        default=False,
        title="快速模式",
        description="跳过所有来源网页抓取，仅返回搜图原始结果与基础文本整理，响应最快",
    )
    webpage_prefer_proxy: bool = Field(
        default=True,
        title="优先使用代理",
        description="网页抓取优先使用代理（配置了 DEFAULT_PROXY 时）",
    )
    webpage_try_fallback: bool = Field(
        default=True,
        title="失败时自动切换代理策略重试",
        description="网页抓取失败时自动切换代理策略再试一次（优先用代理→失败试不用代理，或反过来）",
    )


config: PicSearcherConfig = plugin.get_config(PicSearcherConfig)

_PYQUERY_READY = False
_WEBPAGE_CACHE: Dict[str, Tuple[float, str]] = {}

_ENGINE_ALIASES = {
    "animetrace": "anime_trace",
    "anime": "anime_trace",
    "a": "anime_trace",
    "saucenao": "saucenao",
    "sauce": "saucenao",
    "s": "saucenao",
    "ehentai": "ehentai",
    "e-hentai": "ehentai",
    "e": "ehentai",
    "yandex": "yandex",
    "ydx": "yandex",
    "y": "yandex",
    "google": "google",
    "baidu": "baidu",
    "bd": "baidu",
}

_INTENT_ENGINE_WEIGHTS = {
    "anime_trace": {
        "角色": 10,
        "人物": 8,
        "是谁": 8,
        "动漫": 8,
        "动画": 6,
        "番剧": 6,
        "cos": 6,
    },
    "saucenao": {
        "出处": 10,
        "来源": 9,
        "画师": 10,
        "作者": 8,
        "pixiv": 8,
        "pid": 7,
        "原图": 6,
    },
    "ehentai": {"本子": 10, "同人": 8, "汉化": 8, "漫画": 6, "r18": 8},
    "yandex": {"相似": 10, "类似": 8, "找图": 5, "照片": 4},
    "google": {"找原图": 10, "综合": 8, "商品": 6, "新闻": 6, "原图": 5},
}


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
    return plugin.get_config(PicSearcherConfig)


def _normalize_engine_name(engine: str) -> str:
    normalized = _clean_text(engine).lower().replace(" ", "_")
    return _ENGINE_ALIASES.get(normalized, normalized)


def _infer_engine_from_intent(intent: str) -> Tuple[Optional[str], int]:
    text = _clean_text(intent).lower()
    if not text:
        return None, 0
    scores: Dict[str, int] = {}
    for engine, keywords in _INTENT_ENGINE_WEIGHTS.items():
        score = sum(weight for keyword, weight in keywords.items() if keyword.lower() in text)
        if score:
            scores[engine] = score
    if not scores:
        return None, 0
    engine, score = max(scores.items(), key=lambda item: item[1])
    return engine, score


async def _get_recent_image_context(ctx: AgentCtx) -> Tuple[Optional[str], str]:
    """从最近用户消息中提取图片和意图文本。

    AgentCtx 本身不携带原始消息对象，因此从已持久化的聊天记录读取最近窗口。
    只读取当前频道且跳过机器人消息，避免把机器人刚发送的结果图片误当成输入。
    """
    try:
        from nekro_agent.models.db_chat_message import DBChatMessage
        from nekro_agent.schemas.chat_message import ChatMessageSegmentImage
        from nekro_agent.tools.path_convertor import convert_filename_to_access_path

        messages = await (
            DBChatMessage.filter(chat_key=ctx.chat_key)
            .order_by("-send_timestamp")
            .limit(12)
        )
    except Exception as exc:
        core.logger.debug(f"读取最近消息图片失败: {exc}")
        return None, ""

    intent_parts: List[str] = []
    for message in messages:
        if str(message.sender_id) == "-1":
            continue
        content_text = _clean_text(getattr(message, "content_text", ""))
        if content_text:
            intent_parts.append(content_text[:240])
        try:
            segments = message.parse_content_data()
        except Exception:
            continue
        for segment in segments:
            if not isinstance(segment, ChatMessageSegmentImage):
                continue
            candidates: List[Path] = []
            if segment.local_path:
                candidates.append(Path(segment.local_path))
            if segment.file_name:
                candidates.append(convert_filename_to_access_path(segment.file_name, ctx.chat_key))
            for candidate in candidates:
                try:
                    if candidate.exists():
                        return str(ctx.fs.forward_file(candidate)), " ".join(reversed(intent_parts))
                except (OSError, ValueError):
                    continue
            remote_url = _clean_text(segment.remote_url or "")
            if _is_url(remote_url):
                return remote_url, " ".join(reversed(intent_parts))
    return None, " ".join(reversed(intent_parts))


def _validate_image_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("图片地址必须是有效的 http/https URL")
    if _is_private_host(parsed.hostname):
        raise ValueError("已阻止抓取私网或本机图片地址")


def _engine_selection(
    cfg: PicSearcherConfig,
    requested_engine: Optional[str],
    intent: str,
    context_text: str,
) -> Tuple[List[str], str]:
    enabled = [
        name
        for name, is_enabled in [
            ("ascii2d", cfg.enable_ascii2d),
            ("anime_trace", cfg.enable_anime_trace),
            ("tracemoe", cfg.enable_tracemoe),
            ("yandex", cfg.enable_yandex),
            ("google", cfg.enable_google),
            ("iqdb", cfg.enable_iqdb),
            ("baidu", cfg.enable_baidu),
            ("bing", cfg.enable_bing),
            ("lenso", cfg.enable_lenso),
            ("copyseeker", cfg.enable_copyseeker),
            ("saucenao", cfg.enable_saucenao),
            ("tineye", cfg.enable_tineye),
            ("ehentai", cfg.enable_ehentai),
            ("exhentai", cfg.enable_exhentai),
        ]
        if is_enabled
    ]
    if requested_engine:
        selected = _normalize_engine_name(requested_engine)
        if selected not in enabled:
            raise ValueError(f"引擎 {requested_engine} 未启用或不存在")
        return [selected], f"指定引擎：{selected}"

    inferred, score = _infer_engine_from_intent(intent or context_text)
    if inferred and inferred in enabled and score >= 7:
        return [inferred], f"按意图优先使用：{inferred}（匹配分 {score}）"
    return enabled, "多引擎并行模式"


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


def _safe_output_text(value: Any, max_len: int = 0) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = text.replace("|", " / ").replace("`", "'").replace("\t", " ")
    cleaned_chars: List[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if category in {"Cc", "Cs", "So"}:
            continue
        cleaned_chars.append(ch)
    text = re.sub(r"\s+", " ", "".join(cleaned_chars)).strip()
    if max_len > 0:
        text = text[:max_len]
    return text


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _domain_matches(domain: str, patterns: List[str]) -> bool:
    normalized = (domain or "").lower().strip(".")
    if not normalized:
        return False
    for pattern in patterns:
        target = (pattern or "").lower().strip(".")
        if not target:
            continue
        if normalized == target or normalized.endswith("." + target):
            return True
    return False


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


def _build_page_evidence(url: str, item: Dict[str, Any], page_text: str) -> Tuple[List[str], str]:
    domain = _domain_of(url)
    path = urlparse(url).path.lower()
    title = _clean_text(
        item.get("title")
        or item.get("source")
        or item.get("site_name")
        or item.get("author")
        or ""
    )
    text = _clean_text(page_text)
    evidence: List[str] = []
    if domain:
        evidence.append(f"域名 {domain}")
    if path and path != "/":
        evidence.append(f"路径 {path[:120]}")
    if title:
        evidence.append(f"标题字段 {title[:120]}")
    if text:
        evidence.append(f"正文前缀 {text[:160]}")
    else:
        evidence.append("无网页正文")
    return evidence, "；".join(evidence)


def _primary_item_label(item: Dict[str, Any], fallback: str = "") -> str:
    return _safe_output_text(
        item.get("title")
        or item.get("source")
        or item.get("site_name")
        or item.get("author")
        or fallback
    )


def _split_candidate_text(text: str) -> List[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    candidates = [cleaned]
    for sep in [" | ", " / ", " - ", " — ", "：", ":"]:
        if sep in cleaned:
            candidates.extend(part.strip() for part in cleaned.split(sep))
    unique: List[str] = []
    seen: set[str] = set()
    for value in candidates:
        normalized = value.strip("[](){}<>\"'` ")
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _is_meaningful_candidate(text: str) -> bool:
    candidate = _clean_text(text).strip("[](){}<>\"'` ")
    if not candidate:
        return False
    if len(candidate) < 2 or len(candidate) > 80:
        return False
    if _is_url(candidate):
        return False
    lower = candidate.lower()
    blocked = {
        "official",
        "official site",
        "official website",
        "artist",
        "author",
        "source",
        "image",
        "images",
        "result",
        "results",
        "similar image",
        "similar images",
        "untitled",
        "unknown",
        "pixiv",
        "fanbox",
        "artstation",
        "deviantart",
        "twitter",
        "x",
    }
    if lower in blocked:
        return False
    if re.fullmatch(r"[\W_]+", candidate):
        return False
    if sum(ch.isalnum() for ch in candidate) < 2:
        return False
    return True


def _extract_tag_values(item: Dict[str, Any], prefixes: List[str]) -> List[str]:
    values: List[str] = []
    for raw_tag in item.get("tags", []) or []:
        tag = _clean_text(raw_tag)
        lower_tag = tag.lower()
        for prefix in prefixes:
            prefix_lower = prefix.lower()
            if lower_tag.startswith(prefix_lower):
                payload = tag[len(prefix):].lstrip(" :：")
                for part in _split_candidate_text(payload):
                    if _is_meaningful_candidate(part):
                        values.append(part)
    return values


def _dedupe_keep_order(values: List[str]) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _collect_entry_entities(entry: Dict[str, Any]) -> Dict[str, List[str]]:
    item = entry["item"]
    engine = str(entry.get("engine") or "")
    domain = _domain_of(entry["url"])
    entities: Dict[str, List[str]] = {
        "characters": [],
        "works": [],
        "authors": [],
        "sites": [],
        "objects": [],
    }

    if domain:
        entities["sites"].append(domain)
    for site_value in [item.get("site_name")]:
        for candidate in _split_candidate_text(str(site_value or "")):
            if _is_meaningful_candidate(candidate) and len(candidate) <= 40:
                entities["sites"].append(candidate)

    for candidate in _split_candidate_text(str(item.get("author") or "")):
        if _is_meaningful_candidate(candidate):
            entities["authors"].append(candidate)

    title_text = str(item.get("title") or "")
    source_text = str(item.get("source") or "")

    # 根据引擎返回的常见字段进行基础分类
    if engine == "anime_trace":
        for candidate in _split_candidate_text(title_text):
            if _is_meaningful_candidate(candidate):
                entities["characters"].append(candidate)
        for candidate in _split_candidate_text(source_text):
            if _is_meaningful_candidate(candidate):
                entities["works"].append(candidate)
    elif engine == "tracemoe":
        for candidate in _split_candidate_text(title_text):
            if _is_meaningful_candidate(candidate):
                entities["works"].append(candidate)
    else:
        # 通用引擎的 source 字段经常混入站点名或分发页文案，容易误导判断；
        # 因此这里只保留标题中的主题片段，把 source 留给原始证据区供 AI 自行比对。
        for candidate in _split_candidate_text(title_text):
            if _is_meaningful_candidate(candidate):
                entities["objects"].append(candidate)

    # 显式标签提取
    entities["authors"].extend(_extract_tag_values(item, ["artist:", "creator:", "author:", "group:", "circle:"]))
    entities["characters"].extend(_extract_tag_values(item, ["character:"]))
    entities["works"].extend(_extract_tag_values(item, ["parody:", "series:", "copyright:"]))

    return {
        key: _dedupe_keep_order(values)
        for key, values in entities.items()
    }


def _collect_result_evidence(engine: str, item: Dict[str, Any]) -> List[str]:
    reasons: List[str] = [f"检索引擎 {engine}"]
    similarity = item.get("similarity")
    if similarity is not None:
        reasons.append(f"相似度 {similarity}")
    if item.get("title"):
        reasons.append("含标题")
    if item.get("source") or item.get("site_name") or item.get("author") or item.get("index_name"):
        reasons.append("含来源信息")
    if item.get("size"):
        reasons.append(f"尺寸 {item.get('size')}")
    if item.get("url"):
        domain = _domain_of(str(item.get("url")))
        if domain:
            reasons.append(f"来源域名 {domain}")
    return reasons


def _flatten_search_results(search_results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_no_url: set[str] = set()
    order = 0
    for result in search_results:
        engine = str(result.get("engine") or "")
        for item_index, item in enumerate(result.get("items", []), 1):
            url = str(item.get("url") or item.get("video") or item.get("image") or "").strip()
            if _is_url(url):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            else:
                # AnimeTrace 等识别型引擎通常只返回角色/作品文本，没有网页 URL；
                # 这类结果仍然是高价值证据，不能因为无法抓网页而被聚合器丢弃。
                identity = "|".join(
                    _clean_text(str(item.get(key) or ""))
                    for key in ("title", "source", "author", "site_name", "index_name")
                )
                if not identity or identity in seen_no_url:
                    continue
                seen_no_url.add(identity)
            order += 1
            flattened.append(
                {
                    "order": order,
                    "engine": engine,
                    "item_index": item_index,
                    "item": item,
                    "url": url,
                    "fetchable": bool(url),
                    "reasons": _collect_result_evidence(engine, item),
                }
            )
    return flattened[: max(0, limit)]


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


async def _try_fetch_once(url: str, use_proxy: bool, cfg: PicSearcherConfig) -> str:
    _validate_fetch_url(url, cfg)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    proxies = _get_proxy()
    client_kwargs: Dict[str, Any] = {
        "timeout": cfg.webpage_fetch_timeout,
        "follow_redirects": True,
        "headers": headers,
    }
    if use_proxy and proxies:
        client_kwargs["proxy"] = proxies
    try:
        client = httpx.AsyncClient(**client_kwargs)
    except TypeError:
        if use_proxy and proxies:
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


async def _fetch_webpage_text(url: str, cfg: PicSearcherConfig) -> str:
    cache_ttl = max(0, int(cfg.webpage_cache_ttl))
    if cache_ttl > 0:
        cached = _WEBPAGE_CACHE.get(url)
        if cached and time.time() - cached[0] <= cache_ttl:
            return cached[1]
        if cached:
            _WEBPAGE_CACHE.pop(url, None)

    proxies = _get_proxy()
    prefer_proxy = bool(cfg.webpage_prefer_proxy) and bool(proxies)
    try_fallback = bool(cfg.webpage_try_fallback) and bool(proxies)

    first_use_proxy = prefer_proxy
    first_exc = None

    try:
        text = await _try_fetch_once(url, first_use_proxy, cfg)
        if cache_ttl > 0:
            if len(_WEBPAGE_CACHE) >= 256:
                oldest = min(_WEBPAGE_CACHE, key=lambda key: _WEBPAGE_CACHE[key][0])
                _WEBPAGE_CACHE.pop(oldest, None)
            _WEBPAGE_CACHE[url] = (time.time(), text)
        return text
    except Exception as ex:
        first_exc = ex
        if not try_fallback:
            raise

    try:
        text = await _try_fetch_once(url, not first_use_proxy, cfg)
        if cache_ttl > 0:
            if len(_WEBPAGE_CACHE) >= 256:
                oldest = min(_WEBPAGE_CACHE, key=lambda key: _WEBPAGE_CACHE[key][0])
                _WEBPAGE_CACHE.pop(oldest, None)
            _WEBPAGE_CACHE[url] = (time.time(), text)
        return text
    except Exception as second_exc:
        raise first_exc or second_exc


async def _enrich_ranked_result(entry: Dict[str, Any], cfg: PicSearcherConfig) -> Dict[str, Any]:
    try:
        text = await _fetch_webpage_text(entry["url"], cfg)
        if not text:
            value = {
                "page_summary": "网页不是可读取正文内容或正文为空",
                "page_error": "empty",
                "page_text_for_type": "",
            }
            page_evidence, page_evidence_summary = _build_page_evidence(entry["url"], entry["item"], "")
            return {
                **entry,
                **value,
                "page_evidence": page_evidence,
                "page_evidence_summary": page_evidence_summary,
            }
        value = {
            "page_summary": text[: max(500, cfg.webpage_content_chars)],
            "page_error": "",
            "page_text_for_type": text[:2000],
        }
        page_evidence, page_evidence_summary = _build_page_evidence(entry["url"], entry["item"], text)
        return {
            **entry,
            **value,
            "page_evidence": page_evidence,
            "page_evidence_summary": page_evidence_summary,
        }
    except Exception as ex:
        page_evidence, page_evidence_summary = _build_page_evidence(entry["url"], entry["item"], "")
        return {
            **entry,
            "page_summary": "",
            "page_error": str(ex),
            "page_evidence": page_evidence,
            "page_evidence_summary": page_evidence_summary,
        }


async def _enrich_without_webpage(
    entry: Dict[str, Any],
    skipped: bool = False,
) -> Dict[str, Any]:
    reason = "未抓取网页" if skipped else "结果不含可抓取网页 URL"
    return {
        **entry,
        "page_summary": "",
        "page_error": "skipped for performance" if skipped else "no source url",
        "page_evidence": [reason],
        "page_evidence_summary": reason,
    }


async def _enrich_trusted_results(
    search_results: List[Dict[str, Any]],
    cfg: PicSearcherConfig,
    fetch_webpage_for_top: Optional[int] = None,
    fast_mode: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    use_fast_mode = fast_mode if fast_mode is not None else bool(cfg.fast_mode)
    use_fetch_top = fetch_webpage_for_top if fetch_webpage_for_top is not None else int(cfg.fetch_webpage_for_top)
    use_fetch_top = max(0, use_fetch_top)

    flattened = _flatten_search_results(search_results, cfg.trusted_results)
    if not flattened:
        return []

    if use_fast_mode:
        use_fetch_top = 0

    enriched_full: List[Optional[Dict[str, Any]]] = []
    if use_fetch_top > 0:
        enriched_top = await asyncio.gather(
            *[
                _enrich_ranked_result(entry, cfg) if entry.get("fetchable") else _enrich_without_webpage(entry)
                for entry in flattened[:use_fetch_top]
            ]
        )
        enriched_full.extend(enriched_top)

    for entry in flattened[use_fetch_top:]:
        enriched_full.append(await _enrich_without_webpage(entry, skipped=True))

    finalized: List[Dict[str, Any]] = []
    for entry in enriched_full:
        entities = _collect_entry_entities(entry)
        finalized.append(
            {
                **entry,
                "entities": entities,
            }
        )
    finalized.sort(key=lambda entry: int(entry.get("order", 0)))
    return finalized


def _add_candidate_occurrence(
    bucket: Dict[str, Dict[str, Any]],
    text: str,
    evidence: str,
) -> None:
    candidate = _safe_output_text(text)
    if not _is_meaningful_candidate(candidate):
        return
    key = candidate.lower()
    if key not in bucket:
        bucket[key] = {"text": candidate, "count": 0, "evidence": []}
    bucket[key]["count"] += 1
    safe_evidence = _safe_output_text(evidence, 120)
    if safe_evidence and safe_evidence not in bucket[key]["evidence"]:
        bucket[key]["evidence"].append(safe_evidence)


def _format_bucket_with_evidence(
    bucket: Dict[str, Dict[str, Any]],
    limit: int,
    fallback: str,
) -> str:
    if not bucket:
        return fallback
    ordered = sorted(bucket.values(), key=lambda item: (-int(item["count"]), item["text"]))
    parts: List[str] = []
    for item in ordered[:limit]:
        evidences = " / ".join(item["evidence"][:2]) if item.get("evidence") else ""
        if evidences:
            parts.append(f"{item['text']} (出现 {item['count']} 次; 证据: {evidences})")
        else:
            parts.append(f"{item['text']} (出现 {item['count']} 次)")
    return "；".join(parts)


def _build_candidate_snapshot(trusted: List[Dict[str, Any]]) -> List[str]:
    if not trusted:
        return ["暂无可供整理的候选线索。"]
    character_bucket: Dict[str, Dict[str, Any]] = {}
    work_bucket: Dict[str, Dict[str, Any]] = {}
    author_bucket: Dict[str, Dict[str, Any]] = {}
    object_bucket: Dict[str, Dict[str, Any]] = {}
    site_bucket: Dict[str, Dict[str, Any]] = {}
    for entry in trusted[: max(3, min(6, len(trusted)))]:
        title = _primary_item_label(entry["item"], entry["url"])
        entities = entry.get("entities") or _collect_entry_entities(entry)
        for value in entities.get("characters", []):
            _add_candidate_occurrence(character_bucket, value, title)
        for value in entities.get("works", []):
            _add_candidate_occurrence(work_bucket, value, title)
        for value in entities.get("authors", []):
            _add_candidate_occurrence(author_bucket, value, title)
        for value in entities.get("objects", []):
            _add_candidate_occurrence(object_bucket, value, title)
        for value in entities.get("sites", []):
            _add_candidate_occurrence(site_bucket, value, title)
    best = trusted[0]
    lines = [
        f"人物/角色线索（仅显式角色字段）：{_format_bucket_with_evidence(character_bucket, 4, '暂无稳定角色文本')}",
        f"作品/出处线索（仅显式作品字段）：{_format_bucket_with_evidence(work_bucket, 4, '暂无稳定作品或出处文本')}",
        f"作者/画师线索：{_format_bucket_with_evidence(author_bucket, 4, '暂无稳定作者文本')}",
        f"标题/主题文本片段（可能混有页面标题，不可直接当结论）：{_format_bucket_with_evidence(object_bucket, 4, '暂无可直接归纳的主题文本')}",
        f"站点分布：{_format_bucket_with_evidence(site_bucket, 6, _domain_of(best['url']) or '暂无明确站点')}",
    ]
    return lines


def _build_data_usage_notes(trusted: List[Dict[str, Any]]) -> List[str]:
    if not trusted:
        return ["本次没有形成可读候选，需结合原图视觉内容自行判断。"]
    notes = [
        "候选线索汇总只是文本片段聚合，不能直接当作最终身份、出处或作者结论。",
        "标题/来源字段可能混入站点名、转载页标题、商品页文案或搜索页文案，必须与网页正文、页面证据和画面细节交叉核对。",
        "候选结果数据区按引擎展示原始命中，不代表事实正确率或可信度排序。",
    ]
    if len(trusted) == 1:
        notes.append("当前仅有一个候选结果，证据覆盖面有限。")
    else:
        notes.append("存在多个候选结果时，应重点比较原图细节、网页正文、页面证据和作者/作品文本是否互相印证。")
    if any(entry.get("page_error") == "skipped for performance" for entry in trusted):
        notes.append("部分候选未抓取网页正文；若需要更强证据，可提高 `fetch_webpage_for_top` 后重试。")
    return notes


def _build_duplicate_url_hints(search_results: List[Dict[str, Any]], limit: int = 6) -> List[str]:
    url_hits: Dict[str, Dict[str, Any]] = {}
    for result in search_results:
        engine = str(result.get("engine") or "")
        for item in result.get("items", []):
            url = str(item.get("url") or item.get("video") or item.get("image") or "").strip()
            if not _is_url(url):
                continue
            if url not in url_hits:
                url_hits[url] = {"engines": [], "title": _primary_item_label(item, url)}
            if engine and engine not in url_hits[url]["engines"]:
                url_hits[url]["engines"].append(engine)
    duplicated = [
        (url, value)
        for url, value in url_hits.items()
        if len(value["engines"]) > 1
    ]
    duplicated.sort(key=lambda item: (-len(item[1]["engines"]), item[0]))
    hints: List[str] = []
    for url, value in duplicated[: max(0, limit)]:
        title = value["title"] or url
        engines = "、".join(value["engines"])
        hints.append(f"{title} <- {engines} -> {url}")
    return hints


def _build_enriched_lookup(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        url = str(entry.get("url") or "").strip()
        if _is_url(url):
            lookup[url] = entry
        engine = str(entry.get("engine") or "")
        item_index = entry.get("item_index")
        if engine and item_index is not None:
            lookup[f"{engine}:{item_index}"] = entry
    return lookup


def _build_result_risk_flags(entry: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    if entry.get("page_error") == "skipped for performance":
        flags.append("未抓网页")
    elif entry.get("page_error") == "no source url":
        flags.append("无来源网页 URL")
    elif entry.get("page_error") == "empty":
        flags.append("网页正文为空")
    elif entry.get("page_error"):
        flags.append("网页抓取失败")
    item = entry.get("item") or {}
    title = _clean_text(item.get("title") or "")
    if not title or title.lower() in {"unknown", "untitled"}:
        flags.append("标题弱")
    return flags


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


def _build_exhentai_cookie(cfg: PicSearcherConfig) -> str:
    pairs = {
        "ipb_member_id": cfg.exhentai_cookie_member_id,
        "ipb_pass_hash": cfg.exhentai_cookie_pass_hash,
        "igneous": cfg.exhentai_cookie_igneous,
    }
    return "; ".join(f"{key}={value}" for key, value in pairs.items() if value)


async def _do_reference_search(
    engine: str,
    cfg: PicSearcherConfig,
    top_k: int,
    file_arg: Dict[str, Any],
    proxy: Optional[str],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """使用参考插件的统一请求/解析链路执行核心引擎。"""
    opts = dict(options or {})
    normalized = engine.lower()
    reference_name = normalized
    default_params: Dict[str, Dict[str, Any]] = {}
    if reference_name == "yandex":
        default_params["yandex"] = {
            "cookies": cfg.yandex_cookies or None,
            "max_results": top_k,
            "use_ru_fallback": opts.pop("use_ru_fallback", True),
        }
    elif reference_name == "saucenao":
        default_params["saucenao"] = {"api_key": cfg.saucenao_api_key or None}
    elif reference_name in {"ehentai", "exhentai"}:
        default_params[reference_name] = {
            "is_ex": reference_name == "exhentai",
            "cookies": _build_exhentai_cookie(cfg) or None,
        }

    model = BaseSearchModel(
        proxies=proxy,
        timeout=max(1, cfg.search_timeout),
        default_params=default_params,
        allow_third_party_image_host=cfg.allow_third_party_image_host,
    )
    response = await model.search(reference_name, **file_arg, **opts)
    raw_items = list(getattr(response, "raw", []) or [])
    items: List[Dict[str, Any]] = []
    if reference_name in {"animetrace", "anime_trace"}:
        for raw_item in raw_items[: max(1, top_k)]:
            for character in getattr(raw_item, "characters", []) or []:
                items.append(
                    {
                        "title": getattr(character, "name", ""),
                        "source": getattr(character, "work", ""),
                        "url": "",
                        "thumbnail": "",
                        "ai_detected": getattr(response, "ai", None),
                    }
                )
    elif reference_name == "saucenao":
        items = [
            {
                "title": getattr(item, "title", ""),
                "author": getattr(item, "author", ""),
                "author_url": getattr(item, "author_url", ""),
                "url": getattr(item, "url", ""),
                "thumbnail": getattr(item, "thumbnail", ""),
                "similarity": getattr(item, "similarity", None),
                "index_name": getattr(item, "index_name", ""),
                "source": getattr(item, "source", ""),
            }
            for item in raw_items[: max(1, top_k)]
        ]
    elif reference_name == "yandex":
        items = [
            {
                "title": getattr(item, "title", ""),
                "url": getattr(item, "url", ""),
                "thumbnail": getattr(item, "thumbnail", ""),
                "source": getattr(item, "source", ""),
                "author": getattr(item, "author", ""),
                "content": getattr(item, "other_info", ""),
            }
            for item in raw_items[: max(1, top_k)]
        ]
    else:
        items = [
            {
                "title": getattr(item, "title", ""),
                "url": getattr(item, "url", ""),
                "thumbnail": getattr(item, "thumbnail", ""),
                "type": getattr(item, "type", ""),
                "date": getattr(item, "date", ""),
                "pages": getattr(item, "pages", ""),
                "tags": getattr(item, "tags", []),
            }
            for item in raw_items[: max(1, top_k)]
        ]
    output_engine = "anime_trace" if reference_name in {"animetrace", "anime_trace"} else normalized
    return {"engine": output_engine, "url": getattr(response, "url", ""), "items": items}


@plugin.mount_prompt_inject_method("picsearcher_image_source_analysis")
async def picsearcher_prompt_inject(_ctx: AgentCtx) -> str:
    return (
        "【核心规则】识别图片时必须优先调用搜图工具：\n"
        "1. 只要用户让你识别图片、解释图片内容、确认图片里的人物是谁、来自哪里、出自什么作品、作者/画师是谁、哪些网站能找到这张图，或要求考据图片来源、判断是否被搬运/误传时，**必须先调用 `reverse_search`（或兼容名称 `render_multi_engine_search`）进行反向搜图，绝不能只用视觉模态回答**。\n"
        "2. 即使你认为自己“看出来了”，也要调用搜图工具交叉验证，避免幻觉；但**不要把工具输出里的顺序、字段或文本候选直接当作最终结论**。\n"
        "3. 这个工具只负责提供候选结果、网页摘录、实体文本、页面证据和客观状态；**调用完成后你必须继续分析，并直接给用户输出结论、证据和不确定性，不能停在工具原始结果或候选列表上**。\n"
        "4. 如果多个搜图结果不一致，要主动比较网页正文、域名、标题、作者、相似度与画面细节，并明确说明不确定性；如果证据不足，也要明确说“暂时无法确定”以及差在哪些证据。\n"
        "5. 如果你在 `/exec` 或 Python 脚本场景中调用此工具，绝对不要把自然语言结果、Markdown 表格、emoji 或项目符号直接写进 Python 代码；如需展示结果，只能在代码里用字符串包裹后 `print(...)`，或在脚本结束后再用自然语言回答。\n"
        "【工具说明】\n"
        "- `reverse_search` / `render_multi_engine_search` 会自动取当前消息图片，按意图选择引擎或执行多引擎反向搜图，并整理候选结果、网页摘录、实体文本与页面证据，供你继续分析。\n"
        "- 可选参数（按需使用）：\n"
        "  - `fast_mode=True`：跳过网页抓取，响应最快，适合只需要快速知道角色名/游戏名/作品名的场景；\n"
        "  - `fetch_webpage_for_top=N`：只对前 N 条抓网页，后面保留搜图信息以平衡速度与信息量；\n"
        "  - 一般默认不用传额外参数，直接 `reverse_search()` 即可；需要显式指定图片时传 `image=...`。"
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

    # 核心引擎优先走参考插件的统一请求/解析实现；其余引擎继续兼容旧适配器。
    if e in {"anime_trace", "animetrace", "anime", "saucenao", "nao", "yandex", "ydx", "y"}:
        reference_engine = {
            "anime": "animetrace",
            "anime_trace": "animetrace",
            "nao": "saucenao",
            "ydx": "yandex",
            "y": "yandex",
        }.get(e, e)
        return await _do_reference_search(reference_engine, cfg, top_k, file_arg, proxy, options)
    if e in {"ehentai", "exhentai", "e-hentai"}:
        reference_engine = "exhentai" if e == "exhentai" else "ehentai"
        return await _do_reference_search(reference_engine, cfg, top_k, file_arg, proxy, options)
    if e in {"ascii2d", "asc"}:
        bovw = options.get("bovw", cfg.ascii2d_bovw)
        _ensure_pyquery()
        cli = Ascii2D(bovw=bovw, proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "ascii2d", "url": resp.url, "items": [_fmt_ascii2d(i) for i in items]}
    if e in {"tracemoe", "trace"}:
        mute = bool(options.get("mute", False))
        size = options.get("size")
        cli = TraceMoe(mute=mute, size=size, proxies=proxy, timeout=max(1, cfg.search_timeout))
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
        cli = Yandex(proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "yandex", "url": resp.url, "items": [_fmt_yandex(i) for i in items]}
    if e in {"google", "ggl"}:
        _ensure_pyquery()
        cli = Google(proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "google", "url": resp.url, "items": [_fmt_google(i) for i in items]}
    if e in {"iqdb"}:
        _ensure_pyquery()
        is_3d = bool(options.get("is_3d", False))
        force_gray = bool(options.get("force_gray", False))
        cli = Iqdb(is_3d=is_3d, proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(force_gray=force_gray, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "iqdb", "url": resp.url, "items": [_fmt_iqdb(i) for i in items]}
    if e in {"baidu", "bd"}:
        _ensure_pyquery()
        cli = BaiDu(proxies=proxy, timeout=max(1, cfg.search_timeout))
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
        cli = SauceNAO(api_key=api_key, proxies=proxy, timeout=max(1, cfg.search_timeout), **saucenao_kwargs)
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "saucenao", "url": resp.url, "items": [_fmt_saucenao(i) for i in items]}
    if e in {"bing"}:
        cli = Bing(proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(**file_arg)
        pool = getattr(resp, "pages_including", []) or getattr(resp, "visual_search", [])
        items = pool[: max(1, top_k)]
        return {"engine": "bing", "url": resp.url, "items": [_fmt_bing_pages(i) for i in items]}
    if e in {"lenso"}:
        search_type = options.get("search_type", "") if options else ""
        sort_type = options.get("sort_type", "SMART") if options else "SMART"
        cli = Lenso(proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(search_type=search_type, sort_type=sort_type, **file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "lenso", "url": resp.url, "items": [_fmt_lenso(i) for i in items]}
    if e in {"copyseeker", "copy"}:
        cli = Copyseeker(proxies=proxy, timeout=max(1, cfg.search_timeout))
        resp = await cli.search(**file_arg)
        items = [*resp.raw][: max(1, top_k)]
        return {"engine": "copyseeker", "url": resp.url, "items": [_fmt_copyseeker(i) for i in items]}
    if e in {"anime_trace", "animetrace", "anime"}:
        cli = AnimeTrace(
            is_multi=options.get("is_multi"),
            ai_detect=options.get("ai_detect"),
            proxies=proxy,
            timeout=max(1, cfg.search_timeout),
        )
        model_name = options.get("model")
        base64_data = options.get("base64")
        if base64_data:
            resp = await cli.search(base64=base64_data, model=model_name)
        else:
            resp = await cli.search(model=model_name, **file_arg)
        anime_items: List[Dict[str, Any]] = []
        for raw_item in [*resp.raw][: max(1, top_k)]:
            characters = getattr(raw_item, "characters", None) or []
            for character in characters:
                anime_items.append(
                    {
                        "title": getattr(character, "name", ""),
                        "source": getattr(character, "work", ""),
                        "url": "",
                        "thumbnail": "",
                        "ai_detected": getattr(resp, "ai", None),
                    }
                )
        return {"engine": "anime_trace", "url": resp.url, "items": anime_items[: max(1, top_k * 3)]}
    if e in {"tineye", "tine"}:
        cli = Tineye(proxies=proxy, timeout=max(1, cfg.search_timeout))
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
            timeout=max(1, cfg.search_timeout),
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
    description="【优先调用】识别图片时先调用此工具。它会返回反向搜索结果、网页证据与候选线索；拿到结果后必须继续综合分析并直接回答用户，不能停在候选列表。",
)
async def render_multi_engine_search(
    _ctx: AgentCtx,
    image: Optional[str] = None,
    engine: Optional[str] = None,
    intent: Optional[str] = None,
    top_k: Optional[int] = None,
    options: Optional[Dict[str, Any]] = None,
    fast_mode: Optional[bool] = None,
    fetch_webpage_for_top: Optional[int] = None,
    **kwargs: Any,
) -> str:
    """
    在多个引擎上同时进行反向搜索，整理候选结果并抓取网页正文，
    给大模型提供原始结果和证据，由大模型自行完成最终推理。

    Args:
        _ctx (AgentCtx): 调用上下文（自动注入）
        image (str | None): 图片地址（http/https URL 或 AI 沙盒文件路径）。省略时自动使用最近一条用户图片或引用图片。
        engine (str | None): 指定单个引擎，可用 `animetrace`、`saucenao`、`ehentai`、`yandex` 等别名；省略时按意图路由或多引擎并行。
        intent (str | None): 搜索意图，如“找角色”“找出处/画师”“找相似图”，用于选择更合适的引擎。
        top_k (int | None): 每个引擎返回的最大条数，默认使用配置项 max_results
        options (dict | None): 引擎可选项，示例
            - ascii2d: {"bovw": true}
            - tracemoe: {"key": "...", "anilist_id": 123, "chinese_title": true, "cut_borders": true, "mute": false, "size": "m"}
            - iqdb: {"is_3d": false, "force_gray": false}
            - saucenao: {"api_key": "...", "numres": 5, "hide": 0, "minsim": 30, "output_type": 2}
            - anime_trace: {"model": "anime", "is_multi": 1, "ai_detect": 1, "base64": "..."}
            - ehentai: {"covers": false, "similar": true, "exp": false}
            - tineye: {"show_unavailable_domains": false, "domain": "", "sort": "score", "order": "desc", "tags": ""}
        fast_mode (bool | None): 是否开启快速模式，跳过所有来源网页抓取，仅返回搜图原始结果和基础证据整理
        fetch_webpage_for_top (int | None): 仅对前 N 条候选结果抓取来源网页，后面结果保留搜图信息以提升速度

    Returns:
        str: 多引擎聚合结果、候选文本、页面证据和网页摘录。

    Example:
        # 在聊天频道中使用 /exec（无需传入 _ctx）
        /exec render_multi_engine_search(
            image="https://example.com/image.jpg",
            top_k=2,
            options={"bovw": true}
        )
        # 快速模式（最快，只不抓网页）
        /exec render_multi_engine_search(
            image="https://example.com/image.jpg",
            fast_mode=True
        )
        # 只对前 2 条抓网页，后面跳过
        /exec render_multi_engine_search(
            image="https://example.com/image.jpg",
            fetch_webpage_for_top=2
        )
    """
    # 兼容旧版通过 kwargs 传参的调用方式。
    image = image or kwargs.pop("image", None)
    engine = engine or kwargs.pop("engine", None)
    intent = intent or kwargs.pop("intent", None)
    if top_k is None:
        top_k = kwargs.pop("top_k", None)
    if options is None:
        options = kwargs.pop("options", None)
    if fast_mode is None:
        fast_mode = kwargs.pop("fast_mode", None)
    if fetch_webpage_for_top is None:
        fetch_webpage_for_top = kwargs.pop("fetch_webpage_for_top", None)
    cfg = _get_cfg()
    recent_context_text = ""
    if not image:
        image, recent_context_text = await _get_recent_image_context(_ctx)
    if not image:
        raise ValueError("未找到图片，请在消息中附图，或传入 image 图片地址/沙盒路径")
    if _is_url(image):
        await asyncio.to_thread(_validate_image_url, image)
    if top_k is None:
        k = int(cfg.max_results)
    else:
        try:
            k = int(top_k)
        except (TypeError, ValueError):
            raise ValueError("top_k 必须是大于等于 1 的整数")
        if k < 1:
            raise ValueError("top_k 必须是大于等于 1 的整数")
    engs, selection_info = _engine_selection(cfg, engine, intent or "", recent_context_text)
    if not engs:
        raise ValueError("未启用任何引擎，请在配置中开启至少一个引擎")
    file_arg = _build_file_arg(image, _ctx)
    proxy = _get_proxy()
    pyquery_engines = {"ascii2d", "yandex", "google", "iqdb", "baidu", "ehentai", "exhentai"}
    enabled_pyquery_engines = [e for e in engs if e in pyquery_engines]
    pyquery_init_error = ""
    if enabled_pyquery_engines:
        try:
            _ensure_pyquery()
        except Exception as ex:
            pyquery_init_error = _safe_output_text(str(ex), 240)
            engs = [e for e in engs if e not in pyquery_engines]
    search_results: List[Dict[str, Any]] = []
    engine_errors: list[str] = []
    if pyquery_init_error:
        engine_errors.extend([f"[{engine}] error: {pyquery_init_error}" for engine in enabled_pyquery_engines])
    use_fast_mode = fast_mode if fast_mode is not None else bool(cfg.fast_mode)
    use_fetch_top = fetch_webpage_for_top if fetch_webpage_for_top is not None else int(cfg.fetch_webpage_for_top)
    use_fetch_top = max(0, use_fetch_top)
    if use_fast_mode:
        use_fetch_top = 0
    mode_info = []
    if use_fast_mode:
        mode_info.append("快速模式：已跳过所有来源网页抓取，仅返回搜图结果与基础证据，响应最快")
    else:
        mode_info.append(f"常规模式：仅对前 {use_fetch_top} 条候选结果抓取来源网页，后面结果保留搜图信息以提升速度")
    lines: list[str] = [
        f"Image: {image}",
        f"引擎策略：{selection_info}",
        "效率说明：" + "；".join(mode_info),
        "阅读提示：上方候选线索汇总是为了帮助快速定位方向，详细网页证据与原始命中结果在后文。",
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
        else:
            engine_errors.append(f"[{e}] error: {_safe_output_text(outcome['error'], 240)}")
    trusted = await _enrich_trusted_results(search_results, cfg, fetch_webpage_for_top=use_fetch_top, fast_mode=use_fast_mode)
    if trusted:
        consensus_hints = _detect_result_consensus(trusted)
        duplicate_url_hints = _build_duplicate_url_hints(search_results)
        enriched_lookup = _build_enriched_lookup(trusted)
        candidate_snapshot = _build_candidate_snapshot(trusted)
        usage_notes = _build_data_usage_notes(trusted)
        lines.append("\n[候选线索汇总]")
        for structured_line in candidate_snapshot:
            lines.append(structured_line)
        lines.append("\n[数据使用提示]")
        for note in usage_notes:
            lines.append(note)
        lines.append("\n[候选结果数据]")
        lines.append("说明：本区按引擎分组展示原始命中结果，不做跨引擎全局合并；全局层面仅额外提示重复 URL。")
        lines.append(f"搜索概况：已启用 {len(engs)} 个引擎，成功返回 {len(search_results)} 个引擎结果，整理出 {len(trusted)} 条可读证据。")
        lines.append("跨结果提示：" + "；".join(consensus_hints))
        if duplicate_url_hints:
            lines.append("重复 URL 提示：" + "；".join(duplicate_url_hints))
        if engine_errors:
            lines.append("引擎异常：" + "；".join(engine_errors))
        for result in search_results:
            engine = _safe_output_text(result.get("engine", ""), 60)
            search_url = _safe_output_text(result.get("url", ""), 240)
            lines.append(f"\n[{engine}]")
            if search_url:
                lines.append(f"引擎入口：{search_url}")
            items = result.get("items", [])
            if not items:
                lines.append("无原始命中结果")
                continue
            for idx, item in enumerate(items, 1):
                item_url = str(item.get("url") or item.get("video") or item.get("image") or "").strip()
                title = _safe_output_text(item.get("title") or item.get("source") or item.get("site_name") or item.get("author") or "", 200)
                parts: List[str] = []
                if title:
                    parts.append(title)
                sim = item.get("similarity")
                if sim is not None:
                    parts.append(f"相似度 {sim}")
                size = _safe_output_text(item.get("size") or "", 80)
                if size:
                    parts.append(f"尺寸 {size}")
                src = _safe_output_text(item.get("author") or item.get("site_name") or item.get("source") or "", 120)
                if src:
                    parts.append(f"来源字段 {src}")
                line = f"{idx}. " + " | ".join(parts) if parts else f"{idx}."
                if item_url:
                    line += f" -> {item_url}"
                lines.append(line)
                entry = enriched_lookup.get(item_url) if _is_url(item_url) else enriched_lookup.get(f"{engine}:{idx}")
                if not entry:
                    lines.append("页面证据：未整理 | 说明：未纳入网页整理范围")
                    continue
                risk_flags = _build_result_risk_flags(entry)
                lines.append(
                    f"页面证据：{_safe_output_text('；'.join((entry.get('page_evidence') or [])[:8]), 320)} | 摘要："
                    f"{_safe_output_text(entry.get('page_evidence_summary', '无页面证据'), 320)}"
                )
                if risk_flags:
                    lines.append(f"风险提示：{_safe_output_text('；'.join(risk_flags), 240)}")
                entities = entry.get("entities") or {}
                if entities.get("characters"):
                    lines.append(f"人物/角色文本：{_safe_output_text('；'.join(entities['characters'][:4]), 240)}")
                if entities.get("works"):
                    lines.append(f"作品/出处文本：{_safe_output_text('；'.join(entities['works'][:4]), 240)}")
                if entities.get("authors"):
                    lines.append(f"作者/画师文本：{_safe_output_text('；'.join(entities['authors'][:4]), 240)}")
                if entities.get("objects"):
                    lines.append(f"内容主题文本：{_safe_output_text('；'.join(entities['objects'][:4]), 240)}")
                lines.append(f"结果元数据：{_safe_output_text('；'.join(entry['reasons']), 320)}")
                if entry.get("page_summary"):
                    lines.append(f"网页正文：{_safe_output_text(entry['page_summary'], cfg.webpage_content_chars)}")
                if entry.get("page_error") and entry.get("page_error") != "empty":
                    page_error = entry.get("page_error")
                    if page_error == "no source url":
                        lines.append("网页处理提示：该识别结果不含来源网页 URL，已保留文本证据")
                    else:
                        lines.append(f"网页处理提示：{_safe_output_text(page_error, 240)}")
                elif entry.get("page_error"):
                    lines.append(f"网页内容获取失败：{_safe_output_text(entry['page_error'], 240)}")
    else:
        lines.append("\n[候选结果数据]")
        lines.append("未找到可访问 URL 的候选结果，以下按引擎回退展示原始返回，供 AI 继续自行判断。")
        for result in search_results:
            engine = _safe_output_text(result.get("engine", ""), 60)
            search_url = _safe_output_text(result.get("url", ""), 240)
            lines.append(f"\n[{engine}]")
            if search_url:
                lines.append(f"引擎入口：{search_url}")
            items = result.get("items", [])
            if not items:
                lines.append("无原始命中结果")
                continue
            for idx, item in enumerate(items, 1):
                parts: List[str] = []
                title = _safe_output_text(item.get("title") or item.get("source") or item.get("site_name") or "", 160)
                if title:
                    parts.append(title)
                sim = item.get("similarity")
                if sim is not None:
                    parts.append(f"相似度 {sim}")
                size = _safe_output_text(item.get("size") or "", 80)
                if size:
                    parts.append(f"尺寸 {size}")
                src = _safe_output_text(item.get("author") or item.get("site_name") or item.get("source") or "", 120)
                if src:
                    parts.append(f"来源字段 {src}")
                item_url = str(item.get("url") or item.get("video") or item.get("image") or "").strip()
                line = f"{idx}. " + " | ".join(parts) if parts else f"{idx}."
                if item_url:
                    line += f" -> {item_url}"
                lines.append(line)
        if engine_errors:
            lines.append("\n[引擎异常]")
            lines.extend(engine_errors)
    lines.append("\n[下一步回答要求]")
    lines.append("请基于以上证据直接完成对用户的回答，不要只复述候选列表。")
    lines.append("先给出当前最可能的身份/出处/作者判断，再说明关键证据来自哪些引擎、页面或重复 URL。")
    lines.append("如果证据冲突或不足，请明确保留不确定性，并说明还缺什么证据。")
    return "\n".join(lines)


@plugin.mount_sandbox_method(
    method_type=SandboxMethodType.AGENT,
    name="reverse_search",
    description="以图搜图入口：自动从当前消息取图，并按‘找角色/找出处/找相似图’等意图选择引擎。",
)
async def reverse_search(
    _ctx: AgentCtx,
    image: Optional[str] = None,
    engine: Optional[str] = None,
    intent: Optional[str] = None,
    top_k: Optional[int] = None,
    options: Optional[Dict[str, Any]] = None,
    fast_mode: Optional[bool] = None,
    fetch_webpage_for_top: Optional[int] = None,
    **kwargs: Any,
) -> str:
    """以图搜图的简洁入口，功能与 `render_multi_engine_search` 相同。

    Args:
        image (str | None): 图片 URL 或 AI 沙盒路径；省略时自动使用当前消息图片。
        engine (str | None): 可选，指定 `animetrace`、`saucenao`、`yandex` 等引擎。
        intent (str | None): 可选，说明“找角色”“找出处/画师”“找相似图”等目标。
        top_k (int | None): 每个引擎返回的最大结果数。
        options (dict | None): 引擎专属参数。
        fast_mode (bool | None): 是否跳过来源网页抓取。
        fetch_webpage_for_top (int | None): 仅抓取前 N 条候选网页。

    Returns:
        str: 搜图候选、证据和网页摘录，供后续回答使用。
    """
    return await render_multi_engine_search(
        _ctx,
        image=image,
        engine=engine,
        intent=intent,
        top_k=top_k,
        options=options,
        fast_mode=fast_mode,
        fetch_webpage_for_top=fetch_webpage_for_top,
        **kwargs,
    )

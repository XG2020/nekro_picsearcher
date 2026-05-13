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
    fetch_webpage_for_top: int = Field(
        default=3,
        title="仅对前 N 条抓取网页",
        description="仅对前 N 条高可信结果抓取来源网页，后面结果只保留搜图信息与结构化结论，可大幅提升响应速度",
    )
    fast_mode: bool = Field(
        default=False,
        title="快速模式",
        description="跳过所有来源网页抓取，仅进行搜图、实体提取与结构化结论，响应最快",
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
        return "电商商品页", "页面更像商品销售或店铺展示，通常不是原始来源", -16.0
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


def _primary_item_label(item: Dict[str, Any], fallback: str = "") -> str:
    return _clean_text(
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


def _entry_text_corpus(entry: Dict[str, Any]) -> str:
    item = entry["item"]
    return _clean_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("source") or ""),
                str(item.get("site_name") or ""),
                str(item.get("author") or ""),
                str(entry.get("page_summary") or ""),
                str(entry.get("url") or ""),
            ]
        )
    ).lower()


def _is_game_domain(domain: str) -> bool:
    if not domain:
        return False
    game_domains = [
        "steamcommunity.com",
        "steampowered.com",
        "fandom.com",
        "gamewith.jp",
        "gamewith.net",
        "appmedia.jp",
        "4gamer.net",
        "famitsu.com",
        "ign.com",
        "gamespot.com",
        "polygon.com",
        "kotaku.com",
        "rockpapershotgun.com",
        "pcgamer.com",
        "gamer.com.tw",
        "vgtime.com",
        "3dmgame.com",
        "ali213.net",
        "gamersky.com",
        "bilibili.com",
        "hoyolab.com",
        "miyoushe.com",
        "game8.jp",
        "siliconera.com",
        "destructoid.com",
        "gameinformer.com",
        "edge-online.com",
        "playstation.com",
        "xbox.com",
        "nintendo.com",
        "epicgames.com",
        "gog.com",
        "itch.io",
        "nexusmods.com",
        "reddit.com",
        "twitter.com",
        "x.com",
    ]
    return any(token in domain for token in game_domains)


def _has_game_signals(entry: Dict[str, Any]) -> bool:
    text = _entry_text_corpus(entry)
    domain = _domain_of(entry.get("url", ""))
    if _is_game_domain(domain):
        return True
    if not text:
        return False
    game_keywords = [
        "game",
        "gaming",
        "gameplay",
        "video game",
        "visual novel",
        "rpg",
        "mmo",
        "mmorpg",
        "gacha",
        "boss",
        "npc",
        "quest",
        "mission",
        "walkthrough",
        "steam",
        "playstation",
        "xbox",
        "nintendo",
        "手游",
        "端游",
        "网游",
        "单机",
        "游戏",
        "实机",
        "过场",
        "剧情",
        "攻略",
        "角色",
        "立绘",
        "皮肤",
        "武器",
        "boss",
        "截图",
    ]
    screenshot_keywords = [
        "screenshot",
        "in-game",
        "in game",
        "cutscene",
        "hud",
        "ui",
        "battle pass",
        "quest",
        "mission",
        "游戏截图",
        "实机截图",
        "过场截图",
        "战斗界面",
        "角色界面",
        "菜单界面",
        "任务界面",
    ]
    return any(keyword in text for keyword in [*game_keywords, *screenshot_keywords])


def _split_game_title_parts(text: str) -> Tuple[List[str], List[str]]:
    cleaned = _clean_text(text)
    if not cleaned:
        return [], []
    separators = [" | ", " - ", " — ", " – ", " : ", "：", " / ", " × "]
    character_candidates: List[str] = []
    work_candidates: List[str] = []
    for sep in separators:
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep)]
            if len(parts) >= 2:
                for i in range(len(parts)):
                    part = parts[i]
                    if not _is_meaningful_candidate(part):
                        continue
                    if i == 0:
                        character_candidates.append(part)
                    else:
                        work_candidates.append(part)
    return _dedupe_keep_order(character_candidates), _dedupe_keep_order(work_candidates)


def _collect_entry_entities(entry: Dict[str, Any]) -> Dict[str, List[str]]:
    item = entry["item"]
    engine = str(entry.get("engine") or "")
    domain = _domain_of(entry["url"])
    source_type = str(entry.get("source_type") or "")
    has_game_signals = _has_game_signals(entry)
    is_game_domain = _is_game_domain(domain)
    entities: Dict[str, List[str]] = {
        "characters": [],
        "works": [],
        "authors": [],
        "sites": [],
        "objects": [],
    }

    if domain:
        entities["sites"].append(domain)
    for site_value in [item.get("site_name"), item.get("source")]:
        for candidate in _split_candidate_text(str(site_value or "")):
            if _is_meaningful_candidate(candidate) and len(candidate) <= 40:
                entities["sites"].append(candidate)

    for candidate in _split_candidate_text(str(item.get("author") or "")):
        if _is_meaningful_candidate(candidate):
            entities["authors"].append(candidate)

    if engine == "anime_trace":
        for candidate in _split_candidate_text(str(item.get("title") or "")):
            if _is_meaningful_candidate(candidate):
                entities["characters"].append(candidate)
        for candidate in _split_candidate_text(str(item.get("source") or "")):
            if _is_meaningful_candidate(candidate):
                entities["works"].append(candidate)
    elif engine == "tracemoe":
        for candidate in _split_candidate_text(str(item.get("title") or "")):
            if _is_meaningful_candidate(candidate):
                entities["works"].append(candidate)
    else:
        for candidate in _split_candidate_text(str(item.get("source") or "")):
            if _is_meaningful_candidate(candidate):
                entities["works"].append(candidate)

    if has_game_signals or is_game_domain:
        title_text = str(item.get("title") or "")
        chars_from_split, works_from_split = _split_game_title_parts(title_text)
        entities["characters"].extend(chars_from_split)
        entities["works"].extend(works_from_split)
        for candidate in _split_candidate_text(title_text):
            if _is_meaningful_candidate(candidate):
                entities["characters"].append(candidate)
                entities["works"].append(candidate)

    if item.get("title") and source_type in {"电商商品页", "官方/权威页", "聚合转载页", "资讯/资料页"}:
        for candidate in _split_candidate_text(str(item.get("title") or "")):
            if _is_meaningful_candidate(candidate):
                entities["objects"].append(candidate)

    entities["authors"].extend(_extract_tag_values(item, ["artist:", "creator:", "author:", "group:", "circle:"]))
    entities["characters"].extend(_extract_tag_values(item, ["character:"]))
    entities["works"].extend(_extract_tag_values(item, ["parody:", "series:", "copyright:"]))

    return {
        key: _dedupe_keep_order(values)
        for key, values in entities.items()
    }


def _infer_image_kind(entry: Dict[str, Any]) -> Tuple[str, float]:
    engine = str(entry.get("engine") or "")
    source_type = str(entry.get("source_type") or "")
    domain = _domain_of(entry["url"])
    text = _entry_text_corpus(entry)
    if engine == "tracemoe":
        return "动画截图", 16.0
    if engine == "anime_trace":
        return "二次元角色图", 16.0
    if any(keyword in text for keyword in ["screenshot", "in-game", "in game", "cutscene", "hud", "ui", "游戏截图", "实机截图", "过场截图", "战斗界面", "角色界面", "任务界面"]):
        return "游戏截图", 16.0
    if _has_game_signals(entry):
        return "游戏角色图或游戏宣传图", 14.0
    if source_type == "电商商品页":
        return "商品或周边图", 14.0
    if source_type == "官方/权威页":
        return "官方宣传图或资料图", 12.0
    if source_type == "原始发布页":
        if any(token in domain for token in ["pixiv.net", "artstation.com", "deviantart.com", "fanbox.cc", "skeb.jp"]):
            return "插画或创作图", 14.0
        return "原始发布内容", 10.0
    if source_type == "社交媒体页":
        return "社交媒体发布图", 8.0
    if source_type == "聚合转载页":
        return "转载或索引图", 6.0
    return "未识别", 0.0


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
        ("identity_bonus", "身份识别增强"),
        ("source_bonus", "出处识别增强"),
    ]
    parts = [
        f"{label} {score_detail[key]:.1f}"
        for key, label in ordered_keys
        if score_detail.get(key)
    ]
    if score_detail.get("identity_total") is not None:
        parts.append(f"身份分 {score_detail['identity_total']:.1f}")
    if score_detail.get("source_total") is not None:
        parts.append(f"出处分 {score_detail['source_total']:.1f}")
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
    proxies = _get_proxy()
    prefer_proxy = bool(cfg.webpage_prefer_proxy) and bool(proxies)
    try_fallback = bool(cfg.webpage_try_fallback) and bool(proxies)

    first_use_proxy = prefer_proxy
    first_exc = None

    try:
        return await _try_fetch_once(url, first_use_proxy, cfg)
    except Exception as ex:
        first_exc = ex
        if not try_fallback:
            raise

    try:
        return await _try_fetch_once(url, not first_use_proxy, cfg)
    except Exception as second_exc:
        raise first_exc or second_exc


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


async def _enrich_trusted_results(
    search_results: List[Dict[str, Any]],
    cfg: PicSearcherConfig,
    fetch_webpage_for_top: Optional[int] = None,
    fast_mode: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    use_fast_mode = fast_mode if fast_mode is not None else bool(cfg.fast_mode)
    use_fetch_top = fetch_webpage_for_top if fetch_webpage_for_top is not None else int(cfg.fetch_webpage_for_top)
    use_fetch_top = max(0, use_fetch_top)

    ranked = _flatten_ranked_results(search_results, cfg.trusted_results)
    if not ranked:
        return []

    if use_fast_mode:
        use_fetch_top = 0

    enriched_full: List[Optional[Dict[str, Any]]] = []
    if use_fetch_top > 0:
        enriched_top = await asyncio.gather(*[_enrich_ranked_result(entry, cfg) for entry in ranked[:use_fetch_top]])
        enriched_full.extend(enriched_top)

    for entry in ranked[use_fetch_top:]:
        enriched_full.append(
            {
                **entry,
                "page_summary": "",
                "page_error": "skipped for performance",
                "cache_hit": "false",
                "source_type": "未识别",
                "source_type_reason": "未抓取网页",
                "source_type_weight": 0.0,
            }
        )

    domain_count: Dict[str, int] = {}
    title_count: Dict[str, int] = {}
    for entry in enriched_full:
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
    for entry in enriched_full:
        score_detail = dict(entry.get("score_detail") or {})
        score_detail["source_type"] = float(entry.get("source_type_weight") or 0.0)
        webpage_bonus = 0.0
        if entry.get("page_summary") and entry.get("page_error") not in {"skipped for performance", "empty"}:
            webpage_bonus = 12.0
        elif entry.get("page_summary"):
            webpage_bonus = 6.0
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
        base_total = sum(value for key, value in score_detail.items() if key not in {"total", "identity_total", "source_total", "identity_bonus", "source_bonus"})
        entities = _collect_entry_entities(entry)
        identity_bonus = 0.0
        source_bonus = 0.0
        domain = _domain_of(entry["url"])
        is_game_domain = _is_game_domain(domain)
        if entities["characters"]:
            identity_bonus += 16.0
        if entities["works"]:
            identity_bonus += 12.0
        if _has_game_signals(entry):
            identity_bonus += 10.0
        if is_game_domain:
            identity_bonus += 14.0
            source_bonus += 12.0
        if entities["authors"]:
            identity_bonus += 6.0
            source_bonus += 10.0
        if entities["objects"]:
            identity_bonus += 8.0
        if entry.get("engine") in {"anime_trace", "tracemoe"}:
            identity_bonus += 10.0
        if entry.get("source_type") in {"原始发布页", "官方/权威页"}:
            source_bonus += 16.0
        elif entry.get("source_type") == "社交媒体页":
            source_bonus += 6.0
        elif entry.get("source_type") == "聚合转载页":
            source_bonus -= 6.0
        elif entry.get("source_type") == "电商商品页":
            source_bonus -= 12.0
        if entry["item"].get("author_url"):
            source_bonus += 6.0
        path = urlparse(entry["url"]).path.lower()
        if re.search(r"/(artworks|illust|status|posts?|gallery|works?)/[\w-]+", path):
            source_bonus += 6.0
        if re.search(r"/\d{4,}", path):
            source_bonus += 4.0
        score_detail["identity_bonus"] = identity_bonus
        score_detail["source_bonus"] = source_bonus
        identity_total = base_total + identity_bonus
        source_total = base_total + source_bonus
        overall_total = identity_total * 0.6 + source_total * 0.4
        score_detail["identity_total"] = identity_total
        score_detail["source_total"] = source_total
        score_detail["total"] = overall_total
        finalized.append(
            {
                **entry,
                "score": overall_total,
                "identity_score": identity_total,
                "source_score": source_total,
                "entities": entities,
                "score_detail": score_detail,
            }
        )
    finalized.sort(key=lambda entry: entry["score"], reverse=True)
    return finalized


def _build_final_assessment(trusted: List[Dict[str, Any]]) -> List[str]:
    if not trusted:
        return ["暂无可形成结论的可信来源。"]
    best = trusted[0]
    best_identity = max(trusted, key=lambda entry: float(entry.get("identity_score") or entry["score"]))
    best_source = max(trusted, key=lambda entry: float(entry.get("source_score") or entry["score"]))
    best_title = _primary_item_label(best["item"], best["url"])
    best_identity_title = _primary_item_label(best_identity["item"], best_identity["url"])
    best_source_title = _primary_item_label(best_source["item"], best_source["url"])
    lines = [
        f"综合最优候选：{best_title}",
        f"综合最优链接：{best['url']}",
        f"身份识别最佳候选：{best_identity_title}（身份分 {float(best_identity.get('identity_score') or best_identity['score']):.1f}）",
        f"出处识别最佳候选：{best_source_title}（出处分 {float(best_source.get('source_score') or best_source['score']):.1f}）",
        f"综合最优来源类型：{best.get('source_type', '未识别')}（{best.get('source_type_reason', '无')}）",
        f"综合最优得分：{best['score']:.1f}（{_score_detail_text(best.get('score_detail') or {})}）",
    ]
    if len(trusted) > 1:
        second = trusted[1]
        second_title = _primary_item_label(second["item"], second["url"])
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


def _add_weighted_candidate(
    bucket: Dict[str, Dict[str, Any]],
    text: str,
    weight: float,
    evidence: str,
) -> None:
    candidate = _clean_text(text)
    if not _is_meaningful_candidate(candidate):
        return
    key = candidate.lower()
    if key not in bucket:
        bucket[key] = {"text": candidate, "score": 0.0, "evidence": []}
    bucket[key]["score"] += weight
    if evidence and evidence not in bucket[key]["evidence"]:
        bucket[key]["evidence"].append(evidence)


def _top_bucket_text(bucket: Dict[str, Dict[str, Any]], limit: int, fallback: str) -> str:
    if not bucket:
        return fallback
    ordered = sorted(bucket.values(), key=lambda item: item["score"], reverse=True)
    return "；".join(item["text"] for item in ordered[:limit])


def _build_structured_summary(trusted: List[Dict[str, Any]]) -> List[str]:
    if not trusted:
        return ["暂无可供结构化提取的可信候选。"]
    identity_ranked = sorted(trusted, key=lambda entry: float(entry.get("identity_score") or entry["score"]), reverse=True)
    source_ranked = sorted(trusted, key=lambda entry: float(entry.get("source_score") or entry["score"]), reverse=True)
    best_identity = identity_ranked[0]
    best_source = source_ranked[0]
    kind_bucket: Dict[str, Dict[str, Any]] = {}
    character_bucket: Dict[str, Dict[str, Any]] = {}
    work_bucket: Dict[str, Dict[str, Any]] = {}
    author_bucket: Dict[str, Dict[str, Any]] = {}
    object_bucket: Dict[str, Dict[str, Any]] = {}
    site_bucket: Dict[str, Dict[str, Any]] = {}
    for entry in trusted[: max(3, min(6, len(trusted)))]:
        identity_weight = max(1.0, float(entry.get("identity_score") or entry["score"]))
        source_weight = max(1.0, float(entry.get("source_score") or entry["score"]))
        title = _primary_item_label(entry["item"], entry["url"])
        entities = entry.get("entities") or _collect_entry_entities(entry)
        for value in entities.get("characters", []):
            _add_weighted_candidate(character_bucket, value, identity_weight, title)
        for value in entities.get("works", []):
            _add_weighted_candidate(work_bucket, value, identity_weight, title)
        for value in entities.get("authors", []):
            _add_weighted_candidate(author_bucket, value, source_weight, title)
        for value in entities.get("objects", []):
            _add_weighted_candidate(object_bucket, value, identity_weight, title)
        for value in entities.get("sites", []):
            _add_weighted_candidate(site_bucket, value, source_weight, title)
        image_kind, kind_weight = _infer_image_kind(entry)
        if image_kind != "未识别":
            _add_weighted_candidate(kind_bucket, image_kind, kind_weight + identity_weight * 0.2, title)

    identity_delta = float(best_identity.get("identity_score") or best_identity["score"]) - float(identity_ranked[1].get("identity_score") or identity_ranked[1]["score"]) if len(identity_ranked) > 1 else 999.0
    source_delta = float(best_source.get("source_score") or best_source["score"]) - float(source_ranked[1].get("source_score") or source_ranked[1]["score"]) if len(source_ranked) > 1 else 999.0
    if identity_delta >= 15 and source_delta >= 15:
        uncertainty = "身份和出处候选都比较集中，可优先采用首选结论。"
    elif identity_delta >= 10 or source_delta >= 10:
        uncertainty = "已有较强候选，但仍建议核对角色名、作品名或作者名是否一致。"
    else:
        uncertainty = "前几名结果接近，请保留不确定性，避免把单一候选当作最终事实。"

    best_source_label = _primary_item_label(best_source["item"], best_source["url"])
    lines = [
        f"图片类型：{_top_bucket_text(kind_bucket, 2, '暂未明确')}",
        f"人物/角色候选：{_top_bucket_text(character_bucket, 3, '暂无明确人物或角色名，可结合作品候选继续判断')}",
        f"作品/出处/游戏候选：{_top_bucket_text(work_bucket, 3, '暂无稳定作品名、出处名或游戏名')}",
        f"作者/画师候选：{_top_bucket_text(author_bucket, 3, '暂无明确作者或画师名')}",
        f"图片内容候选：{_top_bucket_text(object_bucket, 3, '暂无可直接归纳的物体/主题名称')}",
        f"最可能原始来源：{best_source_label} -> {best_source['url']}",
        f"可找到的网站：{_top_bucket_text(site_bucket, 6, _domain_of(best_source['url']) or '暂无明确站点')}",
        f"判断提示：{uncertainty}",
    ]
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
        "【核心规则】识别图片时必须优先调用搜图工具：\n"
        "1. 只要用户让你识别图片、解释图片内容、确认图片里的人物是谁、来自哪里、出自什么作品、作者/画师是谁、哪些网站能找到这张图，或要求考据图片来源、判断是否被搬运/误传时，**必须先调用 `render_multi_engine_search` 进行反向搜图，绝不能只用视觉模态回答**。\n"
        "2. 即使你认为自己“看出来了”，也要调用搜图工具交叉验证，避免幻觉，优先以搜图的结构化结论为依据。\n"
        "3. 回答时优先使用搜图结果里的「人物/角色候选」「作品/出处/游戏候选」「作者/画师候选」「最可能原始来源」这些结构化字段，不要自己编造。\n"
        "4. 如果多个搜图结果不一致，要优先看身份分、出处分更高的结果，并且明确说明不确定性。\n"
        "【工具说明】\n"
        "- `render_multi_engine_search` 会在多个图片搜索引擎上同时反向搜图，自动筛选高可信结果，对部分来源网页抓取正文，最终返回结构化识别结论。\n"
        "- 可选参数（按需使用）：\n"
        "  - `fast_mode=True`：跳过网页抓取，响应最快，适合只需要快速知道角色名/游戏名/作品名的场景；\n"
        "  - `fetch_webpage_for_top=N`：只对前 N 条抓网页，后面保留搜图信息以平衡速度与信息量；\n"
        "  - 一般默认不用传额外参数，直接 `render_multi_engine_search(image=...)` 即可。"
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
    description="【优先调用】识别图片时必须先调用此工具！反向搜索图片来源，筛选可信结果并抓取来源网页正文，提供结构化识别结论：人物/角色候选、作品/出处/游戏候选、作者/画师候选、图片类型、最可能原始来源、可找到的网站。",
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
        fast_mode (bool | None): 是否开启快速模式，跳过所有来源网页抓取，仅返回搜图、实体提取与结构化结论
        fetch_webpage_for_top (int | None): 仅对前 N 条高可信结果抓取来源网页，后面结果保留搜图信息以提升速度

    Returns:
        str: 多引擎聚合结果、可信度排序和高可信来源网页正文。

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
    image: Optional[str] = kwargs.pop("image", None) or (args[0] if len(args) > 0 else None)
    top_k: Optional[int] = kwargs.pop("top_k", None)
    options: Optional[Dict[str, Any]] = kwargs.pop("options", None)
    fast_mode: Optional[bool] = kwargs.pop("fast_mode", None)
    fetch_webpage_for_top: Optional[int] = kwargs.pop("fetch_webpage_for_top", None)
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
    raw_result_lines: list[str] = []
    engine_errors: list[str] = []
    use_fast_mode = fast_mode if fast_mode is not None else bool(cfg.fast_mode)
    use_fetch_top = fetch_webpage_for_top if fetch_webpage_for_top is not None else int(cfg.fetch_webpage_for_top)
    use_fetch_top = max(0, use_fetch_top)
    if use_fast_mode:
        use_fetch_top = 0
    mode_info = []
    if use_fast_mode:
        mode_info.append("快速模式：已跳过所有来源网页抓取，仅返回搜图、实体提取与结构化结论，响应最快")
    else:
        mode_info.append(f"常规模式：仅对前 {use_fetch_top} 条高可信结果抓取来源网页，后面结果保留搜图信息以提升速度")
    lines: list[str] = [
        f"Image: {image}",
        "效率说明：" + "；".join(mode_info),
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
            raw_result_lines.append(f"\n[{res.get('engine','')}] {res.get('url','')}".strip())
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
                raw_result_lines.append(line)
                idx += 1
        else:
            engine_errors.append(f"[{e}] error: {outcome['error']}")
    trusted = await _enrich_trusted_results(search_results, cfg, fetch_webpage_for_top=use_fetch_top, fast_mode=use_fast_mode)
    if trusted:
        consensus_hints = _detect_result_consensus(trusted)
        structured_summary = _build_structured_summary(trusted)
        final_assessment = _build_final_assessment(trusted)
        lines.append("\n[结构化识别结论]")
        for structured_line in structured_summary:
            lines.append(structured_line)
        lines.append("\n[最终研判摘要]")
        for assessment_line in final_assessment:
            lines.append(assessment_line)
        lines.append("\n[筛选后结果]")
        lines.append("说明：综合排序同时考虑身份识别和出处识别；身份分更关注人物/作品/物体识别，出处分更关注原始来源、作者与可信发布页。")
        lines.append(f"搜索概况：已启用 {len(engs)} 个引擎，成功返回 {len(search_results)} 个引擎结果，筛出 {len(trusted)} 条可信候选。")
        lines.append("共识/冲突提示：" + "；".join(consensus_hints))
        if engine_errors:
            lines.append("引擎异常：" + "；".join(engine_errors))
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
            if entry.get("entities"):
                entities = entry["entities"]
                if entities.get("characters"):
                    lines.append(f"人物线索：{'；'.join(entities['characters'][:3])}")
                if entities.get("works"):
                    lines.append(f"作品线索：{'；'.join(entities['works'][:3])}")
                if entities.get("authors"):
                    lines.append(f"作者线索：{'；'.join(entities['authors'][:3])}")
            lines.append(f"可信依据：{'；'.join(entry['reasons'])}")
            lines.append(f"评分明细：{_score_detail_text(entry.get('score_detail') or {})}")
            if entry.get("page_summary"):
                lines.append(f"网页正文：{entry['page_summary']}")
            if entry.get("page_error") and entry.get("page_error") != "empty":
                lines.append(f"网页处理提示：{entry['page_error']}")
            elif entry.get("page_error"):
                lines.append(f"网页内容获取失败：{entry['page_error']}")
    else:
        lines.append("\n[筛选后结果]")
        lines.append("未找到可访问 URL 的可信结果，以下回退展示各引擎原始返回，供你继续人工判断。")
        if raw_result_lines:
            lines.extend(raw_result_lines)
        if engine_errors:
            lines.append("\n[引擎异常]")
            lines.extend(engine_errors)
    return "\n".join(lines)

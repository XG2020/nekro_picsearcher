from typing import Any, Dict, List, Optional, Union

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
    version="1.0.0",
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
    try:
        from nekro_agent.services.plugin.packages import dynamic_import_pkg
        dynamic_import_pkg("pyquery", "pyquery")
        dynamic_import_pkg("lxml", "lxml")
        dynamic_import_pkg("cssselect", "cssselect")
        import pyquery  # noqa: F401
        import lxml  # noqa: F401
    except Exception as ee:
        raise RuntimeError(
            f"缺少依赖 pyquery/lxml：{ee}. 请确保 dynamic_import_pkg 可用，或手动执行 pip install pyquery lxml cssselect"
        )


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


async def _do_search_single(
    engine: str,
    image: str,
    ctx: AgentCtx,
    cfg: PicSearcherConfig,
    top_k: int,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    e = engine.lower()
    if options is None:
        options = {}
    use_url = _is_url(image)
    file_arg: Dict[str, Any]
    if use_url:
        file_arg = {"url": image}
    else:
        host_path = ctx.fs.get_file(image)
        file_arg = {"file": str(host_path)}
    proxy = _get_proxy()

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

@plugin.mount_sandbox_method(
    method_type=SandboxMethodType.AGENT,
    name="render_multi_engine_search",
    description="并行在多个引擎中检索图片来源，并以可读文本展示聚合结果。",
)
async def render_multi_engine_search(
    _ctx: AgentCtx,
    *args: Any,
    **kwargs: Any,
) -> str:
    """
    在多个引擎上同时进行反向搜索，并以文本内容展示图片信息，给大模型提供图片参考。

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
        str: 多引擎聚合的可读文本，每个引擎独立分段展示 Top-K 项。

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
    lines: list[str] = [f"Image: {image}"]
    for e in engs:
        try:
            res = await _do_search_single(e, image, _ctx, cfg, k, options)
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
        except Exception as ex:
            lines.append(f"\n[{e}] error: {ex}")
    return "\n".join(lines)

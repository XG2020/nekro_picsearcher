# nekro_picsearcher 图片搜源插件

基于 PicImageSearch 的多引擎图片反向搜索插件，支持在多个引擎中并行检索并聚合结果，重点优化了**识别图片人物、出处、画师、哪些网站能找到**这几类场景，并支持高效模式以平衡速度与信息量。

## 功能概览
- 多引擎并行搜索与聚合输出
- 结构化识别结论：直接给出人物/角色候选、作品/出处/游戏候选、作者/画师候选、图片类型、最可能原始来源、可找到的网站
- 双评分系统：身份分（更关注识别角色/作品/物体）与出处分（更关注原始来源、作者与可信发布页）
- 游戏场景优化：专门识别游戏人物、游戏截图，并对游戏相关站点（wiki/攻略站/官方社区等）增强
- 通过配置项控制每个引擎启用或关闭
- 效率控制：仅对前 N 条高可信结果抓取网页，或完全跳过网页抓取以提升响应速度
- 网页抓取优化：更完整的浏览器模拟请求头、支持优先用代理、失败时自动切换代理策略重试
- 支持 Ascii2D、AnimeTrace、TraceMoe、Yandex、Google、IQDB、Baidu、Bing、Google Lens、Lenso、Copyseeker、SauceNAO、Tineye、EHentai/ExHentai

## 使用方式

在聊天频道中使用 /exec（无需传入 _ctx）：

```
/exec render_multi_engine_search(
    image="https://example.com/image.jpg",
    top_k=3,
    options={"bovw": true}
)
```

快速模式（跳过所有网页抓取，响应最快，仅返回搜图、实体提取与结构化结论）：

```
/exec render_multi_engine_search(
    image="https://example.com/image.jpg",
    fast_mode=True
)
```

仅对前 N 条抓网页（后面结果保留搜图信息，平衡速度与信息量）：

```
/exec render_multi_engine_search(
    image="https://example.com/image.jpg",
    fetch_webpage_for_top=2
)
```

## 配置项

> 通过 enable_* 控制每个引擎是否参与多引擎搜索。

- enable_ascii2d
- enable_anime_trace
- enable_tracemoe
- enable_yandex
- enable_google
- enable_iqdb
- enable_baidu
- enable_bing
- enable_google_lens
- enable_lenso
- enable_copyseeker
- enable_saucenao
- enable_tineye
- enable_ehentai
- enable_exhentai
- ascii2d_bovw
- max_results
- saucenao_api_key
- exhentai_cookie_member_id
- exhentai_cookie_pass_hash
- exhentai_cookie_igneous
- webpage_fetch_timeout
- webpage_content_chars
- webpage_max_bytes
- webpage_cache_ttl
- allow_private_webpage_fetch
- fetch_webpage_for_top：仅对前 N 条高可信结果抓取来源网页，后面结果只保留搜图信息，可大幅提升响应速度
- fast_mode：快速模式，跳过所有来源网页抓取，仅进行搜图、实体提取与结构化结论，响应最快
- webpage_prefer_proxy：网页抓取优先使用代理（配置了 DEFAULT_PROXY 时）
- webpage_try_fallback：失败时自动切换代理策略重试（优先用代理→失败试不用代理，或反过来）

## options 参数示例

> options 仅对启用的引擎生效。

- ascii2d
  - {"bovw": true}
- tracemoe
  - {"key": "...", "anilist_id": 123, "chinese_title": true, "cut_borders": true, "mute": false, "size": "m"}
- iqdb
  - {"is_3d": false, "force_gray": false}
- google_lens
  - {"search_type": "all|products|visual_matches|exact_matches", "q": "...", "hl": "en", "country": "US"}
- saucenao
  - {"api_key": "...", "numres": 5, "hide": 0, "minsim": 30, "output_type": 2}
- anime_trace
  - {"model": "anime", "is_multi": 1, "ai_detect": 1, "base64": "..."}
- ehentai / exhentai
  - {"covers": false, "similar": true, "exp": false}
- tineye
  - {"show_unavailable_domains": false, "domain": "", "sort": "score", "order": "desc", "tags": ""}

## 依赖与注意事项

- 部分引擎依赖 pyquery/lxml/cssselect，缺失时会提示安装
- Lenso 引擎在主仓标注为受 Cloudflare 影响，可能不可用
- ExHentai 需要有效的登录 Cookie（ipb_member_id、ipb_pass_hash，可选 igneous）
- 默认只返回筛选后的可信结果，仅在无筛选结果时回退展示各引擎原始返回
- 商品页面、聚合转载页面在出处识别中会被压低权重，优先返回原始发布平台与官方来源
- 网页抓取支持自动代理策略切换：优先用代理→失败后（若启用）试不用代理，或反过来

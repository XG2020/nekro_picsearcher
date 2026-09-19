# nekro_picsearcher 图片搜源插件

基于 PicImageSearch 的多引擎图片反向搜索插件，支持在多个引擎中并行检索并聚合结果，重点优化了**识别图片人物、出处、画师、哪些网站能找到**这几类场景，并支持高效模式以平衡速度与信息量。

## 功能概览
- 多引擎并行搜索与聚合输出
- 结构化证据整理：汇总人物/角色候选、作品/出处/游戏候选、作者/画师候选、图片类型、可能原始来源和可找到的网站，供大模型继续综合判断
- 双评分系统：身份分（更关注识别角色/作品/物体）与出处分（更关注原始来源、作者与可信发布页）
- 游戏场景优化：专门识别游戏人物、游戏截图，并对游戏相关站点（wiki/攻略站/官方社区等）增强
- 通过配置项控制每个引擎启用或关闭
- 效率控制：仅对前 N 条高可信结果抓取网页，或完全跳过网页抓取以提升响应速度
- 网页抓取优化：更完整的浏览器模拟请求头、支持优先用代理、失败时自动切换代理策略重试
- 结果整理：统一返回 Markdown，按候选摘要、引擎、来源链接和网页证据分层展示
- 支持 Ascii2D、AnimeTrace、TraceMoe、Yandex、Google、IQDB、Baidu、Bing、Lenso、Copyseeker、SauceNAO、Tineye、EHentai/ExHentai

## 使用方式

插件提供 `reverse_search`（推荐）和兼容的 `render_multi_engine_search` 两个入口。使用 `/exec` 时无需传入 `_ctx`；如果当前消息或最近一条用户消息带有图片，也可以省略 `image`：

```
/exec reverse_search(
    image="https://example.com/image.jpg",
    top_k=3,
    options={"bovw": true}
)
```

按意图选择引擎，或直接指定引擎：

```text
/exec render_multi_engine_search(intent="找角色")
/exec render_multi_engine_search(intent="找出处和画师")
/exec render_multi_engine_search(engine="saucenao", image="https://example.com/image.jpg")
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
- enable_lenso
- enable_copyseeker
- enable_saucenao
- enable_tineye
- enable_ehentai
- enable_exhentai
- ascii2d_bovw
- max_results
- saucenao_api_key
- yandex_cookies
- allow_third_party_image_host
- exhentai_cookie_member_id
- exhentai_cookie_pass_hash
- exhentai_cookie_igneous
- webpage_fetch_timeout
- webpage_content_chars
- webpage_max_bytes
- allow_private_webpage_fetch
- fetch_webpage_for_top：仅对前 N 条高可信结果抓取来源网页，后面结果只保留搜图信息，可大幅提升响应速度
- fast_mode：快速模式，跳过所有来源网页抓取，仅进行搜图、实体提取与结构化结论，响应最快
- search_timeout：单个搜索引擎请求超时时间，避免单个失效引擎拖慢整体响应
- webpage_cache_ttl：来源网页缓存时间，减少同一图片重复调用时的网页抓取
- webpage_prefer_proxy：网页抓取优先使用代理（配置了 DEFAULT_PROXY 时）
- webpage_try_fallback：失败时自动切换代理策略重试（优先用代理→失败试不用代理，或反过来）

## Cookie 获取方法

### Yandex Cookie

Yandex 反爬较严格，建议从插件实际使用的 `yandex.ru` 域名获取 Cookie：

1. 在浏览器打开 `https://yandex.ru/images/`，完成登录或人机验证。
2. 按 `F12` 打开开发者工具，切换到 **Network（网络）** 面板并刷新页面。
3. 点击一个发往 `yandex.ru` 的请求，在 **Headers → Request Headers** 中找到 `Cookie`。
4. 复制 `Cookie` 后面的完整内容，例如：

   ```text
   yandexuid=...; Session_id=...; is_gdpr=0; ...
   ```

5. 将整行内容粘贴到插件配置的 `yandex_cookies`。不要只复制某一个字段；通过 Network 面板获取可以包含 `HttpOnly` Cookie。

### ExHentai Cookie

如果启用了 `enable_exhentai`，需要从已登录的 `https://exhentai.org` 页面获取以下字段：

1. 登录 ExHentai 后按 `F12`，进入 **Application（应用）→ Storage → Cookies → https://exhentai.org**。
2. 分别找到 `ipb_member_id`、`ipb_pass_hash`，以及可选的 `igneous`。
3. 将三个字段分别填写到插件配置中的 `exhentai_cookie_member_id`、`exhentai_cookie_pass_hash`、`exhentai_cookie_igneous`。

Cookie 等同于登录凭证。不要把 Cookie 发给他人、提交到 Git 或写入日志；失效后重新获取即可。

## options 参数示例

> options 仅对启用的引擎生效。

- ascii2d
  - {"bovw": true}
- tracemoe
  - {"key": "...", "anilist_id": 123, "chinese_title": true, "cut_borders": true, "mute": false, "size": "m"}
- iqdb
  - {"is_3d": false, "force_gray": false}
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
- AnimeTrace 的角色/作品识别结果即使没有网页 URL 也会保留在候选证据中
- 参考实现的 Yandex 本地图搜会上传到临时图床，可通过 `allow_third_party_image_host` 关闭
- Yandex 搜图固定使用 `yandex.ru`；Google 搜图会先访问 `/ncr` 固定非地区跳转，再进入 `searchbyimage`
- 默认只返回筛选后的可信结果，仅在无筛选结果时回退展示各引擎原始返回
- 候选线索汇总属于文本片段聚合，可能混入站点名、转载页标题或商品页文案，最终结论应结合网页正文、页面证据和原图细节综合判断
- 商品页面、聚合转载页面在出处识别中会被压低权重，优先返回原始发布平台与官方来源
- 网页抓取支持自动代理策略切换：优先用代理→失败后（若启用）试不用代理，或反过来
- AnimeTrace、SauceNAO、Yandex、E-Hentai 已切换到参考插件的统一请求/解析模块，支持共享代理、超时与 Cookie

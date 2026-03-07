# nekro_picsearcher 图片搜源插件

基于 PicImageSearch 的多引擎图片反向搜索插件，支持在多个引擎中并行检索并聚合结果。

## 功能概览
- 多引擎并行搜索与聚合输出
- 通过配置项控制每个引擎启用或关闭
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

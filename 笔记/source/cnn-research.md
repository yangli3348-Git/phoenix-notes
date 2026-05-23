# CNN 源研究

## 官方 RSS
- `rss.cnn.com` 全部停更（最晚2024年8月）
- 不可用

## Sitemap ✅ 可用
- URL: `https://edition.cnn.com/sitemap/news.xml`
- 条目: 226条，sitemap格式
- 时效: 200+条在3天内，需 `is_within_24h` 过滤
- 字段: 标题(`<news:title>`)、链接(`<loc>`)、日期(`<news:publication_date>`)、图片(`<image:loc>`)
- 图片覆盖: 144/226 (64%)
- 过滤后(去视频+购物): 36条正经新闻，全部有图(100%)
- 发布规律: 5/22的96条全天均匀分布，北京时间下午对应美国早晨是高峰

## 详情页
- `meta name="description"` 质量高(100-160字)，可作为摘要
- `og:image` 有高清大图(w_800)
- 正文在 `<p>` 标签里(18-27段)
- 无 JSON-LD

## 集成方案
- 类型: `sitemap`（新增采集类型）
- 采集: sitemap XML 解析 → 标题+链接+图片
- 详情: CNNFetcher → meta description + og:image
- 过滤规则: 排除 `/video/` 路径和 `cnn-underscored`
- 24h内可用: 约36条，100%有图

## 首页 `https://edition.cnn.com/world`
- 纯 SPA，JS 渲染
- 无内嵌文章数据
- 不可用

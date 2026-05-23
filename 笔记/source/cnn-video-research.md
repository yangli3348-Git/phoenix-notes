# CNN 视频新闻研究

## 视频条目
- sitemap 中占 84/226 条（37%），当前已过滤
- URL 路径含 `/video/`
- 标题+日期可用，无图片直接提供

## 详情页
- 纯 JS 渲染（Handlebars 模板），curl 拿不到正文
- 无 `meta description`
- 浏览器环境也可能渲染失败（CNN JS 依赖复杂）

## 字幕 ✅ 可用
- 标准 SRT 格式，URL 可从页面 HTML 提取
- 格式: `https://clips-media-aka.warnermediacdn.com/cnn/clips/{date}/{id}/cc/{slug}.srt`
- 同时有 .vtt 版本
- 内容: 完整视频旁白/对话（200-400词）
- 特点: 逐词展开式，去重后可用
- 可做口播素材

## 视频文件 ❌ 不可用
- 视频 URL 是 JS 动态加载，curl 拿不到
- 需要 Puppeteer/Playwright 或完整浏览器环境
- 当前浏览器工具环境也无法获取（页面渲染失败）

## 弹窗播放
- 如果有视频 URL，HTML `<video>` 标签可直接播放
- 实际无法获取 URL → 不能播视频
- 替代方案: 字幕当口播素材 + TTS 语音 → 弹窗无需视频本身

## 结论
- 视频新闻有字幕可作文本素材，但获取成本高（需渲染页面取 SRT URL）
- 优先使用文字新闻（sitemap 中有 36 条，100% 有图）
- 视频新闻暂不集成，后续如有需求再研究

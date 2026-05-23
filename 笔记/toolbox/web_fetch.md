# web_fetch 使用技巧

## 基本用法
- 抓取 URL 内容，自动转为 markdown/text
- 支持 RSS/XML，支持静态 HTML
- 不支持 JS 动态渲染的 SPA 页面

## 参数
- `url` — 目标网址
- `maxChars` — 最大返回字符数（超出截断）
- `extractMode` — 提取模式：`markdown`（默认）或 `text`

## 已知限制
- 可能被 403 拦截（知乎、微博 API）
- 部分重定向后内容为空（Bing News）
- 国内服务器无法访问境外网站（X.com、Reuters、BBC、Google News）

## 替代方案
- 被拦 → 换 Bing 搜索间接获取
- 页面 JS 渲染 → 可尝试 browser 工具

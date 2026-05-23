# CNN 视频获取完整方案

## 视频 CDN
- 域名: `gcp.apac-free.prd.media.max.com` (Warner Bros Discovery GCP CDN)
- 格式: `https://gcp.apac-free.prd.media.max.com/global/{bolt_id}/v/3_ec77d2/v{quality}.mp4`
- 清晰度: v0(720p) ~ v6(234p)
- 可直接下载，需要 Origin + Referer 头，不需要代理

## bolt_id 获取
- 在页面 HTML 的 `data-bolt-id` 属性中
- 格式: UUID v4 (如 `6cc1322a-aa25-5b8e-a8eb-2e421290ac95`)
- **需要 JS 渲染才能拿到**（curl 被反爬）
- 对应关系: data-bolt-id → playbackInfo API 的 editId → dash.mpd → CDN URL

## 字幕 ✅
- URL 可静态获取：`clips-media-aka.warnermediacdn.com/cnn/clips/{date}/{internal_id}-{hash}/cc/{slug}.srt`
- SRT 格式，逐词展开式
- 同时有 VTT版本
- 不需要 bolt_id 就能获取

## 路线图
1. ✅ 字幕直接可用 → 口播素材
2. ❌ 视频文件 → 需要 bolt_id，curl 拿不到
3. 🔮 可能的突破: 用浏览器渲染取 data-bolt-id → 拼接 CDN URL → 下载 mp4

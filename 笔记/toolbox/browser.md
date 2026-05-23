# Browser 工具使用指南

> 本服务器的浏览器工具（OpenClaw browser tool + Chromium）正确使用方法。
> 更新于 2026-04-28。

---

## 环境

- **Chromium**: snap 安装，v147.0.7727.116（备用）
- **Playwright**: npm 依赖内置 Chromium，常驻运行
- **资源**: 服务器 3.6GB RAM，可用约 1.8GB

## 操作规范

### ✅ 用前须知

- browser 是 **JS 渲染页面**的最后手段
- 优先用 web_fetch（轻量、无状态）
- web_fetch 搞不定（JS 渲染/反爬）时才上 browser
- 常见需要 browser 的场景：
  - SPA 动态页面（Vue/React 渲染、懒加载内容）
  - 需要登录态的操作
  - 反爬严格的网站

### 🔴 用完关标签页

每次 browser navigate 后，操作完**必须关闭标签页**：
```
browser action=close targetId=xxx
```
或者导航到 about:blank：
```
browser action=navigate url=about:blank targetId=xxx
```

**不关的后果**：服务器内存只有 1.8GB 可用，十几个标签页就能把内存吃光，导致会话挂掉。

### 🔴 注意内存红线

- 服务器 RAM 总量 3.6GB，可用 ~1.8GB
- Chrome 进程内存飙升时需及时止损
- 避免同时打开多个标签页
- 每个标签页操作完立即关闭

## 常用操作

### 1. 打开页面 + 获取快照
```
browser action=open url=https://example.com
browser action=snapshot targetId=xxx
```

### 2. 页面内操作
```
browser action=act ref=e12 type=click    # 点击元素
browser action=act ref=e34 type=type text=xxx  # 输入文本
browser action=act ref=e56 type=select values=["option1"]  # 下拉选择
```

### 3. 截图
```
browser action=screenshot targetId=xxx
```

### 4. 关闭标签页
```
browser action=close targetId=xxx
```

## 常见问题

### Q: 页面空白或加载不全？
- 可能是 JS 没加载完，等几秒再 snapshot
- 或页面需要登录，先手动操作登录流程

### Q: 内存不够了？
- 检查有哪些标签页开着，全部关闭
- 必要时可以重启 browser 进程

### Q: 连接失败？
- 第一次用可能需要先 `browser action=start`
- 检查 Chromium 是否在运行

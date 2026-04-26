# BrightBean Studio 学习笔记

> 已 fork 到工作区：`brightbean-studio-fork/`
> 原项目：https://github.com/brightbeanxyz/brightbean-studio（1327⭐）

## 核心架构（值得参考）

### 模块化设计（Django apps）

| app | 功能 |
|---|---|
| `approvals/` | 审批流程（提交/通过/驳回/重提）|
| `publisher/` | 发布引擎（队列 + 重试 + 限速）|
| `composer/` | 内容编排（多平台版本覆盖）|
| `providers/` | 各平台适配器（抽象基类 + 实现）|
| `social_accounts/` | 社交账号管理 |
| `inbox/` | 统一收件箱 |
| `media_library/` | 媒体库 |
| `calendar/` | 可视化排程日历 |
| `credentials/` | API 凭证管理（加密存储）|
| `notifications/` | 通知（站内/邮件/Webhook）|
| `client_portal/` | 客户门户（无需注册，30天魔法链接）|
| `organizations/` | 多组织/多工作区管理 |

### 适配器模式（直接复用思路）

`providers/base.py` → `SocialProvider` 抽象基类
- `publish_post()` → 发布
- `get_post_metrics()` → 数据
- `get_profile()` → 账号信息
- `get_messages()` → 收件箱
- 每个平台一个文件继承实现

我们做的时候：**继承这个基类，写抖音、快手、B站、微博、视频号适配器**

### 审批流程设计
- 支持多级审批（不做/可选/内部/内部+客户）
- 内部/外部评论可见性
- 催办提醒 + 升级机制
- 完整审计追踪

### 发布引擎
- 异步队列发布
- 自动重试
- 各账号限速追踪
- 90天审计日志

## 技术栈
- Python 3.12+ / Django 5.x
- PostgreSQL + Redis
- Docker 部署
- HTMX + TailwindCSS（前端）
- httpx（API 客户端）

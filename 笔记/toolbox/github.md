# GitHub 使用指南

> 本服务器在 GitHub 上的操作方式、凭证管理、常见问题。
> 更新于 2026-04-28。

---

## 凭证

- **账号**: yangli3348-Git
- **Token**: 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
- **Token 位置**: MEMORY.md 和 AGENTS.md 中有记录
- **注**: Token 有完整 repo 权限，注意不要暴露

## 访问方式（按推荐优先级）

### 1. git CLI（完整功能）
支持：clone / pull / push / commit / log / ls-remote / status

**示例：**
```
git clone https://yangli3348-Git:<TOKEN>@github.com/yangli3348-Git/<REPO>.git
```

**注意**：本服务器连 GitHub 有时 TLS 不稳定，会报：
```
GnuTLS recv error (-110): The TLS connection was non-properly terminated.
```

**如果 clone 失败**：
- 加 `GIT_SSL_NO_VERIFY=1` 重试
- 或用方式 2 的 zip 下载
- 多试几次（网络间歇性恢复）

### 2. GitHub API（只读/查询）
不需要 git CLI，直接 HTTP 请求，更稳定。

**查看仓库列表：**
```
curl -s -H "Authorization: token <TOKEN>" https://api.github.com/user/repos?per_page=100
```

**查看文件/目录：**
```
curl -s -H "Authorization: token <TOKEN>" https://api.github.com/repos/<USER>/<REPO>/contents/<PATH>
# 返回 JSON，.content 需要 base64 -d 解码
```

**拉取整个仓库（zip 下载）：**
```
curl -sL -H "Authorization: token <TOKEN>" \
  https://api.github.com/repos/<USER>/<REPO>/zipball -o /tmp/<REPO>.zip
unzip /tmp/<REPO>.zip -d <目标目录>
# 注意：zip 内的目录名带 commit hash，需要 mv 重命名
```

### 3. web_fetch（只读网页内容）
```
web_fetch url=https://github.com/<USER>/<REPO>
```
限制：只能看页面内容，不能操作 repo，且可能被反爬。

## 已管理的仓库

| 仓库 | 本地路径 | 说明 |
|---|---|---|
| zhanyan | /home/boss/ftp/zhanyan/ | 旧项目 |
| phoenix-notes | /home/boss/ftp/phoenix-notes/ | 工作笔记（虾壳维护） |
| feihuang-demo | /home/boss/ftp/feihuang-demo/ | 凤凰Demo（git远程已有） |

## 推送到 GitHub

### 首次：建新仓库后
```bash
cd <本地目录>
git init
git remote add origin https://yangli3348-Git:<TOKEN>@github.com/yangli3348-Git/<REPO>.git
git add .
git commit -m "初始提交"
git push -u origin main
```

### 更新已有仓库
```bash
cd <本地目录>
git add .
git commit -m "更新内容"
git push
```

## 已知问题

### TLS 连接不稳定
- 症状：clone/push 间歇性报 GnuTLS error (-110)
- 原因：服务器网络到 GitHub 的 TLS 握手有时超时
- 对策：重试几次；紧急情况用 API zip 下载代替 clone

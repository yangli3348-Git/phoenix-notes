# phoenix-notes 🦐

虾壳的工作笔记仓库。记录工具使用经验、项目讨论、流水线搭建等一切需要备忘和延续的东西。

> GitHub: [yangli3348-Git/phoenix-notes](https://github.com/yangli3348-Git/phoenix-notes)

## 目录结构

```
├── README.md
├── _索引.md                   # 笔记索引（启动时加载）
├── 笔记/                      # 工作笔记
│   ├── 工作守则.md            # 老板钦定铁律
│   ├── 尝试记录.md            # 首次操作/实验日志
│   ├── source/
│   │   └── 信源档案.md         # 各新闻来源访问方式、可靠度评估
│   └── toolbox/
│       ├── 工具能力.md         # 服务器各工具可用性实测
│       ├── web_fetch.md       # web_fetch 使用技巧与限制
│       ├── browser.md         # 浏览器工具正确用法
│       └── github.md          # GitHub 正确用法（凭证/克隆/API）
├── pipeline/                  # 新闻弹窗流水线
│   ├── collect.py             # 采集器（9源轮询 → titles_24h.json）
│   ├── main.py                # 弹窗制作器（抓详情→口播→TTS→popup_data.json）
│   ├── fetcher.py             # 各源详情抓取
│   ├── script_gen.py          # DeepSeek 中文口播生成
│   ├── tts.py                 # Edge TTS 语音合成
│   ├── sources.py             # 新闻源配置
│   ├── store.py               # JSON 持久化
│   ├── data/                  # 运行时数据（titles_24h.json 等）
│   └── archive/               # 旧版归档
├── 大屏/                      # 新闻弹窗前端
│   ├── 动态新闻流.html         # 大屏主体（地图+飞线+词云）
│   ├── 双向飞线图.html         # 飞线图（蓝线汇聚+金色电波）
│   ├── news_popup.js          # 弹窗渲染模块
│   ├── news_popup.html        # 弹窗模板
│   ├── world.json             # 世界地图数据
│   ├── popup_data.json        # 弹窗数据队列
│   └── archive/               # 开发过程的HTML草案归档
└── 项目/                      # 各项目讨论/方案
    ├── 凤凰融媒体.md
    ├── 凤凰融媒体-报告草稿.md
    ├── 数据大屏.md
    ├── 抖音网站应用.md
    ├── BrightBean-学习笔记.md
    └── 照片角色扮演游戏设计.md
```

## 新闻弹窗流水线

```
采集(15分钟) → 详情抓取 → DeepSeek口播 → EdgeTTS → popup_data.json → 大屏弹窗
```

启动方式：
```bash
# 进程一：标题采集
cd pipeline && python3 collector.py

# 进程二：弹窗制作
cd pipeline && python3 main.py
```

## 维护

由虾壳维护。笔记持续更新中。

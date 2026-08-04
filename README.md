# 408考研插件

`kaoyan-408` 是面向数学一、数学二、英语一、英语二、408 与政治的中文 Skills-only 学习插件。它提供 2010—2026 年五类真题的合规来源发现、真题分析、新手图文讲解、规划、执行、诊断、错题复测、原创模考以及可选 Notion/Obsidian 学习记忆。

当前版本：`2.0.0`

项目没有 App、MCP、后台服务、云端题库、账号或 API Key。网页搜索、图片生成、Notion 和本地文件能力由当前 ChatGPT/Codex 宿主决定；不可用时插件会明确降级。

## 13 个 Skills

| Skill | 用途 |
| --- | --- |
| `kaoyan-408-planner` | 阶段、月度、周度和跨科配额 |
| `kaoyan-review-executor` | 将计划展开为当前学习时段 |
| `kaoyan-progress-diagnostician` | 根据真实记录诊断进度和风险 |
| `kaoyan-error-loop-coach` | 跨题错因聚类、复测和掌握证据 |
| `kaoyan-mock-exam-coach` | 原创或授权题目的冻结题面模考 |
| `kaoyan-408-tutor` | 408 单题与概念的新手图文讲解 |
| `kaoyan-math-coach` | 数学一/二单题、验算与专项训练 |
| `kaoyan-english-coach` | 英语一/二阅读、翻译和写作批改 |
| `kaoyan-politics-coach` | 政治理论、材料题和背诵复测 |
| `kaoyan-past-paper-searcher` | 五类真题来源、许可、冲突与重复项核验 |
| `kaoyan-past-paper-analyst` | 已提供或已核验真题的覆盖与有限趋势分析 |
| `kaoyan-material-study-assistant` | 用户材料的摘要、卡片和原创练习 |
| `kaoyan-official-info-researcher` | 当年大纲、报名、院校和考试安排核验 |

## 真题与图文回答

- 自动发现范围固定为试卷年度 2010—2026，科目固定为数学一、数学二、英语一、英语二和 408。政治辅导保留，但不建设政治真题库。
- 宿主搜索可用时同时执行普通网页发现与 `site:github.com` 查询。只有实际访问 Google 结果时才会标明 Google；搜索关闭时输出 `[真题未命中]` 和可复制搜索式。
- GitHub 来源记录仓库、文件、commit、raw URL 与许可证。许可证不明时只保存索引、必要短摘录和 `[原创解析]`，不复制整卷。
- 数学、英语、408、政治单题与真题逐题解析默认面向新手，包含前置知识、可编辑图解、逐步推导、独立复核、第一处易错点和 `[原创练习]`。
- 精确关系优先用 Mermaid、表格、状态图或可审计 SVG；宿主支持图片生成时可附辅助示意图，但图片不替代公式、代码或答案证据。

## 安装

新版 Codex CLI/IDE 可添加仓库 marketplace 后安装：

```powershell
codex plugin marketplace add yq6666-66/kaoyan-22408-codex-plugin --ref v2.0.0
codex plugin add kaoyan-408@kaoyan-408
```

也可克隆固定版本，在 ChatGPT Desktop 或 Codex Desktop 打开仓库并从 repo marketplace 安装：

```powershell
git clone --branch v2.0.0 --depth 1 https://github.com/yq6666-66/kaoyan-22408-codex-plugin.git
```

跨平台安装器：

```powershell
python scripts/install_local.py --check
python scripts/install_local.py
```

退出码：`0` 成功；`1` 校验、命令或安装失败；`2` 当前 Codex 不支持插件命令，需要桌面端人工安装。只有实际成功才输出 `Installed kaoyan-408`。

### 从 v1.4.0 迁移

`kaoyan-408` 是新的插件 ID，不会静默覆盖 `kaoyan-22408`。先安装并验证 v2，再禁用或移除旧插件；旧 Releases 和旧便携记录保持可用。

## Obsidian 大脑

新配置位置为 `.codex/kaoyan-408/obsidian-brain.json`，Schema 1.1 增加 `knowledgeRoot` 和 `pastPaperRoot`：

```powershell
python scripts/configure_obsidian_brain.py configure --vault <Vault绝对路径>
python scripts/configure_obsidian_brain.py check
```

从 Schema 1.0 无损迁移：

```powershell
python scripts/configure_obsidian_brain.py migrate --dry-run
python scripts/configure_obsidian_brain.py migrate
```

迁移会保留旧配置和私人目录，沿用旧 Vault、项目目录及已存在的知识目录，不自动移动或删除 `考研 22408` 笔记。新安装默认使用 `20-项目/408考研`、`30-知识/408考研`、`40-真题/408考研`。

## Notion 大脑

首次写入时确认一个“408考研”主页或数据库，插件写入标记 `kaoyan-408-brain:1.0`。之后只在该范围内自动搜索、去重和增量更新；多个标记、授权失败或目标不可访问时停止写入。

默认结构为 `00｜真题索引`、`01｜数学一`、`02｜数学二`、`03｜英语一`、`04｜英语二`、`05｜408`。写入后会重新读取验证；页面 ID 和工作区信息不会进入仓库或发布包。

用户说“本次不记忆”“只读模式”或“不要同步 Notion”时，本轮禁止 Notion 和 Obsidian 写入。

## 开发与发布门禁

```powershell
python scripts/check.py
python scripts/build_release.py
python scripts/install_local.py --check
```

门禁完全离线，不要求登录 Codex CLI：真实 YAML/JSON Schema、13 个官方 `quick_validate.py` 证据、65 个路由场景、52 个行为场景、单元测试、Semgrep、Git 历史凭据扫描与 Windows/Ubuntu 可重复 ZIP。发布包采用完整路径允许列表，不包含真题、搜索缓存、私人配置或知识库数据。

## 隐私与版权

- 发布者没有后台服务，无法访问会话、Notion、Obsidian、真题文件、学习记录或 API Key。
- 只有官方明确允许或开放许可证覆盖时才保存真题全文；其他来源只保存索引、合法短摘录和原创解析。
- 不提供付费题库、批量答案、网盘资料或未授权材料下载。

参见 [PRIVACY.md](PRIVACY.md)、[TERMS.md](TERMS.md)、[SECURITY.md](SECURITY.md) 和 [THIRD_PARTY_CONTENT.md](THIRD_PARTY_CONTENT.md)。

源码与支持：[GitHub 仓库](https://github.com/yq6666-66/kaoyan-22408-codex-plugin) · [Issues](https://github.com/yq6666-66/kaoyan-22408-codex-plugin/issues)

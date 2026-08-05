# 408考研插件

`kaoyan-408` 是面向考研 408 方向的中文 Skills-only 学习插件，帮助你在 Codex 和 ChatGPT 中完成真题检索、图文讲解、学习规划、错题复测与双知识库记忆。它覆盖数学一、数学二、英语一、英语二和 408，并保留政治辅导。

当前版本：`2.0.0`

项目没有 App、MCP、后台服务、云端题库、账号或 API Key。网页搜索、图片生成、Notion 和本地文件能力由当前 ChatGPT/Codex 宿主决定；不可用时插件会明确降级，不伪造搜索结果或学习记录。

## 主要功能

- 真题搜索与核验：按试卷年度 2010—2026 检索数学一、数学二、英语一、英语二和 408 的公开来源，记录仓库、文件、commit、raw URL 与许可证；搜索关闭时输出 `[真题未命中]` 和可复制搜索式。
- 新手图文讲解：单题解析包含题型定位、`[真题证据]`、前置知识、可编辑图解（Mermaid/表格/SVG）、逐步推导、独立复核、第一处易错点与 `[原创练习]`，全程用“为什么”解释每一步。
- 学习闭环：阶段/月/周规划、单次学习时段执行、进度诊断、错因聚类与复测、原创或授权模考，以及便携学习记录（Schema 1.1）。
- 双知识库记忆：可选接入 Obsidian Vault 与授权 Notion 工作区，自动检索相关记忆并增量写回；未配置或权限不足时自动降级为会话内模式。
- 官方信息核验：当年大纲、报名、院校招生和考试安排只以教育部、研招网、院校官网及政府机构来源为准，离线时明确说明无法核验。

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

## 使用示例

```text
帮我搜索 2024 年数学一真题的公开来源
用图解和前置知识讲一下这道 408 数据结构题
我做了 2023 年英语二阅读，帮我批改并标出证据链
根据我的目标和每周时间，制定 408 四科周计划
用原创题目生成一张章节测，交卷后评分复盘
把本次错因复测计划写入 Obsidian 和 Notion
```

## 安装

新版 Codex CLI/IDE 可添加仓库 marketplace 后安装：

```powershell
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.0.0
codex plugin add kaoyan-408@kaoyan-408
```

也可克隆固定版本，在 ChatGPT Desktop 或 Codex Desktop 打开仓库并从 repo marketplace 安装：

```powershell
git clone --branch v2.0.0 --depth 1 https://github.com/yq6666-66/408-codex-plugin.git
```

跨平台安装器：

```powershell
python scripts/install_local.py --check
python scripts/install_local.py
```

退出码：`0` 成功；`1` 校验、命令或安装失败；`2` 当前 Codex 不支持插件命令，需要桌面端人工安装。只有实际成功才输出 `Installed kaoyan-408`。

## Obsidian 大脑

配置位置为 `.codex/kaoyan-408/obsidian-brain.json`，支持 `knowledgeRoot` 和 `pastPaperRoot`：

```powershell
python scripts/configure_obsidian_brain.py configure --vault <Vault绝对路径>
python scripts/configure_obsidian_brain.py check
```

新安装默认使用 `20-项目/408考研`、`30-知识/408考研`、`40-真题/408考研`。插件只保存学习档案、当前进度、错题队列和可复用方法；不保存整段对话、私人敏感内容或未授权材料。写入前会重新读取目标文件并合并，冲突时保留双方内容并标记待整理。

## Notion 大脑

首次写入时确认一个“408考研”主页或数据库，插件写入标记 `kaoyan-408-brain:1.0`。之后只在该范围内自动搜索、去重和增量更新；多个标记、授权失败或目标不可访问时停止写入。

默认结构为 `00｜真题索引`、`01｜数学一`、`02｜数学二`、`03｜英语一`、`04｜英语二`、`05｜408`。写入后会重新读取验证；页面 ID 和工作区信息不会进入仓库或发布包。

用户说“本次不记忆”“只读模式”或“不要同步 Notion”时，本轮禁止 Notion 和 Obsidian 写入。

## 隐私与版权

- 发布者没有后台服务，无法访问会话、Notion、Obsidian、真题文件、学习记录或 API Key。
- 只有官方明确允许或开放许可证覆盖时才保存真题全文；其他来源只保存索引、合法短摘录和原创解析。
- 不提供付费题库、批量答案、网盘资料或未授权材料下载。
- 插件不收集、不保存用户数据；用户上传的题目、材料和进度只由当前会话处理。

参见 [PRIVACY.md](PRIVACY.md)、[TERMS.md](TERMS.md)、[SECURITY.md](SECURITY.md) 和 [THIRD_PARTY_CONTENT.md](THIRD_PARTY_CONTENT.md)。

源码与支持：[GitHub 仓库](https://github.com/yq6666-66/408-codex-plugin) · [Issues](https://github.com/yq6666-66/408-codex-plugin/issues)

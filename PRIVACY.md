# 隐私政策

生效日期：2026-08-04

## 适用范围

本政策适用于 `kaoyan-408` Skills 插件。插件由公开的静态文件组成，不提供发布者控制的 App、MCP、后台服务、账号系统、模型代理或云端数据存储。用户可以选择让具备本地文件权限的宿主连接其自行配置的 Obsidian Vault，或连接用户自己授权的 Notion 工作区、Udemy 课程、Sider Scholar/Exa 检索、GoodNotes 笔记、Wolfram 计算、A-Z Dictionary 词典、Quizlet 闪卡、Ace Quiz Maker 章节测、Ace Knowledge Graph 图谱、AhaMotion 视频、Vocabulary Trainer 词汇与 Kahoot 互动复习。

## 发布者接收的数据

发布者不会通过本插件接收或保存以下内容：

- ChatGPT 或 Codex 会话；
- 用户上传的题目、讲义、笔记、试卷或其他文件；
- 学习计划、作答、进度快照、复测队列或模考记录；
- API Key、访问凭据、设备文件、设备路径或设备标识。
- 网页搜索结果、GitHub 真题来源、Notion 页面 ID、Obsidian 配置，以及各学习应用（Udemy、Sider Scholar、Exa、GoodNotes、Wolfram、A-Z Dictionary、Quizlet、Ace Quiz Maker、Ace Knowledge Graph、AhaMotion、Vocabulary Trainer、Kahoot）的登录态、会话或导出数据。

用户材料由所使用的 ChatGPT 或 Codex 宿主处理。宿主如何处理数据由用户与对应服务之间的条款和隐私政策决定，不由本插件控制。

## 可选本地 Obsidian 记忆

未配置或未启用 Obsidian 大脑时，插件不写入本机状态，也不拥有跨会话记忆。

启用后，宿主可根据公开的大脑契约读取和更新用户指定 Vault 中的 Markdown。默认只保存目标、计划、用户确认的完成记录、错因、复测安排、掌握证据和稳定方法；不保存整段会话、密钥、身份信息或完整付费资料。配置与 Vault 均保存在用户设备上，发布者没有后端接收这些内容。

`StudyProfile`、`ProgressSnapshot` 和 `ReviewQueue` 仍是可复制、可迁移的 Schema 1.1 JSON。用户可以在请求中使用“本次不记忆”切换为单轮只读，也可以关闭本地配置。

## 外部信息核验

当用户要求核验当前招考信息或发现五类真题来源时，Skill 可能建议宿主访问官方页面、GitHub 和公开网页。检索词只包含科目、年份、试卷类型和来源条件，不加入用户作答、学习记录、Notion 页面 ID、Vault 路径或个人信息。宿主的网页搜索记录由宿主服务处理，发布者无法访问。

## 可选 Udemy / Sider Scholar / GoodNotes 学习层

Udemy、Sider Scholar 与 GoodNotes 均为用户授权的可选学习层。宿主仅在用户已登录并授权时访问对应应用：Udemy 用于检索已购课程与章节，Sider Scholar 用于检索学术与扩展资料，GoodNotes 用于读写手写笔记（或由用户导出 Markdown/PDF 后在本会话处理）。插件发布者不接收这些应用的登录态、会话、笔记、课程或导出数据，也没有独立访问权限。未连接时插件明确降级并仅处理用户在本会话提供的材料。
## 可选 Exa / Wolfram / A-Z Dictionary / Quizlet / Ace Quiz Maker / Ace Knowledge Graph / AhaMotion / Vocabulary Trainer / Kahoot 学习层

Exa、Wolfram、A-Z Dictionary、Quizlet、Ace Quiz Maker、Ace Knowledge Graph、AhaMotion、Vocabulary Trainer 与 Kahoot 均为用户授权的可选学习层。宿主仅在用户已登录并授权时访问对应应用：Exa 用于网页与资料检索，Wolfram 用于计算核验，A-Z Dictionary 用于词典查询，Quizlet 用于闪卡记忆，Ace Quiz Maker 用于章节自测，Ace Knowledge Graph 用于知识点图谱，AhaMotion 用于概念视频，Vocabulary Trainer 用于词汇训练，Kahoot 用于互动复习。插件发布者不接收这些应用的登录态、会话、笔记、课程、词表或导出数据，也没有独立访问权限。未连接时插件明确降级并仅处理用户在本会话提供的材料。

## 可选 Notion 学习记忆

启用 Notion 后，当前宿主通过用户已授权的 Notion 工具搜索、读取和更新用户一次确认绑定的页面范围。插件发布者不接收 Notion Token、页面内容、会话记录或学习状态，也没有独立访问用户工作区的权限。默认只保存最小可复用学习增量、真题来源索引和插件原创解析；用户可以使用“本次不记忆”“只读模式”或“不要同步 Notion”禁止本轮写入。

## 保存与删除

发布者没有本插件的数据存储，因此没有可由发布者保留或删除的会话数据。用户可在宿主产品中管理会话和文件，并直接在自己的 Obsidian Vault 中查看、修订、归档或删除本地记忆。插件对“忘记”请求默认采用可恢复归档，避免误删。

## 变更与联系

政策更新会通过本仓库版本记录发布。隐私问题可通过 [GitHub Issues](https://github.com/yq6666-66/kaoyan-22408-codex-plugin/issues) 联系；请勿在公开 Issue 中提交个人信息、访问凭据或未公开材料。

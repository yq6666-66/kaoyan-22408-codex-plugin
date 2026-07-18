# 考研 22408 Skills 插件

`kaoyan-22408` 是面向数学二、英语二、408 与政治的中文学习插件，可在支持 Skills 插件的 ChatGPT 与 Codex 环境中使用。项目只包含 12 个 Skills、共享契约与品牌图标，不提供独立应用、App、MCP、后台服务、账号、内置题库或学习状态持久化。

当前版本：`1.2.0`

默认采用自适应简洁输出：先给可执行结论或立即行动，复杂问题再展开必要依据；需要连续学习时使用三行 Markdown 交接卡，必须生成的 Schema 1.1 JSON 永远放在回答末尾。

## 能力

| Skill | 主责 |
| --- | --- |
| `kaoyan-22408-planner` | 阶段、月度、周度、目标日期倒排与跨科时间分配 |
| `kaoyan-review-executor` | 把既有计划或用户给出的本次目标、科目与时长展开为当前学习时段 |
| `kaoyan-progress-diagnostician` | 根据用户提供的记录诊断进度、风险与调整信号 |
| `kaoyan-error-loop-coach` | 跨题错因聚类、间隔复测与掌握证据判断 |
| `kaoyan-mock-exam-coach` | 组织原创或用户授权题目的自计时测验，并在交卷后评分复盘 |
| `kaoyan-408-tutor` | 408 单题、概念、题面缺失与答案冲突处理 |
| `kaoyan-math2-coach` | 数学二解题、单题错误定位与专项训练 |
| `kaoyan-english2-coach` | 英语二阅读、翻译、完形、新题型与写作批改 |
| `kaoyan-politics-coach` | 政治理论、材料题与背诵复测 |
| `kaoyan-past-paper-analyst` | 分析用户实际提供且有权使用的真题文件 |
| `kaoyan-material-study-assistant` | 把用户提供的材料转成摘要、卡片、提纲与练习 |
| `kaoyan-official-info-researcher` | 核验当年大纲、报名、招生、考试安排与当前政策事实 |

材料路由按意图判断：讲解材料中的学科概念或题目时使用对应学科 Skill；做摘要、卡片、提纲或改写时使用 `kaoyan-material-study-assistant`。

## 数据与内容边界

- 发布者没有接收会话、文件、学习记录或 API Key 的服务器。
- 插件只处理当前会话内容，不写入用户设备，也不暗示拥有跨会话记忆。
- 真题和学习材料只处理用户当前会话直接提供的有限内容，或用户有权使用且实际提供的文件；不会搜索、补全或重建整套资料。
- 跨会话继续时，用户可复制插件输出的 Schema 1.1 `StudyProfile`、`ProgressSnapshot` 或 `ReviewQueue` JSON。
- 招考信息以教育部、研招网和目标院校官网为依据；时政与政策事实以中国政府网、国务院、中央部门或事项发布机构官网为依据。不能核验时会标记 `[待核验]`。
- 输出使用 `[用户材料]`、`[原创练习]`、`[官方核验]`、`[待核验]` 区分证据来源。

详见 [隐私政策](PRIVACY.md)、[使用条款](TERMS.md) 与 [第三方内容边界](THIRD_PARTY_CONTENT.md)。

## 分发与兼容性

GitHub 仓库是 repo marketplace 的安装源。GitHub Release 中的 ZIP 与 SHA-256 文件用于审计、离线检查和复现构建，不是另一套应用安装包。

| 环境 | 使用方式 |
| --- | --- |
| 支持插件命令的新版 Codex CLI / IDE | 添加固定版本的 GitHub marketplace，再从插件目录安装 |
| ChatGPT Desktop / Codex Desktop | 克隆并打开仓库，重启桌面端，再从 repo marketplace 选择 `kaoyan-22408` |
| 不支持插件命令的旧版 CLI | CLI 不能直接安装；使用上面的桌面端 repo marketplace 流程 |
| ChatGPT Web | 仅当个人或工作区已经提供、安装或分享该插件时可用；不能直接从 GitHub 搜索安装 |

### 新版 CLI 安装

以下命令要求当前 CLI 的 `codex plugin` 帮助中存在相应子命令：

```text
codex plugin marketplace add yq6666-66/kaoyan-22408-codex-plugin --ref v1.2.0
codex plugin add kaoyan-22408@kaoyan-22408
```

安装后新建任务，让宿主重新加载 Skills。

### 桌面端安装

```text
git clone --branch v1.2.0 --depth 1 https://github.com/yq6666-66/kaoyan-22408-codex-plugin.git
```

在 ChatGPT Desktop 或 Codex Desktop 中打开克隆后的仓库，重启桌面端，然后从仓库提供的 marketplace 安装 `kaoyan-22408`。桌面端菜单名称可能随版本变化。

### 本地开发安装

在仓库根目录运行跨平台安装器：

```text
python scripts/install_local.py
```

只验证、不安装：

```text
python scripts/install_local.py --validate-only
```

Windows 也可使用只负责转发参数与退出码的 PowerShell 包装：

```powershell
./scripts/install-local.ps1
./scripts/install-local.ps1 -ValidateOnly
```

退出码含义：`0` 表示验证成功或实际安装成功；`1` 表示验证、命令或安装失败；`2` 表示当前 Codex 不支持插件命令，需要改用桌面端 repo marketplace 人工安装。只有 `codex plugin add` 确实成功时，安装器才会输出 `Installed kaoyan-22408`。

## 调用示例

Codex 可使用 `$skill-name` 显式调用；ChatGPT 可从插件或 Skill 选择器调用。例如：

```text
使用 $kaoyan-review-executor。我现在有 90 分钟，目标是复习数据结构树与二叉树并完成一次闭卷复述，请安排这个学习时段。
```

```text
使用 $kaoyan-mock-exam-coach，生成 10 道原创操作系统章节测；我会自行计时，明确交卷前不要显示答案、提示或得分线索。
```

## 开发、验证与发布包

```text
python scripts/check.py
python scripts/build_release.py
```

`check.py` 运行仓库静态检查、结构校验和测试。`build_release.py` 从 `plugin.json.version` 派生 ZIP 文件名，同时生成对应的 `.zip.sha256`，并只打包完整路径允许列表中的插件文件。正式发布还要求官方插件校验、12 个 Skill 校验、动态前向评测证据，以及 Windows 与 Ubuntu 构建得到完全相同的 SHA-256。

动态评测在已提交且输入树干净的版本上运行。评测器会生成证据和逐响应摘要清单：

```text
python evals/run_forward_eval.py --model <固定的-Codex-模型> --service-tier <固定服务层> --no-cache
python evals/forward_attestation.py prepare --repo .
ssh-keygen -Y sign -f <离线签名私钥路径> -n kaoyan-forward-eval tests/forward-eval-attestation.json
```

私钥不得进入仓库、CI 变量或评测工作区。仓库只提交评测证据、响应摘要清单、规范化声明和 OpenSSH 分离签名。受保护工作流从基分支运行可信验证器，并从仓库变量 `KAOYAN_FORWARD_EVAL_ALLOWED_SIGNERS` 将维护者公钥固定到候选 checkout 之外：

```text
python evals/forward_attestation.py verify --repo . --allowed-signers <仓库外-allowed_signers-路径>
```

`evals/verify_forward_evidence.py` 只检查仓库内证据的一致性，不能证明模型运行来源；它不替代上述分离签名门禁。签名有效期最多 30 天，且签名锁定源提交、插件树、测试集、评测器、完整证据字节和 108 份结构化响应摘要（60 份路由响应、24 份行为响应与 24 份独立 judge 结果）。正式门禁要求路由 `60/60`、行为 `24/24`，并拒绝混用模型、服务层或失败缓存。

版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 支持与许可

- 源码与 marketplace：[GitHub 仓库](https://github.com/yq6666-66/kaoyan-22408-codex-plugin)
- 问题与建议：[GitHub Issues](https://github.com/yq6666-66/kaoyan-22408-codex-plugin/issues)
- 安全问题：[SECURITY.md](SECURITY.md)
- 许可：[MIT](LICENSE)

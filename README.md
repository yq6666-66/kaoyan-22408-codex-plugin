# 考研 22408 Skills 插件

面向数学二、英语二、408 与政治的中文学习插件，可在支持 Skills 的 ChatGPT 与 Codex 环境中使用。项目只包含工作流说明、共享契约和品牌图标，不提供独立应用、后台服务、账号系统或学习数据存储。

## 能力

插件包含 12 个单一职责 Skill：

| Skill | 用途 |
| --- | --- |
| `kaoyan-22408-planner` | 阶段、月度、周度与跨科时间规划 |
| `kaoyan-review-executor` | 把既有计划展开为当前学习任务 |
| `kaoyan-progress-diagnostician` | 根据用户提供的快照诊断进度与风险 |
| `kaoyan-error-loop-coach` | 错因聚类、间隔复测与掌握证据判断 |
| `kaoyan-mock-exam-coach` | 原创或用户授权题目的计时测验与交卷后复盘 |
| `kaoyan-408-tutor` | 408 题目、概念、缺失题面与答案冲突处理 |
| `kaoyan-math2-coach` | 数学二解题、错因与专项训练 |
| `kaoyan-english2-coach` | 英语二阅读、翻译、完形、新题型与写作批改 |
| `kaoyan-politics-coach` | 政治理论、材料题与背诵复测 |
| `kaoyan-past-paper-analyst` | 分析用户上传或明确有权使用的真题 |
| `kaoyan-material-study-assistant` | 把用户提供的材料转成摘要、卡片与练习 |
| `kaoyan-official-info-researcher` | 核验当年大纲、报名、招生与考试安排 |

## 数据边界

- 发布者没有接收会话或文件的服务器。
- 插件不会保存计划、作答、进度或访问凭据，也不会暗示拥有跨会话记忆。
- 真题和学习材料只处理用户在当前会话提供或明确有权使用的内容。
- 跨会话继续时，用户可复制插件输出的 `StudyProfile`、`ProgressSnapshot` 或 `ReviewQueue`。
- 最新招考信息只以教育部、研招网和目标院校官方站点为主要依据；不能核验时会明确说明。

详见 [隐私政策](PRIVACY.md)、[使用条款](TERMS.md) 与 [第三方内容边界](THIRD_PARTY_CONTENT.md)。

## 安装与使用

### 从 GitHub marketplace 安装

仓库公开后，可在 Codex CLI 中添加并安装：

```text
codex plugin marketplace add yq6666-66/kaoyan-22408-codex-plugin
codex plugin add kaoyan-22408@kaoyan-22408
```

安装后新建任务，让宿主加载新的 Skills。也可在 ChatGPT 桌面端或 Codex 的插件目录中选择该 marketplace。

### 本地开发安装

在仓库根目录运行：

```powershell
./scripts/install-local.ps1
```

脚本从当前仓库解析路径，不复制个人数据，也不依赖某个缓存版本目录。若本机 Codex CLI 尚未提供插件子命令，脚本会完成验证并提示重启 ChatGPT 桌面端；桌面端会读取仓库中的 marketplace。

### 调用示例

Codex 使用 `$skill-name` 显式调用；ChatGPT 可从插件或 Skill 选择器调用。例如：

```text
使用 $kaoyan-22408-planner，根据 2026-12-26 的目标日期和每周 35 小时时间预算制定跨科周计划。
```

```text
使用 $kaoyan-mock-exam-coach，生成 10 道原创操作系统章节测；我交卷前不要显示答案或提示。
```

## 开发与验证

```text
python scripts/check.py
python scripts/build_release.py
```

`check.py` 运行仓库契约测试，并在本机存在官方插件与 Skill 校验器时一并执行。`build_release.py` 只把 manifest、12 个 Skills、三份共享契约与 SVG Logo 写入发布压缩包。

提交门户材料位于 `submission/`，其中测试集严格为 5 个正向场景和 3 个负向场景。公开目录提交仍需要通过 OpenAI Platform 的身份与权限检查。

## 支持与许可

- 问题与建议：[GitHub Issues](https://github.com/yq6666-66/kaoyan-22408-codex-plugin/issues)
- 安全问题：[SECURITY.md](SECURITY.md)
- 许可：[MIT](LICENSE)

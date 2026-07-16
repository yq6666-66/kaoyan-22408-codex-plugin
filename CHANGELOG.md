# 版本记录

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.1.0] - 2026-07-15

### 新增

- 增加便携学习记录 Schema 1.1 与机器可验证 JSON Schema，并兼容读取 1.0 记录。
- 增加跨平台 Python 安装器、确定的退出码和 PowerShell 薄包装。
- 增加 12 个多轮行为场景，与 36 个路由场景共同构成发布前动态评测门禁。
- 增加可重复 Release 构建、SHA-256 文件与 Windows/Ubuntu 字节一致性检查。

### 调整

- `kaoyan-review-executor` 现在可在没有长期计划时，根据本次目标、科目与时长安排单次学习时段。
- 统一 12 个 Skills 的正向与邻近负向路由，材料按用户意图而不是文件类型分流。
- 修正模考流程：用户自行计时；题面、版本、分值和通用 rubric 在出卷时冻结；明确交卷前不泄露答案或得分线索。
- 统一用户材料授权边界、证据标签和官方一手来源范围。
- GitHub 仓库成为唯一 marketplace 分发源；Release ZIP 只作为可审计、可校验的插件包。
- 本地安装器现在要求同名 marketplace 的规范化根路径与当前仓库完全一致，拒绝路径后缀或重复来源混淆。
- 本地安装器在 GBK/ASCII 等控制台中安全转义不可编码的 validator 日志字符，避免校验通过后因输出编码崩溃。
- 密钥扫描补充加密私钥、PGP 私钥、npm Token 与 GitLab Personal Access Token 类别，并覆盖当前发布树、完整 Git 历史和 Semgrep。

### 移除

- 移除与 GitHub repo marketplace 分发无关的提交流程材料。

## [1.0.0] - 2026-07-15

- 首次公开发布 12 个中文 Skills。
- 采用纯 Skills 架构，无 App、MCP、后台服务、账号系统或数据持久化。
- 不内置第三方题库、讲义、真题合集或解析库。

[1.1.0]: https://github.com/yq6666-66/kaoyan-22408-codex-plugin/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/yq6666-66/kaoyan-22408-codex-plugin/releases/tag/v1.0.0

# Obsidian 大脑契约

## 配置与迁移

每次 Skill 开始时检查当前用户目录 `.codex/kaoyan-408/obsidian-brain.json`。配置 Schema 1.1：

```json
{
  "schemaVersion": "1.1",
  "enabled": true,
  "vaultPath": "绝对 Vault 路径",
  "projectRoot": "20-项目/408考研",
  "knowledgeRoot": "30-知识/408考研",
  "pastPaperRoot": "40-真题/408考研",
  "writeMode": "auto-structured",
  "retrievalScope": "project-first"
}
```

- 新安装使用上述默认目录。
- 配置脚本可读取旧 `.codex/kaoyan-22408/obsidian-brain.json` Schema 1.0，并生成新配置；沿用旧 `vaultPath`、`projectRoot` 和已存在的旧知识目录，不移动、覆盖或删除私人笔记。
- 旧目录继续有效；配置脚本只在索引中增加“408考研插件”入口和别名。只有用户明确运行目录迁移操作时才移动文件。
- 不猜测或扫描 Vault。配置、Vault、根 `AGENTS.md` 或 `00-系统/知识库索引.md` 不可读时继续回答并降级。

## 有限检索

1. 先读 Vault `AGENTS.md`、总索引、`projectRoot/主页.md` 和 `projectRoot/记忆索引.md`。
2. 按主责读取最小记录：规划/诊断读档案与进度；执行读进度与错题；学科/模考读错题及主题；真题搜索/分析读 `pastPaperRoot/真题索引.md` 和对应科目年度；官方核验只读考试目标。
3. 优先检索 `projectRoot`、`knowledgeRoot` 和 `pastPaperRoot`。先读索引摘要，再打开必要正文；单轮最多使用 8 篇笔记、约 16,000 字符。
4. 实际使用的历史内容标 `[Obsidian记忆]` 并附 Vault 相对路径；它不是当前官方事实或真题来源证明。

## 结构化写入

- 学习档案、当前进度和错题队列继续使用便携记录 Schema 1.1。
- 真题来源、题目和原创解析使用真题知识 Schema 1.0，并按 `dedupeKey` 去重。
- `pastPaperRoot` 下建立 `真题索引.md` 和数学一、数学二、英语一、英语二、408五个科目目录；年度页同时记录 `paperYear` 和 `examDate`。
- Mermaid/SVG 源保存于解析页或其附件目录；只有许可证允许才保存试卷全文。
- 写入前重新读取目标；内容变化时合并并标待整理，不覆盖新内容。更新总索引和成长日志。
- 计划只能写 `planned`，用户报告完成后才写 `completed`；推测错因标 `hypothesis`，有复测证据后才标掌握。
- 不保存整段对话、凭据、身份信息、搜索缓存、未授权题库或第三方长篇解析。
- “忘记/删除”先定位，默认移动到 `90-归档/`，不直接永久删除。

## 控制与状态

用户说“本次不记忆”或“只读模式”时可检索但禁止写入；说“关闭大脑”时提示运行配置脚本 `disable`。失败不影响学习回答，并提供可复制记录。

- 成功：`Obsidian：已读取 N 条记忆；已更新 <相对路径>。`
- 只读：`Obsidian：已连接；已读取 N 条记忆；本轮只读，无写入。`
- 无命中：`Obsidian：已连接；未命中相关记忆；无写入。`
- 降级：`Obsidian：未连接（原因）；本轮使用会话信息。`

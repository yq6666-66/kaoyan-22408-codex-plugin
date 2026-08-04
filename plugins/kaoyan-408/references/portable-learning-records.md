# 便携学习记录契约 1.1

便携记录用于把当前会话结果复制到下一次会话。未启用 Obsidian 大脑时由用户自行保管并在需要时重新粘贴；启用后可按大脑契约在用户自己的 Vault 中结构化保存，但仍保持可复制、可审计和可迁移。机器校验规则见 [portable-learning-records.schema.json](portable-learning-records.schema.json)。

## 通用规则

- 新输出必须使用 `schemaVersion: "1.1"`，并包含正确的 `recordType`。
- 输出严格 JSON；日期使用 `YYYY-MM-DD`。未知值统一使用 `null`，不得使用空字符串、“未提供”或猜测值。
- `unit` 未知时使用兼容值 `"unspecified"`。正确率 `rate` 使用 `0` 到 `1`；`total` 为 `0` 时 `rate` 必须为 `null`。
- `correct` 与 `total` 同时存在时必须满足 `correct <= total`；`total` 为 `0` 时 `correct` 只能为 `0` 或 `null`。三者均有值时，`rate` 必须与 `correct / total` 一致；冲突值只报告并请求确认，不伪造修正。
- 不加入姓名、账号、凭据、设备路径、原始题面全文或与学习交接无关的信息。
- 解析旧对象时保留所有安全的未识别字段及其所在层级，不静默删除；迁移前说明发现的缺失、冲突或不兼容值。若未知字段含凭据、个人标识、设备路径或原始材料全文，隐私边界优先：把原字段值改为 `null`，在根级 `redactedFields` 记录其 JSON Pointer 路径，并明确说明已脱敏。
- 旧扩展字段与 1.1 规范字段同名且值冲突时，以有效的 1.1 字段承载规范值，把安全的旧值移入根级 `legacyExtensions`，以原 JSON Pointer 为键，并在 `migrationWarnings` 说明；无法安全确定规范值时先请求确认，不声称已经完成迁移。

机器校验时，Schema 根入口只接受新的 1.1 输出；读取旧记录时使用同一文件的 `#/$defs/legacyInput` 定义，规范化后再用根入口验证 1.1 结果。

## StudyProfile 1.1

规划师每次输出一个 `StudyProfile`。未知字段写 `null`，`constraints` 没有已知限制时使用空数组。

```json
{
  "schemaVersion": "1.1",
  "recordType": "StudyProfile",
  "targetExam": "408考研",
  "targetDate": "2026-12-26",
  "weeklyHours": 35,
  "currentPhase": "foundation",
  "constraints": ["周三晚不可学习"]
}
```

## ProgressSnapshot 1.1

执行器每次输出可回填对象：已计划的数据写入 `planned`，尚未完成的 `completed`、正确率和实际结果写 `null`。诊断师每次输出规范化对象，只整理用户实际提供的数据。

```json
{
  "schemaVersion": "1.1",
  "recordType": "ProgressSnapshot",
  "period": {
    "start": "2026-07-06",
    "end": "2026-07-12"
  },
  "metrics": [
    {
      "subject": "408",
      "name": "练习题",
      "unit": "questions",
      "planned": 10,
      "completed": 8
    }
  ],
  "accuracy": [
    {
      "subject": "408",
      "correct": 17,
      "total": 25,
      "rate": 0.68
    }
  ],
  "blockers": ["进程同步题耗时过长"]
}
```

不得把不同单位合并为一个数字；分钟、小时、章节和题数分别建立 `metrics` 项。

## ReviewQueue 1.1

错题闭环每次输出一个 `ReviewQueue`；模考在用户明确交卷并完成复盘后每次输出一个。没有待复测项时允许 `items: []`，但不得把当场答对直接标为 `mastered`。

```json
{
  "schemaVersion": "1.1",
  "recordType": "ReviewQueue",
  "generatedAt": "2026-07-15",
  "items": [
    {
      "subject": "408",
      "topic": "操作系统/进程同步/信号量",
      "errorCause": "把资源数量和等待进程数量混为一谈",
      "errorCauseStatus": "confirmed",
      "nextRetestDate": "2026-07-18",
      "retestOffsetDays": null,
      "status": "pending",
      "masteryEvidence": []
    }
  ]
}
```

- `errorCauseStatus` 使用 `confirmed`、`hypothesis` 或 `null`。
- `status` 使用 `pending`、`due`、`retesting`、`mastered` 或 `null`。
- 没有日历基准时，把 `nextRetestDate` 设为 `null`，在 `retestOffsetDays` 写非负整数。
- 掌握证据必须是延迟后独立作答与迁移表现等可观察事实；立即重做或自评不能单独证明掌握。

## Schema 1.0 兼容迁移

读取 1.0 后先规范化，再按 1.1 输出：

1. 根据对象字段补充 `recordType`，把 `schemaVersion` 更新为 `"1.1"`。
2. 根级 `plannedUnits/completedUnits` 转为一条 `metrics`：`subject: null`、`name: "overall"`。若旧扩展字段或等价记录明确给出单位则原样保留；只有单位未知时才写 `unit: "unspecified"`。
3. `bySubject` 中每个科目的 `plannedUnits/completedUnits` 分别转为 `metrics`，`name: "workload"`；优先保留该项实际提供的单位，只有未知时才写 `unit: "unspecified"`，不同已知单位不得合并。
4. 只有 `accuracy` 与 `sampleSize` 时，转为 `rate` 与 `total`，并把 `correct` 设为 `null`；不得由四舍五入的正确率反推出正确题数。
5. 旧 `retestDate: "D+N"` 转为 `nextRetestDate: null` 与 `retestOffsetDays: N`；合法绝对日期转入 `nextRetestDate`。
6. 旧版空字符串、`"未提供"`、`"unknown"` 等未知标量哨兵统一转为 `null`；`constraints`、`blockers`、`masteryEvidence` 等集合字段的未知哨兵转为空数组。未识别字段和字段冲突按通用规则处理，不静默覆盖或丢失。
7. 根据特征字段推断 1.0 对象类型；多个类型同时匹配时先说明歧义并请求最小确认，不擅自丢弃扩展字段。

纯讲题、翻译、写作批改或材料摘要不生成无意义的空记录；需要跨题复测时转交错题闭环。

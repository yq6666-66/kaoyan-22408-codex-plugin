# 便携学习记录契约

这些对象用于把当前会话结果复制到下一次会话。插件不保存对象；由用户自行保管并在需要时重新粘贴。

## 通用规则

- 使用 `schemaVersion: "1.0"`。
- 日期使用 `YYYY-MM-DD`；不知道时使用 `null`，不要猜测。
- 正确率使用 `0` 到 `1` 的小数，并同时给出样本量。样本量为 `0` 时正确率必须为 `null`。
- 不加入姓名、账号、设备路径、原始题面全文或其他与学习诊断无关的信息。
- 用户提供旧对象时，保留未知字段，修正前先说明不兼容或缺失之处。

## StudyProfile

用于规划所需的最小背景。

```json
{
  "schemaVersion": "1.0",
  "targetExam": "考研 22408",
  "targetDate": "2026-12-26",
  "weeklyHours": 35,
  "currentPhase": "foundation",
  "constraints": ["周三晚不可学习"]
}
```

`currentPhase` 建议使用 `foundation`、`intensive`、`past-paper`、`sprint` 或 `unknown`。

## ProgressSnapshot

用于诊断某个统计周期的完成情况。总量与分科数据可以只提供其一；不得用缺失值补出虚假精度。

```json
{
  "schemaVersion": "1.0",
  "period": {
    "start": "2026-07-06",
    "end": "2026-07-12"
  },
  "plannedUnits": 28,
  "completedUnits": 23,
  "accuracy": 0.72,
  "sampleSize": 50,
  "bySubject": [
    {
      "subject": "408",
      "plannedUnits": 10,
      "completedUnits": 8,
      "accuracy": 0.68,
      "sampleSize": 25
    }
  ],
  "blockers": ["操作系统进程同步题耗时过长"]
}
```

## ReviewQueue

用于记录需要复测的知识点与掌握证据。`status` 使用 `pending`、`due`、`retesting` 或 `mastered`。

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "2026-07-15",
  "items": [
    {
      "subject": "408",
      "topic": "操作系统/进程同步/信号量",
      "errorCause": "把资源数量和等待进程数量混为一谈",
      "retestDate": "2026-07-18",
      "status": "pending",
      "masteryEvidence": []
    }
  ]
}
```

掌握证据应写可观察事实，例如“间隔 7 天后独立正确完成两道变式题并能解释边界条件”。一次自评或立即重做正确不能单独证明掌握。

## Markdown 交接格式

当用户不需要 JSON 时，使用以下简表，字段含义保持一致：

```markdown
### 学习交接快照
- 目标与日期：考研 22408 / 2026-12-26
- 当前阶段：foundation
- 每周时间：35 小时
- 本周期：计划 28，完成 23；50 题正确率 72%
- 阻塞项：操作系统进程同步题耗时过长
- 下次复测：2026-07-18，信号量，pending
```

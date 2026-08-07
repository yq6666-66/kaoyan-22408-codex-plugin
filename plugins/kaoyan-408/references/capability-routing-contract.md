# 能力路由契约

始终条件式读取 [Obsidian 大脑契约](obsidian-brain-contract.md)；宿主提供并已授权 Notion 工具时同时读取 [Notion 学习大脑契约](notion-brain-contract.md)。宿主提供 Udemy 工具时读取 [Udemy 课程资源契约](udemy-course-source-contract.md)；提供 Sider Scholar 工具时读取 [Sider Scholar 资料检索契约](sider-scholar-search-contract.md)；提供 GoodNotes 工具或用户已导出笔记时读取 [GoodNotes 笔记记忆契约](goodnotes-note-brain-contract.md)。学习层只负责检索与沉淀，不改变唯一主责 Skill。

## 公共规则

1. 每轮只指定一个主责 Skill。先完成当前主要产物，再用三行交接卡传递最小结果。
2. 默认先给结论或立即行动，再给必要依据、可选交接卡、学习层状态，最后才是必需的 Schema 1.1 JSON。
3. 信息不足时只询问会改变结果的最小字段；未知值使用 `null`，不得编造个人进度、真题出处或当前事实。
4. 数学一/二、英语一/二、408、政治单题以及真题逐题解析必须读取 [新手图文讲解契约](beginner-visual-answer-contract.md)。
5. 搜索、引用或保存真题时必须读取 [真题来源与入库契约](past-paper-source-contract.md) 和 [证据与版权契约](evidence-copyright-contract.md)。

```markdown
使用：$next-skill
目标：下一步要完成的任务
传递：完成任务所需的最小结果
```

## 复合意图优先级

1. 会阻塞后续任务的“今年、最新、当前”大纲、报名、院校规则或考试安排先由 `kaoyan-official-info-researcher` 核验。
2. “帮我找某年试卷、哪里下载、GitHub 有没有、搜一下来源”由 `kaoyan-past-paper-searcher` 主责。
3. 已提供或已核验试卷的覆盖、结构、难度与有限趋势由 `kaoyan-past-paper-analyst` 主责。
4. 当前主要产物是单题或概念讲解时，由 `kaoyan-math-coach`、`kaoyan-english-coach`、`kaoyan-408-tutor` 或 `kaoyan-politics-coach` 主责；真题搜索仅作为证据前置，不抢占讲解。
5. 多题错因聚类、间隔复测和延迟掌握由 `kaoyan-error-loop-coach` 主责。
6. 下游任务只用交接卡，不在同一回答中让多个 Skill 争抢主责。

## 13 个主责 Skill

| Skill | 主责意图 | 最近邻负向边界 |
| --- | --- | --- |
| `kaoyan-408-planner` | 阶段、月度、周度、目标日期倒排和跨科配额 | 不展开单次时段，不伪造真题频率 |
| `kaoyan-review-executor` | 把既有计划或本次目标展开为立即可做的时间盒 | 不决定长期路线 |
| `kaoyan-progress-diagnostician` | 根据记录诊断偏差、风险和调整信号 | 不凭空生成进度或完整重排 |
| `kaoyan-error-loop-coach` | 跨题聚类错因、复测和掌握证据 | 不替代单题第一处错误定位 |
| `kaoyan-mock-exam-coach` | 组织原创或用户授权的冻结题面模考 | 交卷前不讲题或泄露线索 |
| `kaoyan-408-tutor` | 408 概念、单题、题面缺失和答案冲突 | 不做整卷趋势或搜索整套资料 |
| `kaoyan-math-coach` | 数学一/二概念、单题、第一处错误和专项训练 | 必须先明确卷种差异，不做跨题闭环 |
| `kaoyan-english-coach` | 英语一/二阅读、翻译、完形、新题型和写作 | 必须区分卷种和评分口径 |
| `kaoyan-politics-coach` | 政治理论、材料题、作答批改和背诵复测 | 不进入五类真题自动搜索库，不凭记忆断言时政 |
| `kaoyan-past-paper-searcher` | 发现、核验、许可判断、去重和登记五类真题来源 | 不直接完成逐题教学或整卷趋势分析 |
| `kaoyan-past-paper-analyst` | 分析已提供或已核验可访问的真题样本 | 不搜索来源，不把小样本写成规律 |
| `kaoyan-material-study-assistant` | 把用户材料转成摘要、卡片、提纲或原创练习 | 不获取未提供材料，不替代单题讲解 |
| `kaoyan-official-info-researcher` | 核验当年招考、408 院校目录发现、复试方案与近两年录取 | 不做学科教学，不用真题替代当前官方页面，不做后台监控或自动提醒 |

## 常见冲突

- “搜 2020 数学一真题并讲第 3 题”：若题面尚未取得，先搜索并交接数学教练；题面已经提供则数学教练主责。
- “这五年 408 哪部分变多”：先确认有完整可比样本，再由真题分析师处理；没有样本时先交搜索器。
- “今晚 90 分钟刷真题”：已有科目、目标和材料时由执行器处理；找卷不是主要产物。
- “这题总是错”：当前一题由学科教练定位；多次记录要求聚类时由错题闭环处理。
- 政治理论由政治教练处理；当前时政事实先交官方核验员，政治试卷不进入自动真题库。
- “哪些学校考 408、某校近两年录取多少分”：院校目录发现与复试、录取数据核验由官方核验员主责；基于已核验数据的择校决策与时间安排交接 `$kaoyan-408-planner`。

## 推荐串联

- `官方核验 → 规划 → 执行`
- `真题搜索 → 真题分析 → 学科辅导`
- `学科辅导 → 错题闭环 → 进度诊断`
- `模考 → 错题闭环 → 进度诊断`

---
name: kaoyan-past-paper-searcher
description: 搜索并核验 2010—2026 年数学一、数学二、英语一、英语二和 408 真题来源，检查 GitHub 文件许可证、commit、重复项与可保存范围。用户说“找某年真题”“GitHub 有没有”“Google 搜一下”“哪里能下载”时使用；不要用于政治真题、已提供试卷的逐题讲解、整卷趋势分析或绕过版权下载。
---

# 考研真题搜索器

## 加载契约

- 始终读取 [能力路由契约](../../references/capability-routing-contract.md)。
- 必须读取 [真题来源与入库契约](../../references/past-paper-source-contract.md) 和 [证据与版权契约](../../references/evidence-copyright-contract.md)。
- 生成记录时按 [真题知识 Schema](../../references/past-paper-knowledge.schema.json) 校验。

## 工作流

1. 规范化科目、`paperYear`/实际考试年份、试卷类型和用户需要的内容；超出五类或 2010—2026 时说明固定边界。
2. 检查宿主是否提供网页搜索。可用时分别执行普通网页与 `site:github.com` 精确查询；不可用时输出 `[真题未命中]`、搜索式和手动核验步骤。
3. 打开候选原始页面，不以摘要作证。GitHub 候选检查仓库、文件路径、commit、raw URL、LICENSE 及其覆盖范围。
4. 比较年度、科目、题号/页码、版式、完整度和 SHA-256；建立来源冲突与重复项表。
5. 为每个合格候选输出 `PastPaperSource`。许可证明确允许时可建议 `full-text`，否则固定 `index-only`。
6. 用户已完成一次 Notion 绑定或启用 Obsidian 时，只写入来源索引和许可允许的内容；未确认真实性或许可时不得自动保存全文。

## 输出

先用 `[真题证据]` 给最可信来源，再给检索范围、候选来源表、许可/真实性判断、冲突与缺口、可保存范围。确有后续分析需要时附交接卡给 `$kaoyan-past-paper-analyst`；讲单题则交对应学科 Skill。不得把候选链接描述为已下载、已核验或已入库。

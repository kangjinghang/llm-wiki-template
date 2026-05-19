---
title: "因子拥挤与因子衰减"
title_zh: "因子拥挤与因子衰减"
type: source
summary: "讨论因子拥挤的成因（套利资金涌入、策略同质化、市场结构变化）及应对方法（因子迭代、高频数据、机器学习）。"
tags: [量化投资, 因子投资, Alpha衰减]
sources: []
origin: agent-compiled
status: developing
created: 2026-05-19
updated: 2026-05-19
source_type: article
source_language: zh
raw_path: "raw/articles/factor-crowding-and-decay.md"
---

# 因子拥挤与因子衰减

## Abstract / 摘要

本文讨论因子拥挤现象的三个成因——套利资金涌入导致定价收窄、策略同质化引发持仓共振、市场结构变化加速 Alpha 衰减——并提出因子迭代、高频数据挖掘、机器学习三种应对思路。

## Key Facts / 关键事实

- 因子拥挤本质是过多资金追逐同一个错误定价，导致套利空间消失
- A 股量化私募规模从 2017 年约 1000 亿增长到 2021 年约 1 万亿
- 传统日频因子（价值、动量）因广为人知，持续衰减
- 高频数据因开发门槛高、数据量大的特点，因子拥挤度较低
- 深度学习方法可在 76 个日频变量中提取非线性选股特征

## Related Pages / 关联页面

- [[Factor-Crowding]] — 因子拥挤的概念页
- [[High-Frequency-Factor-Mining]] — 高频因子挖掘
- [[Deep-Learning-Factor-Extraction]] — 深度学习因子提取
- [[GF-Securities-Quantitative-Research]] — 广发金融工程研究团队

## Evidence / 原文证据摘录

> 因子拥挤是因子收益下降的原因之一。因子代表着市场某方面的非有效性、或者是一段时期内的定价失效。当某类因子收益高的时候，会吸引更多的资金进入，从而出现因子拥挤，降低因子的预期收益。

## Claims to Verify / 待核实问题

- "A 股量化私募规模从 1000 亿增长到 1 万亿" — 需要核实具体年份和数据来源
- 深度学习特征在中证 500 的 26% 年化超额收益 — 回测区间未明确

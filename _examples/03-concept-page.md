---
title: "Factor Crowding"
title_zh: "因子拥挤"
type: concept
summary: "当过多投资者使用同一因子时，该因子的预期收益下降的现象。核心机制是套利资金涌入压缩定价空间。"
tags: [量化投资, 因子投资, Alpha衰减]
sources: [raw/articles/factor-crowding-and-decay.md]
origin: agent-compiled
status: developing
created: 2026-05-19
updated: 2026-05-19
---

# Factor Crowding / 因子拥挤

## Definition / 定义

因子拥挤（Factor Crowding）是指当某个选股因子被过多投资者同时使用时，因子预期收益下降的现象。因子代表市场的非有效性或一段时期内的定价失效，当资金涌入利用这种非有效性时，错误定价被收窄，因子收益随之衰减。

## How It Works / 工作原理

因子拥挤的传导机制有三个阶段：

1. **发现期** — 少数投资者发现某因子有效，获取超额收益
2. **拥挤期** — 因子收益公开后，更多资金进入，持仓高度重叠
3. **衰减期** — 错误定价被充分套利，因子收益显著下降；极端情况下平仓共振导致因子大幅回撤（如 2007 年 August Quant Quake）

## Why It Matters / 为什么重要

- 因子拥挤是理解 Alpha 衰减的核心框架
- 对个人投资者：使用广为人知的因子大概率无法获得超额收益
- 对策略开发：需要不断迭代新因子、转向低拥挤度的数据源（如高频数据）
- 对风险管理：拥挤度指标可以作为因子配置的风险调整维度

## Examples / 示例

- **A股量化扩容** — 2017-2021 年量化私募规模 10x 增长，传统价量因子持续衰减
- **Value Factor** — 价值因子在 2017-2020 年全球范围内表现疲软，部分原因即为过度拥挤
- **Momentum Crash** — 2009 年 3 月动量因子极端回撤，拥挤持仓被迫平仓是重要原因

## Related Pages / 关联页面

- [[High-Frequency-Factor-Mining]] — 高频因子是应对拥挤的方案之一
- [[Deep-Learning-Factor-Extraction]] — 深度学习提取的因子因复杂性高、拥挤度低
- [[因子拥挤与因子衰减]] — 讨论拥挤问题的来源文章

## Sources / 来源

- raw/articles/factor-crowding-and-decay.md

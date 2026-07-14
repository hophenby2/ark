# Roguelike 区域规则核对矩阵

> 状态：第一阶段骨架，尚未完成 PRTS 区域章节的逐项转录
> 运行时：未接入
> 数据文件：[zone_routes.json](../data/rlv2/rules/zone_routes.json)

## 1. 使用边界

本文只把客户端表事实、用户已确认口径和仍待 PRTS 核对的内容分开。它不是地图生成器规格，也不授权当前运行时随机开启隐藏路线。

- 客户端表可证明区域 ID、名称与 `isHiddenZone`。
- 用户确认后续区域奖励先按第六档记录，但未确认完整进入条件、前后继、Boss/事件替换和结算顺序。
- 特殊区域奖励跟随实际关卡规则，不从 cursor zone 或第六档区域规则推断。
- PRTS 的自然语言进入条件在转换成无歧义 AST 前，只能保存为来源文本。

## 2. zone 6/7/8 客户端事实

| 主题 | 区域 | 名称 | `isHiddenZone` | 暂记奖励档位 | 路线状态 |
| --- | --- | --- | --- | --- | --- |
| RO1 | `zone_6` | 渴欲大厅 | true | 6 | 进入条件、前后继待核对 |
| RO2 | `zone_6` | 幽海丛林 | true | 6 | 进入条件、结局映射待核对 |
| RO2 | `zone_7` | 绀碧摇篮 | true | 6 | 进入条件、结局映射待核对 |
| RO3 | `zone_6` | 远见之构 | true | 6 | 进入条件、结局映射待核对 |
| RO3 | `zone_7` | 永恒之尘 | true | 6 | 进入条件、结局映射待核对 |
| RO4 | `zone_6` | 辉光天顶 | false | 6 | 实际路线角色待核对 |
| RO4 | `zone_7` | 逍遥兰若 | false | 6 | 替代/分支关系待核对 |
| RO4 | `zone_8` | 无终安息 | false | 6 | 终局关系待核对 |
| RO5 | `zone_6` | 始末陵 | false | 6 | 实际路线角色待核对 |
| RO5 | `zone_7` | 明灭顶 | false | 6 | 替代/分支关系待核对 |
| RO5 | `zone_8` | 来去处 | false | 6 | 终局关系待核对 |

`rewardTier=6` 是用户确认的待接线口径，不会被解释为 `min(zone, 6)`，也不会泛化到未知 zone。

## 3. 特殊区域策略

| 主题 | stage 候选 | event pool | 已确认 | 待核对 |
| --- | --- | --- | --- | --- |
| RO2 | 第 5/6 层关卡 | 继承进入前区域 | 用户确认 | 特殊区域 ID、stage ID、权重、节点排布 |
| RO3 | 当前层关卡 | 独立池 `special_region_ro3` | 用户确认 | 独立池成员、人工 tag、区域 ID、节点排布 |
| RO4 | 当前层与下一层关卡 | 继承进入前区域 | 用户确认 | 上界、stage ID、权重、是否包含 Boss/紧急 |
| RO5 | `null` | `null` | 未提供，不外推 | PRTS 区域章节完整规则 |

## 4. PRTS 转录清单

下一步按主题逐项固定页面 URL、revision 和访问日期，再填写以下矩阵：

| 主题/结局 | 进入条件原文 | 条件 AST | 有序区域 | Boss/事件替换 | 节点列容量与类型 | 来源 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RO1 | 待转录 | `null` | `null` | `null` | `null` | `null` | `needs_review` |
| RO2 | 待转录 | `null` | `null` | `null` | `null` | `null` | `needs_review` |
| RO3 | 待转录 | `null` | `null` | `null` | `null` | `null` | `needs_review` |
| RO4 | 待转录 | `null` | `null` | `null` | `null` | `null` | `needs_review` |
| RO5 | 待转录 | `null` | `null` | `null` | `null` | `null` | `needs_review` |

## 5. RO4 旗帜/印象重建

当前不能确认“旗帜挑战”就是 PRTS 的“印象重建”。`levelReplaceIds` 在普通关卡中也存在，不能作为识别依据。后续核对时必须记录：

- PRTS 对应章节的固定 revision 与原文语义。
- 客户端 map/node/stage 中可稳定识别的字段。
- 普通与对应变体的 stage ID、奖励差异和刷新后行为。

在三项完成前，`zone_routes.json` 中该关联保持 `null`，运行时保持现状。

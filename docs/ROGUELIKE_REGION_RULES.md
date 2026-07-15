# Roguelike 区域与结局规则核对矩阵

> 状态：固定 revision 首轮转录完成；36 条核心线性区域、22 条结局终点及显式核心路线已接入运行时，特殊/平面区域仍未接入
> 目标版本：客户端 `2.7.51 / Data 26-07-10`
> 数据文件：[zone_routes.json](../data/rlv2/rules/zone_routes.json)

## 1. 使用边界

本文记录客户端区域/结局身份与 PRTS 固定版本“区域”章节之间可复核的交集。它是当前核心生成器和 EndingRoute 的事实输入之一，但不是完整拓扑规格，也不授权运行时随机开启特殊/平面区域。

- 客户端表证明 zone、ending、stage 与 `bossIconId` / `specialNodeId`。
- PRTS 固定页面证明核心区域的节点长度、最大分支数、布局摘要、结局卡所属区域和“进入方式”原文。
- `sourceLayoutText` 和 `entryConditionText` 保留来源语义，但尚未转成节点图或条件 AST。
- 特殊区域奖励仍跟随实际关卡规则，不能从 cursor zone、`rewardTier=6` 或区域编号推断。
- 来源 JSON 的新增记录仍保留 `runtimeEnabled=false`，避免把整段自然语言直接当可执行规则；运行时只通过 `server/rlv2_rules.py`、`server/rlv2_ending_rules.py` 消费人工审核后的核心线性投影。同步工具只在维护时联网。

## 2. 固定来源

| 主题 | 页面 revision | MediaWiki SHA-1 |
| --- | ---: | --- |
| `rogue_1` | `408420` | `b602537278585d7040c4c526fe25ad4e8145c64f` |
| `rogue_2` | `408421` | `ccd182ace56c5800f4293801f97f663aca7b3d9d` |
| `rogue_3` | `408422` | `851ae40d3aed08731e74c6b08ae209f424cee113` |
| `rogue_4` | `408423` | `ca39b2ac37db1afbc6f834dfaa6e82ca0e207179` |
| `rogue_5` | `408424` | `519659b991f4ce965ebad7837a1ae938f37c693f` |

脚本同时校验客户端 topic table 的规范化 LF SHA-256：`643df7574c8955c827bec2645ed09c06df44bc6654a85ead96002a8298b91bb6`。

## 3. 核心线性区域

共转录 36 条 `areaLayouts`。下表每格为 `baseNodeLength / maximumBranches`；RO5 前两层的来源长度原文为 `4（+1）`，因此 JSON 另保留 `nodeLengthText`，基础值仍为 4。

| 主题 | zone 1 | zone 2 | zone 3 | zone 4 | zone 5 | zone 6 | zone 7 | zone 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rogue_1` | `4/3` | `4/3` | `6/3` | `6/3` | `7/3` | `4/1` | - | - |
| `rogue_2` | `5/3` | `5/3` | `6/4` | `6/4` | `7/4` | `4/1` | `4/2` | - |
| `rogue_3` | `4/3` | `4/3` | `5/4` | `5/4` | `6/4` | `4/2` | `5/1` | - |
| `rogue_4` | `4/3` | `5/3` | `6/4` | `6/4` | `8/4` | `5/2` | `5/2` | `1/1` |
| `rogue_5` | `4(+1)/3` | `4(+1)/4` | `5/4` | `5/4` | `6/4` | `5/2` | `6/1` | `2/1` |

每条记录都保留完整 `sourceLayoutText`，包括“至少出现”“不会出现”和《扩园篇》替代布局等限定。当前没有把 `？个`、wiki 模板或自然语言保证解释为精确列容量、节点白名单、纵向连接或生成概率。

同名客户端变体不会自动共享核心布局。`identityResolution.excludedCandidateZoneIds` 明确列出 RO1 portal zone、RO4 `zone_portal_end_3` 和 RO5 `_b` zone 等被排除候选。

## 4. 结局终点映射

客户端共有 23 个 ending；固定区域章节可放置其中 22 个：

| 主题 | `zone_5` | `zone_6` | `zone_7` | `zone_8` |
| --- | --- | --- | --- | --- |
| `rogue_1` | `ro_ending_1`, `ro_ending_2` | `ro_ending_3`, `ro_ending_4` | - | - |
| `rogue_2` | `ro2_ending_1`, `ro2_ending_2` | `ro2_ending_3`, `ro2_ending_4` | 非结局特殊区域 | - |
| `rogue_3` | `ro3_ending_1`, `ro3_ending_2` | `ro3_ending_3` | `ro3_ending_4` | - |
| `rogue_4` | `ro4_ending_1`, `ro4_ending_2` | `ro4_ending_3` | `ro4_ending_4` | `ro4_ending_5` |
| `rogue_5` | `ro5_ending_1`, `ro5_ending_2` | `ro5_ending_3` | `ro5_ending_4` | `ro5_ending_5` |

20 条结局卡具有明确“进入方式”，其 wikitext 保存到 `entryConditionText`；RO1 `ro_ending_1` 和 RO2 `ro2_ending_1` 的卡片没有该标题，因此保持 `null`。全部 `entryConditionAst` 均为 `null`，入口原文中的事件、收藏品、难度与资源条件不得直接执行。

Boss stage 只按客户端等式 `ending.bossIconId == stage.specialNodeId` 推导。该等式可能得到多个难度/变体 stage；全部候选都会保留。事实文件中 RO1 `ro_ending_1` 的 `bossIconId=null`，所以 `bossStageIds` 保持 `null`，不根据名称猜测；运行时适配器另以固定 PRTS 终点和客户端 stage 目录显式覆盖为 `ro1_b_6`。

`endingZones` 只聚合非标准终局区域；每个结局的来源事实位于 `endingRoutes`。数据文件中的条件 AST、事件替换和结算顺序仍未结构化；运行时另由 `server/rlv2_ending_rules.py` 保存经审核的 `orderedZones/bossEndings`，支持核心 zone 6/7/8、关键物品改线及未访问 Boss 替换，但不覆盖特殊/平面区域和历史解锁。

## 5. Quarantine

| 记录 | 类型 | 候选 | 隔离原因 |
| --- | --- | ---: | --- |
| `rogue_3:ro3_ending_c` | ending | 2 个同 boss stage，zone 未知 | 客户端有“短暂光芒”，固定区域章节没有对应结局卡；共享 Boss 图标不能证明终点 |
| `rogue_3:prts-area:deep-buried-maze` | area | 330 zones | “深埋迷境”有 9 种来源布局，页面没有逐一绑定客户端变体 |
| `rogue_4:prts-area:bizarre-chapter` | area | 12 zones | “诡谲断章”存在通用和事件专属布局，客户端同名 ID 未消歧 |
| `rogue_4:prts-area:no-end-rest-extra` | area | 1 zone | 特殊失败区与核心“无终安息”同名，且没有线性长度/分支摘要 |
| `rogue_5:prts-area:past-present-realm` | area | 1 zone | “今昔境”为 5x5 平面区域，不适用线性布局模型 |
| `rogue_5:prts-area:right-wrong-realm` | area | 2 zones | “是非境”为 5x7 平面区域，且有两个同名客户端 ID |

Quarantine 中保留来源布局文本和全部 canonical 候选，不会进入运行时候选池。

核心线性区域已完成 36 个 `theme × zone` 各使用固定 seed `hard-property-0..2499` 的硬性质审计：共 90000 张地图、849924 个节点，全部通过可达性、边引用、分支上限、固定列、Boss/stage 完整性和同 seed 复现检查。该结果不包含下列 quarantine 特殊/平面区域。

## 6. 特殊区域与旗帜边界

现有 `specialRegions` 继续保留用户确认的 RO2-RO4 stage 深度与 event pool 口径；这些规则没有因本次页面转录而升级为客户端事实。RO5 策略仍为 `null`，不从其他主题外推。

RO4“旗帜挑战”是否等于 PRTS“印象重建”仍未确认。`levelReplaceIds` 在普通关卡中也存在，不能作为识别依据；`flagVariantMapping.equivalent`、检测字段、stage IDs 和奖励 variant 继续保持 `null`。

## 7. 维护与验证

```bash
python3 tools/sync_rlv2_prts_regions.py
python3 tools/sync_rlv2_prts_regions.py --check
```

同步器固定校验页面 revision/SHA-1、topic table SHA-256、36 条核心布局、22 条结局路线、20 条入口原文、6 条 quarantine，以及所有 zone/ending/stage canonical 引用。生成结果仍需通过 Draft 2020-12 Schema 与跨文件引用检查后才能提交；运行时不得访问 PRTS。

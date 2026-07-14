# RLV2 离线规则数据

本目录是 `2.7.51` Roguelike 规则的版本化离线事实层，当前没有被运行时加载。新增或修改这里的 JSON 不会改变服务器行为。

## 文件分层

| 类型 | 文件 | 内容 |
| --- | --- | --- |
| 元数据 | `manifest.json` | 目标版本、实际 GameData 来源、外部来源与文件清单 |
| 契约 | `rules.schema.json` | 所有 JSON 文档的 Draft 2020-12 Schema |
| 客户端事实 | `themes.json` | 主题名称、客户端 module type 和资源 ID |
| 客户端事实 | `collectibles.json` | `items[type=RELIC]` 的 canonical 藏品目录 |
| 客户端事实 | `stages.json` | 关卡 ID 与客户端直接给出的关卡元数据 |
| 客户端事实 | `zones.json` | 区域 ID、名称与客户端区域属性 |
| 客户端事实 | `scenes.json` | choice scene ID 与展示元数据；不等同于可随机事件池 |
| 人工规则 | `relic_tags.json` | 藏品 tag、池定义和待核对成员关系 |
| 人工规则 | `event_tags.json` | scene 到事件/楼层/模式/特殊区域的注解，以及不能唯一映射的 quarantine |
| 人工规则 | `battle_reward_rules.json` | 基础矩阵、领取策略、Boss/紧急/乘区规则意图 |
| 人工规则 | `zone_routes.json` | 核心区域布局、结局终点、特殊区域和不能唯一映射的 quarantine |
| 人工规则 | `modules.json` | 五主题模块描述和 RO1 剧目确认项 |

## 来源优先级

1. 当前客户端表和同版本真实协议样本。
2. 固定 revision 的 PRTS/官方资料。
3. Tomimi 整理表中人工核验后的单条事实。
4. 旧视频或统计资料，只能作为近似和回归参考。

运行时不得访问这些外部来源。Tomimi 页面不在仓库中镜像；只保存人工核验后的结构化事实、定位信息和核对状态。

## 状态语义

- `client_verified`：当前客户端表或同版本协议可直接证明。
- `public_sourced`：有固定 URL/revision 的公开资料支持，但未由客户端协议证明。
- `user_confirmed`：本轮人工确认，尚缺可复核外部证据。
- `needs_review`：字段、范围、映射或证据仍不完整。
- `rejected`：已确认不能使用的旧假设。

`reviewStatus`、`implementationStatus` 和 `runtimeEnabled` 是三个独立维度。规则得到确认，不代表代码已实现；代码现有近似行为，也不代表规则已经证实。

## 事件资料同步状态

五个主题的 PRTS“事件一览”页面已固定到 revision，并与客户端 scene 目录交叉核对：

| 主题 | 页面事件 | canonical 注解 | quarantine | 有明确楼层 |
| --- | ---: | ---: | ---: | ---: |
| `rogue_1` | 45 | 45 | 0 | 38 |
| `rogue_2` | 53 | 53 | 0 | 46 |
| `rogue_3` | 44 | 42 | 2 | 29 |
| `rogue_4` | 50 | 50 | 0 | 33 |
| `rogue_5` | 62 | 60 | 2 | 25 |
| 合计 | 254 | 250 | 4 | 171 |

`floor=` 只转成 `eligibility.logicalDepths`。页面没有证明的 `zoneIds`、`modes`、`endingIds`、`conditionAst` 和 `weight` 均保持 `null`。RO3 标准 scene 与同名 `month*` scene 不共用 canonical ID；被排除的候选保留在 `identityResolution` 中。无法唯一消歧的特殊节点/变体只进入 `quarantine`，不得进入候选池。

## 区域资料同步状态

五个固定主题页的“区域”章节已与客户端 zone、ending 和 stage 目录交叉核对：

| 主题 | 核心线性布局 | 结局路线 | 明确“进入方式” | quarantine |
| --- | ---: | ---: | ---: | ---: |
| `rogue_1` | 6 | 4 | 3 | 0 |
| `rogue_2` | 7 | 4 | 3 | 0 |
| `rogue_3` | 7 | 4 | 4 | 2 |
| `rogue_4` | 8 | 5 | 5 | 2 |
| `rogue_5` | 8 | 5 | 5 | 2 |
| 合计 | 36 | 22 | 20 | 6 |

`sourceLayoutText` 只保存页面布局摘要，尚未转成生成器图约束；`entryConditionText` 只保存入口原文，全部 `entryConditionAst=null`。Boss stage 仅按客户端 `ending.bossIconId == stage.specialNodeId` 推导；RO1 基础结局没有 `bossIconId`，因此不猜测 stage。`ro3_ending_c` 和不能唯一绑定的线性/平面特殊区域保留在 quarantine。完整边界见 [ROGUELIKE_REGION_RULES.md](../../../docs/ROGUELIKE_REGION_RULES.md)。

## 空值语义

- `null`：未知或尚未核对。
- `[]` / `{}`：已知集合当前为空。
- 字段缺失：该记录不适用此字段。

不得使用空数组同时表示“未知”“允许所有”或“禁止所有”。未确认的池成员、stage 绑定和路线关系必须使用 `null`。

## ID 与引用

- canonical ID 只来自 `roguelike_topic_table.json`。
- scene、choice、zone 等可能跨主题重复，外部唯一键为 `(theme, id)`。
- `xx123` 形式只允许写入 `sourceAliases`，不得替换客户端 scene ID。
- 藏品目录只取 `details.<theme>.items[id].type == "RELIC"`。`details.<theme>.relics` 混有其他类型，不能直接当目录。
- `levelReplaceIds` 只保留客户端引用，不据此推断楼层、旗帜或奖励变体。
- `poolRef` 必须指向 `poolDefinitions[].id`；tag 选择器只允许出现在对应 pool definition 内。
- 无匹配规则时禁止回退到普通/紧急收益、全主题事件池或任意藏品池。

## 维护流程

1. 更新 `data/excel` 后先核对 GameData commit、Data 版本和 topic table SHA-256。
2. 重新生成五个客户端事实文件，并核对 manifest 中逐主题记录数。
3. 保持人工规则文件独立；事件/区域同步只刷新各自生成字段和对应未决项，并保留人工 tag、奖励、特殊区域与 identity policy。
4. 新增人工事实时先登记 source，再添加 `sourceRefs`、`reviewStatus` 和具体适用范围。
5. 解析全部 JSON、执行 Schema 校验并检查跨文件 ID 引用。

PRTS 同步是维护时联网操作，不是运行时依赖：

```bash
python3 tools/sync_rlv2_prts_events.py
python3 tools/sync_rlv2_prts_events.py --check
python3 tools/sync_rlv2_prts_regions.py
python3 tools/sync_rlv2_prts_regions.py --check
```

脚本只访问 manifest 已登记且由工具固定的 MediaWiki revision，并同时校验 revision SHA-1 与客户端 topic table 的规范化 LF 哈希。事件同步另校验 scene 标题/开场描述、254/250/4 总数和 171 条楼层映射；区域同步另校验 36/22/20/6 总数及 zone/ending/stage 引用。CRLF/LF 只在 topic table 哈希前规范化，其他内容差异仍会失败。

当前只新增维护期同步工具，不包含运行时 adapter；接线工作按 [ROGUELIKE_RULES_PLAN.md](../../../docs/ROGUELIKE_RULES_PLAN.md) 后续阶段单独实施。

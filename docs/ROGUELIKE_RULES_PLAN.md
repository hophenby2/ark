# Roguelike 离线规则建设计划

> 建立日期：2026-07-14
> 目标客户端：国服 `2.7.51`
> 当前边界：只建设版本化离线数据，不修改运行时逻辑

## 1. 结论

后续不直接把 PRTS、Tomimi 或人工结论写进 handler。先建立两层离线数据：

1. **客户端事实目录**：从当前 `roguelike_topic_table.json` 机械提取主题、藏品、关卡、区域和场景的 canonical ID 及可直接证明的字段。
2. **人工规则注解**：保存奖励池、事件资格、区域路线和主题模块规则。每条关系单独记录来源与核对状态，未确认值保持 `null`。

两层数据在接入前均设置 `runtimeEnabled=false`。本阶段不修改 `server/`、SQLite schema、handler、地图生成器、状态机或现有测试预期。

## 2. 数据基线

- 目标版本统一为客户端 `2.7.51`。Windows 是当前工作配置，平台角色不作为已验证规则事实；Android 是本地表快照来源。
- 当前 `data/excel` 来自 Android Data `26-07-10-13-49-06_a14b4a`，GameData commit 为 `634e7e7d12c9d099c55896d51b4cf8ef633fa2a5`。
- `roguelike_topic_table.json` SHA-256 为 `643df7574c8955c827bec2645ed09c06df44bc6654a85ead96002a8298b91bb6`。
- Windows Data `26-07-10-13-52-38_fcd8ed` 是目标配置，不冒充当前本地表的提取来源。
- 公开资料只在人工核验后转成结构化事实；运行时不访问网络。

## 3. 分阶段方案

| 阶段 | 工作 | 逻辑改动 | 验收 |
| --- | --- | --- | --- |
| 1. 离线事实层 | 建 manifest、Schema、客户端事实目录、人工规则骨架和区域核对文档 | 无 | JSON 可解析并通过 Schema；ID 按主题唯一；未知值不被补猜 |
| 2. 资料同步 | 按固定 revision 人工核验 PRTS/Tomimi 的藏品、事件、Boss、特殊区域和结局资料 | 无 | 每条关系有 `sourceRefs` 和状态；跨表引用可解析；歧义进入 quarantine |
| 3. 战斗奖励接线 | 接 EXP 自动结算、可跳过奖励、职业券、紧急藏品、Boss 藏品和乘区 | 有 | 只命中显式 stage/variant；未知规则不回退；奖励可重放测试通过 |
| 4. 事件与藏品接线 | 实现 typed adapter、条件 AST、效果解释器和标签池 | 有 | 未知条件/效果不静默成功；事件与藏品资格均可追踪来源 |
| 5. 区域与地图 | 实现特殊区域池、EndingRoute、约束式地图生成并修复无 stage Boss 节点 | 有 | 每个支持的 `theme × zone` 以 2500 固定种子通过硬性质测试 |
| 6. 主题模块 | 先接 RO1 剧目，再按 PRTS 描述逐项实现 RO2-RO5 | 有 | 每个模块有状态转移表、fixture 和边界测试 |

## 4. 第一阶段文件

`data/rlv2/rules/` 分为两类文件：

- `themes.json`、`collectibles.json`、`stages.json`、`zones.json`、`scenes.json`：当前客户端表的机械快照。
- `relic_tags.json`、`event_tags.json`、`battle_reward_rules.json`、`zone_routes.json`、`modules.json`：人工核验规则及本次用户结论。
- `manifest.json`、`rules.schema.json`、`README.md`：版本、来源、契约和维护边界。

人类可读的区域核对矩阵单独保存在 [ROGUELIKE_REGION_RULES.md](./ROGUELIKE_REGION_RULES.md)。

第一阶段只会将能由客户端表直接证明的字段写入事实目录：

- 藏品按 `items[id].type == "RELIC"` 过滤；不把 `details.<theme>.relics` 中混入的其他物品当藏品。
- 关卡保留原始 `stageId`、Boss/紧急标记和变体引用；不从 ID 或 `levelReplaceIds` 猜楼层、旗帜或奖励。
- 场景只称为 scene；在完成 PRTS/Tomimi 映射前，不把所有 `choiceScenes` 宣称为可随机事件。
- scene、zone 等可能跨主题重名的 ID 一律使用 `(theme, id)` 作为外部键。

## 5. 已确认并先记录的规则

- EXP 自动结算；gold、职业券、藏品均可不领并直接结束奖励阶段。
- 普通/紧急战斗各给随机职业券；第 3/5 层存在两张随机职业券二选一规则，但适用战斗范围仍待核对。
- 紧急作战额外掉落随机藏品；各额外掉落独立判定。
- Boss 使用 `(theme, stageId, variant, context)` 显式表；价值 16 的藏品基础二选一，候选数增益按加算处理。
- EXP/gold 增益连乘，其他增益加算；具体 modifier、顺序与舍入仍待核对。
- 特殊区域奖励由关卡决定。RO2 候选深度为 5/6，RO3 为当前层且使用专属事件池，RO4 为当前层/下一层；RO5 未外推。
- 后续 zone 6/7/8 的区域奖励先记录为第六档，但不据此启用路线或覆盖特殊区域的 stage 规则。
- 重名事件的 `xx123` 只作为来源别名，不替换客户端 scene ID。
- RO1 剧目记录战后 50%、等权、目标节点开始触发、未命中不消耗、换层重置；可达范围与消费细节保持未决。

这些规则目前没有同版本协议样本或逐条外部证据，统一标为 `user_confirmed` 或 `needs_review`，不能标为 `client_verified`。

## 6. 明确暂缓

- `finishGame/gameSettle` 与 per-UID outer 存储不改。
- 状态转移矩阵、request-id 幂等和空 `202` 接口行为不改。
- UID 保持单机非安全模式，不清理旧大写 `Windows` 配置。
- 不修复地图、Boss 池 regex 或当前 gold 强制领取行为；这些只作为已知差异记录。

## 7. 仍需核对

- 第 3/5 层券二选一的 battle kind、职业去重、权重和协议外形。
- Boss stage 清单、EXP/gold、减半项目和舍入。
- `售价 8/16` 对应的规范经济字段，以及藏品池的实际成员。
- RO2-RO5 特殊区域的具体 stage/event ID、节点排布和完整路线。
- RO4“旗帜”是否等同 PRTS“印象重建”。
- 完整乘区目录、顺序、舍入和“其他增益”的准确范围。
- RO1 剧目的可达范围、命中后消费、重复与累计上限。

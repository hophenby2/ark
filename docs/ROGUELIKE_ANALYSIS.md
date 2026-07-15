# Roguelike 模块分析与原版拟合路线

> 审计日期：2026-07-15
> 客户端基准：国服 `2.7.51`，资源版本 `26-07-10`（仓库配置中的完整资源版本为 `26-07-10-13-49-06_a14b4a` / `26-07-10-13-52-38_fcd8ed`）  
> 范围：`rogue_1` 至 `rogue_5`。`rogue_0` 是项目测试入口，不作为原版主题讨论。

## 1. 结论

当前模块已经从“返回客户端所需外形的演示实现”推进到“可以完成开局、招募、移动、战斗、事件和商店基本闭环”的阶段。开局参数、等级表、招募券和干员过滤等逻辑已开始直接读取当前客户端表，这是正确方向。

它仍不能被视为原版规则模拟器。主要差距不是几个数值，而是以下三类服务端规则尚未建模：

1. 核心地图已接入 36 条区域约束、22 条结局 Boss/终点和显式隐藏层路线，但问号节点权重、详细拓扑、特殊/平面区域及区域专属状态仍未完整建模。
2. 事件已按楼层、节点类别及一组藏品/模块门槛过滤，并实现经审核的结局事件链子集；模式、历史解锁、完整 eligibility、随机权重和五主题核心模块状态仍不完整。
3. 终局目前只有零奖励的安全清局闭环，原版分数、BP 和外层奖励仍未实现；除 `battleFinish` 重试外，动作级幂等和若干状态机分支仍不完整，多个已注册接口仍返回空 `202`。

按 UID 的存档隔离与事务基线已经落地，因此后续顺序调整为“状态机与终局协议 -> 表驱动的公共规则 -> 地图生成 -> 五主题机制 -> 协议回归”，而不是继续堆叠事件特判。

本轮已经落地的高置信修复包括：SQLite 按 UID 保存 run、随机种子与 revision，动作级 `BEGIN IMMEDIATE` 事务与 revision/CAS，Legacy 单一 owner 迁移，`SyncData` 按 UID 合并唯一真源；以及按表开局与等级/招募规则、事件支付与门禁、商店库存、战斗结算和零奖励安全清局。新增的结局规则会按关键物品更新 `toEnding/chgEnding`，以显式 `orderedZones/bossEndings` 驱动 zone 6/7/8、ending5 underlay 和当前未访问 Boss 替换；新增事件 overlay 接入 RO1 关键链、RO2 灯火门槛/骑士死亡、RO4 构想炼金及 RO3-5 经审核剧情/结局事件。完整主题模块、特殊区域、历史结局解锁、奖励池和原版外层结算仍属于后续阶段。

## 2. 证据使用原则

原版服务端实现并不公开，客户端表也不包含全部抽取权重和状态转移。本文按以下优先级处理冲突：

| 优先级 | 资料 | 适合确认 | 不应直接推断 |
| --- | --- | --- | --- |
| 1 | 当前客户端表、同版本真实协议样本 | ID、枚举、初始值、表间引用、协议字段、奖励与 Buff 描述 | 表中不存在的服务端随机权重 |
| 2 | PRTS、官方专题/公告 | 公开玩法规则、术语、主题差异、版本时间线 | 精确内部概率、未标注版本的隐藏规则 |
| 3 | 腾讯表格《特米米特别版集批宝典》 | 玩家实测整理、复杂触发条件、交叉检查 | 未附样本/版本的结论，或直接作为运行时数据源 |
| 4 | B 站视频 `BV1qC4y1Q7Gy` 的统计分析 | 萨米地图生成顺序、拓扑约束假设、统计回归参考 | 将样本均值或旧版本分布硬编码为当前常量 |

这里的“当前客户端表”特指 [roguelike_topic_table.json](../data/excel/roguelike_topic_table.json) 等随 `2.7.51 / Data 26-07-10` 提取的文件。若表与网络资料冲突，以表和同版本抓包为准，并将差异固化为测试用例。

仓库路径 `data/excel` 是指向 `/Users/happyelements/ArknightsGameData/zh_CN/gamedata/excel` 的软链接。本轮直接复核其 `roguelike_topic_table.json`，SHA-256 为 `643df7574c8955c827bec2645ed09c06df44bc6654a85ead96002a8298b91bb6`。PRTS 五主题页 revision 为 `rogue_1=408420`、`rogue_2=408421`、`rogue_3=408422`、`rogue_4=408423`、`rogue_5=408424`（页面时间均为 2026-07-13 UTC，访问日期 2026-07-14）。这些 revision 用于固定公开基础收益证据，不改变“客户端表/同版本协议优先”的原则。

视频发布于 2023-12-17，标题为“全网首个肉鸽节点生成机制解析……在萨米，用‘占卜’透视很正常吧”。它分析的是当时版本和实测样本；相对当前数据已经属于旧版资料。视频中的平均节点数、平均紧急作战数和出现率只能用作统计回归的参考区间，不能写成固定节点数或固定权重。

腾讯表格匿名页面可读，但页面标明禁止复制、导出和打印；审计时显示 19 个工作表，最后保存时间为 2026-07-11。实现中只应把人工核验后的规则转换为带来源、版本和测试的结构化规则，不应抓取并内置整表内容。

## 3. 代码架构

| 层次 | 代码入口 | 当前职责 | 主要问题 |
| --- | --- | --- | --- |
| HTTP 路由 | [server/app.py](../server/app.py) 的 `/rlv2/*` 路由 | 将客户端接口映射到 handler | 大量已注册接口仍只返回 `202` 空对象 |
| 流程编排 | [server/rlv2.py](../server/rlv2.py) | 读请求、推进 `pending/state`、生成地图、结算并持久化 | 文件过大；协议、领域规则、存储和主题特判混合 |
| 纯逻辑 | [server/rlv2_logic.py](../server/rlv2_logic.py) | 开局表选择、等级、资源增减、难度 Buff、招募和战斗生命结算 | 是合适的拆分边界，但尚未覆盖地图、奖励、事件资格与主题模块 |
| 结局与事件规则 | [server/rlv2_ending_rules.py](../server/rlv2_ending_rules.py)、[server/rlv2_event_rules.py](../server/rlv2_event_rules.py) | 显式核心路线、逐层 Boss、关键物品触发及经审核事件 overlay | 只覆盖可由当前 Excel 与固定 PRTS revision 确认的子集；不含特殊区域和历史解锁存档 |
| 客户端表 | [data/excel/roguelike_topic_table.json](../data/excel/roguelike_topic_table.json) | 主题、模式、初始值、关卡、物品、节点类型、月队、难度等 | 不能单独还原服务端生成算法 |
| 人工补充数据 | [data/rlv2/event_choices.json](../data/rlv2/event_choices.json)、[server/data/rlv2_data.py](../server/data/rlv2_data.py) | 事件效果和部分难度 Buff | 数据来源/版本未逐条记录；事件效果与解释器耦合 |
| 局内存储 | [server/rlv2_repository.py](../server/rlv2_repository.py) | SQLite 按 UID 保存 run、随机种子与 revision；同一事务提交并通过 CAS 拒绝陈旧写入 | 动作级 request-id 幂等日志尚未实现；`Uid` 请求头仍缺认证 |
| Legacy 兼容 | `data/user/rlv2.json`、`data/user/serverData.json` | 单用户一次性导入及可选兼容镜像；多用户必须显式指定唯一 owner | 镜像不是事实源，不能重新参与多用户归属推断 |
| 测试 | [tests/test_rlv2_logic.py](../tests/test_rlv2_logic.py)、[tests/test_rlv2_repository.py](../tests/test_rlv2_repository.py)、[tests/test_rlv2_rules.py](../tests/test_rlv2_rules.py)、[tests/test_rlv2_transactions.py](../tests/test_rlv2_transactions.py)、[tests/test_rlv2_ending_routes.py](../tests/test_rlv2_ending_routes.py) | 纯逻辑、UID 隔离、事务、地图规则和结局路线回归 | 尚缺完整依赖环境下的接口状态机、特殊区域和主题模块回归 |

当前全量 133 项 RLV2 测试通过：logic 50、repository 11、rules 9、transactions 42、ending routes 21。路线测试覆盖显式路线、逐层 Boss、合法手工 `toEnding`、坏路线修复、额外层手改保护、ending5 underlay 优先级、跳层计数和私有状态剥离；事务测试覆盖 RO1 关键链、RO2 骑士死亡必领、RO4 构想炼金、RO5 追忆仪、普通 gold 跳过和零生命失败。另对 36 个 `theme × zone` 各运行固定 seed `hard-property-0..2499`，共 90000 张地图、849924 个节点，硬性质审计全部通过。

建议保持 `rlv2_logic.py` 无 Flask、无磁盘 I/O，并继续拆出三个明确边界：

- `RunRepository`：按用户读取、事务提交、版本迁移和 revision/CAS 已落地；动作级 request-id 幂等仍待补充。
- `RunEngine`：唯一负责动作合法性和状态转移，输入为 `RunState + Command`，输出为 `RunState + DomainEvents`。
- `TableAdapter`：把客户端表转换为带类型的主题规则，启动时完成引用完整性校验。

## 4. 状态模型与主流程

局内状态以 [server/rlv2.py](../server/rlv2.py) 的 `rlv2CreateGame()` 为入口，主要分区如下：

| 分区 | 内容 | 必须保持的不变量 |
| --- | --- | --- |
| `game` | 主题、模式、难度、预设、等效难度、开始时间 | 一局内主题/模式/预设不可被普通动作修改 |
| `player` | `state`、属性、游标、轨迹、`pending`、结局 | `state` 与 `pending[0].type` 必须匹配；游标只能沿有效边移动 |
| `map` | 分层 `zones`、节点、边、访问状态 | 节点可达；结局/层末节点满足主题和楼层约束；已消费的一次性节点不可重进 |
| `troop` | 已招募干员、外派及归队状态 | 实例 ID 唯一；招募/进阶不能产生重复或非法阶段 |
| `inventory` | 藏品、券、道具、消耗品、探索工具 | 所有增减走统一账本；数量不得为负；一次性效果只结算一次 |
| `buff` | 临时生命、分队 Buff 等公共效果 | 可持久效果与单场效果分离，不污染全局表对象 |
| `module` | 五主题专属状态 | 只由对应主题规则修改，且能从动作日志确定性重放 |
| `_server` | `schemaVersion/events/route` 服务端私有中间态 | 随当前局原子持久化；所有 HTTP 响应和 `SyncData` 必须递归剥离，不能进入客户端协议 |

`_server.route` 保存 `endingId/baseEndingId/underlayEndingId/orderedZones/bossEndings`；`_server.events` 保存事件战待发奖励、`requiredBattleRewardIndexes` 和 `pendingAlchemyReward`。旧存档会在读取时补齐该结构；它不是客户端状态模型的一部分。

当前主流程可概括为：

| 阶段 | 入口 | 预期转移 | 当前评价 |
| --- | --- | --- | --- |
| 创建 | `rlv2CreateGame()` | 无局 -> `INIT`，按表建立初始 `pending` | 已实现核心路径；特殊挑战缺服务端预置阵容时会明确拒绝 |
| 初始选择 | `rlv2ChooseInitialRelic()`、`rlv2ChooseInitialRecruitSet()`、招募接口 | 依次消费遗物、招募组、招募券 | 已实现/近似；月队和特殊券已接表，仍需完整协议回归 |
| 开始探索 | `rlv2FinishEvent()` | `INIT` -> 生成第一层 -> `WAIT_MOVE` | 近似；地图不是原版生成器 |
| 非战斗节点 | `rlv2MoveTo()`、`rlv2SelectChoice()`、商店接口 | `WAIT_MOVE` -> `PENDING` -> `WAIT_MOVE` | 有邻接/重复访问和余额校验；节点类型与事件资格仍过于通用 |
| 战斗节点 | `rlv2MoveAndBattleStart()`、`rlv2BattleFinish()` | `WAIT_MOVE` -> `BATTLE` -> `BATTLE_REWARD` | 普通/紧急基础 EXP 自动结算并升级；基础源石锭进入独立 reward；掉落池和主题乘区仍是近似 |
| 奖励 | `rlv2ChooseBattleReward()`、`rlv2FinishBattleReward()` | 领取奖励/招募 -> 完成节点或进下一层 | 按整数 `index + sub` 单项领取且可防重复；普通源石锭和券可跳过，只有明确必得的事件奖励会阻止结束；全职业券仍是占位近似 |
| 结局改线/跨层 | 关键物品入库、`rlv2ReadEndingChange()`、`_rlv2.finishNode()` | 更新 `toEnding` 与私有路线 -> 确认提示 -> 按显式下一层生成地图 | 核心 zone 5/6/7/8 和逐层 Boss 已实现；特殊区域及历史解锁门槛未实现 |
| 放弃 | `rlv2GiveUpGame()` | 任意局内状态 -> 当前 UID 的空局 | 已在当前 UID 的仓储事务内清局；它仍不能代替原版终局结算 |

后续不应让每个 handler 自行 `pop(0)`。应建立显式状态转移表，例如只有 `BATTLE_REWARD` 能接受 `chooseBattleReward`，只有奖励与其插入的招募流程都完成后才能 `finishBattleReward`。每条命令同时校验 `run_id`、`revision`、`state`、首个 `pending.type` 和目标对象状态。

## 5. 公共逻辑完成度

状态含义：**已实现**表示存在实际状态变更且规则主要来自当前表；**近似**表示能走通客户端流程但规则或概率不完整；**未实现**表示接口为空、只有初值，或没有产生原版要求的状态转移。

| 能力 | 状态 | 可验证入口 | 仍需补齐 |
| --- | --- | --- | --- |
| 模式/难度/预设开局 | 已实现 | `select_init_config()`、`rlv2CreateGame()` | 建立各模式真实请求/响应 golden fixtures |
| 普通与挑战等级表 | 已实现 | `select_player_level_table()`、`resolve_player_levels()` | 核对所有预设表；RO3 部分挑战上限为 50，不能统一截为 10 |
| 月队预置干员 | 已实现 | `prepare_predefined_characters()` | 覆盖阿米娅模板、多形态、玩家缺失干员的协议行为 |
| 初始招募组与券后缀 | 已实现 | `recruit_group_ticket_ids()` | 用表/协议验证随机高级券的抽取权重，而不只验证职业集合 |
| 招募/进阶/希望 | 已实现/近似 | `prepare_recruit_candidates()`、`rlv2RecruitChar()` | 特殊免费规则、助战、留券、主题专属减费和不能进阶条件 |
| 生命、护盾、经验、升级 | 已实现/近似 | `settle_battle_life()`、`battle_base_reward()`、`resolve_player_levels()` | 已区分 RO1 每场临时生命与后续主题可消耗护盾；普通/紧急经验已按楼层结算，战后效果将生命扣至 0 会直接失败；复活和完整最终结算仍缺失 |
| 难度 Buff | 近似 | `_rlv2.getBuffs()`、`collect_difficulty_buffs()` | 把手写按层倍率与当前表/抓包逐项对齐；区分替换和叠加 |
| 藏品/道具入库 | 近似 | `_rlv2.add_item()`、`grant_resource()`、`remove_item()` | 已处理即时资源/券、结局触发、跨实例原子扣除、RO3 `CHAOS_PURIFY`、RO4 `FRAGMENT/MAX_WEIGHT` 和 `immediate_cost`；`immediate_mutation` 与其余 RO4/RO5 专属资源尚未完整转成主题状态 |
| 事件 | 部分实现 | `event_choices.json`、`runtime_event_rules()`、`rlv2SelectChoice()` | 已校验楼层/节点/场景/部分藏品和模块门槛，并支持事件战后关键奖励；仍缺模式、历史、完整 eligibility、权重和大量 RO3-5 效果 |
| 商店 | 近似 | `rlv2MoveTo()`、`rlv2BuyGoods()` | 已排除事件链专属物品并保留 RO3 `视界邀约` 的 1 锭来源；仍缺表驱动权重、折扣、刷新、银行、投资和主题交互 |
| 普通/紧急基础收益 | 已实现，待真实协议回归 | `battle_base_reward()`、`battle_resource_item_ids()`、`rlv2BattleFinish()` | 60 格矩阵、资源类型、标准区域、Boss/特殊区域边界及领取事务均有测试；仍缺同版本真实响应 fixture |
| 战斗奖励池 | 近似 | `rlv2BattleFinish()`、`rlv2ChooseBattleReward()` | 按节点/关卡/难度生成券、藏品和主题额外掉落；紧急额外奖励及各独立乘区仍待实现 |
| 地图 | 近似 | `_rlv2.getMap_new()`、`build_route_plan()` | 36 条核心区域约束、显式隐藏层顺序和逐层 Boss 已接入；特殊/平面区域及通用权重仍不能代表完整原版拓扑 |
| 多结局 | 核心路线已实现 | `player.toEnding/chgEnding`、`ENDING_ON_ACQUIRE`、`rlv2ReadEndingChange()` | 关键物品或手工合法 `toEnding` 可改线并替换未访问 Boss；RO2 骑士死亡可产生必领 `grace_84` 并恢复默认路线；仍缺 per-UID 历史解锁、特殊区域和原版外层结算 |
| 银行/节点任务/刷新/助战等 | 未实现 | `rlv2BankPut()` 至 `rlv2ChooseInitialExploreTool()` | 多个路由目前只返回空对象与 HTTP 202 |

### 普通/紧急基础收益矩阵

下表每格为“普通作战 `exp/gold`；紧急作战 `exp/gold`”。数值来自上述固定 PRTS revision，表示不含幕后筹备、认知塑造、历史重构、古今学识、收藏品及其他乘区的基础收益。矩阵及其事务 handler 已实现并通过回归。

| 主题 | zone 1 | zone 2 | zone 3 | zone 4 | zone 5 | zone 6 |
| --- | --- | --- | --- | --- | --- | --- |
| `rogue_1` | `10/3; 12/4` | `12/3; 18/4` | `16/3; 24/5` | `20/4; 30/5` | `25/4; 38/6` | `25/4; 45/6` |
| `rogue_2` | `10/2; 12/3` | `12/2; 18/3` | `14/2; 24/4` | `16/3; 30/4` | `20/3; 36/5` | `20/3; 36/5` |
| `rogue_3` | `10/2; 12/3` | `12/2; 18/3` | `14/2; 24/4` | `16/3; 30/4` | `20/3; 36/5` | `20/3; 36/5` |
| `rogue_4` | `10/1; 12/2` | `12/2; 18/2` | `13/2; 25/3` | `15/3; 30/3` | `20/3; 36/5` | `20/5; 36/5` |
| `rogue_5` | `10/1; 12/2` | `12/2; 18/2` | `13/2; 25/3` | `15/2; 30/3` | `20/2; 36/5` | `20/5; 36/5` |

矩阵的适用边界必须编码为显式规则，而不是宽松回退：

- `rogue_1/2/3` 只接受 cursor zone 1-6。
- `rogue_4` zone 7“逍遥兰若”和 `rogue_5` zone 7“明灭顶”是替代第六层，分别显式映射到第 6 档。禁止以 `min(zone, 6)` 处理任意未知 zone。
- zone 8、传送区域、特殊节点和其他非标准区域不进入本矩阵；handler 通过 `zone.id == zone_N` 限定标准区域。公开资料注明“按战斗节点所属层”时，也必须先有可靠的所属层上下文。
- 发奖 ID 使用 `details[theme].gameConst.goldItemId` 与 `expItemId`。`exploreExpOnKill` 在 RO1/2 为 `null`、RO3/4/5 为 `10,20,100`，它不是逐层战斗结算表。
- RO4 旗帜挑战在 zone 2-5 有独立升级行，但当前 run/node 没有可靠的奖励 variant 标志；`levelReplaceIds` 在普通关卡中也广泛存在，不能作为旗帜判据。本轮只发基础行。
- Boss 不纳入本轮矩阵。RO2-RO5 存在 Boss 关卡变体、特殊险路恶敌或额外减半条件；当前 handler 明确不发矩阵 EXP/gold，只保留占位全职业券，后续必须进入独立规则分支。

当前 `_rlv2.finishNode()` 不再统一执行 `zone + 1`，而是读取私有 EndingRoute：RO3 ending4 可从 zone 5 或已进入的 zone 6 前往 zone 7；RO4/RO5 ending4 从 zone 5 前往 zone 7；RO4/RO5 ending5 在此前实际终局 zone 5/6/7 后追加 zone 8。路线逐层保存 `bossEndings`，因此隐藏路线的 zone 5 仍使用已经确定的基础 Boss，最终隐藏层使用目标结局 Boss。ending5 overlay 可升级但不会被后来取得的低优先级 underlay 物品降级；损坏路线会重建，已进入额外层后手改成终点在身后的 ending 会恢复仍包含当前位置的原有效路线。合法手工 `toEnding` 会即时替换当前层未访问 Boss，跳层 `record.cntZone` 按实际路线位置计数；这些只提供核心路线的调试/兼容能力，不代表已校验原版历史解锁门槛。

当前 `event_choices.json` 包含五主题条目，但“存在数据”不等于“已实现条件”：审计快照中 `rogue_1` 到 `rogue_5` 分别有 107、176、923、357、1788 个 choice。运行时会叠加 `rlv2_event_rules.py` 中经审核的严格子集：RO1 writer 事件战、RO2 关键门槛/骑士撤线、RO4 构想炼金，以及 RO3-5 的少量固定剧情/结局场景；其余仍按主题、节点类别、明确楼层和 quarantine 过滤。RO2“深蓝之心”同时要求前置藏品和灯火 `>=20`，园林选项自身免费且必出；骑士死亡只匹配 `SIMPLE,<specialTrapId>,killed > 0`，必领 `grace_84` 后恢复默认路线/Boss。RO4 `D01/D02` 进入 fragment 模块，固定 Excel 公式可经 `/alchemy`、`/alchemyReward` 合成“巴别塔誓言”，随机炼金池不猜测。RO2 `bossa1` 掷骰结果协议未知，相关选项保持禁用；RO3 `ex3` 随机权重未知，安全降级为离开。模式、历史、完整 eligibility 与大量效果仍未实现。

客户端 `PlayerRoguelikePlayerState` 只有 `NONE/INIT/PENDING/WAIT_MOVE`，因此终局必须直接生成 `PENDING + GAME_SETTLE + content.result`，不能写入 `GAME_OVER` 或不存在的 `status.gameResult`。`gameSettle` 以对象型零分和字段完整的零外层收益结构清空当前局，并在同一事务回收 seed；旧的 `GAME_OVER`、错误 `GAME_SETTLE` 和旧战斗奖励会在登录/动作入口自动迁移。该闭环不改全局外层进度，不能当作原版终局奖励实现；分数、BP、记录和奖励仍必须依据同版本抓包补齐。

## 6. 五主题机制对照

客户端表顶层 `topics[*].moduleTypes` 是判断主题模块边界的直接证据。下表把公开规则、项目状态和优先实现点分开列出；网络资料只补充客户端表未表达的触发顺序。

| 主题 | 客户端模块/公开核心机制 | 当前实现 | 结论与下一步 |
| --- | --- | --- | --- |
| `rogue_1` 傀影与猩红孤钻 | `moduleTypes=[]`；经典生命/临时生命、剧目（`CAPSULE`）、幕间余兴及古堡节点 | 临时生命参与结算；已接 `m16`、`m19 -> m20 -> m21` 和 writer `n01/n02` 关键链，可切换四个核心结局 | 近似。剧目触发/消费/换层重置仍未实现，事件链也不代表所有历史/模式门槛已还原 |
| `rogue_2` 水月与深蓝之树 | `SANCHECK`、`DICE`；灯火区间、骰子、排异反应、钥匙、深入海洋 | 初始化灯火/骰子；“深蓝之心”校验藏品和 `>=20` 灯火；关键藏品/Buff 已接入；精确骑士死亡字段生成必领 `grace_84` 并恢复默认路线 | 近似。`immediate_mutation`、骰子 pending、排异反应和完整检定仍缺失 |
| `rogue_3` 探索者的银凇止境 | `CHAOS`、`TOTEMBUFF`、`VISION`；坍缩、密文板、抗干扰指数、树篱之途 | 初始化模块外形；`CHAOS_PURIFY` 方向已接入；固定剧情和部分关键事件/结局物品已接入，核心 ending4 可前往 zone 7 | 大部未实现。坍缩完整状态机、密文板拼装、抗干扰遮蔽及特殊支路仍需进入地图/战斗规则 |
| `rogue_4` 萨卡兹的无终奇语 | `FRAGMENT`、`DISASTER`、`NODE_UPGRADE`；构想/负荷、灵感、时代（灾厄）、节点升级 | `D01/D02` 进入 fragment 并计算负荷；固定公式炼金与奖励接口、`MAX_WEIGHT`、ending2 巴别塔誓言门槛及 zone 7/8 核心路线已接入 | 仍不完整。随机炼金池、刷新、2V2、诡谲断章、时代和节点升级缺失 |
| `rogue_5` 岁的界园志异 | `COPPER`、`WRATH`、`CANDLE`、`SKY`；大炎通宝、戌绘、烛火、特殊区域和留存招募券 | 通宝初始展示；追忆仪清资源/收益倍率及必领“小磨唧”事件战、少量固定剧情和 zone 7/8 核心路线已接入 | 大部未实现。普通“古今交汇”入口、5x5/5x7 `module.sky`、AP/移动、留存券/燃烛、退出和跨战敌人生命仍缺失；无追忆仪的 portal 当前安全绕过 |

自然可达性仍是事件 overlay 的重要边界：RO3 `story2/story3`、RO4 `end2` 和 RO5 `portalboss` 的 `logicalDepths` 为空且没有固定场景映射，当前普通地图不会自然进入；密文板强制支路、刷新/传送、特殊区域和 RO4/RO5 若干关键藏品也仍没有完整自然 grant path。规则表中存在 choice 不等于完整事件链已可游玩。

主题机制应当以事件驱动方式实现。例如 `BattleCompleted` 同时交给公共结算器、RO2 灯火/排异规则、RO3 坍缩规则、藏品乘区和任务计数器处理，最后一次性提交状态。这样能避免把同一触发条件散落在多个 HTTP handler 中。

## 7. 地图生成：视频结论与当前差距

`_rlv2.getMap_new()` 当前从固定 `zone_routes.json` 读取 36 个核心区域的列数、分支上限和已审核列规格，再按逻辑层选择普通/紧急关卡，按路线传入的逐层 ending 选择 Boss，最后只连接相邻列并修复入边。它已经不是简单的 `zone * 2` 通用地图，但问号列权重、详细连线概率、特殊/平面区域和结局条件 AST 仍属于近似或未实现。

结合 B 站视频的萨米实测，可以把候选算法拆为以下可验证步骤：

1. 按主题、楼层、模式、结局和特殊状态选择拓扑模板。
2. 从配置决定本层节点总数与各列容量，而不是逐格独立抽取。
3. 先分配作战/紧急作战池和非战斗事件池。
4. 应用保底、上限、结局和特殊节点替换；结局节点占用普通拓扑槽位，不能简单追加一列。
5. 最后依据模板生成连线，并验证所有必要节点可达。

视频中较明确、适合作为 RO3 性质测试的约束包括：

- 第一层若出现第二个作战节点，至少一个应为紧急作战。
- 第二层最多一个紧急作战。
- 第三至第六层最多两个紧急作战。
- 结局节点计入模板节点总数。

这些约束仍应由当前客户端表或同版本样本复核后再推广到其他主题。实现时不要写 `averageNodeCount = ...`；应写模板容量和约束。地图硬验收统一为每个受支持的 `theme × zone` 组合运行 2500 个固定种子，验证可达性、边完整性、节点上限、结局占位和同种子复现；本轮 36 组使用 `hard-property-0..2499`，共 90000 张地图、849924 个节点已经全部通过。每组合 10000 个种子仅用于发布前非阻塞分布审计，不作为单元测试或合并门槛。推荐生成器接口为：

```text
generate_map(theme_rules, floor_context, run_state, rng)
  -> choose_topology
  -> allocate_slots
  -> allocate_battle_pool / allocate_event_pool
  -> apply_guarantees_and_endings
  -> connect_and_validate
  -> MapZone + GenerationTrace
```

`GenerationTrace` 记录模板、候选池、每次替换原因和随机抽取序号，只用于调试和回归，不下发客户端。它能让“某种子为什么没有紧急作战”成为可定位问题。

## 8. P0：按 UID 持久化已落地，待最终回归

原先“全服共享 JSON sidecar”的 P0 结论已经过时。当前 [server/rlv2_repository.py](../server/rlv2_repository.py) 以 SQLite 为唯一真源，`roguelike_runs` 以 `uid` 为主键，在同一行保存 revision、run、`rlv2_seed` 与 `seed_list`；旧 JSON 只在单用户模式中承担一次性导入和可选兼容镜像。

| 能力 | 当前状态与证据 | 剩余检查点 |
| --- | --- | --- |
| UID 隔离 | 已落地。多用户模式要求合法 `Uid`；所有动作通过 Repository 读取当前 UID 的 run | 完整依赖环境下补两用户接口级回归；`Uid` 仍需由上层认证 |
| run/随机种子原子提交 | 已落地。run、`rlv2_seed`、`seed_list` 与 revision 在一个 SQLite 事务内提交 | 补跨进程故障注入和重登续局回归 |
| handler 事务边界 | 已落地。外层 handler 使用 `BEGIN IMMEDIATE`，嵌套 handler 复用同一事务；响应状态 `<400` 提交，`4xx/5xx` 或异常回滚 | 在完整 Flask 依赖下补接口级异常与嵌套动作回归 |
| revision/CAS | 已落地。显式保存可用 expected revision 拒绝陈旧写入，事务写入递增 revision | 补多进程竞争与客户端重试场景 |
| `SyncData` | 已落地。按请求 UID 从 Repository 合并 `user.rlv2.current` | 补完整依赖下的接口响应 fixture |
| Legacy 迁移 | 已落地。首个显式 UID 原子认领唯一 owner，禁止第二个 UID 重复认领；单用户 sentinel 可原子转移 | 保留重复认领、sentinel 切换和无 Legacy 数据回归 |
| 动作级幂等 | 尚未落地。revision/CAS 防止陈旧覆盖，但没有 `(run_id, request_id, command, result_revision)` 日志 | 后续增加 request-id 幂等记录，重复请求返回原结果 |

当前仓储 schema 为：

```text
roguelike_runs(uid, revision, run_json, rlv2_seed_json, seed_list_json, updated_at_ns)
repository_metadata(key, value)
```

SQLite 已解决已知串档与两文件非事务提交问题，不应再把 JSON sidecar 描述为当前事实源。仍需明确区分两个残余风险：一是动作重试尚无统一幂等键，二是 `Uid` 请求头只是存储键而非认证机制。它们不否定 P0 数据隔离基线已落地，但必须在发布前继续处理或记录限制。

## 9. 分阶段路线图

| 阶段 | 工作 | 验收门槛 |
| --- | --- | --- |
| P0 数据安全（基线已落地） | SQLite 按 UID 保存 run、种子与 revision，同事务提交；`SyncData` 合并唯一真源；Legacy 唯一 owner 迁移 | 现有 UID/迁移/CAS/事务测试保持通过；补完整接口、跨进程故障注入、重登和动作 request-id 幂等回归 |
| P1 状态机 | 将 handler 收敛为 command；建立 `state + pending` 转移矩阵；统一邻接、访问、库存和余额校验 | 非法顺序全部返回 4xx 且状态不变；合法主流程五主题均可重放；重复请求结果一致 |
| P2 公共表驱动规则 | 在现有关键物品、事件 overlay 和核心 EndingRoute 上补完整物品解释器、奖励池、eligibility 与历史解锁 | 当前表所有引用可解析；资源账本无负数；每个未支持 Buff key 显式报出，不静默忽略 |
| P3 地图生成 | 在 36 个核心区域和 zone 6/7/8 路由上补特殊/平面区域、拓扑适配器和真实槽位分配 | 每个受支持的 `theme × zone` 组合以 2500 个固定种子通过硬性质测试；特殊区域另有状态/拓扑 fixture |
| P4 主题模块 | 依次完成 RO1 剧目、RO2 灯火/骰子、RO3 坍缩/密文板、RO4 构想/时代、RO5 通宝交换图及其余模块 | 每个模块都有状态转移表、表驱动 fixture、边界与回放测试；空 `202` 路由清零或明确返回“不支持” |
| P5 原版协议回归 | 收集同版本、去标识化的合法真实请求/响应；建立 golden fixtures 和版本差异清单 | 五主题普通、月队、挑战各至少一条完整局流程；升级客户端表时自动报告字段和行为差异 |

P2 和 P3 可以在 P1 的接口设计稳定后并行；所有新增可变主题状态都必须进入当前 UID 的 Repository 事务，不能重新引入独立事实源。

## 10. 可执行的验证矩阵

| 维度 | 最小测试集 | 关键断言 |
| --- | --- | --- |
| 开局 | 五主题 × NORMAL/MONTH_TEAM/CHALLENGE 的有效组合 | 初始属性与表一致；特殊模式缺 `predefinedId` 时不静默选第一项 |
| 招募 | 所有初始组、随机组、特殊组、RO5 `_init/_vip_init` | 职业/星级过滤正确；希望守恒；首次招募与进阶唯一；不可留存券不残留 |
| 战斗 | 本轮覆盖普通/紧急、完美/漏怪/失败、临时生命/护盾；Boss 后续独立覆盖 | HP/护盾/经验/升级收益正确；失败进入不可继续终态；奖励不能重复领取；Boss 不回退到普通/紧急矩阵 |
| 事件 | 每个 choice 的满足/不满足条件各一例 | 未满足条件不下发；消耗与奖励原子；空场景仍有合法离开路径 |
| 结局路线 | 五主题每个 ending、触发前后当前 zone、目标路线包含当前 zone 的手工 `toEnding` | `orderedZones`、逐层 Boss、`chgEnding` 和事件战奖励一致；终点在身后的改线被拒绝；私有 `_server` 不下发；历史解锁另测 |
| 地图 | 每个受支持的 `theme × zone` 组合 2500 个确定性种子 | 可达性、入/出边、节点上限、结局占位、一次性节点、主题专属节点约束及同种子复现；每组合 10000 个种子只生成发布前非阻塞分布报告 |
| 主题模块 | 每个 DomainEvent 对模块状态的测试 | RO1 剧目只触发一次；RO2 灯火区间影响检定；RO3 范式不超过四个；RO5 交换只走合法边 |
| 持久化 | 两 UID、两进程、请求重试、提交中断、重登 | 不串档、不双发、不丢种子、不回到旧 current |
| 数据升级 | 当前表与下一版本表的 schema diff | 新枚举、新 Buff key、新接口字段必须显式分类，禁止默认吞掉 |

测试应区分两类：精确规则使用 golden/unit test；随机算法使用 2500 固定种子的硬性质测试和 10000 固定种子的发布前非阻塞分布审计。分布告警只提示可能回归，不应因社区视频中的某个均值发生小幅变化就直接判定失败。

## 11. 近期可落地的改动顺序

在完整重构前，以下改动投入小且能明显降低错误面：

1. UID 隔离、SQLite 事务、revision/CAS、Legacy 唯一 owner 迁移和 `SyncData` 合并已经落地；下一步补完整接口、跨进程故障注入、重登和 request-id 幂等回归。
2. 已让 `_rlv2.add_item()` 传播即时券副作用并补齐 `level_life_point_add`，RO3 净化资源和 RO4 构想/负荷已进入各自模块；下一步补 RO4 其余资源与 RO5 `module.sky`，而不是长期停留在通用账本。
3. 事件已校验楼层、节点、余额、持有物和当前场景，并接入严格 overlay；下一步补模式、历史、完整结局/模块 eligibility、随机权重和事务 handler 回归。
4. 五主题普通/紧急基础经验与源石锭已按固定矩阵接入；下一步收集真实协议 fixture，并独立实现 Boss、RO4 旗帜变体、特殊区域、紧急额外掉落、藏品增益和灵感等乘区，禁止宽松回退。
5. RO3 紧急节点上限、核心有序路线和逐层 Boss 已接入；下一步用同版本样本校准问号节点与连线，并分别实现 RO3/4/5 特殊区域，禁止用核心 zone 跳转代替特殊区状态机。
6. 所有仍为空的接口返回明确的 `501 unsupported` 和不支持的机制名，避免客户端把“HTTP 202 空对象”误判为成功并继续污染状态。

## 12. 资料链接

- PRTS：[集成战略](https://prts.wiki/w/%E9%9B%86%E6%88%90%E6%88%98%E7%95%A5)，用于模式总览、主题入口和公开机制交叉检查；页面会持续更新，引用时应记录访问日期。本轮收益矩阵固定五主题页 revision：`408420`、`408421`、`408422`、`408423`、`408424`。
- Bilibili：[BV1qC4y1Q7Gy](https://www.bilibili.com/video/BV1qC4y1Q7Gy)，发布于 2023-12-17，用作萨米节点生成机制与统计分布参考。
- 腾讯文档：[《特米米特别版集批宝典》指定工作表](https://docs.qq.com/sheet/DQkhoWVpEcUF2T3FV?tab=BB08J2)，用作玩家实测规则交叉检查；受页面复制/导出限制，不作为仓库数据镜像。
- 仓库事实基准：[config/config.json](../config/config.json)、通过 `data/excel` 软链接读取的 [roguelike_topic_table.json](../data/excel/roguelike_topic_table.json) 及同版本合法协议样本；软链接目标与 SHA-256 见第 2 节。

“尽可能符合原版”的可验证定义应是：同版本、同输入状态、同随机种子和同动作序列得到相同的合法状态转移与协议外形；对无法从公开证据确定的概率，保留可配置与可追踪实现，并明确标注为近似，而不是制造看似精确的常量。

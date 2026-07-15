# Roguelike 模块完善进度

> 最后更新：2026-07-15（进行中）
> 目标版本：客户端 `2.7.51 / Data 26-07-10`
> 证据优先级：当前客户端表/协议 > PRTS/官方资料 > 腾讯整理表 > B 站旧版统计

## 当前状态

| 工作项 | 状态 | 当前结果 | 下一检查点 |
| --- | --- | --- | --- |
| 按 UID 持久化 | 已完成，待最终回归 | SQLite 保存 run、随机种子与 revision；每个动作使用 `BEGIN IMMEDIATE` 事务；状态 `<400` 提交，`4xx/5xx` 或异常回滚 | 两用户、嵌套动作、重登与迁移测试全部通过 |
| Legacy 数据迁移 | 已完成，待最终回归 | 首个显式 UID 原子认领；记录唯一 owner；禁止第二个 UID 重复认领；单用户 sentinel 可原子转移 | 仓储测试已覆盖重复认领和 sentinel 切换 |
| `SyncData` | 已完成，待最终回归 | 按请求 UID 从仓储合并 `user.rlv2.current` | 完整依赖环境下补接口级回归 |
| 终局结算 | 最小安全闭环已完成，原版收益待研究 | 终局直接生成合法的 `PENDING + GAME_SETTLE + content.result`；`gameSettle` 原子清局并回收 seed；登录时自动迁移历史 `GAME_OVER`；当前返回类型完整的零分、零外层收益结构 | 用同版本真实终局抓包补齐分数、记录、BP 与外层奖励 |
| 战斗基础收益 | 已完成，待真实协议回归 | 五主题逐层普通/紧急矩阵已接入；EXP 自动结算升级，源石锭作为独立奖励领取；确认 `exploreExpOnKill` 不是该经验表 | 收集同版本真实 `battleFinish/chooseBattleReward` fixture；另行实现 Boss、特殊区域与主题乘区 |
| 离线规则事实层 | 严格子集已接线 | `server/rlv2_rules.py` 只读加载区域、结局 Boss 与事件楼层/类别；未知值、禁用项和 quarantine 不执行 | 继续固定藏品页面 revision，逐条转录成员关系并保持未知值为 `null` |
| 事件楼层与事件链 | 经审核子集已接线 | 250 条 canonical 注解按主题、节点类别和 171 条显式楼层过滤；RO1 关键链、RO2 灯火门槛/骑士死亡、RO4 构想炼金及 RO3-5 明确 overlay 已接入；未知项不回退为 no-op | 补模式、历史、完整结局条件、权重、特殊区域事件及未确认效果 |
| 区域与结局资料 | 核心路线已接线 | 36 条核心区域约束、22 条 canonical Boss/终点及显式 `orderedZones/bossEndings` 进入运行时；关键藏品可更新 `toEnding` | 特殊/平面区域单独建模；补按 UID 持久化的历史结局解锁门槛 |
| 地图生成 | 核心区域约束与隐藏层路由已接线，仍有近似 | 同 seed 可复现、相邻列可达、无空 stage Boss；RO3 ending4 可 `5/6 -> 7`，RO4/5 ending4 可 `5 -> 7`，RO4/5 ending5 在已选终局后追加 zone 8；36 组各 2500 seed 的硬性质审计通过 | 实现特殊区域拓扑、问号列真实权重和连线概率 |
| 主题专属模块 | 部分实现 | RO1 临时生命/关键事件战，RO2 灯火/骰子子集与骑士撤线，RO3 净化资源，RO4 构想/炼金，RO5 通宝/追忆仪严格子集已接入 | 按客户端协议逐模块实现，未知概率保持显式近似 |

## 本轮已落地

- 新增 `server/rlv2_repository.py`，以 SQLite 作为当前局唯一真源。
- `server/rlv2.py` 的动作处理已接入按 UID 事务，嵌套 handler 复用同一事务。
- `server/account.py` 的 `SyncData` 已按 UID 合并当前局。
- 数据库提交通过 revision/CAS 防止陈旧写入。
- 单用户模式兼容导入和镜像旧 JSON；多用户模式必须提供合法 `Uid`。
- Legacy sidecar 只能由一个 UID 认领，避免同一旧存档被复制给多个用户。
- 五主题普通/紧急基础收益按 `theme + zone + nodeType` 结算，并校验客户端 `expItemId/goldItemId` 类型。
- EXP 在 `battleFinish` 自动入账并处理升级；源石锭作为独立 reward，可领取也可直接跳过，已领取项不能重复发放。只有明确标记为自动获得的事件战奖励会阻止提前结束奖励阶段。
- 新增完整矩阵、边界、规则适配、结局路线和 handler 事务测试；当前 roguelike 相关测试为 **133 项通过**。
- 补齐 `/rlv2/finishGame` 与 `/rlv2/gameSettle`；`battleFinish` 返回完整公共响应并让已应用请求幂等返回 200；战斗奖励补齐 `state/isPerfect` 且不再下发伪造干员实例 ID。
- 终局不再写入客户端枚举中不存在的 `GAME_OVER` 或 `status.gameResult`；旧 SQLite 状态在 `SyncData` 和肉鸽动作入口自动迁移，避免结算 30000 和重登循环。
- 新建 `data/rlv2/rules` 离线事实层：从当前 topic table 提取主题、1489 件藏品、591 个关卡、390 个区域和 2495 个 scene，并将用户确认规则单独保存为未接线注解。
- 固定五个 PRTS“事件一览”revision 及 SHA-1，转录 254 条页面事件；250 条绑定 canonical scene，4 条歧义记录进入 quarantine，171 条明确楼层完成结构化。
- 新增确定性事件同步工具，校验页面 revision、客户端 scene 引用、RO3 month 重名候选和生成结果；运行时不联网，只读加载审核后的严格子集。
- 固定五个 PRTS 主题页 revision 及 SHA-1，转录 36 条核心区域布局和 22 条结局终点；20 条“进入方式”保留来源原文，条件 AST 仍为 `null`。
- 从客户端 `bossIconId == specialNodeId` 推导结局 Boss stage 集合；RO1 空图标不猜测，`ro3_ending_c` 与 5 条特殊/平面区域记录进入 quarantine。
- 新增确定性区域同步工具，校验 zone/ending/stage 引用、同名变体排除、固定计数和生成结果；运行时不联网，只读加载核心线性区域与结局终点子集。
- 开局在 `allChars=true` 下仍生成客户端描述的三张招募券，普通模式不再注入配置中的初始干员。
- 高普尼克按客户端真实 `chestCnt` 计数语义实现：仅数字楼层普通/紧急关按拟态候选数生成 `0/1`，RO1-4 分别按 20%/40%/30%/40% 保留组；RO5 明确五候选的 18 个 stage 使用 50%，其余无法辨认当前 DLC replacer 的 stage 保守按基础四候选 40%。`goldTrapCnt` 只对应 `trap_051_vultres`，独立保持 100。
- 核心地图生成器接入 36 个区域布局、已审核逐列规则、22 个结局终点与 canonical Boss，移除普通列无 stage Boss 和无依据同列边。
- 事件候选接入节点类别/逻辑楼层/quarantine；RO1/2 补齐明确资源、券、藏品、持有条件、消耗全部、概率奖励、互斥分支和随机菜单，未知复杂场景默认禁用。
- 事件支付按未占用希望校验，RO2 灯火限制为 `0..100`；旧局会移除已禁用选项，通用随机藏品池不再泄漏事件链/结局藏品，非明确可重复事件同局只出现一次。
- Boss 缺少难度/条件状态时只使用基础变体，不再把相同 `specialNodeId` 的强化或条件关当成等概率池。
- 新增 `server/rlv2_ending_rules.py`：为五主题建立显式核心路线和逐区域 Boss 结局；跨层不再统一使用 `zone + 1`。RO3 第四结局可从 zone 5 或已经进入的 zone 6 前往 zone 7；RO4/RO5 第四结局从 zone 5 前往 zone 7；第五结局在此前实际终局 zone 5/6/7 后追加 zone 8，并保留此前区域已确定的 Boss。
- 获得经审核的最终关键物品时会按优先级更新 `player.toEnding`，设置 `chgEnding=true`，重建私有路线并替换当前层尚未访问的 Boss；`/rlv2/readEndingChange` 已实现确认并清除标记。旧存档或手工修改的合法 `toEnding` 会在归一化时补建路线，并立即替换当前层尚未访问的 Boss；损坏路线会重建，已经进入额外层后手改成终点在身后的 ending 会恢复仍包含当前位置的原有效路线。
- RO4/RO5 ending5 作为 zone 8 overlay 保留并可升级其 underlay；之后取得低优先级结局物品不会把 underlay 降级或丢失 zone 6/7。跳层终局的 `record.cntZone` 按 `orderedZones` 中实际完成的区域数记录，不再误用 zone ID。
- 路线和事件中间态保存在 `_server.route/events`，所有动作响应和 `SyncData` 都递归剥离 `_server`，不向客户端泄漏服务端私有状态。
- 新增 `server/rlv2_event_rules.py` 作为经审核运行时 overlay：RO1 接入 `m16 -> ending2`、`m19 + zone 3 Boss -> m20 -> hidden2 -> m21 -> ending3`，以及 writer1/2 事件战后 `n01/n02`、`n02 -> ending4`；事件战关键物品按 PRTS 语义区分可选领取与必领。
- RO2 接入已确认的关键物品门槛、`curse_7` 每战灯火变化、`curse_8/9` 获得时灯火消耗与完美作战恢复类 Buff。“深蓝之心”入口同时要求前置藏品与灯火 `>=20`，园林选项自身不收费且在抽取菜单中必出。战斗结果精确匹配 `SIMPLE,<specialTrapId>,killed > 0`；持有 `grace_83` 且未持有 `grace_84` 时生成必领奖励，领取后恢复默认 ending 和当前未访问 Boss，`born`、别名键、零死亡及重复提交都不会误触发。
- RO4 `D01/D02` 会进入 `module.fragment.fragments` 并计算负荷；固定 Excel 炼金公式已接入 `/rlv2/alchemy` 与 `/rlv2/alchemyReward`，可合成“巴别塔誓言”`rogue_4_relic_final_1`，再由 ending2 固定事件校验并改线。没有确认结果池的随机炼金会明确返回不支持。
- RO3 `CHAOS_PURIFY` 与 RO4 `MAX_WEIGHT` 已进入对应主题模块；Excel `up_reward` 对 EXP/gold 的连乘、战后 `battle_extra_reward/gain_on_perfect` 及生命扣至 0 后直接失败均已接入。`immediate_cost` 不再把负数物品递归入库，修复了自消耗藏品的递归崩溃。
- RO5 追忆仪会清空源石锭和剩余希望但保留已花费希望，EXP/gold 获取倍率按表生效；“小磨唧”事件战奖励为必领。该严格分支不等于普通“古今交汇”特殊区域已完成。
- RO3-5 其余部分仍只启用固定 PRTS/Excel 能确认的剧情场景、持有条件、资源变化和关键物品效果。
- 通用事件藏品池和商店池会排除事件链/结局专属物品；RO3 `rogue_3_relic_boss_4a` 保留普通获得来源并按 PRTS 在商店定价 1。`remove_item()` 已改为先检查总余额，再跨多个实例原子扣足，避免部分扣除或少扣。
- 结局路线定向测试扩展到 21 项，事务测试扩展到 42 项；覆盖坏路线修复、额外层手改保护、ending5 underlay 优先级、跳层计数、RO1 链、RO2 骑士死亡必领、RO4 构想炼金、RO5 追忆仪、普通 gold 跳过及零生命失败。五组全量 **133/133** 通过。
- 对 36 个 `theme × zone` 组合各运行固定 seed `hard-property-0..2499`：共 90000 张地图、849924 个节点，全部满足可达性、边引用、分支上限、固定列、Boss/stage 完整性和同 seed 复现要求。

## 进行中

1. 从当前客户端 IL2CPP 元数据和真实抓包继续确认 `/rlv2/gameSettle` 的分数、记录、BP 与外层奖励字段。
2. 按固定 revision 继续将 PRTS/Tomimi 的藏品和模块事实转成版本化注解；事件部分继续补模式、历史、权重、未确认效果及 4 条 quarantine，运行时绝不联网。
3. 独立建模特殊区域：RO3 密文板/特殊支路，RO4 刷新、2V2 与诡谲断章，RO5 “古今交汇”的 5x5/5x7 `module.sky`、AP/移动、留存券/燃烛和退出协议；这些能力不属于本次核心 `orderedZones` 路线实现。
4. 收集同版本真实战斗奖励协议 fixture，并补 Boss 奖励、RO4 旗帜、主题乘区及按 UID 保存的历史结局解锁状态。

## 战斗基础收益矩阵

下表每格为“普通作战 `exp/gold`；紧急作战 `exp/gold`”，均是不含幕后筹备、认知塑造、历史重构、古今学识、收藏品及其他乘区的基础值。

| 主题 | zone 1 | zone 2 | zone 3 | zone 4 | zone 5 | zone 6 |
| --- | --- | --- | --- | --- | --- | --- |
| `rogue_1` | `10/3; 12/4` | `12/3; 18/4` | `16/3; 24/5` | `20/4; 30/5` | `25/4; 38/6` | `25/4; 45/6` |
| `rogue_2` | `10/2; 12/3` | `12/2; 18/3` | `14/2; 24/4` | `16/3; 30/4` | `20/3; 36/5` | `20/3; 36/5` |
| `rogue_3` | `10/2; 12/3` | `12/2; 18/3` | `14/2; 24/4` | `16/3; 30/4` | `20/3; 36/5` | `20/3; 36/5` |
| `rogue_4` | `10/1; 12/2` | `12/2; 18/2` | `13/2; 25/3` | `15/3; 30/3` | `20/3; 36/5` | `20/5; 36/5` |
| `rogue_5` | `10/1; 12/2` | `12/2; 18/2` | `13/2; 25/3` | `15/2; 30/3` | `20/2; 36/5` | `20/5; 36/5` |

实现边界：

- `rogue_1/2/3` 的普通/紧急收益只接受 cursor zone 1-6。
- `rogue_4` 的 zone 7“逍遥兰若”和 `rogue_5` 的 zone 7“明灭顶”是替代第六层，必须分别显式映射到第 6 档；禁止用 `min(zone, 6)` 泛化。
- zone 8、传送区域、特殊节点与其他非标准区域不进入该矩阵；handler 只接受地图 `zone.id == zone_N`，有“按所属层结算”的规则时必须先有可靠上下文。
- Boss 本轮不纳入普通/紧急矩阵。handler 明确不再回退旧 `10/20/100`，当前只保留近似的全职业券；RO2-RO5 的 Boss 关卡变体、特殊险路恶敌或额外减半条件后续独立实现。
- RO4 旗帜挑战在 zone 2-5 有独立升级收益，但当前 run/node 没有可靠的奖励 variant 标志；本轮只使用基础行，`levelReplaceIds` 不能作为旗帜判据。
- 发奖物品 ID 从 `details[theme].gameConst.goldItemId` 与 `expItemId` 读取；`exploreExpOnKill` 不作为结算矩阵。

## 已确认但暂不臆造的规则

- RO4 带旗帜关卡有独立收益，但当前状态尚无可靠 variant 标志；在能判定关卡变体前不按楼层误发，也不把 `levelReplaceIds` 当作奖励变体标志。
- RO5 紧急作战公开规则明确额外掉落一件收藏品和一枚通宝，但当前客户端表没有服务端掉落权重；先不伪造具体池。
- `rollNodeData` 是刷新/重掷节点候选组，不是自然地图节点类型白名单。
- `Uid` 请求头目前没有 secret/session 认证；SQLite 已解决串档与事务一致性，但不能防止 UID 冒用。

## 验证记录

| 时间 | 验证 | 结果 |
| --- | --- | --- |
| 2026-07-15 | 四组 RLV2 测试、相关 Python 编译、两项固定 PRTS revision 检查 | 101/101 通过 |
| 2026-07-15 | 五组 RLV2 中间回归，含 13 项路线/事件规则测试和 3 项新增 RO1 handler 测试 | 117/117 通过 |
| 2026-07-15 | 五组 RLV2 最终回归：logic 50、repository 11、rules 9、transactions 42、ending routes 21 | 133/133 通过 |
| 2026-07-15 | 36 个 `theme × zone` 各使用 `hard-property-0..2499` 的地图硬性质审计 | 90000 张地图、849924 个节点全部通过 |
| 2026-07-15 | 运行中服务：历史 `GAME_OVER` 经 `syncData` 迁移，再由 `gameSettle` 清局并回收 seed | HTTP 200；响应类型与 SQLite 状态正确 |
| 2026-07-14 | `tests.test_rlv2_logic` + `tests.test_rlv2_repository` + `tests.test_rlv2_transactions` | 55/55 通过 |
| 2026-07-14 | Flask test client：放弃战斗重复 `battleFinish -> finishGame -> gameSettle`，含重复结算 | 通过 |
| 2026-07-14 | 相关 Python 文件 `py_compile` | 通过 |
| 2026-07-14 | 相关文件 `git diff --check` | 通过 |
| 2026-07-14 | `data/rlv2/rules` JSON、Draft 2020-12 Schema、记录数、sourceRefs 与 canonical ID 交叉校验 | 通过 |
| 2026-07-14 | 五个固定 PRTS 事件页 SHA-1、254 条来源记录、250 条 canonical 映射、4 条 quarantine、171 条楼层映射及同步确定性 | 通过 |
| 2026-07-14 | 五个固定 PRTS 主题页 SHA-1、36 条核心布局、22 条结局路线、20 条入口原文、6 条 quarantine 及同步确定性 | 通过 |

## 资料与可复核来源

- [PRTS 集成战略](https://prts.wiki/w/%E9%9B%86%E6%88%90%E6%88%98%E7%95%A5)及五个主题页、事件一览页（访问日期：2026-07-14）。收益矩阵、核心区域摘要和结局入口对应五个主题页 revision：`rogue_1=408420`、`rogue_2=408421`、`rogue_3=408422`、`rogue_4=408423`、`rogue_5=408424`（页面时间均为 2026-07-13 UTC）。
- 事件楼层对应五个事件页 revision：`rogue_1=408344`、`rogue_2=408461`、`rogue_3=408462`、`rogue_4=408463`、`rogue_5=408460`。每页 SHA-1 已写入 `manifest.json` 并由同步工具强校验。
- [Bilibili BV1qC4y1Q7Gy](https://www.bilibili.com/video/BV1qC4y1Q7Gy)，用于萨米主题地图节点统计的交叉参考。
- [腾讯文档指定工作表](https://docs.qq.com/sheet/DQkhoWVpEcUF2T3FV?tab=BB08J2)，用于玩家实测规则交叉检查，不作为运行时依赖。
- 仓库路径 `data/excel` 是指向 `/Users/happyelements/ArknightsGameData/zh_CN/gamedata/excel` 的软链接；本轮直接复核其 `roguelike_topic_table.json`，SHA-256 为 `643df7574c8955c827bec2645ed09c06df44bc6654a85ead96002a8298b91bb6`。该表与客户端 IL2CPP 元数据共同作为版本协议和表结构事实基准。

## 剩余风险

- 多个主题接口仍返回空 `202`，客户端可能把未实现动作误认为成功。
- 终局外层记录、分数、BP 与奖励字段尚无完整同版本协议证据。
- 五主题核心结局路线、关键物品触发、逐层 Boss 和同层未访问 Boss 替换已接入；外层“完成某结局后解锁后续内容”的 per-UID 历史状态尚未建模，因此不能声称完整实现 PRTS 解锁门槛。手工设置的 `toEnding` 只有在目标 `orderedZones` 包含当前区域时才能改线；已进入额外层后改成终点在身后的 ending 会恢复原有效路线，不支持倒退换层。
- Boss、传送/特殊区域、RO4 旗帜、紧急额外掉落及藏品/主题乘区仍无可靠完整规则；当前不会回退到普通/紧急矩阵。
- 奖励外形已按 `2.7.51` IL2CPP 字段约束实现，但仍缺同版本真实请求/响应 fixture。
- 171 条明确楼层及一组经审核结局事件 overlay 已接线，但模式、历史、完整 eligibility、权重和大量 RO3-5 choice 效果仍缺失，4 条特殊节点/变体继续 quarantine；楼层资格和局部事件链不等于事件完整还原。
- RO2 骑士死亡只执行已由 Excel 与战斗字段确认的精确分支；`immediate_mutation` 的客户端状态和 `bossa1` 掷骰 pending 结果形态仍未实现，该掷骰选项保持禁用。RO3 `ex3` 因随机结果权重未知安全降级为离开。
- RO3 `story2/story3` 和 RO4 `end2` 当前缺少可确认的自然地图替换位置；RO3 密文板强制支路、RO4 刷新/传送及 RO4/RO5 若干关键藏品的自然 grant path 仍不完整。RO4 已支持固定公式炼金，但不猜测随机炼金池。
- RO5 `portalboss` 的追忆仪分支只在持有对应藏品时出现，且不再提供与固定 PRTS 冲突的 `choice_leave`；没有追忆仪时当前普通 portal 仍会安全绕过。真正的“古今交汇”入口、5x5/5x7 `module.sky`、AP/移动、留存券/燃烛和退出协议仍未实现。
- 36 条核心线性摘要、22 条终点映射和核心有序路线已接线；特殊/平面区域、传送入口、区域内专属状态和结算顺序仍未实现，6 条隔离记录继续 quarantine。
- 完整 Flask 接口测试仍取决于 Flask、PyCryptodome、msgspec、colorama 等运行依赖是否可用。

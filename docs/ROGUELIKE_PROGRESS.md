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
| 离线规则事实层 | 第二阶段进行中，未接线 | `data/rlv2/rules` 已分离客户端事实快照与人工规则；固定 `2.7.51`、GameData commit、topic table hash、Schema 和来源状态；事件与区域页资料已完成首轮同步 | 继续固定藏品页面 revision，逐条转录成员关系并保持未知值为 `null` |
| 事件楼层资格 | 首轮资料转录完成，未接线 | 五个固定 PRTS revision 共 254 条页面事件已映射为 250 条 canonical 注解和 4 条 quarantine；171 条显式楼层范围已结构化，RO3 标准/month 候选分离 | 人工消歧 4 条特殊节点/变体，并补模式、结局条件、权重与效果；禁止全主题随机回退 |
| 区域与结局资料 | 首轮资料转录完成，未接线 | 五个固定主题页生成 36 条核心线性布局、22 条结局路线和 20 条入口原文；6 条结局/特殊区域记录隔离；Boss stage 仅按客户端字段等式推导 | 将入口原文审成条件 AST；为特殊/平面区域单独建模；核心布局转图约束前逐列核验 |
| 地图生成 | 已有安全约束，仍为近似 | 已实现基本可达、RO3 紧急节点上限等性质；`rollNodeData` 只可用于节点刷新候选，不能当自然地图白名单 | 每个受支持的 `theme × zone` 组合跑 2500 个固定种子硬验收 |
| 主题专属模块 | 部分实现 | RO1 临时生命、RO2 部分灯火/骰子、RO4/5 初始化外形等已存在 | 按客户端协议逐模块实现，未知概率保持显式近似 |

## 本轮已落地

- 新增 `server/rlv2_repository.py`，以 SQLite 作为当前局唯一真源。
- `server/rlv2.py` 的动作处理已接入按 UID 事务，嵌套 handler 复用同一事务。
- `server/account.py` 的 `SyncData` 已按 UID 合并当前局。
- 数据库提交通过 revision/CAS 防止陈旧写入。
- 单用户模式兼容导入和镜像旧 JSON；多用户模式必须提供合法 `Uid`。
- Legacy sidecar 只能由一个 UID 认领，避免同一旧存档被复制给多个用户。
- 五主题普通/紧急基础收益按 `theme + zone + nodeType` 结算，并校验客户端 `expItemId/goldItemId` 类型。
- EXP 在 `battleFinish` 自动入账并处理升级；源石锭作为独立 reward，经 `chooseBattleReward` 领取且不能重复发放或未领取即结束。
- 新增完整矩阵、边界和 handler 事务测试；当前 roguelike 相关测试为 **59 项通过**。
- 补齐 `/rlv2/finishGame` 与 `/rlv2/gameSettle`；`battleFinish` 返回完整公共响应并让已应用请求幂等返回 200；战斗奖励补齐 `state/isPerfect` 且不再下发伪造干员实例 ID。
- 终局不再写入客户端枚举中不存在的 `GAME_OVER` 或 `status.gameResult`；旧 SQLite 状态在 `SyncData` 和肉鸽动作入口自动迁移，避免结算 30000 和重登循环。
- 新建 `data/rlv2/rules` 离线事实层：从当前 topic table 提取主题、1489 件藏品、591 个关卡、390 个区域和 2495 个 scene，并将用户确认规则单独保存为未接线注解。
- 固定五个 PRTS“事件一览”revision 及 SHA-1，转录 254 条页面事件；250 条绑定 canonical scene，4 条歧义记录进入 quarantine，171 条明确楼层完成结构化。
- 新增确定性事件同步工具，校验页面 revision、客户端 scene 引用、RO3 month 重名候选和生成结果；运行时仍不联网、不加载这些规则。
- 固定五个 PRTS 主题页 revision 及 SHA-1，转录 36 条核心区域布局和 22 条结局终点；20 条“进入方式”保留来源原文，条件 AST 仍为 `null`。
- 从客户端 `bossIconId == specialNodeId` 推导结局 Boss stage 集合；RO1 空图标不猜测，`ro3_ending_c` 与 5 条特殊/平面区域记录进入 quarantine。
- 新增确定性区域同步工具，校验 zone/ending/stage 引用、同名变体排除、固定计数和生成结果；运行时仍不联网、不加载这些规则。

## 进行中

1. 从当前客户端 IL2CPP 元数据和真实抓包继续确认 `/rlv2/gameSettle` 的分数、记录、BP 与外层奖励字段。
2. 按固定 revision 继续将 PRTS/Tomimi 的藏品和模块事实转成版本化注解；事件部分继续补条件、权重、效果及 4 条 quarantine，区域部分继续审入口 AST 与 6 条 quarantine，运行时绝不联网。
3. 收集同版本真实战斗奖励协议 fixture，并独立建模 Boss、特殊区域、RO4 旗帜与主题乘区。

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
| 2026-07-15 | 三组 RLV2 测试、相关 Python 编译 | 59/59 通过 |
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
- 当前地图生成和结局改线仍在 zone 5 结束标准流程，尚不能自然进入隐藏第六层或 RO4/RO5 的替代 zone 7；矩阵已覆盖这些合法状态，但路线生成仍属独立缺口。
- Boss、传送/特殊区域、RO4 旗帜、紧急额外掉落及藏品/主题乘区仍无可靠完整规则；当前不会回退到普通/紧急矩阵。
- 奖励外形已按 `2.7.51` IL2CPP 字段约束实现，但仍缺同版本真实请求/响应 fixture。
- 事件页明确给出的 171 条楼层范围已转录但尚未接线；模式、结局条件、权重及大量 choice 效果仍为空，4 条特殊节点/变体仍在 quarantine。补楼层资格只解决“可能在哪层出现”，不等于事件已还原。
- 区域页的 36 条线性摘要和 22 条终点映射已转录但尚未接线；来源布局仍是 wikitext，入口条件 AST、完整有序路线、事件替换与结算顺序为空，6 条结局/特殊区域记录仍在 quarantine。
- 完整 Flask 接口测试仍取决于 Flask、PyCryptodome、msgspec、colorama 等运行依赖是否可用。

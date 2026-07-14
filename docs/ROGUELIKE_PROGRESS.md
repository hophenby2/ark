# Roguelike 模块完善进度

> 最后更新：2026-07-14（进行中）  
> 目标版本：客户端 `2.7.51 / Data 26-07-10`  
> 证据优先级：当前客户端表/协议 > PRTS/官方资料 > 腾讯整理表 > B 站旧版统计

## 当前状态

| 工作项 | 状态 | 当前结果 | 下一检查点 |
| --- | --- | --- | --- |
| 按 UID 持久化 | 已完成，待最终回归 | SQLite 保存 run、随机种子与 revision；每个动作使用 `BEGIN IMMEDIATE` 事务；2xx 提交，4xx/异常回滚 | 两用户、嵌套动作、重登与迁移测试全部通过 |
| Legacy 数据迁移 | 已完成，待最终回归 | 首个显式 UID 原子认领；记录唯一 owner；禁止第二个 UID 重复认领；单用户 sentinel 可原子转移 | 仓储测试已覆盖重复认领和 sentinel 切换 |
| `SyncData` | 已完成，待最终回归 | 按请求 UID 从仓储合并 `user.rlv2.current` | 完整依赖环境下补接口级回归 |
| 终局结算 | 研究中 | 当前客户端元数据确认存在 `POST /rlv2/gameSettle`；现有 `GAME_OVER` 仅是内部不可继续闸门 | 确认请求/响应字段后实现最小安全清局流程 |
| 战斗基础收益 | 数据已核对，待实现 | 已整理五主题逐层普通/紧急作战的指挥经验与源石锭矩阵；确认 `exploreExpOnKill` 不是该经验表 | 替换错误常量并补边界测试 |
| 事件楼层资格 | 数据已核对，待落表 | PRTS 事件模板可映射五主题事件与可出现楼层；RO1/2/4/5 可完整连接，RO3 重名可排除 month 变体消歧 | 生成离线数据、强校验引用、禁止全主题随机回退 |
| 地图生成 | 已有安全约束，仍为近似 | 已实现基本可达、RO3 紧急节点上限等性质；`rollNodeData` 只可用于节点刷新候选，不能当自然地图白名单 | 最终跑 2500 组固定种子性质测试 |
| 主题专属模块 | 部分实现 | RO1 临时生命、RO2 部分灯火/骰子、RO4/5 初始化外形等已存在 | 按客户端协议逐模块实现，未知概率保持显式近似 |

## 本轮已落地

- 新增 `server/rlv2_repository.py`，以 SQLite 作为当前局唯一真源。
- `server/rlv2.py` 的动作处理已接入按 UID 事务，嵌套 handler 复用同一事务。
- `server/account.py` 的 `SyncData` 已按 UID 合并当前局。
- 数据库提交通过 revision/CAS 防止陈旧写入。
- 单用户模式兼容导入和镜像旧 JSON；多用户模式必须提供合法 `Uid`。
- Legacy sidecar 只能由一个 UID 认领，避免同一旧存档被复制给多个用户。
- 新增仓储和 handler 事务测试；当前 roguelike 逻辑相关测试为 **38 项通过**。

## 进行中

1. 从当前客户端 IL2CPP 元数据继续确认 `/rlv2/gameSettle` 的协议字段。
2. 将战斗收益改为 `theme + zone + nodeType` 规则，并使用客户端 `goldItemId` / `expItemId`。
3. 将 PRTS 事件楼层资料转成版本化离线数据，运行时绝不联网。
4. 同步更新 `docs/ROGUELIKE_ANALYSIS.md` 中已经过时的 P0 与战斗收益结论。

## 已确认但暂不臆造的规则

- RO4 带旗帜关卡有独立收益，但当前状态尚无可靠 variant 标志；在能判定关卡变体前不按楼层误发。
- RO5 紧急作战公开规则明确额外掉落一件收藏品和一枚通宝，但当前客户端表没有服务端掉落权重；先不伪造具体池。
- `rollNodeData` 是刷新/重掷节点候选组，不是自然地图节点类型白名单。
- `Uid` 请求头目前没有 secret/session 认证；SQLite 已解决串档与事务一致性，但不能防止 UID 冒用。

## 验证记录

| 时间 | 验证 | 结果 |
| --- | --- | --- |
| 2026-07-14 | `tests.test_rlv2_logic` + `tests.test_rlv2_repository` + `tests.test_rlv2_transactions` | 38/38 通过 |
| 2026-07-14 | 相关 Python 文件 `py_compile` | 通过 |
| 2026-07-14 | 相关文件 `git diff --check` | 通过 |

## 资料与可复核来源

- [PRTS 集成战略](https://prts.wiki/w/%E9%9B%86%E6%88%90%E6%88%98%E7%95%A5)及五个主题页、事件一览页（访问日期：2026-07-14）。
- [Bilibili BV1qC4y1Q7Gy](https://www.bilibili.com/video/BV1qC4y1Q7Gy)，用于萨米主题地图节点统计的交叉参考。
- [腾讯文档指定工作表](https://docs.qq.com/sheet/DQkhoWVpEcUF2T3FV?tab=BB08J2)，用于玩家实测规则交叉检查，不作为运行时依赖。
- 当前仓库 `data/excel/roguelike_topic_table.json` 与客户端 IL2CPP 元数据，作为版本协议和表结构事实基准。

## 剩余风险

- 多个主题接口仍返回空 `202`，客户端可能把未实现动作误认为成功。
- 终局外层记录、分数、BP 与奖励字段尚无完整同版本协议证据。
- RO3/RO4/RO5 的大量事件 choice 效果仍为空，补楼层资格只解决“何时出现”，不等于效果已还原。
- 完整 Flask 接口测试仍取决于 Flask、PyCryptodome、msgspec、colorama 等运行依赖是否可用。

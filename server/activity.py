from flask import request, jsonify
from virtualtime import time
from utils import read_json, write_json, run_after_response, get_memory, decrypt_battle_data
from quest import questBattleStart
from constants import (
    SYNC_DATA_TEMPLATE_PATH,
    SERVER_DATA_PATH
)
import random

class checkInReward:
    # 这个类用于处理签到奖励
        
    def getCheckInReward():
        json_body = request.get_json()
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        access_id = json_body["activityId"]

        items = []
        modified = {}

        match access_id:
            case access_id if access_id.endswith("access"):
                activity_data = user_data["user"]["activity"]["CHECKIN_ACCESS"][access_id]
                activity_data["rewardsCount"] += 1
                activity_data["lastTs"] = time()
                items = [
                    {
                        "type": "AP_SUPPLY",
                        "id": "ap_supply_lt_80",
                        "count": 1
                    },
                    {
                        "type": "DIAMOND_SHD",
                        "id": "4003",
                        "count": 200
                    }
                ]
                
                modified = {
                    "activity": {
                        "CHECKIN_ACCESS": {
                            access_id: activity_data
                        }
                    }
                }
            case access_id if access_id.endswith("blessing"):
                activity_data = user_data["user"]["activity"]["BLESS_ONLY"][access_id]
                index = json_body["index"]

                if json_body["isFestival"] == 1:
                    activity_data["festivalHistory"][index]["state"] = 0
                else:
                    activity_data["history"][index] = 0

                modified = {
                    "activity": {
                        "BLESS_ONLY": {
                            access_id: activity_data
                        }
                    }
                }
            case _:
                modified = {}
                items = []

        result = {
            "playerDataDelta": {
                "modified": modified,
                "deleted": {}
            },
            "items": items
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def getActivityCheckInReward():

        json_body = request.get_json()

        activity_id = json_body["activityId"]
        target_index = json_body["index"]
        dyn_opt = json_body["dynOpt"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_data = user_data["user"]["activity"]["CHECKIN_ONLY"][activity_id]

        activity_data["history"][target_index] = 0
        activity_data["dynOpt"].append(dyn_opt)

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "CHECKIN_ONLY": {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        return result
    
    def getReward():

        json_body = request.get_json()
        # {'prayArray': [0, 1], 'activityId': 'act11pray'}
        # {'activityId': 'act24login'}
        # {'activityId': 'act3unique'}

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]
        items = []

        match activity_id:
            case activity_id if activity_id.endswith("pray"):
                activity_type = "PRAY_ONLY"
                activity_data = user_data["user"]["activity"][activity_type][activity_id]

                activity_data["lastTs"] = time()
                activity_data["praying"] = True

                count_list = [200,300, 400, 500, 600, 700, 800]
                random.shuffle(count_list)
                count_1 = random.choice(count_list)
                random.shuffle(count_list)
                count_2 = random.choice(count_list)
                if count_1 >= count_2:
                    activity_data["prayMaxIndex"] = json_body["prayArray"][0]
                    count = count_1
                else:
                    activity_data["prayMaxIndex"] = json_body["prayArray"][1]
                    count = count_2

                activity_data["prayArray"] = [
                    {
                        "index": json_body["prayArray"][0],
                        "count": count_1
                    },
                    {
                        "index": json_body["prayArray"][1],
                        "count": count_2
                    }
                ]
                items.append({
                    "type": "DIAMOND_SHD",
                    "id": "4003",
                    "count": count
                })

            case activity_id if activity_id.endswith("login"):
                activity_type = "LOGIN_ONLY"
                activity_data = user_data["user"]["activity"][activity_type][activity_id]
                activity_data["reward"] = 0

            case activity_id if activity_id.endswith("unique"):
                activity_type = "UNIQUE_ONLY"
                activity_data = user_data["user"]["activity"][activity_type][activity_id]
                activity_data["reward"] = 0

            case _:
                result = {
                    "playerDataDelta":{
                        "modified": {},
                        "deleted": {}
                    }
                }
                return result

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        activity_type: {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {}
            },
            "items": items
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        return result
    
    def changeFestivalChar():
        json_body = request.get_json()
        # {'activityId': 'act3blessing', 'index': 0, 'newChar': 'act1blessing_festival_1_1'}
        activity_id = json_body["activityId"]
        index = json_body["index"]
        new_char = json_body["newChar"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_data = user_data["user"]["activity"]["BLESS_ONLY"][activity_id]

        activity_data["festivalHistory"][index]["charId"] = new_char

        result = {
            "playerDataDelta":{
                "modified": {
                    "activity": {
                        "BLESS_ONLY": {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def sign():
        json_body = request.get_json()
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        # {'actId': 'act3signvs', 'tasteChoice': 2} 咸粽子
        # {'actId': 'act3signvs', 'tasteChoice': 1} 甜粽子
        # "act3signvs": {
        #             "sweetVote": 0,
        #             "saltyVote": 0,
        #             "canVote": 1,
        #             "todayVoteState": 0,
        #             "voteRewardState": 0,
        #             "signedCnt": 0,
        #             "availSignCnt": 1,
        #             "socialState": 2,
        #             "actDay": 1
        #         }
        act_id = json_body["actId"]
        act_data = user_data["user"]["activity"]["CHECKIN_VS"][act_id]

        act_data["signedCnt"] += 1
        act_data["canVote"] = 0
        if json_body["tasteChoice"] == 1:
            act_data["sweetVote"] += 1
        else:
            act_data["saltyVote"] += 1

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "CHECKIN_VS": {
                            act_id: act_data
                        }
                    }
                },
                "deleted": {}
            },
            "items": [
                {
                "type": "AP_SUPPLY",
                "id": "ap_supply_lt_120",
                "count": 1
                },
                {
                "type": "GOLD",
                "id": "4001",
                "count": 30000
                }
            ]
        }

        return result 

class switchOnly:
    def getSwitchOnlyReward():
        json_body = request.get_json()

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]
        reward_id = json_body["reward"]
        activity_data = user_data["user"]["activity"]["SWITCH_ONLY"][activity_id]

        activity_data["rewards"][reward_id] = 0

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "SWITCH_ONLY": {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        return result

class enemyDuel:
    def singleBattleStart():
        
        #{"activityId": "act1enemyduel", "modeId": "soloOperation"}

        return{
            "pushMessage": [],
            "result": 0,
            "battleId": "abcdefgh-1234-5678-a1b2c3d4e5f6",
        }

    def singleBattleFinish():

        json_body = request.get_json()
        # run_after_response(write_json ,json_body, "debug.json")

        rankList = json_body["settle"]["rankList"]
        rank_lst = [
            {"id": "1", "rank": 1, "score": 1919810, "isPlayer": 1},
        ]
        activity_table = get_memory("activity_table")
        activity_id = json_body["activityId"]
        for npc_id in activity_table["activity"]["ENEMY_DUEL"][activity_id]["npcData"]:
            if len(rank_lst) >= 8:
                break
            rank_lst.append(
                {"id": npc_id, "rank": 2, "score": 114514, "isPlayer": 0},
            )

        result = {
            "result": 0,
            "apFailReturn": 0,
            "itemReturn": [],
            "rewards": [],
            "unusualRewards": [],
            "overrideRewards": [],
            "additionalRewards": [],
            "diamondMaterialRewards": [],
            "furnitureRewards": [],
            "goldScale": 0.0,
            "expScale": 0.0,
            "firstRewards": [],
            "unlockStages": None,
            "pryResult": [],
            "alert": [],
            "suggestFriend": False,
            "extra": None,
            "choiceCnt": {
                "skip": 0,
                "normal": 5,
                "allIn": 1
            },
            "commentId": "Comment_Operation_7",
            "isHighScore": False, # 是否为最高记录
            "rankList": rankList,
            "dailyMission": {
                "add": 0,
                "reward": 0
            },
            "bp": 0
        }

        return result

class act24side:

    def act24alchemy():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        gacha_box_id = json_body["gachaBox"]
        items = json_body["items"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_table = get_memory("activity_table")
        activity_data = user_data["user"]["activity"]["TYPE_ACT24SIDE"][activity_id]
        items_data:dict[str, int] = activity_data["alchemy"]["item"]
        gachabox = activity_table["activity"]["TYPE_ACT24SIDE"][activity_id]["meldingGachaBoxGoodDataMap"][gacha_box_id]
        total_score = 0

        items_score_map = {
            "act50side_melding_1": 2,
            "act50side_melding_2": 3,
            "act50side_melding_3": 5,
            "act50side_melding_4": 10,
            "act50side_melding_5": 20,
            "act50side_melding_6": 200
        }

        for key in items.keys():
            if items_data.get(key, 0) < items[key]:
                return {}, 400
            else:
                items_data[key] -= items[key]
                total_score += items[key] * items_score_map[key]

        gacha_times = total_score // 100

        gacha_data = activity_data["alchemy"]["gacha"]
        available = []
        for box_item in gachabox:
            good_id = box_item["goodId"]
            drawn = gacha_data.get(good_id, 0)
            remaining = box_item["totalCount"] - drawn
            if remaining > 0:
                available.append([box_item, remaining])

        draw_result = {}
        for _ in range(gacha_times):
            if not available:
                break
            idx = random.randint(0, len(available) - 1)
            box_item, remaining = available[idx]
            good_id = box_item["goodId"]
            if good_id not in draw_result:
                draw_result[good_id] = {
                    "goodId": good_id,
                    "itemId": box_item["itemId"],
                    "itemType": box_item["itemType"],
                    "perCount": box_item["perCount"],
                    "count": 0
                }
            draw_result[good_id]["count"] += 1
            remaining -= 1
            if remaining <= 0:
                available.pop(idx)
            else:
                available[idx][1] = remaining

        draw_list = []
        for v in draw_result.values():
            draw_list.append(v)
        # {
        #     "goodId": "gachabox1_1",
        #     "itemId": "p_char_4215_buddy",
        #     "itemType": "MATERIAL",
        #     "perCount": 1,
        #     "count": 1
        # }
        rewards = []
        for item in draw_list:
            # 活动数据添加已获得奖品计数
            box = activity_data["alchemy"]["gacha"][gacha_box_id]
            good_id = item["goodId"]
            box[good_id] = box.get(good_id, 0) + item["count"]
            # 计算物品总数，不写添加逻辑，要添加物品自行调用admin.adminutils的GiveItem函数
            items_count = item["perCount"] * item["count"]
            items = {
                "id": item["itemId"],
                "type": item["itemType"],
                "count": items_count
            }
            rewards.append(items)

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT24SIDE": {
                            activity_id: {
                                "alchemy": activity_data["alchemy"]
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "rewards": rewards
        }

        return result
    
    def act24setTool():
        json_body = request.get_json()
        print(json_body)
        activity_id = json_body["activityId"]
        tools = json_body["tools"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_data = user_data["user"]["activity"]["TYPE_ACT24SIDE"][activity_id]
        # 传入的tools是激活列表，不能以tools为基准，否则全撤了会处理异常
        for key in activity_data["tool"].keys():
            if key in tools:
                activity_data["tool"][key] = 2
            else:
                activity_data["tool"][key] = 1

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT24SIDE": {
                            activity_id: {
                                "tool": activity_data["tool"]
                            }
                        }
                    }
                },
                "deleted": {},
            }
        }

        return result

class act35side:
    # public class Torappu.UI.Carving.Carving
    from data.act_data import ROUND_DATA, INITIAL_CARD, PREPARED_CARD_DATA, MATERIAL_PRICE, MATERIAL_LIST, SHOP_DATA, COIN_DATA, CARD_DATA

    def _BuildPreparedCardData() -> dict:

        data = {}

        def make_simple(inp: str, out: str, mults: list[float]) -> dict:
            """单输入单输出卡牌"""
            return {
                str(i + 1): {"inputs": {inp: 1}, "outputs": {out: 1}, "multiplier": mult}
                for i, mult in enumerate(mults)
            }

        def make_simple2(inputs: dict, outputs: dict) -> dict:
            """多输入多输出卡牌（所有等级相同）"""
            return {
                str(i): {"inputs": dict(inputs), "outputs": dict(outputs), "multiplier": 1.0}
                for i in range(1, 4)
            }
        data.update({
            "card_fire_1": make_simple("material_fire_1", "material_fire_2", [1.0, 1.0, 2.0]),
            "card_fire_2": make_simple("material_fire_2", "material_fire_3", [1.0, 2.0, 2.0]),
            "card_fire_3": make_simple("material_fire_3", "material_fire_4", [1.0, 2.4, 2.4]),
            "card_fire_4": make_simple("material_fire_4", "material_fire_5", [1.0, 1.0, 1.0]),
        })

        data["card_leaf_1"] = {
            "1": {"inputs": {"material_leaf_1": 10}, "outputs": {"material_leaf_2": 5, "material_sand": 5}, "multiplier": 1.0},
            "2": {"inputs": {"material_leaf_1": 10}, "outputs": {"material_leaf_2": 8, "material_sand": 2}, "multiplier": 1.0},
            "3": {"inputs": {"material_leaf_1": 1},  "outputs": {"material_leaf_2": 1}, "multiplier": 1.0},
        }

        leaf_rules = {
            "card_leaf_2": [(4, 6), (6, 4), (8, 2)],
            "card_leaf_3": [(3, 7), (5, 5), (7, 3)],
        }

        for card_name, ratios in leaf_rules.items():
            n = int(card_name.split("_")[-1])
            data[card_name] = {
                str(i + 1): {
                    "inputs": {f"material_leaf_{n}": 10},
                    "outputs": {f"material_leaf_{n+1}": a, "material_sand": b},
                    "multiplier": 1.0,
                }
                for i, (a, b) in enumerate(ratios)
            }

        data.update({
            "card_clst_1": make_simple2({"material_clst_1": 1, "material_sand": 1}, {"material_clst_2": 1}),
            "card_clst_2": make_simple2({"material_clst_2": 1, "material_leaf_2": 1}, {"material_clst_3": 1}),
            "card_clst_3": make_simple2({"material_clst_3": 1, "material_fire_4": 1}, {"material_clst_4": 1}),
        })

        data.update({
            "card_sand_1": make_simple("material_sand", "material_sand", [2, 3, 5]),
            "card_sand_2": make_simple("material_sand", "material_sand", [3, 5, 8]),
            "card_sand_3": make_simple("material_sand", "material_sand", [5, 9, 9]),
        })

        return data
    
    def _RandomCard(carving_data):
        max_lv_card = []
        # 获取满级卡信息
        card_info = carving_data["card"]
        for card, lv in card_info.items():
            if card_info[card] == 3:
                max_lv_card.append(card)

        # 随机选卡
        def _PickRandom(max_lv_card1, pool_name=None, count=3):
            if pool_name is None:
                return [None] * count
            if pool_name == "all":
                card_data = (
                    act35side.CARD_DATA["fire"] +
                    act35side.CARD_DATA["leaf"] +
                    act35side.CARD_DATA["clst"] +
                    act35side.CARD_DATA["sand"]
                )
            else:
                card_data = act35side.CARD_DATA[pool_name]
            random_list = list(set(card_data) - set(max_lv_card1))
            random.shuffle(random_list)
            return random_list[:count]

        # 映射表：关卡ID -> 池子名
        challenge_map = {
            "challenge_3": "fire",
            "challenge_4": "leaf",
            "challenge_5": "clst",
            "challenge_6": "sand",
            "challenge_7": "all",
            "challenge_9": "all",
            "challenge_10": "all",
            "challenge_8": None,
        }

        cid = carving_data["id"]

        if cid == "challenge_1":
            good = [{"id": "card_fire_3", "price": 0}, None, None]
        elif cid in challenge_map:
            good = _PickRandom(max_lv_card, challenge_map[cid])
        else:
            good = [None, None, None]

        return good

    def act35create():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        challenge_id = json_body["challengeId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]
        activity_data["carving"] = {}

        material = {
            "material_fire_1": 0,
            "material_leaf_1": 0,
            "material_clst_1": 0,
            "material_sand": 0
        }
        if act35side.ROUND_DATA[challenge_id + "_r1"] is None:
            keys = list(material.keys())
            n = len(keys)

            total = 100
            max_diff = 25
            
            # 计算每个值的最小和最大可能范围
            # 平均值
            avg = total / n
            
            # 确定每个值的范围，确保差值不超过max_diff
            min_val = max(0, avg - max_diff/2)
            max_val = min(total, avg + max_diff/2)
            
            # 生成第一个随机值
            values = [random.randint(int(min_val), int(max_val))]
            
            # 生成后续值，考虑已分配的值和剩余的总和
            remaining = total - values[0]
            for i in range(1, n-1):
                # 计算当前值可能的范围
                remaining_avg = remaining / (n - i)
                current_min = max(0, remaining_avg - max_diff/2, remaining - max_val*(n-i-1))
                current_max = min(remaining, remaining_avg + max_diff/2, remaining - min_val*(n-i-1))
                
                # 确保范围有效
                current_min = max(min_val, current_min)
                current_max = min(max_val, current_max)
                
                # 生成随机值
                if current_min <= current_max:
                    value = random.randint(int(current_min), int(current_max))
                else:
                    value = int(remaining_avg)  # 如果范围无效，使用平均值
                
                values.append(value)
                remaining -= value
            
            # 添加最后一个值
            values.append(remaining)
            
            # 打乱顺序
            random.shuffle(values)
            
            # 分配值到材料
            for i, key in enumerate(keys):
                material[key] = values[i]

        else:
            material = act35side.ROUND_DATA[challenge_id + "_r1"]


        # 特殊关卡卡牌处理
        match challenge_id:
            case "challenge_1":
                card = {
                    "card_fire_1": 1
                }
                free_cnt = 1
            case "challenge_8":
                card = {
                    "card_fire_1": 3,
                    "card_fire_2": 3,
                    "card_fire_3": 3,
                    "card_fire_4": 3,
                    "card_leaf_1": 3,
                    "card_leaf_2": 3,
                    "card_leaf_3": 3,
                    "card_clst_1": 3,
                    "card_clst_2": 3,
                    "card_clst_3": 3,
                    "card_sand_1": 3,
                    "card_sand_2": 3,
                    "card_sand_3": 3
                }
                free_cnt = 0
            case _:
                card = {}
                free_cnt = 2
        
        good = []
        if act35side.INITIAL_CARD[challenge_id] is not None:
            for card_id in act35side.INITIAL_CARD[challenge_id]:
                good.append({
                    "id": card_id,
                    "price": 0
                })
            if len(good) < 3:
                good += [None] * (3 - len(good))
        else:
            good = [None, None, None]
        shop = {
            "coin": 0,
            "good": good,
            "freeCardCnt": free_cnt,
            "refreshPrice":99,
            "slotPrice": 8
        }

        carving_data = {
            "id": challenge_id,
            "round": 1,
            "roundCoinAdd": -1,
            "score": 0,
            "state": 5,
            "material": material,
            "card": card,
            "slotCnt": 2,
            "shop": shop,
            "mission": None
        }
        activity_data["carving"] = carving_data

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": carving_data
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def act35settle():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]

        challenge_id = carving_data["id"]
        score = carving_data["score"]
        round_num = carving_data["round"]
        # 清空数据
        user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"] = None

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": None
                            }
                        }
                    }
                }
            },
            "challengeId": challenge_id,
            "score": score,
            "oldRound": 0,
            "newRound": round_num,
            "pointStage": 0,
            "pointRound": 0,
            "pointBefore": 0,
            "pointAfter": 0
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result
    
    def act35toBuy():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]
        
        # 商店卡牌刷新
        good_list = act35side._RandomCard(carving_data)
        good = []
        if carving_data["shop"]["freeCardCnt"] > 0:
            for card_id in good_list:
                if card_id is None:
                    good.append(None)
                else:
                    good.append({
                        "id": card_id,
                        "price": 0
                    })
            if len(good) < 3:
                good += [None] * (3 - len(good))
        else:
            for card_id in good_list:
                if card_id is None:
                    good.append(None)
                else:
                    good.append({
                        "id": card_id,
                        "price": 2
                    })
            if len(good) < 3:
                good += [None] * (3 - len(good))

        carving_data["shop"]["good"] = good
        carving_data["shop"]["coin"] = 0

        result = {
            
        }
        carving_data["shop"]["good"] = good

        # 操作台槽位
        if carving_data["slotCnt"] < 8:
            carving_data["shop"]["slotPrice"] = act35side.SHOP_DATA["slot"][carving_data["slotCnt"] - 2]


        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": {
                                    "shop": carving_data["shop"],
                                    "state": 1
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result
    
    def act35refreshShop():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]
        good_list = act35side._RandomCard(carving_data)
        good = []
        if carving_data["shop"]["freeCardCnt"] > 0:
            for card_id in good_list:
                good.append({
                    "id": card_id,
                    "price": 0
                })
            if len(good) < 3:
                good += [None] * (3 - len(good))
        else:
            for card_id in good_list:
                good.append({
                    "id": card_id,
                    "price": 2
                })
            if len(good) < 3:
                good += [None] * (3 - len(good))
        
        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            "carving": {
                                "shop": carving_data["shop"],
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result
    
    def act35buySlot():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]

        carving_data["slotCnt"] += 1
        carving_data["shop"]["coin"] -= 8
        carving_data["shop"]["slotPrice"] = -1

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": {
                                    "shop": carving_data["shop"],
                                    "slotCnt": carving_data["slotCnt"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def act35buyCard():
        json_body = request.get_json()
        # {'activityId': 'act35sre', 'slot': 0}
        activity_id = json_body["activityId"]
        slot = json_body["slot"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]

        # 获取要购买的卡片ID
        card_id = carving_data["shop"]["good"][slot]["id"]
        
        # 更新卡片数量
        if card_id in carving_data["card"]:
            carving_data["card"][card_id] += 1
        else:
            carving_data["card"][card_id] = 1
        
        # 更新商店状态
        if carving_data["shop"]["freeCardCnt"] > 0:
            carving_data["shop"]["freeCardCnt"] -= 1  # 减少免费卡次数
        carving_data["shop"]["coin"] -= carving_data["shop"]["good"][slot]["price"]
        carving_data["shop"]["good"][slot] = None
        # 免费次数为0时，开始收费
        if carving_data["shop"]["freeCardCnt"] <= 0:
            for good in carving_data["shop"]["good"]:
                if good is not None:
                    if good["price"] == 0:
                        # 初始价格
                        good["price"] = 3
                    else:
                        good["price"] += 1

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": {
                                    "shop": {
                                        "coin": 10,
                                        "freeCardCnt": carving_data["shop"]["freeCardCnt"],
                                        "good": carving_data["shop"]["good"]
                                    },
                                    "card": carving_data["card"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "pushMessage": []
        }
        
        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result
    
    def act35toProcess():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]
        carving_data["state"] = 2

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": {
                                    "state": carving_data["state"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    # def act35SideProcess_old():
    #     json_body = request.get_json()
    #     activity_id = json_body["activityId"]
    #     cards = json_body["cards"]

    #     user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    #     carving_data = user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"]

    #     card_info = carving_data["card"]
    #     materials = carving_data["material"]
    #     slot_cnt = carving_data["slotCnt"]
    #     empty_slots = slot_cnt - len(cards)

    #     card_data_map = act35side.PREPARED_CARD_DATA
    #     material_data_map = act35side.MATERIAL_PRICE

    #     frames = []

    #     # 上一回合总分
    #     base_score = carving_data["score"]
    #     total_score = base_score

    #     # 非工艺区生效卡处理
    #     pre_exec_cards = []
    #     for card, lv in card_info.items():
    #         lv = str(lv)
    #         if card in card_data_map and card_data_map[card][lv]["pre_exec"]:
    #             if card not in cards:
    #                 pre_exec_cards.append(card)

    #     ordered_cards = pre_exec_cards + cards

    #     # 遍历卡列表
    #     for card in ordered_cards:
    #         lv = str(card_info[card])
    #         card_cfg = card_data_map[card][lv]
    #         if not card_cfg:
    #             continue

    #         inputs = card_cfg["inputs"]
    #         outputs = card_cfg["outputs"]
    #         multiplier = card_cfg["multiplier"]
    #         extra_outputs = card_cfg["extra_outputs"]
    #         flat_score = card_cfg["flat_score"]
    #         series_bonus = card_cfg["series_bonus"]

    #         product = {}
    #         # 如果材料足够，则循环合成
    #         while all(materials.get(mat, 0) >= need for mat, need in inputs.items()):
    #             # 扣输入
    #             for mat, need in inputs.items():
    #                 materials[mat] -= need

    #             # 正常产出
    #             for mat, out in outputs.items():
    #                 amount = int(out * multiplier)
    #                 materials[mat] = materials.get(mat, 0) + amount
    #                 product[mat] = product.get(mat, 0) + amount

    #             # 额外产出
    #             for mat, out in extra_outputs.items():
    #                 materials[mat] = materials.get(mat, 0) + out
    #                 product[mat] = product.get(mat, 0) + out

    #         # 计算当前库存的估值
    #         step_score = 0
    #         for mat, num in materials.items():
    #             base_val = material_data_map.get(mat, 0)
    #             for prefix, bonus in series_bonus.items():
    #                 if mat.startswith(prefix):
    #                     base_val += bonus
    #                     break
    #             step_score += base_val * num

    #         # 空槽位加分
    #         step_score += empty_slots * flat_score

    #         # 基础分 + 当前估值
    #         total_score = base_score + step_score

    #         frames.append({
    #             "card": card,
    #             "product": product,
    #             "score": total_score,  
    #             "type": 0
    #         })

    #     # 更新 carving_data 的 总分
    #     carving_data["score"] = total_score

    #     # 加钱
    #     coin = act35side.COIN_DATA[carving_data["id"]][carving_data["round"] - 1]
    #     carving_data["shop"]["coin"] += coin
    #     carving_data["roundCoinAdd"] += coin

    #     result = {
    #         "playerDataDelta": {
    #             "modified": {
    #                 "activity": {
    #                     "TYPE_ACT35SIDE": {
    #                         activity_id: {
    #                             "carving": {
    #                                 "score": frames[-1]["score"],
    #                                 "shop": carving_data["shop"],
    #                                 "roundCoinAdd": carving_data["roundCoinAdd"],
    #                                 "state": 3
    #                             }
    #                         }
    #                     }
    #                 }
    #             },
    #             "deleted": {}
    #         },
    #         "frames": frames
    #     }

    #     # run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
    #     return result
    
    def act35process():
        """
        处理活动35侧边流程的函数
        负责处理卡牌合成、材料管理和分数计算等功能
        """
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        cards:list[str] = json_body["cards"]

        # 读取数据
        card_data_map = act35side.PREPARED_CARD_DATA
        material_data_map = act35side.MATERIAL_PRICE
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = dict(user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"])

        card_info:dict[str, int] = carving_data["card"]
        materials:dict[str, int] = carving_data["material"]
        slot_cnt:int = carving_data["slotCnt"]
        empty_slots = slot_cnt - len(cards)# 空槽位数量

        frames = []# 帧记录列表
        base_score = carving_data["score"]# 当前分数
        total_score = base_score

        # 用于宝石合成的闭包函数
        def score_calculation(card: str):
            card_lv = str(card_info[card])  # 卡牌等级
            card_cfg = card_data_map[card][card_lv]  # 卡牌信息
            inputs: dict[str, int] = card_cfg["inputs"]  # 输入材料
            outputs: dict[str, int] = card_cfg["outputs"]  # 输出材料
            multiplier: float = card_cfg["multiplier"]  # 合成倍率

            syn_times: int = float('inf')  # 初始化为无穷大，找出所有输入能支持的最小合成次数
            for mat, need in inputs.items():
                count: int = materials.get(mat, 0)
                if need <= 0:
                    continue
                syn_times = min(syn_times, count // need)

            # syn_times转整数
            if syn_times == float('inf'):
                syn_times = 0
            else:
                syn_times = int(syn_times)

            # 消耗材料
            for mat, need in inputs.items():
                count: int = materials.get(mat, 0)
                materials[mat] = count - need * syn_times

            product: dict[str, int] = {}

            # 产出材料
            for mat, out in outputs.items():
                gain = int(out * multiplier * syn_times)
                materials[mat] = materials.get(mat, 0) + gain
                product[mat] = gain

            result = {
                "syn_times": syn_times,
                "product": product
            }

            return result

        # —— 淬雕I/II/III 合成
        fire_card = {"card_fire_1", "card_fire_2", "card_fire_3"}
        syn_card = {}
        for card in fire_card:
            # 卡牌等级检查
            card_lv:int = card_info.get(card, 0)
            if card_lv <= 1:
                continue
            # 合成
            product = score_calculation(card)
            # 算分
            step_score = 0
            for mat, num in materials.items():
                base_val = material_data_map[mat]
                step_score += base_val * num
            total_score += step_score

            frames.append({
                "card": card,
                "product": product,
                "score": total_score,  
                "type": 0
            })

            syn_card.add(card)

        cards = [item for item in cards if item not in syn_card]

        # —— 常规合成
        for card in cards:# 遍历cards列表，根据卡牌顺序进行合成
            card_lv: int = card_info[card]

            # 交糅I/II/III 均分材料
            if card.startswith("card_clst"):
                match card:
                    case "card_clst_1":
                        if card_lv > 1:
                            sum_cnt = materials.get("material_sand", 0) + materials.get("material_clst_1", 0)
                            count_half = int(sum_cnt / 2)
                            materials["material_sand"] = count_half
                            materials["material_clst_1"] = count_half
                    case "card_clst_2":
                        if card_lv == 3:
                            sum_cnt = materials.get("material_leaf_2", 0) + materials.get("material_clst_2", 0)
                            count_half = int(sum_cnt / 2)
                            materials["material_leaf_2"] = count_half
                            materials["material_clst_2"] = count_half
                    case "card_clst_3":
                        if card_lv > 1:
                            sum_cnt = materials.get("material_fire_4", 0) + materials.get("material_clst_3", 0)
                            count_half = int(sum_cnt / 2)
                            materials["material_fire_4"] = count_half
                            materials["material_clst_3"] = count_half

            # 合成
            syn_info = score_calculation(card)
            syn_times:int = syn_info["syn_times"]
            product:dict[str, int] = syn_info["product"]

            # —— 算分
            step_score:int = 0
            extra_score:int = 0
            # 卡牌等级效果处理
            match card:
                # —— 淬雕 IV 空槽位加分
                case "card_fire_4":
                    if card_lv > 1:
                        step_score += empty_slots * (1500 if card_lv == 2 else 5000)

                # —— 滤纯I/II/III 三级额外产出沙伊纳
                case "card_leaf_1" | "card_leaf_2" | "card_leaf_3":
                    if card_lv == 3:
                        count:int = syn_times
                        product["material_sand"] = count

                # —— 交糅I/II/III 三级额外加分
                case "card_clst_1" | "card_clst_2" | "card_clst_3":
                    match card:
                        case "card_clst_1":
                            if card_lv == 3:
                                extra_score += 5
                        case "card_clst_2":
                            if card_lv > 1:
                                extra_score += 15
                        case "card_clst_3":
                            if card_lv == 3:
                                step_score += syn_times * 100

                case _:
                    pass
                
            # 当前全部材料的总分
            for mat, num in materials.items():
                base_val = material_data_map.get(mat, 0)
                # 天空伊纳系列宝石额外加分
                if mat.startswith("card_clst"):
                    base_val += extra_score
                step_score += base_val * num
            total_score += step_score

            frames.append({
                "card": card,
                "product": product,
                "score": total_score,  
                "type": 0
            })

        # 更新 carving_data 的 总分
        carving_data["score"] = total_score

        # 加钱
        coin = act35side.COIN_DATA[carving_data["id"]][carving_data["round"] - 1]
        carving_data["shop"]["coin"] += coin
        carving_data["roundCoinAdd"] += coin

        carving_data["state"] = 3

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": carving_data
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "frames": frames
        }

        # run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def act35nextRound():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        carving_data = dict(user_data["user"]["activity"]["TYPE_ACT35SIDE"][activity_id]["carving"])
        challenge_id = carving_data["id"]
        
        # 回合计数
        carving_data["round"] += 1

        # 下回合初始材料
        material = {
            "material_fire_1": 0,
            "material_leaf_1": 0,
            "material_clst_1": 0,
            "material_sand": 0
        }
        if act35side.ROUND_DATA[challenge_id + "_r" + str(carving_data["round"])] is None:
            keys = list(material.keys())
            n = len(keys)

            total = 100
            max_diff = 25
            
            # 计算每个值的最小和最大可能范围
            # 平均值
            avg = total / n
            
            # 确定每个值的范围，确保差值不超过max_diff
            min_val = max(0, avg - max_diff/2)
            max_val = min(total, avg + max_diff/2)
            
            # 生成第一个随机值
            values = [random.randint(int(min_val), int(max_val))]
            
            # 生成后续值，考虑已分配的值和剩余的总和
            remaining = total - values[0]
            for i in range(1, n-1):
                # 计算当前值可能的范围
                remaining_avg = remaining / (n - i)
                current_min = max(0, remaining_avg - max_diff/2, remaining - max_val*(n-i-1))
                current_max = min(remaining, remaining_avg + max_diff/2, remaining - min_val*(n-i-1))
                
                # 确保范围有效
                current_min = max(min_val, current_min)
                current_max = min(max_val, current_max)
                
                # 生成随机值
                if current_min <= current_max:
                    value = random.randint(int(current_min), int(current_max))
                else:
                    value = int(remaining_avg)  # 如果范围无效，使用平均值
                
                values.append(value)
                remaining -= value
            
            # 添加最后一个值
            values.append(remaining)
            
            # 打乱顺序
            random.shuffle(values)
            
            # 分配值到材料
            for i, key in enumerate(keys):
                material[key] = values[i]
        else:
            material = act35side.ROUND_DATA[challenge_id + "_r" + str(carving_data["round"])]

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT35SIDE": {
                            activity_id: {
                                "carving": {
                                    "round": carving_data["round"],
                                    "state": 1,
                                    "material": material,
                                    "shop": carving_data["shop"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

class act42side:
    def act42getDailyRewards():
        json_body = request.get_json()
        activity_id = json_body["activityId"]

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT42SIDE": {
                            activity_id: {
                                "dailyRewardState": 0
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result

    def act42acceptTask():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        task_id = json_body["taskId"]
        # 任务状态定义位于 public enum Torappu.PlayerActivity.PlayerAct42SideActivity.TaskState

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT42SIDE": {
                            activity_id: {
                                "taskMap": {
                                    task_id: 2
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result

    def act42confirmTask():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        task_id = json_body["taskId"]

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "TYPE_ACT42SIDE": {
                            activity_id: {
                                "taskMap": {
                                    task_id: 4
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result

class vhalfidle:
    from data.act_data import SPEC_CHAR, VHALFIDLE_POOLS, E_0, E_1, E_2

    def _AddCharToActivity(activity_data, user_data, char_id):
        """
        角色添加逻辑
        将角色添加到活动数据中，如果角色已存在则不添加
        """
        # 确保 troop/char 结构存在
        troop = activity_data.get("troop", {})
        troop.get("char", {})

        # ① 检查是否已有相同角色（防止重复添加）
        for char_info in troop["char"].values():
            if char_info.get("charId") == char_id:
                return  # 已存在则直接跳过

        # ② 从用户主数据中查找对应角色
        chars_from_sync = user_data.get("user", {}).get("troop", {}).get("chars", {})
        target_char_info = next(
            (info for info in chars_from_sync.values() if info.get("charId") == char_id),
            None
        )
        if not target_char_info:
            return  # 找不到对应角色则跳过

        inst_id = str(target_char_info["instId"])

        # ③ 构建活动角色信息
        new_char_info = {
            "instId": target_char_info["instId"],
            "charId": target_char_info["charId"],
            "level": target_char_info.get("level", 1),
            "evolvePhase": target_char_info.get("evolvePhase", 0),
            "skillLvl": 10 if target_char_info.get("evolvePhase", 0) == 2 else 7,
            "isAssist": False,
            "defaultSkillId": "",
            "defaultEquipId": "",
        }

        # ④ 处理默认技能
        default_skill_index = target_char_info.get("defaultSkillIndex", -1)
        if default_skill_index != -1 and "skills" in target_char_info:
            skills = target_char_info["skills"]
            if len(skills) > default_skill_index:
                new_char_info["defaultSkillId"] = skills[default_skill_index].get("skillId", "")

        # ⑤ 处理默认模组
        if target_char_info.get("currentEquip"):
            new_char_info["defaultEquipId"] = target_char_info["currentEquip"]

        # ⑥ 添加到活动数据
        troop["char"][inst_id] = new_char_info

    def refreshProduct():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        production = act_info["production"]

        now_ts = time()
        last_ts = production["harvestTs"]
        diff_mult = (now_ts - last_ts) / 3600
        production["refreshTs"] = now_ts

        for key, value in production["rate"].items():
            cnt = int(value * diff_mult)
            production["product"].update({key: cnt})

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "production": production
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def harvest():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        production = act_info["production"]

        keys_to_remove = []
        items = []
        milestoneAdd = 0

        for key, value in production["product"].items():
            if key == "act1vhalfidle_token_point":
                milestoneAdd = production["product"][key]
                items.append({
                    "itemId": key,
                    "count": production["product"][key]
                })
            cnt = int(value + act_info["inventory"].get(key, 0))
            act_info["inventory"].update({key: cnt})
            items.append({
                "itemId": key,
                "count": production["product"][key]
            })
            keys_to_remove.append(key)

        production["product"] = {}

        production["harvestTs"] = time()
        production["refreshTs"] = time()

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "inventory": act_info["inventory"],
                                "production": production
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "milestoneAdd": milestoneAdd,
            "items": items
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def unlockTech():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        # {'activityId': 'act1vhalfidle', 'techId': 'node_1_2'}
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        tech_list = act_info["tech"]["unlock"]

        tech_list.append(json_body["techId"])

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "tech": {
                                    "unlock": tech_list
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def recruitNormal():
        json_body = request.get_json()
        activity_id = json_body["activityId"]
        pool_id = json_body["poolId"]
        count = json_body["count"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        troop_chars = sync_data["user"]["troop"]["chars"]
        act_chars = act_info["troop"]["char"]
        poolTimes = act_info["recruit"]["poolTimes"]

        vhalfidle_pools = vhalfidle.VHALFIDLE_POOLS
        spec_char = vhalfidle.SPEC_CHAR

        # 资源检查
        if act_info["inventory"]["gacha_normal"] >= count * 20:
            act_info["inventory"]["gacha_normal"] -= count * 20
        else:
            return jsonify({"result": 1, "errMsg": "封装矿核不足"}), 404

        # 初始数据定义
        newChar = []
        oldChar = []
        have_chars = set()

        # 获取已有角色ID集合
        for key, value in act_chars.items():
            have_chars.add(act_chars[key]["charId"])

        # 卡池逻辑
        if pool_id in [f"gachaPac{i}" for i in range(1, 7)]:
            # 定向卡池：一次性获取该卡池的所有角色
            pool_set = vhalfidle_pools.get(pool_id, set()).copy()

            for char_id in pool_set:
                if char_id not in have_chars:
                    newChar.append(char_id)
                    vhalfidle._AddCharToActivity(act_info, sync_data, char_id)
                    have_chars.add(char_id)
                else:
                    oldChar.append(char_id)

        elif pool_id == "normalGachaPool":
            # 普通卡池：随机抽取
            # 获取可选角色id
            char_id_list = set()
            for key, value in troop_chars.items():
                char_id_list.add(troop_chars[key]["charId"])
            # 使用差集运算删除特殊干员，再转list
            filtered_char_list = [key for key in char_id_list if key not in spec_char]

            # 随机选择指定数量的角色id
            random_char = random.choices(filtered_char_list, k=count)

            # 添加角色
            for char_id in random_char:
                if char_id not in have_chars:
                    newChar.append(char_id)
                    vhalfidle._AddCharToActivity(act_info, sync_data, char_id)
                    have_chars.add(char_id)
                else:
                    oldChar.append(char_id)

            poolTimes["normalGachaPool"] += json_body["count"]

        elif pool_id == "newPlayerGachaPool":
            # 专项任命卡池：随机抽取
            pool_set = vhalfidle_pools.get(pool_id, set())
            char_data = list(pool_set) if pool_set else []

            for _ in range(count):
                if char_data:
                    selected_char = random.choice(char_data)
                    if selected_char not in have_chars:
                        newChar.append(selected_char)
                        vhalfidle._AddCharToActivity(act_info, sync_data, selected_char)
                        have_chars.add(selected_char)
                    else:
                        oldChar.append(selected_char)
                else:
                    return jsonify({"result": 1, "errMsg": "专项任命卡池为空"}), 404

            poolTimes["newPlayerGachaPool"] = poolTimes.get("newPlayerGachaPool", 0) + count

        ticketCount = len(oldChar)

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": {
                                    "char": act_chars
                                },
                                "recruit": {
                                    "poolTimes": poolTimes
                                },
                                "inventory": act_info["inventory"]
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "pushMessage": [],
            "newChar": newChar,
            "oldChar": oldChar,
            "ticketCount": ticketCount
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def recruitDirect():
        json_body = request.get_json()

        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]
        char_id = json_body["charId"]

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        act_chars = act_info["troop"]["char"]
        poolTimes = act_info["recruit"]["poolTimes"]

        if act_info["inventory"]["gacha_direct"] >= 100:
            act_info["inventory"]["gacha_direct"] -= 100
        else:
            return jsonify({"result": 1, "errMsg": "特约邀请函不足"}), 404

        newChar = []
        newChar.append(char_id)


        vhalfidle._AddCharToActivity(act_info, sync_data, char_id)

        poolTimes["directionGachaPool"] += 1

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": {
                                    "char": act_chars
                                },
                                "recruit": {
                                    "poolTimes": poolTimes
                                },
                                "inventory": act_info["inventory"]
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "charId": char_id
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def vhalfidlebattleStart():
        json_body = request.get_json()

        global stage_id
        stage_id = json_body["stageId"]

        result = {
            "apFailReturn": 0,
            "battleId": "abcdefgh-1234-5678-a1b2c3d4e5f6",
            "inApProtectPeriod": False,
            "isApProtect": 0,
            "notifyPowerScoreNotEnoughIfFailed": False,
            "playerDataDelta": {"modified": {}, "deleted": {}},
            "result": 0,
        }

        return result

    def vhalfidlebattleFinish():
        json_body = request.get_json()

        activity_id = json_body["activityId"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]

        global stage_id

        halfidle_data = json_body.get("halfidleData", {})
        bossState = halfidle_data["bossState"]
        battleProcess = halfidle_data["battleProcess"]
        resourceNumDict = halfidle_data["resourceNumDict"]
        global settle_info
        # 构造 settleInfo 数据
        settle_info = {
            "stageId": stage_id,
            "rate": resourceNumDict,
            "bossState": bossState,
            "progress": battleProcess
        }
        act_info["settleInfo"] = settle_info

        if act_info["stage"][stage_id]["rate"] is None:
            act_info["stage"][stage_id]["rate"] = {}
            for key, value in json_body["halfidleData"]["resourceNumDict"].items():
                if value > 0:
                    act_info["stage"][stage_id]["rate"].update({key: value})

        # 更新BOSS击杀状态
        bossState = max(json_body["halfidleData"]["bossState"], act_info["stage"][stage_id]["bossState"])
        act_info["stage"][stage_id]["bossState"] = bossState

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "stage": {
                                    stage_id: act_info["stage"][stage_id]
                                },
                                "settleInfo": settle_info
                            }
                        }
                    }
                },
                "deleted": {}
            },
            "pushMessage": [],
            "result": 0,
            "apFailReturn": 0,
            "itemReturn": [],
            "rewards": [],
            "unusualRewards": [],
            "overrideRewards": [],
            "additionalRewards": [],
            "diamondMaterialRewards": [],
            "furnitureRewards": [],
            "goldScale": 0.0,
            "expScale": 0.0,
            "firstRewards": [],
            "unlockStages": [],
            "pryResult": [],
            "alert": [],
            "suggestFriend": False,
            "extra": {},
            "charLvUp": [],
            "bossState": bossState,
            "progress": 2,
            "milestoneAdd": 0,
            "items": []
        }
        # 将 settle_info 也存入 session

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def vhalfidleUpgradeChar():
        json_body = request.get_json()
        cahr_id = json_body["charId"]
        dest_level = json_body["destLvl"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]

        cost = 0

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        act_chars = act_info["troop"]["char"]

        for key, value in act_chars.items():
            if value["charId"] == cahr_id:
                char_info = value
                cahr_str_id = key
                break

        level_list_map = {
            0: vhalfidle.E_0,
            1: vhalfidle.E_1,
            2: vhalfidle.E_2
        }

        level_list = level_list_map[char_info["evolvePhase"]]
        discount = char_info["evolvePhase"] < 2

        # 计算升级所需总成本
        now_level = char_info["level"]
        cost = sum(level_list[lv] for lv in range(now_level + 1, dest_level))

        # 应用折扣并扣除经验
        char_info["level"] = dest_level
        discount_rate = 0.9 if discount else 1.0
        act_info["inventory"]["level_exp"] -= int(cost * discount_rate)

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": {
                                    "char": {
                                        cahr_str_id: char_info
                                    }
                                },
                                "inventory": {
                                    "level_exp": act_info["inventory"]["level_exp"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def vhalfidleUpgradeSkill():
        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        act_chars = act_info["troop"]["char"]

        for key, value in act_chars.items():
            if value["charId"] == json_body["charId"]:
                value["skillLvl"] = json_body["destLvl"]
                act_chars[key] = value
                cahr_str_id = key
                break

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": {
                                    "char": {
                                        cahr_str_id: act_chars[key]
                                    }
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def vhalfidleEvolveChar():
        json_body = request.get_json()

        activity_id = json_body["activityId"]
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        act_info = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id]
        act_chars = act_info["troop"]["char"]

        for key, value in act_chars.items():
            if value["charId"] == json_body["charId"]:
                value["evolvePhase"] = json_body["destEvolvePhase"]
                value["level"] = 1
                act_chars[key] = value
                cahr_str_id = key
                break

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": {
                                    "char": {
                                        cahr_str_id: act_chars[key]
                                    }
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result

    def replaceRate():
        """数据替换"""
        # 获取请求数据
        json_body = request.get_json()

        activity_id = json_body.get("activityId", "")
        stage_id = json_body.get("stageId", "")
        replace = json_body.get("replace", 0)

        global settle_info

        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        # 获取活动数据
        activity_data = sync_data["user"]["activity"]["HALFIDLE_VERIFY1"].get(activity_id, {})

        # 如果replace为1或settleInfo为null，则更新settleInfo
        if replace == 1:
            # 更新sync_data
            stage = activity_data["stage"][stage_id]
            stage["rate"] = settle_info["rate"]
            stage["bossState"] = settle_info["bossState"]
            activity_data["settleInfo"] = None
        else:
            # 如果replace为0且settleInfo已存在，则不覆盖
            activity_data["settleInfo"] = None
            return {
                "playerDataDelta": {
                    "modified": {},
                    "deleted": {}
                }
            }

        data = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {}
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return data

    def setAssistChar():
        """助战逻辑"""
        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        # 获取请求参数
        activity_id = json_body.get("activityId", "")
        index = json_body.get("index", 0)  # 助战位索引(0-3)
        assist_friend = json_body.get("assistFriend", None)

        # 确保 activity_id 存在
        activity_map = sync_data["user"]["activity"].get("HALFIDLE_VERIFY1", {})
        activity_data = activity_map.get(activity_id, {})

        # 确保 troop 结构存在
        troop = activity_data.get("troop", {})
        troop.get("assist", [None, None, None, None])
        troop.get("char", {})

        # 跟踪被删除的角色实例ID
        deleted_char_inst_ids = []

        # 情况 1：清除助战位
        if assist_friend is None:
            old_assist_char = troop["assist"][index] if index < len(troop["assist"]) else None

            if old_assist_char is not None:
                old_char_id = old_assist_char.get("charId", "")
                # 删除 troop.char 中的 isAssist 角色
                for inst_id, char_info in list(troop["char"].items()):
                    if (
                            char_info.get("charId") == old_char_id
                            and char_info.get("isAssist", False)
                    ):
                        deleted_char_inst_ids.append(inst_id)
                        troop["char"].pop(inst_id, None)
                        break

            # 清除助战位
            if index < len(troop["assist"]):
                troop["assist"][index] = None

        # 情况 2：设置新的助战角色
        else:
            assist_char = assist_friend.get("assistChar", {})
            char_id = assist_char.get("charId", "")

            # 确保 assist 数组长度为4
            while len(troop["assist"]) < 4:
                troop["assist"].append(None)

            # 若该角色已在其他助战位上，清除旧槽（换位情况）
            for i in range(len(troop["assist"])):
                if i != index and troop["assist"][i] is not None:
                    if troop["assist"][i].get("charId") == char_id:
                        troop["assist"][i] = None
                        break

            # 清理当前槽原有的助战角色
            old_assist_char = troop["assist"][index]
            if old_assist_char is not None:
                old_char_id = old_assist_char.get("charId", "")
                for inst_id, char_info in list(troop["char"].items()):
                    if (
                            char_info.get("charId") == old_char_id
                            and char_info.get("isAssist", False)
                    ):
                        deleted_char_inst_ids.append(inst_id)
                        troop["char"].pop(inst_id, None)
                        break

            # 设置新的助战角色
            troop["assist"][index] = assist_char

            # 添加该角色（函数内部已自动去重）
            vhalfidle._AddCharToActivity(activity_data, sync_data, char_id)

            # 将添加的角色标记为 isAssist = True
            for char_info in troop["char"].values():
                if char_info.get("charId") == char_id:
                    char_info["isAssist"] = True
                    break

        # 保存更新
        sync_data["user"]["activity"]["HALFIDLE_VERIFY1"][activity_id] = activity_data

        deleted = {
            "activity": {
                "HALFIDLE_VERIFY1": {
                    activity_id: {
                        "troop": {
                            "char": deleted_char_inst_ids
                        }
                    }
                }
            }
        } if deleted_char_inst_ids else {}

        # 构造返回数据
        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "HALFIDLE_VERIFY1": {
                            activity_id: {
                                "troop": troop
                            }
                        }
                    },
                },
                "deleted": deleted
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)

        return result
    
class multiplayer:

    def refreshInfo():

        return {}
    
    def refreshInviteList():

        return {}
    
    def getInfo():
        result = {}
        return result
    
    def changeTitle():
        request_json = request.get_json()
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        activity_id = request_json["activityId"]

        user_data["activity"]["MULTIPLAY_V3"][activity_id]["collection"]["title"]["select"] = request_json["select"]

        result = {}
        return result
    
    def setBuff():
        request_json = request.get_json()
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        activity_id = request_json["activityId"]

        mode_id = request_json["modeType"]

        user_data["activity"]["MULTIPLAY_V3"][activity_id]["troop"]["squads"][mode_id]["buffId"] = request_json["buffId"]

        result = {}
        return result
    
    def setSquads():
        request_json = request.get_json()
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        activity_id = request_json["activityId"]

        mode_id = request_json["modeType"]

        user_data["activity"]["MULTIPLAY_V3"][activity_id]["troop"]["squads"][mode_id]["prefer"] = request_json["prefer"]
        user_data["activity"]["MULTIPLAY_V3"][activity_id]["troop"]["squads"][mode_id]["backup"] = request_json["backup"]

        result = {}
        return result
    
    def guideBattleStart():
        result = {
            "result": 0,
        }
        
        return result

    def guideBattleFinish():

        result = {
        "data": {
            "result": 0,
            "mateQuit": False,
            "normal": {
                "failTip": False,
                "targets": [
                    {
                        "complete": True,
                        "progressShow": ["30", "30"],
                        "progressValue": [30, 30],
                    },
                    {
                        "complete": True,
                        "progressShow": ["5", "3"],
                        "progressValue": [5, 3],
                    },
                    {
                        "complete": True,
                        "progressShow": ["5", "5"],
                        "progressValue": [5, 5],
                    },
                ],
                "newStar": False,
            },
            "raft": {"score": 10000, "newScore": False},
            "defence": {
                "targets": [
                    {"complete": True, "progressValue": [4, 1]},
                    {"complete": True, "progressValue": [4, 2]},
                    {"complete": True, "progressValue": [4, 4]},
                ],
                "damage": 10000,
                "damagePct": 100,
                "bossKill": True,
                "newStar": False,
                "newDamage": False,
            },
            "star": 3,
            "reward": {
                "item": [],
                "milestoneAdd": 0,
                "gainDailyReward": False,
            },
            "newPhoto": False,
            "newPhotoId": "",
            "sameChannel": True,
            "isFriend": False,
            "reverse": 0,
            "ts": time(),
        },
    }
        return result
    
    def switchInviteAccept():
        return {}, 202

    def sendInvite():
        return {}, 202

    def processInvite():
        return {}, 202

class autochessSeason:
    def syncInfo():
        
        result = {
            "changeId": [""],
            "battleInfo": {}
        }

        return result
    
    def getFriendAndRequestSendList():

        result = {
            "friendsList": [
                {
                    "uid": "25249069",
                    "friendAlias": ""
                }
            ],
            "requestSendIdList": []
        }

        return result

    def setChessPoolDeploy():

        json_body = request.get_json()

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        activity_id = json_body["actId"]
        auto_chess_data = user_data["user"]["activity"]["AUTOCHESS_SEASON"][activity_id]
        chess_data = auto_chess_data["chessSquad"]
        for key, value in json_body["chessPool"].items():
            for key2, value2 in value.items():
                chess_data[key][key2] = value2


        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "AUTOCHESS_SEASON": {
                            activity_id: {
                                "chessSquad": chess_data
                            }
                        }
                    }
                },
                "deleted": {}
            },
        }

        return result

    def autoChessStartGuideBattle():
        return {}


    def act2autochess():
        server_config = get_memory("config")
        if server_config["server"]["adaptive"]:
            server = request.host_url[:-1]
        else:
            server = (
                "http://"
                + server_config["server"]["host"]
                + ":"
                + str(server_config["server"]["port"])
            )
        
        result = f'''
        <!doctype html>
        <html lang="zh-cn">

        <head>
            <meta charset="utf-8">
            <meta name="referrer" content="no-referrer">
            <meta http-equiv="pragma" content="no-cache">
            <meta http-equiv="cache-control" content="no-cache">
            <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
            <meta name="renderer" content="webkit">
            <meta name="force-rendering" content="webkit">
            <meta name="viewport"
                content="user-scalable=no,initial-scale=1,maximum-scale=1,minimum-scale=1,width=device-width,height=device-height,viewport-fit=cover">
            <meta name="copyright" content="Hypergryph">
            <meta name="format-detection" content="telephone=no,email=no,address=no">
            <meta name="apple-mobile-web-app-capable" content="yes">
            <meta name="robots" content="noindex">
            <title>卫戍协议 | 明日方舟 - Arknights</title>
            <link href="{server}/arknights/webview/favicon.ico" rel="icon">
            <link as="image" href="{server}/arknights/webview/assets/img/bg-circle.cd5774.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/bg.55399b.jpg" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/bg.cdd07d.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/bond-bg.53ee8c.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/bond-list-empty.671709.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/dash.99f37d.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/elite_0.949306.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/elite_2.71c645.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/header.960345.png" rel="preload">
            <link as="image" href="{server}/arknights/webview/assets/img/title-bg.26ebe7.png" rel="preload">
            <link href="{server}/arknights/webview/commons.d9025b.css" rel="stylesheet">
            <link href="{server}/arknights/webview/act1autochess.41668e.css" rel="stylesheet">
        </head>

        <body>
            <div id="root"></div>


            <script crossorigin="anonymous" src="{server}/arknights/webview/analytics.1585a3.js"></script>
            <script crossorigin="anonymous" src="{server}/arknights/webview/act1autochess_i18n.02dbe5.js"></script>
            <script crossorigin="anonymous" src="{server}/arknights/webview/react.0bb887.js"></script>
            <script crossorigin="anonymous" src="{server}/arknights/webview/commons.1b8875.js"></script>
            <script crossorigin="anonymous" src="{server}/arknights/webview/act1autochess.c65de8.js"></script>
        </body>

        </html>
        '''

        return result

    def act1playerSummary():

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        uid = user_data["user"]["status"]["uid"]
        name = user_data["user"]["status"]["nickName"]

        result = {
            "status": 0,
            "code": 0,
            "msg": "",
            "data": {
                "uid": uid,
                "level": 120,
                "nickname": name,
                "avatar": "char_4172_xingzh@epoque#51",
                "nameCard": "nc_6d5_1",
                "total": {
                    "multi": {
                        "battle": 0,
                        "win": 0,
                        "hardWin": 0
                    },
                    "single": {
                        "battle": 1,
                        "win": 0,
                        "hardWin": 0
                    },
                    "trophy": 0,
                    "beLike": 0
                },
                "max": {
                    "coinCost": 0,
                    "sync": 0,
                    "defeat": 0,
                    "bond": None,
                    "squad": [],
                    "bonds": []
                },
                "topBonds": [],
                "topBands": [
                    {
                        "id": "band_chen",
                        "value": 1,
                        "iconId": "icon_chen",
                        "name": "陈"
                    }
                ],
                "bandPassInfo": [],
                "titleCntInfo": {}
            }
        }
        
        return result

    def act2playerSummary():

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        uid = user_data["user"]["status"]["uid"]
        name = user_data["user"]["status"]["nickName"]

        result = {
            "status": 0,
            "code": 0,
            "msg": "",
            "data": {
                "uid": uid,
                "level": 120,
                "nickname": name,
                "avatar": "char_4172_xingzh@epoque#51",
                "nameCard": "nc_6d5_1",
                "total": {
                    "multi": {
                        "battle": 6,
                        "win": 3,
                        "hardWin": 3
                    },
                    "single": {
                        "battle": 4,
                        "win": 2,
                        "hardWin": 0
                    },
                    "trophy": 22,
                    "beLike": 5
                },
                "max": {
                    "coinCost": 165,
                    "sync": 6,
                    "defeat": 275,
                    "bond": {
                        "id": "sargonShip",
                        "num": 280,
                        "iconId": "icon_sargonShip"
                    },
                    "squad": [
                        {
                            "chessId": "chess_char_6_06_a",
                            "chessLevel": 6,
                            "charId": "char_4058_pepe",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm059_1",
                                "sktok_acarm060_1"
                            ]
                        },
                        {
                            "chessId": "chess_char_4_18_b",
                            "chessLevel": 4,
                            "charId": "char_311_mudrok",
                            "charLevel": 60,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm047_1",
                                "sktok_acarm050_1"
                            ]
                        },
                        {
                            "chessId": "chess_char_5_02_a",
                            "chessLevel": 5,
                            "charId": "char_4056_titi",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm051_1",
                                "sktok_acarm050_2"
                            ]
                        },
                        {
                            "chessId": "chess_char_4_04_a",
                            "chessLevel": 4,
                            "charId": "char_4087_ines",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm125_2"
                            ]
                        },
                        {
                            "chessId": "chess_char_5_diy1_a",
                            "chessLevel": 5,
                            "charId": "char_2012_typhon",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm063_1",
                                "sktok_acarm048_2"
                            ]
                        },
                        {
                            "chessId": "chess_char_2_06_b",
                            "chessLevel": 2,
                            "charId": "char_4139_papyrs",
                            "charLevel": 55,
                            "evolvePhase": 2,
                            "equips": []
                        },
                        {
                            "chessId": "chess_char_5_07_a",
                            "chessLevel": 5,
                            "charId": "char_350_surtr",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm055_1"
                            ]
                        },
                        {
                            "chessId": "chess_char_6_09_a",
                            "chessLevel": 6,
                            "charId": "char_245_cello",
                            "charLevel": 1,
                            "evolvePhase": 2,
                            "equips": [
                                "sktok_acarm062_1"
                            ]
                        }
                    ],
                    "bonds": [
                        {
                            "id": "suntShip",
                            "value": 0,
                            "iconId": "icon_suntShip"
                        },
                        {
                            "id": "soloShip",
                            "value": 0,
                            "iconId": "icon_soloShip"
                        },
                        {
                            "id": "sargonShip",
                            "value": 280,
                            "iconId": "icon_sargonShip"
                        },
                        {
                            "id": "raidShip",
                            "value": 26,
                            "iconId": "icon_raidShip"
                        }
                    ]
                },
                "topBonds": [
                    {
                        "id": "soloShip",
                        "iconId": "icon_soloShip",
                        "name": "独行",
                        "chessList": [
                            {
                                "chessId": "chess_char_1_08_a",
                                "chessLevel": 1,
                                "charId": "char_102_texas",
                                "sortId": 8
                            },
                            {
                                "chessId": "chess_char_2_17_a",
                                "chessLevel": 2,
                                "charId": "char_4207_branch",
                                "sortId": 17
                            },
                            {
                                "chessId": "chess_char_3_17_a",
                                "chessLevel": 3,
                                "charId": "char_126_shotst",
                                "sortId": 17
                            },
                            {
                                "chessId": "chess_char_4_09_a",
                                "chessLevel": 4,
                                "charId": "char_437_mizuki",
                                "sortId": 9
                            },
                            {
                                "chessId": "chess_char_4_18_a",
                                "chessLevel": 4,
                                "charId": "char_311_mudrok",
                                "sortId": 18
                            },
                            {
                                "chessId": "chess_char_5_11_a",
                                "chessLevel": 5,
                                "charId": "char_202_demkni",
                                "sortId": 11
                            }
                        ]
                    },
                    {
                        "id": "suntShip",
                        "iconId": "icon_suntShip",
                        "name": "绝技",
                        "chessList": []
                    },
                    {
                        "id": "yanShip",
                        "iconId": "icon_yanShip",
                        "name": "炎",
                        "chessList": [
                            {
                                "chessId": "chess_char_1_03_a",
                                "chessLevel": 1,
                                "charId": "char_306_leizi",
                                "sortId": 3
                            },
                            {
                                "chessId": "chess_char_2_04_a",
                                "chessLevel": 2,
                                "charId": "char_4122_grabds",
                                "sortId": 4
                            },
                            {
                                "chessId": "chess_char_3_03_a",
                                "chessLevel": 3,
                                "charId": "char_308_swire",
                                "sortId": 3
                            },
                            {
                                "chessId": "chess_char_3_04_a",
                                "chessLevel": 3,
                                "charId": "char_1033_swire2",
                                "sortId": 4
                            },
                            {
                                "chessId": "chess_char_4_15_a",
                                "chessLevel": 4,
                                "charId": "char_4196_reckpr",
                                "sortId": 15
                            },
                            {
                                "chessId": "chess_char_4_17_a",
                                "chessLevel": 4,
                                "charId": "char_136_hsguma",
                                "sortId": 17
                            },
                            {
                                "chessId": "chess_char_5_03_a",
                                "chessLevel": 5,
                                "charId": "char_1040_blaze2",
                                "sortId": 3
                            },
                            {
                                "chessId": "chess_char_5_12_a",
                                "chessLevel": 5,
                                "charId": "char_2015_dusk",
                                "sortId": 12
                            },
                            {
                                "chessId": "chess_char_5_23_a",
                                "chessLevel": 5,
                                "charId": "char_4196_reckpr",
                                "sortId": 23
                            },
                            {
                                "chessId": "chess_char_6_03_a",
                                "chessLevel": 6,
                                "charId": "char_2026_yu",
                                "sortId": 3
                            },
                            {
                                "chessId": "chess_char_6_15_a",
                                "chessLevel": 6,
                                "charId": "char_4082_qiubai",
                                "sortId": 15
                            }
                        ]
                    }
                ],
                "topBands": [
                    {
                        "id": "band_quintus",
                        "value": 5,
                        "iconId": "icon_quintus",
                        "name": "昆图斯"
                    },
                    {
                        "id": "band_amiya",
                        "value": 4,
                        "iconId": "icon_amiya",
                        "name": "阿米娅"
                    },
                    {
                        "id": "band_kirara",
                        "value": 1,
                        "iconId": "icon_kirara",
                        "name": "绮良"
                    }
                ],
                "bandPassInfo": [
                    {
                        "id": "band_amiya",
                        "value": 3,
                        "sortId": 2,
                        "iconId": "icon_amiya",
                        "name": "阿米娅"
                    }
                ],
                "titleCntInfo": {
                    "comment_1": 2,
                    "comment_2": 1,
                    "comment_6": 2
                }
            }
        }

        return result

class vecbreak:

    def getSeasonRecord():
        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        server_data = read_json(SERVER_DATA_PATH)

        stage_info = {}

        for keys in sync_data["user"]["dungeon"]["stages"].keys():
            if keys.startswith("act1break_"):
                one_stage_info = {
                    keys: {
                        "stageId": keys,
                        "state": "COMPLETE"
                    }
                }
                stage_info.update(one_stage_info)

        buff = server_data["vecbreakV2"]["buff"]
        squad = server_data["vecbreakV2"]["squad"]
        assistChar = server_data["vecbreakV2"]["assistChar"]

        result = {
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        },
        "pushMessage": [],
        "seasons": {
            "act1break": {
            "bestRecord": {
                "stageId": "act1break_12",
                "buff": buff,
                "showTs": time(),
                "squad": squad,
                "assistChar": assistChar
            },
            "stageInfo": stage_info
            }
        }
        }
        return result

    def vecV2changeBuffList():
        json_body = request.get_json()
        # {"activityId": "act1break", "buffList": ["act1break_rune01", "act1break_rune04"]}

        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_id = json_body["activityId"]
        buff_list = json_body["buffList"]

        activity_data = sync_data["user"]["activity"]["VEC_BREAK_V2"][activity_id]
        activity_data["activatedBuff"] = buff_list

        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "VEC_BREAK_V2": {
                            activity_id: activity_data
                        }
                    }
                },
                "deleted": {},
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def defendBattleStart():
        json_body = request.get_json()
        # {
        #     "activityId": "act1break",
        #     "stageId": "act1break_sp02",
        #     "squad": {
        #         "squadId": "",
        #         "name": "",
        #         "slots": [
        #             {
        #                 "charInstId": 4133,
        #                 "skillIndex": 2,
        #                 "currentEquip": "uniequip_002_logos"
        #             }
        #         ]
        #     }
        # }
        global battle_data
        battle_data = json_body
        result = questBattleStart()

        return result

    def defendBattleFinish():
        json_body = request.get_json()
        global battle_data
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

        # battle_data = json_body["data"]
        # decrypt_data = decrypt_battle_data(battle_data)

        # 基础信息
        activity_data_id = battle_data["activityId"]
        slots_data = battle_data["squad"]["slots"]
        stage_id = battle_data["stageId"]
        activity_data = sync_data["user"]["activity"]["VEC_BREAK_V2"][activity_data_id]

        # 通关信息更新
        defend_stages_data = activity_data["defendStages"].get(stage_id)
        if defend_stages_data is None:
            defend_squad = [
                {
                    "charInstId": slot["charInstId"],
                    "currentTmpl": None
                }
                for slot in slots_data
            ]
            defend_stages_data = {
                "stageId": stage_id,
                "defendSquad": defend_squad,
                "recvTimeLimited": True,
                "recvNormal": True
            }
            activity_data["defendStages"][stage_id] = defend_stages_data
            activated_buff = activity_data["activatedBuff"]
            activated_buff.append(stage_id)
        else:
            defend_stages_data["defendSquad"] = defend_squad

        # 等级点数
        ponit = activity_data["milestone"]["point"]

        #构建响应内容
        result = {
            "playerDataDelta": {
                "modified": {
                    "activity": {
                        "VEC_BREAK_V2": {
                            activity_data_id: {
                                "milestone": {
                                    "point": ponit
                                },
                                "defendStages": {
                                    stage_id: defend_stages_data
                                }
                            }
                        }
                    }
                }
            },
            "pushMessage": [],
            "result": 0,
            "apFailReturn": 0,
            "goldScale": 0.0,
            "expScale": 0.0,
            "suggestFriend": False,
            "msBefore": ponit,
            "msAfter": ponit,
            "finTs": time()
        }

        battle_data = None
        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def setDefend():
        # 换驻防编队、清空驻防编队
        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        activity_data = sync_data["user"]["activity"]["VEC_BREAK_V2"][json_body["activityId"]]
        stage_id = json_body["stageId"]
        squad_slots = json_body["squadSlots"]

        activity_data["defendStages"][stage_id]["defendSquad"] = squad_slots

        result = {
            "PlayerDataDelta": {
                "modified": {
                    "activity": {
                        "VEC_BREAK_V2": {
                            json_body["activityId"]: {
                                "defendStages": {
                                    stage_id: {
                                        "defendSquad": squad_slots
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        run_after_response(write_json, sync_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def vecV2BattleStart():
        json_body = request.get_json()
        global battle_data
        battle_data = json_body
        result = questBattleStart()

        return result

    def vecV2battleFinish1():
        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        server_data = read_json(SERVER_DATA_PATH)
        char_equip_dict = {}
        global battle_data

        decrypt_data = decrypt_battle_data(json_body["data"])
        if decrypt_data["percent"] == 100:
            write_in = True
        else:
            write_in = False
        activity_data_id = battle_data["activityId"]
        activity_data = sync_data["user"]["activity"]["VEC_BREAK_V2"][activity_data_id]
        ponit = activity_data["milestone"]["point"]

        if battle_data["stageId"].startswith(("act1break_0", "act1break_1")):
            if write_in:
                server_data["vecbreakV2"]["buff"] = sync_data["user"]["activity"]["VEC_BREAK_V2"]["act1break"]["activatedBuff"]
                # if battle_data["assistFriend"] is not None:
                #   server_data["vecbreakV2"]["assistChar"] = battle_data["assistFriend"]
                
                char_equip_dict = battle_data["squad"]["slots"]
                for char_id in sync_data["user"]["troop"]["chars"].keys():
                    matched_slot = next(
                        (slot for slot in char_equip_dict if str(slot["charInstId"]) == char_id),
                        None
                    )
                    
                    if matched_slot is not None:
                        char_data = sync_data["user"]["troop"]["chars"][char_id]
                        if matched_slot["currentEquip"] is not None:
                            equip = {
                                "id": matched_slot["currentEquip"],
                                "level": char_data["equip"][matched_slot["currentEquip"]]["level"]
                            }
                        else:
                            equip = {
                                "id": char_data["currentEquip"],
                                "level": 1
                            }
                        
                        template = {
                            "charInstId": char_data["charId"],
                            "currentTmpl": None,
                            "potentialRank": char_data["potentialRank"],
                            "level": char_data["level"],
                            "mainSkillLvl": char_data["mainSkillLvl"],
                            "evolvePhase": char_data["evolvePhase"],
                            "skin": char_data["skin"],
                            "skill": {
                                "skillIndex": matched_slot["skillIndex"],
                                "specializeLevel": char_data["skills"][str(matched_slot["skillIndex"])]["specializeLevel"]
                            },
                            "equip": equip
                        }
                        
                        server_data["vecbreakV2"]["squad"].update(template)

        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "pushMessage": [],
            "result": 0,
            "apFailReturn": 0,
            "goldScale": 0.0,
            "expScale": 0.0,
            "suggestFriend": False,
            "msBefore": ponit,
            "msAfter": ponit,
            "finTs": time()
        }

        battle_data = None
        return result

    def vecV2battleFinish():

        json_body = request.get_json()
        sync_data = read_json(SYNC_DATA_TEMPLATE_PATH) 
        server_data = read_json(SERVER_DATA_PATH)
        global battle_data

        # 解密战斗数据
        decrypt_data = decrypt_battle_data(json_body["data"])
        # 判断是否写入
        write_in = decrypt_data["percent"] == 100
        # 获取关卡编号
        stage_num = int(battle_data["stageId"].split("_")[-1])
        # 判断是否达到最大关卡
        is_max_level = stage_num >= server_data["vecbreakV2"].get("MaxLevel", 0)
        # 获取活动数据
        activity_data = sync_data["user"]["activity"]["VEC_BREAK_V2"][battle_data["activityId"]]
        # 获取当前积分
        current_point = activity_data["milestone"]["point"]

        # 如果关卡编号不是act1break_0或act1break_1，或未达到100完成度，或不是记录中最高的关卡，则不写入记录
        run = write_in and not is_max_level and battle_data["stageId"].startswith(("act1break_0", "act1break_1"))

        def run_after(stage_num):
            sync_data = read_json(SYNC_DATA_TEMPLATE_PATH) 
            server_data = read_json(SERVER_DATA_PATH)
            global battle_data
            # 生成新的队伍记录
            new_squad = []
            for slot in battle_data["squad"]["slots"]:
                # 获取对应的角色ID
                char_inst_id = str(slot["charInstId"])
                
                if char_inst_id not in sync_data["user"]["troop"]["chars"]:
                    continue

                # 获取角色基础数据
                char_data = sync_data["user"]["troop"]["chars"][char_inst_id]
                
                # 处理装备数据
                equip_id = slot["currentEquip"] or char_data["currentEquip"]
                equip_level = char_data["equip"].get(equip_id, 1) if equip_id else 1
                
                # 构建角色完整数据
                char_template = {
                    "charId": char_data["charId"],
                    "currentTmpl": None,
                    "potentialRank": char_data["potentialRank"],
                    "level": char_data["level"],
                    "mainSkillLvl": char_data["mainSkillLvl"],
                    "evolvePhase": char_data["evolvePhase"],
                    "skin": char_data["skin"],
                    "skill": {
                        "skillIndex": slot["skillIndex"],
                        "specializeLevel": char_data["skills"][slot["skillIndex"]]["specializeLevel"]
                    },
                    "equip": {
                        "id": equip_id,
                        "level": equip_level
                    }
                }
                new_squad.append(char_template)

            assistChar = None #TODO:助战问题暂不处理

            # 更新服务器数据
            server_data["vecbreakV2"] = {
                "maxLevel": stage_num,
                "buff": sync_data["user"]["activity"]["VEC_BREAK_V2"]["act1break"]["activatedBuff"],
                "squad": new_squad,
                "assistChar": assistChar
            }

            battle_data = None
            run_after_response(write_json ,server_data, SERVER_DATA_PATH)

        if run:
            run_after_response(run_after, stage_num)

        return {
            "playerDataDelta": {"modified": {}, "deleted": {}},
            "result": 0,
            "msBefore": current_point,
            "msAfter": current_point,
            "finTs": time()
        }

class football:
    def footballBattleStart():
        json_body = request.get_json()

        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
        }

        return result

    def footballBattleFinish():
        json_body = request.get_json()

        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "rewards": []
        }

        return result


class ActivityMission:
    def confirmActivityMission():
        json_body = request.get_json()
        print(json_body)
        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "rewards": []
        }

        return result

    def confirmActivityMissionList():
        json_body = request.get_json()
        print(json_body)
        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "rewards": []
        }

        return result

    def rewardAllMilestone():
        json_body = request.get_json()
        print (json_body)
        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "rewards": []
        }

        return result

    def rewardMilestone():
        json_body = request.get_json()
        print (json_body)
        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            },
            "rewards": []
        }

        return result

class arcade:

    def arcadeBattleStart():
        return {}, 202

    def arcadeBattleFinish():
        return {}, 202

def getChainLogInReward():
    return {}, 202

def getOpenServerCheckInReward():
    return {}, 202

def getChainLogInFinalRewards():
    return {}, 202

def confirmActivityMission():
    json_body = request.get_json()

    result = {
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        },
        "rewards": []
    }

    return result

def confirmActivityMissionList():
    json_body = request.get_json()

    result = {
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        },
        "rewards": []
    }

    return result
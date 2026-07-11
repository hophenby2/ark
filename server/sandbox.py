from flask import request
from utils import read_json, write_json, get_memory, run_after_response
from virtualtime import time
from constants import SYNC_DATA_TEMPLATE_PATH

def changeTopic():
    json_body = request.get_json()

    return {
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        },
        "result": 0
    }

def pinTopic():
    json_body = request.get_json()
    print(json_body)
    return "", 202

class sandboxV2:
    def V2createGame():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def V2battleStart():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def V2battleFinish():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def V2eatFood():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def cookDrink():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def cookFood():
        json_body = request.get_json()
        print(json_body)
        return "", 202


    def setSquad():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def V2settleGame():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def homeBuildSave():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def monthBattleStart():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def monthBattleFinish():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def exploreMode():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def V2eventChoice():
        json_body = request.get_json
        result = {
                "playerDataDelta": {
                    "modified": {
                        
                    },
                    "deleted": {}
                }
            }

        return result

    def alchemy():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def baseUpgrade():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def build():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def cook():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def discardAp():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def enterChallenge():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def exitChallenge():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def extract():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def getChallengeReward():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def guideLoad():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def load():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def V2nextDay():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def removeSupply():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def riftClose():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def riftCreate():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def riftSetDifficulty():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def riftSetTeam():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def riftSettle():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def setSupply():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def settleChallenge():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def settleDay():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def V2shopBuy():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def startMission():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def V2switchMode():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def V2unlockTech():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingBattleFinish():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingBattleStart():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingLearnTalent():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingRegister():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingRelease():
        json_body = request.get_json()
        print(json_body)
        return "", 202

    def racingSaveMark():
        json_body = request.get_json()
        print(json_body)
        return "", 202


class sandboxV3:

    tech_buff = {
        "sandbox_2_tech_explore_1": "sandbox_v3_talent_3_lv1",
        "sandbox_2_tech_explore_2": "sandbox_v3_talent_4_lv1",
        "sandbox_2_tech_explore_3": "sandbox_v3_talent_1",
        "sandbox_2_tech_explore_4": "sandbox_v3_weather_heat[ex]",
        "sandbox_2_tech_explore_5": "sandbox_v3_talent_6_lv1",
        "sandbox_2_tech_explore_6": "sandbox_v3_talent_5_lv1",
        "sandbox_2_tech_explore_7": "sandbox_v3_talent_3_lv2",
        "sandbox_2_tech_explore_8": "sandbox_v3_talent_2_lv1",
        "sandbox_2_tech_explore_9": "sandbox_v3_talent_7_lv1",
        "sandbox_2_tech_explore_10": "sandbox_v3_talent_5_lv2",
        "sandbox_2_tech_explore_11": "sandbox_v3_talent_4_lv2",
        "sandbox_2_tech_explore_12": "sandbox_v3_weather_storm[ex]",
        "sandbox_2_tech_explore_13": "sandbox_v3_talent_2_lv2",
        "sandbox_2_tech_explore_14": "sandbox_v3_talent_4_lv2",
        "sandbox_2_tech_explore_15": "sandbox_v3_weather_lightning[ex]",
        "sandbox_2_tech_explore_16": "sandbox_v3_talent_7_lv2",
        "sandbox_2_tech_explore_17": "sandbox_v3_weather_rain[ex]",
        "sandbox_2_tech_explore_18": "sandbox_v3_talent_8",
    }

    def V3switchMode():
        json_body = request.get_json()

        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            }
        }

        return result

    def switchMode():
        json_body = request.get_json()

        result = {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            }
        }

        return result

    def productionRefresh():
        json_body = request.get_json()
        topic_id = json_body["topicId"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox = user_data["user"]["sandboxPerm"]
        sandbox_data = sandbox["template"]["SANDBOX_V3"][topic_id]

        production_data = sandbox_data["base"]["production"]
        production_data["refreshTs"] = time()

        return {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "template":{
                            "SANDBOX_V3": {
                                topic_id: {
                                    "base": {
                                        "production": production_data
                                    }
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

    def productionHarvest():
        json_body = request.get_json()
        topic_id = json_body["topicId"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox = user_data["user"]["sandboxPerm"]
        sandbox_data = sandbox["template"]["SANDBOX_V3"][topic_id]

        now_ts = time()
        # 产出最大积累时间（3天）
        max_save_ts = 259200
        rate_data = sandboxV3._harvestFresh(sandbox_data["base"])
        
        production_data:dict = sandbox_data["base"]["production"]
        # 上次收取时间
        harvest_ts:int = production_data["harvestTs"]
        # 每小时产出
        rate:dict = production_data["rate"]

        # 计算产出
        interval_ts = now_ts - harvest_ts
        if interval_ts > max_save_ts:
            interval_ts = max_save_ts

        interval_hours = int(interval_ts / 3600)


        return {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "template":{
                            "SANDBOX_V3": {
                                topic_id: {}
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

    def homeEnter():
        return {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            }
        }

    def homeShopBuy():
        json_body = request.get_json()
        topic_id:str = json_body["topicId"]
        good_id:str = json_body["goodId"]
        count:int = json_body["count"]
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox = user_data["user"]["sandboxPerm"]
        good_unit_price:int = get_memory("sandbox_perm_table")["detail"]["SANDBOX_V3"][topic_id][good_id]["value"]
        good_price = good_unit_price * count
        sandbox_data = sandbox["template"]["SANDBOX_V3"][topic_id]["baseShopGoodData"]
        
        return {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            }
        }

    def homeSave():
        json_body = request.get_json()
        print(json_body)
        # {'topicId': 'sandbox_2', 'operation': [{'type': 1, 'pos': [3, 5], 'dir': 3, 'itemId': 'sandbox_2_building_base_agriculture_3'}], 'catchedAnimals': [], 'derivedItem': {}, 'placeScore': {}, 'npcOutput': []}
        # type 1为放置，type 2为升级，type 3为收起，记得按list的顺序操作！
        topic_id:str = json_body["topicId"]
        operation:list = json_body["operation"]
        user_data:dict = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox:dict = user_data["user"]["sandboxPerm"]
        building_data:dict = sandbox["template"]["SANDBOX_V3"][topic_id]["base"]["building"]

        run_after_response(sandboxV3._harvestFresh(building_data, topic_id, True))
        run_after_response(sandboxV3._freshScore(building_data, topic_id, True))
        
        return {
            "playerDataDelta": {
                "modified": {},
                "deleted": {}
            }
        }
    
    def homeShopSell():
        json_body = request.get_json()
        print(json_body)

        return "", 202
    
    def homeUpgrade():
        json_body = request.get_json()
        print(json_body)

        return "", 202

    def V3createGame():
        json_body = request.get_json()
        topic_id = json_body["topicId"]
        node_id = json_body["nodeId"]
        difficulty_id = json_body["difficultyId"]

        # 读数据
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox_data = user_data["user"]["sandboxPerm"]
        current_base_Lv = sandbox_data["template"]["SANDBOX_V3"][topic_id]["base"]["level"]
        sandbox_data["summary"]["SANDBOX_V3"][topic_id]["inCurrent"] = 1
        sandbox_data["summary"]["SANDBOX_V3"][topic_id]["baseLv"] = current_base_Lv
        tech_list:list = sandbox_data["template"]["SANDBOX_V3"][topic_id]["tech"]["unlock"]

        # 外勤增益buff添加
        rune_data:list = []
        for key in tech_list:
            if key.startswith("sandbox_2_tech_explore_"):
                rune_key = sandboxV3.tech_buff[key]
                rune_data.append(rune_key)
        rune_data.sort()

        # 数据构建
        current_default_data = {
            "nodeId": node_id,
            "state": 0, # Torappu.PlayerSandboxV3GameState
            "game": {
                "idx": 21,
                "openTs": time(),
                "difficultyId": "",
                "npcInstId": -1,
                "day": 1,
                "weather": "weather_rain",
                "windDir": "UP",
                "power": 0,
                "pros": 0,
                "aesth": 0
            },
            "map": {
                "subStage": [],
                "unlockIndex": [],
                "initIndex": []
            },
            "band": {
                "id": "",
                "level": 0
            },
            "troop": {},
            "shop": {},
            "dailyReport": None,
            "bag": {},
            "eventInfo": None,
            "effect": {
                "rune": rune_data,
                "shopRefreshDiscount": 10,
                "shopRefreshFree": 0,
                "shopSlotAdd": 0,
                "shopStockAdd": {
                    "sandbox_2_good_wood_10": 10,
                    "sandbox_2_good_stone_10": 10,
                    "sandbox_2_good_iron_10": 10
                },
                "shopDiscountRate": 0,
                "gapGainItem": {},
                "recipeRefreshDiscount": 0,
                "productAdd": {},
                "trapDrop": {},
                "buildReturn": {},
                "taskRefreshAdd": 1
            },
            "save": None
        }

        sandbox_data["template"]["SANDBOX_V3"][topic_id]["current"] = current_default_data

        result = {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "summary": {
                            "SANDBOX_V3": {
                                topic_id: sandbox_data["summary"]["SANDBOX_V3"][topic_id]
                            }
                        },
                        "template":{
                            "SANDBOX_V3": {
                                topic_id: {
                                    "current": sandbox_data["template"]["SANDBOX_V3"][topic_id]["current"],
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result

    def V3giveUpGame():
        json_body = request.get_json()
        topic_id = json_body["topicId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox_data = user_data["user"]["sandboxPerm"]

        sandbox_data["summary"]["SANDBOX_V3"][topic_id]["inCurrent"] = 0
        sandbox_data["template"]["SANDBOX_V3"][topic_id]["current"] = None

        result = {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "template":{
                            "SANDBOX_V3": {
                                topic_id: {
                                    "summary": sandbox_data["summary"]["SANDBOX_V3"][topic_id],
                                    "current": sandbox_data["template"]["SANDBOX_V3"][topic_id]["current"]
                                }
                            }
                        }
                    }
                },
                "deleted": {}
            }
        }

        return result

    def V3battleStart():
        json_body = request.get_json()
        print(json_body)

        return "", 202

    def V3battleFinish():
        json_body = request.get_json()
        print(json_body)

        return "", 202

    def changeDefend():
        json_body = request.get_json()
        topic_id:str = json_body["topicId"]
        zone_id:str = json_body["zoneId"]
        operate = bool(json_body["operate"])
        chars:list = json_body["chars"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox_data = user_data["user"]["sandboxPerm"]

        zone_data:dict = sandbox_data["template"]["SANDBOX_V3"][topic_id]["map"]["zone"][zone_id]
        if operate:
            zone_data["sub"] = chars
        else:
            if len(chars) > 0:
                zone_data["main"] = chars[0]
            else:
                zone_data["main"] = -1

        result = {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "template":{
                            "SANDBOX_V3": {
                                topic_id: {
                                    "map": sandbox_data["template"]["SANDBOX_V3"][topic_id]["map"]
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

    def chooseBand():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def dailyRecruit():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3eatFood():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3eventChoice():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def getDailyRecruitList():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3nextDay():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def initRecruit():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3settleGame():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3shopBuy():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def shopBuyRecruit():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def shopRefresh():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def shopSell():
        json_body = request.get_json()
        print(json_body)

        return "", 202
        
    def V3unlockTech():
        json_body:dict[str, any] = request.get_json()
        topic_id:str = json_body["topicId"]
        tech_id:str = json_body["techId"]

        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        sandbox_data = user_data["user"]["sandboxPerm"]
        sandbox_excel = get_memory("sandbox_perm_table")

        tech_data:dict = sandbox_data["template"]["SANDBOX_V3"][topic_id]["tech"]
        # 检查基地是否达到解锁所需等级
        limit_base_lv:int = sandbox_excel["detail"]["SANDBOX_V3"][topic_id]["developmentData"][tech_id]["limitBaseLevel"]
        current_base_lv:int = sandbox_data["template"]["SANDBOX_V3"][topic_id]["base"]["level"]
        if current_base_lv < limit_base_lv:
            return {}, 400
        del limit_base_lv, current_base_lv

        # 检查是否已经解锁
        unlock_tech:list = tech_data["unlock"]
        if tech_id in unlock_tech:
            return {
                "playerDataDelta": {
                    "modified": {
                        "sandboxPerm": {
                            "template": {
                                "SANDBOX_V3": {
                                    topic_id: {
                                        "tech": tech_data
                                    }
                                }
                            }
                        }
                    },
                    "deleted": {}
                }
            }

        # 检查前置科技是否解锁
        front_node_id:str = sandbox_excel["detail"]["SANDBOX_V3"][topic_id]["developmentData"][tech_id]["frontNodeId"]
        if front_node_id not in unlock_tech:
            return {}, 400
        del front_node_id
        
        # 解锁科技
        token_cost:int = sandbox_excel["detail"]["SANDBOX_V3"][topic_id]["developmentData"][tech_id]["tokenCost"]
        current_token:int = tech_data["token"]
        if current_token < token_cost:
            return {}, 400
        tech_data["token"] -= token_cost
        unlock_tech.append(tech_id)
        unlock_tech.sort() # 如果不想后期手动编辑数据时看到一团乱麻，这个排序是很有必要的

        result = {
            "playerDataDelta": {
                "modified": {
                    "sandboxPerm": {
                        "template": {
                            "SANDBOX_V3": {
                                topic_id: {
                                    "tech": tech_data
                                }
                            }
                        }
                    },
                    "deleted": {}
                }
            }
        }

        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def _harvestFresh(base_data:dict, topic_id:str, need_write:bool = False):
        '''
        计算基地材料产出
        :param base_data: 基地数据，一般是["template"]["SANDBOX_V3"][topic_id]["base"]
        '''
        # 奖励转换倍率
        conversion_rate = [
            None,
            {"sandbox_2_basegold": 0.10, "sandbox_2_basegoldEx": 0},
            {"sandbox_2_basegold": 0.12, "sandbox_2_basegoldEx": 0},
            {"sandbox_2_basegold": 0.14, "sandbox_2_basegoldEx": 0.01},
            {"sandbox_2_basegold": 0.15, "sandbox_2_basegoldEx": 0.02},
            {"sandbox_2_basegold": 0.18, "sandbox_2_basegoldEx": 0.03}
        ]
        sandbox_table = get_memory("sandbox_perm_table")
        # 基地已部署建筑数据
        building_data:dict = base_data["building"]
        building_keys = building_data.keys()
        pdline_set = set({})
        for keys in building_keys:
            if keys.startswith("sandbox_2_building_base_pdline"):
                pdline_id = keys.split("_")[-1]
                pdline_set.add(pdline_id)
        # 能源核心
        base_energy_core_building = {
            "1", "2", "3", "4", "5",
        }
        # 转化建筑激活所需的产线建筑
        active_building_map = {
            "sandbox_2_building_base_pdline_6": {
                "9", "10", "11", "12", "13"
            },
            "sandbox_2_building_base_pdline_7": {
                "14", "15", "16", "17", "18"
            },
            "sandbox_2_building_base_pdline_8": {
                "19", "20", "21", "22", "23"
            }
        }

        # 检查建筑id所需建筑
        def get_need_building(building_id:str):
            for key, value in active_building_map.items():
                if building_id in value:
                    return key
            return None

        # 检查能源核心是否已部署
        if base_energy_core_building & pdline_set:
            base_core_id:int = int(list(base_energy_core_building & pdline_set)[0])
            pdline_set -= base_energy_core_building
            pdline_list = list(pdline_set)
            activate_building:dict[str,int] = {}
            target_pos_cache: dict[str, set] = {}
            rate_data:dict[str, int] = {}

            # 检查每种建筑中每个建筑的激活情况
            for key in pdline_list:
                key = "sandbox_2_building_base_pdline_" + key
                grids = sandbox_table["detail"]["SANDBOX_V3"][topic_id]["itemExtraData"][key]["grids"]
                need_building = get_need_building(key)
                # 如果没有需要的建筑，则跳过
                if not need_building:
                    continue
                # 已激活的产线数量
                active_count = 0
                # 检查缓存
                if need_building not in target_pos_cache:
                    # 所需建筑的位置
                    target_buildings = building_data.get(need_building, [])
                    target_pos_cache[need_building] = {
                        tuple(item["pos"])
                        for item in target_buildings
                    }
                # 获取缓存
                target_pos_set = target_pos_cache[need_building]
                # 检查范围内是否有所需建筑
                for building in building_data[key]:
                    x, y = building["pos"]
                    # 遍历偏移坐标
                    for grid in grids:
                        check_pos = (
                            x + grid["col"],
                            y + grid["row"]
                        )
                        if check_pos in target_pos_set:
                            active_count += 1
                            break
                # 添加计数
                activate_building[key] = active_count
                del active_count

            total_enery_output = 0
            # 计算能源产出
            for key in activate_building.keys():
                energy_output:int = sandbox_table["detail"]["SANDBOX_V3"][topic_id]["electricTransferData"][key]["skillParam"]
                active_count = activate_building[key]
                total_enery_output += energy_output * active_count

            # 根据基地等级换算资源产出
            conversion_rate = conversion_rate[base_core_id]
            for k, v in conversion_rate.items():
                rate_data[k] = int(total_enery_output * v)
        else:
            rate_data = {
                "sandbox_2_basegold": 30
            }

        if need_write:
            user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
            sandbox_data = user_data["user"]["sandboxPerm"]
            sandbox_data["template"]["SANDBOX_V3"][topic_id]["base"]["production"]["rate"] = rate_data
            write_json(user_data, SYNC_DATA_TEMPLATE_PATH)
        else:
            return rate_data

    def _freshScore(base_data:dict, topic_id:str, need_write:bool = False):
        sandbox_table:dict = get_memory("sandbox_perm_table")
        total_score = 0
        # 建筑自身分数
        for key, value in base_data["building"].items():
            building_count = len(value)
            trap_cfg_id:str = sandbox_table["detail"]["SANDBOX_V3"][topic_id]["itemExtraData"][key]["trapCfgId"]
            building_score:int = sandbox_table["detail"]["SANDBOX_V3"][topic_id]["baseTrapData"][trap_cfg_id]["buildScore"]
            current_building_total_score = building_count * building_score
            total_score += current_building_total_score

        # 区域分数
        for key in base_data["wonder"]:
            match key:
                case "wonder_1":
                    total_score += 200
                case "wonder_2":
                    total_score += 300
                case "wonder_3":
                    total_score += 400
                case "wonder_4":
                    total_score += 500
                case _:
                    pass

        # 相邻连接额外分数
        building_extra_socre = {
            "sandbox_2_building_base_path_1": 5
        }
        # 相邻偏移
        grids = [
            {"row": 1, "col": 0},
            {"row": 0, "col": -1},
            {"row": 0, "col": 1},
            {"row": -1, "col": 0}
        ]
        for key in building_extra_socre.keys():
            # 检查相邻是否存在同类建筑
            for key, extra_score in building_extra_socre.items():
                buildings = base_data["building"].get(key, [])
                scored_pos = set()
                for i, building in enumerate(buildings):
                    pos = tuple(building["pos"])
                    x, y = pos
                    for other in buildings[i + 1:]:
                        other_pos = tuple(other["pos"])
                        dx = other_pos[0] - x
                        dy = other_pos[1] - y
                        # 是否属于相邻范围
                        if {"row": dy, "col": dx} in grids:
                            if pos not in scored_pos:
                                total_score += extra_score
                                scored_pos.add(pos)
                            if other_pos not in scored_pos:
                                total_score += extra_score
                                scored_pos.add(other_pos)
        if need_write:
            user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
            sandbox_data = user_data["user"]["sandboxPerm"]
            sandbox_data["template"]["SANDBOX_V3"][topic_id]["base"]["score"] = total_score
            write_json(sandbox_data, SYNC_DATA_TEMPLATE_PATH)
        else:
            return total_score

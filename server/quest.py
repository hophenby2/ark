from virtualtime import time

from flask import request

from constants import BATTLE_REPLAY_JSON_PATH, USER_JSON_PATH, SYNC_DATA_TEMPLATE_PATH,ASSIST_PATH
from utils import read_json, write_json, decrypt_battle_data, get_memory, run_after_response


def questBattleStart():

    request_data = request.get_json()
    data = {
        "apFailReturn": 0,
        'battleId': 'abcdefgh-1234-5678-a1b2c3d4e5f6',
        "inApProtectPeriod": False,
        "isApProtect": 0,
        "notifyPowerScoreNotEnoughIfFailed": False,
        'playerDataDelta': {
            'modified': {},
            'deleted': {}
        },
        'result': 0
    }

    replay_data = read_json(BATTLE_REPLAY_JSON_PATH)
    replay_data["current"] = request_data["stageId"]
    run_after_response(write_json ,replay_data, BATTLE_REPLAY_JSON_PATH)

    return data


def questBattleFinish():

    data = {
        "result":0,
        "apFailReturn": 0,
        "expScale": 1.2,
        "goldScale": 1.2,
        "rewards": [],
        "firstRewards": [],
        "unlockStages": [],
        "unusualRewards": [],
        "additionalRewards": [],
        "furnitureRewards": [],
        "alert": [],
        "suggestFriend": False,
        "pryResult": [],
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        }
    }

    return data


def questSaveBattleReplay():

    request_data = request.get_json()

    replay_data = read_json(BATTLE_REPLAY_JSON_PATH)

    data = {
        "result": 0,
        "playerDataDelta": {
            "modified": {
                "dungeon": {
                    "stages": {
                        replay_data["current"]: {
                            "hasBattleReplay": 1
                        }
                    }
                }
            },
            "deleted": {}
        }
    }

    char_config = replay_data["currentCharConfig"]

    if char_config in list(replay_data["saved"].keys()):
        replay_data["saved"][char_config].update({
            replay_data["current"]: request_data["battleReplay"]
        })
    else:
        replay_data["saved"].update({
            char_config: {
                replay_data["current"]: request_data["battleReplay"]
            }
        })
    replay_data["current"] = None
    run_after_response(write_json ,replay_data, BATTLE_REPLAY_JSON_PATH)

    return data


def questGetBattleReplay():

    stageId = request.get_json()["stageId"]

    replay_data = read_json(BATTLE_REPLAY_JSON_PATH)
    battleData = {
        "battleReplay": replay_data["saved"][replay_data["currentCharConfig"]][stageId],
        "playerDataDelta": {
            "deleted": {},
            "modified": {}
        }
    }
    
    return battleData


def questChangeSquadName():

    request_data = request.get_json()
    data = {
        "playerDataDelta":{
            "modified":{
                "troop":{
                    "squads":{}
                }
            },
            "deleted":{}
        }
    }

    if request_data["squadId"] and request_data["name"]:
        data["playerDataDelta"]["modified"]["troop"]["squads"].update({
            str(request_data["squadId"]): {
                "name": request_data["name"]
            }
        })

        saved_data = read_json(USER_JSON_PATH)
        saved_data["user"]["troop"]["squads"][str(request_data["squadId"])]["name"] = request_data["name"]
        run_after_response(write_json ,saved_data, USER_JSON_PATH)
        run_after_response(write_json ,saved_data, SYNC_DATA_TEMPLATE_PATH)

        return data


def questSquadFormation():

    request_data = request.get_json()
    data = {
        "playerDataDelta":{
            "modified":{
                "troop":{
                    "squads":{}
                }
            },
            "deleted":{}
        }
    }

    if request_data["squadId"] and request_data["slots"]:
        data["playerDataDelta"]["modified"]["troop"]["squads"].update({
            str(request_data["squadId"]): {
                "slots": request_data["slots"]
            }
        })

        saved_data = read_json(USER_JSON_PATH)
        saved_data["user"]["troop"]["squads"][str(request_data["squadId"])]["slots"] = request_data["slots"]
        run_after_response(write_json ,saved_data, USER_JSON_PATH)
        run_after_response(write_json ,saved_data, SYNC_DATA_TEMPLATE_PATH)

        return data

def load_assist_units(filter_profession=None):
    assist_unit_configs = read_json(ASSIST_PATH)
    saved_data = read_json(USER_JSON_PATH)["user"]["troop"]["chars"]
    char_table = get_memory("character_table")

    # 创建全局UID映射
    global_assist_units = []
    uid_counter = 100000000

    for profession, units in assist_unit_configs.items():
        for unit_config in units:
            if not isinstance(unit_config, dict) or "charId" not in unit_config:
                continue
            char_id = unit_config["charId"]

            # 从角色表中获取角色名称
            char_info = char_table.get(char_id, {})
            profession = char_info.get("profession", "UNKNOWN")
            char_name = char_info.get("name", "未知干员")  # 默认值
            char_resume = char_info.get("itemUsage", "")
            if char_resume is None:
                char_resume = ""
            # 查找玩家角色数据
            for _, char in saved_data.items():
                if char["charId"] == char_id:
                    global_assist_units.append({
                        "charId": char["charId"],
                        "charName": char_name,  # 存储角色名称
                        "charResume": char_resume,  # 存储角色描述
                        "skinId": char["skin"],
                        "skills": char["skills"],
                        "mainSkillLvl": char["mainSkillLvl"],
                        "skillIndex": unit_config.get("skillIndex", 0),
                        "evolvePhase": char["evolvePhase"],
                        "favorPoint": char["favorPoint"],
                        "potentialRank": char["potentialRank"],
                        "level": char["level"],
                        "crisisRecord": {},
                        "currentEquip": (
                            unit_config["currentEquip"]
                            if unit_config.get("currentEquip") in char["equip"] else None
                        ),
                        "equip": char["equip"],
                        "profession": profession,
                        "instId": char["instId"],
                        "fixedUid": uid_counter,  # 分配固定UID
                        # 添加头像信息
                        "avatar": {
                            "type": "ASSISTANT",
                            "id": char["skin"]  # 使用角色皮肤作为头像
                        }
                    })
                    uid_counter += 1
                    break

    # 按职业过滤
    if filter_profession:
        return [unit for unit in global_assist_units if unit["profession"] == filter_profession]
    return global_assist_units

def questGetAssistList():
    req = request.get_json()
    filter_profession = req.get("profession")

    # 获取助战单位（可能按职业过滤）
    assist_units = load_assist_units(filter_profession)

    assist_list = []
    for assist_unit in assist_units:
        # 使用固定的UID
        uid = assist_unit["fixedUid"]
        assist_unit_with_uid = dict(assist_unit)
        assist_unit_with_uid["uid"] = uid

        assist_list.append({
            "uid": str(uid),
            "aliasName": "",
            "nickName": assist_unit["charName"],
            "nickNumber": assist_unit["instId"],
            "level": 120,
            "avatarId": "0",
            # 使用助战角色的头像
            "avatar": assist_unit["avatar"],
            "lastOnlineTime": int(time()),
            "assistCharList": [assist_unit_with_uid, None, None],
            "powerScore": 500,
            "isFriend": True,
            "canRequestFriend": False,
            "assistSlotIndex": 0
        })

    data = {
        "allowAskTs": int(time()),
        "assistList": assist_list,
        "playerDataDelta": {"modified": {}, "deleted": {}}
    }
    return data


def markStoryAcceKnown():
    return {
        "playerDataDelta": {
            "modified": {
                "storyreview": {
                    "tags": {
                        "knownStoryAcceleration": 1
                        }
                    }
                },
            "deleted": {}
        }
    }


def confirmBattleCar():
    return {
        "playerDataDelta": {
            "modified": {
                "car": {
                    "battleCar": request.get_json()["car"]
                }
            },
            "deleted": {}
        }
    }

def questBattleContinue():
    return {
        "result": 0,
        "battleId": "abcdefgh-1234-5678-a1b2c3d4e5f6",
        "apFailReturn": 0,
        "playerDataDelta": {"modified": {}, "deleted": {}},
    }

def readStory():
    return {
        "readCount": 1,
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        }
    }

def setTrapSquad():
    json_body = request.get_json()
    trapDomainId = json_body["trapDomainId"]
    trapSquad = json_body["trapSquad"]
    data = {
        "playerDataDelta": {
            "modified": {
                "templateTrap": {"domains": {trapDomainId: {"squad": trapSquad}}}
            },
            "deleted": {},
        }
    }
    return data

def relicSelect():
    json_bdoy = request.get_json()
    activityId = json_bdoy["activityId"]
    relicId = json_bdoy["relicId"]
    data = {
        "playerDataDelta": {
            "modified": {
                "activity": {"BOSS_RUSH": {activityId: {"relic": {"select": relicId}}}}
            },
            "deleted": {},
        }
    }
    return data

def act7fun_questBattleFinish():

    json_body = request.get_json()

    battle_data = decrypt_battle_data(json_body["data"])

    complete_state = battle_data["completeState"]

    return {
        "completeState": complete_state,
        "rewards": [],
        "unlockedStages": "",
        "playerDataDelta": {"modified": {}, "deleted": {}},
    }

def act6fun_questBattleFinish():

    json_body = request.get_json()

    battle_data = decrypt_battle_data(json_body["data"])
    user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    act6fun_data = user_data["user"]["aprilFool"]["act6fun"]
    
    new_record = False
    coin = 0

    complete_state = battle_data["completeState"]
    pass_sec = battle_data["battleData"]["completeTime"]
    for i in battle_data["battleData"]["stats"]["extraBattleInfo"]:
        if i.startswith("coin_collect_cnt"):
            coin = battle_data["battleData"]["stats"]["extraBattleInfo"][i]
            break

    return {
        "completeState": complete_state,
        "passSec": pass_sec,
        "newRecord": new_record,
        "coin": coin,
        "playerDataDelta": {"modified": {}, "deleted": {}},
    }

def act5fun_questBattleFinish():

    json_body = request.get_json()

    battle_data = decrypt_battle_data(json_body["data"])
    user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    act5fun_data = user_data["user"]["aprilFool"]["act5fun"]

    score = 0
    round = 0
    round_win = 0
    npc_result = {}
    is_high_score = False
    high_score:int = act5fun_data["highScore"]

    for i in battle_data["battleData"]["stats"]["extraBattleInfo"]:
        if i.startswith("DETAILED,player,"):
            round += 1
            if i.endswith("win"):
                round_win += 1
                continue
        if i.startswith("SIMPLE,act5fun_npc_") and i.endswith("win"):
            npc_result[i.split(",")[1]] = battle_data["battleData"]["stats"]["extraBattleInfo"][i]
            continue
        if i.startswith("SIMPLE,money,"):
            score = int(i.split(",")[-1])

    if score > high_score:
        act5fun_data["highScore"] = score
        is_high_score = True
        run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)

    result =  {
        "result": 0,
        "score": score,
        "isHighScore": is_high_score,
        "npcResult": npc_result,
        "playerResult": {
            "totalWin": round_win,
            "streak": score,
            "totalRound": round
        },
        "reward": [],
        "playerDataDelta": {
            "modified": {
                "aprilFool": {
                    "act5fun": user_data["user"]["aprilFool"]["act5fun"]
                }
            },
            "deleted": {}
        },
    }
    
    return result

def act4fun_questBattleFinish():
    return {
        "materials": [
            {"instId": i, "materialId": j, "materialType": 1}
            for i, j in enumerate(
                [
                    "spLiveMat_tr_1",
                    "spLiveMat_tr_2",
                    "spLiveMat_01_1",
                    "spLiveMat_01_2",
                    "spLiveMat_01_3",
                    "spLiveMat_01_4",
                    "spLiveMat_01_5",
                    "spLiveMat_01_6",
                    "spLiveMat_01_7",
                    "spLiveMat_01_8",
                    "spLiveMat_01_9",
                    "spLiveMat_02_1",
                    "spLiveMat_02_2",
                    "spLiveMat_02_3",
                    "spLiveMat_02_4",
                    "spLiveMat_02_5",
                    "spLiveMat_02_6",
                    "spLiveMat_02_7",
                    "spLiveMat_02_8",
                    "spLiveMat_02_9",
                    "spLiveMat_03_1",
                    "spLiveMat_03_2",
                    "spLiveMat_03_3",
                    "spLiveMat_03_4",
                    "spLiveMat_03_5",
                    "spLiveMat_03_6",
                    "spLiveMat_03_7",
                    "spLiveMat_03_8",
                    "spLiveMat_03_9",
                ]
            )
        ],
        "liveId": "abcdefgh-1234-5678-a1b2c3d4e5f6",
        "playerDataDelta": {"modified": {}, "deleted": {}},
    }

def act4fun_liveSettle():
    return {
        "ending": "goodending_1",
        "playerDataDelta": {"modified": {}, "deleted": {}},
    }

def singleBattleStart():

    #{'activityId': 'act1enemyduel', 'modeId': 'soloOperation'}

    return{
        "pushMessage": [],
        "result": 0,
        "battleId": "abcdefgh-1234-5678-a1b2c3d4e5f6",
    }

def singleBattleFinish():

    json_body = request.get_json()

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
        "commentId": "Comment_Operation_1",
        "isHighScore": True,
        "rankList": rankList,
        "dailyMission": {
            "add": 0,
            "reward": 0
        },
        "bp": 0
    }

    return result

def unlockStageFog():
    return {}, 202

def unlockHideStage():
    return {}, 202

def getCowLevelReward():
    json_body = request.get_json()

    stage_id:str = json_body["stageId"]
    user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    # 特殊主线对应的特殊物品
    special_items = {
        "spst_17-01": "main17_spitem_1"
    }

    item_id = special_items.get(stage_id, None)
    if item_id is None:
        return {}, 400

    # user_data["user"]["items"][item_id] -= 1
    cow_level_data = user_data["user"]["dungeon"]["cowLevel"]
    main_line_ep:int = int((stage_id.split("-")[0]).split("_")[1])
    if main_line_ep >= 17:
        level_data = {
            "id": stage_id,
            "type": "STAGE",
            "val": [1, 1],
            "fts": time(),
            "rts": time()
        }
    else:
        level_data = {
            "id": stage_id,
            "fts": time(),
            "rts": time()
        }
    cow_level_data[stage_id] = level_data

    diamond_count = user_data["user"]["status"]["androidDiamond"]
    if diamond_count < 2147483647:
        diamond_count += 1


    result = {
        "playerDataDelta": {
            "deleted": {},
            "modified": {
                "dungeon": {
                    "cowLevel": {
                        stage_id: level_data
                    }
                },
                "status": {
                    "androidDiamond": diamond_count
                }
            }
        },
        "rewards": [
            {
                "id": 4002,
                "count": 1,
                "type": "DIAMOND"
            }
        ]
    }

    run_after_response(write_json, user_data, SYNC_DATA_TEMPLATE_PATH)
    return result

def getMainlineRecordRewards():
    return {}, 202

def getMainlineCache():
    return {}, 202

def unlockRetroBlock():
    return {}, 202

def getRetroTrailReward():
    return {}, 202

def getRetroPassReward():
    return {}, 202

def runeBattleStart():
    return {}, 202

def runeBattleFinish():
    return {}, 202

def unlockStoryByCoin():
    return {}, 202

def rewardGroup():
    return {}, 202

def trailReward():
    return {}, 202

def trainingGroundBattleStart():
    return {}

def trainingGroundBattleFinish():
    return {}

def arcadeBattleStart():
    return {}, 202

def arcadeBattleFinish():
    return {}, 202

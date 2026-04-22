from virtualtime import time
from flask import request
from utils import read_json, write_json, get_memory, run_after_response
from constants import SYNC_DATA_TEMPLATE_PATH, USER_JSON_PATH
import json

def Sync():
    # 读取用户数据
    user_data = read_json(USER_JSON_PATH)
    building_data = user_data["user"]["building"]
    
    ts = time()

    def process_building_data(building_data, user_data, ts):
        """处理建筑数据的闭包函数 - 只在异常时调用"""
        
        # 从建筑数据中提取角色实例ID到角色ID的映射
        def extract_id_mapping():
            """提取实例ID到角色ID的映射"""
            inst_to_role = {}
            role_to_inst = {}
            
            for inst_id, char_data in building_data["chars"].items():
                if "charId" in char_data:
                    char_full_id = char_data["charId"]
                    parts = char_full_id.split("_")
                    if len(parts) >= 2:
                        role_id = parts[1]
                        inst_to_role[inst_id] = role_id
                        if role_id not in role_to_inst:
                            role_to_inst[role_id] = []
                        role_to_inst[role_id].append(inst_id)
            
            return inst_to_role, role_to_inst
        
        # 从数据获取需要保留的角色集合
        def get_user_role_set():
            """获取当前拥有的角色ID集合"""
            return set(user_data["user"]["troop"]["chars"].keys())
        
        # 重建chars字典
        def rebuild_chars_dict():
            """重建building_data["chars"]，保留原有数据"""
            inst_to_role, role_to_inst = extract_id_mapping()
            user_roles = get_user_role_set()
            
            new_chars = {}
            processed_roles = set()
            
            # 处理拥有的角色
            for role_id in user_roles:
                # 查找对应的实例ID
                if role_id in role_to_inst:
                    # 使用第一个可用的实例ID
                    inst_id = role_to_inst[role_id][0]
                    original_data = building_data["chars"].get(inst_id, {})
                    
                    # 保留原有数据并更新
                    new_chars[role_id] = {
                        "charId": original_data.get("charId", f"char_{role_id}_unknown"),
                        "ap": original_data.get("ap", 8640000),
                        "lastApAddTime": ts,
                        "roomSlotId": original_data.get("roomSlotId", ""),
                        "index": original_data.get("index", -1),
                        "changeScale": original_data.get("changeScale", 0),
                        "bubble": original_data.get("bubble", {
                            "normal": {"add": -1, "ts": 0},
                            "assist": {"add": -1, "ts": 0},
                            "private": {"add": -1, "ts": 0}
                        }),
                        "workTime": original_data.get("workTime", 0),
                        "skin": original_data.get("skin")
                    }
                    processed_roles.add(role_id)
                else:
                    # 有新角色，创建新条目
                    char_data = user_data["user"]["troop"]["chars"][role_id]
                    new_chars[role_id] = {
                        "charId": char_data["charId"],
                        "ap": 8640000,
                        "lastApAddTime": ts,
                        "roomSlotId": "",
                        "index": -1,
                        "changeScale": 0,
                        "bubble": {
                            "normal": {"add": -1, "ts": 0},
                            "assist": {"add": -1, "ts": 0},
                            "private": {"add": -1, "ts": 0}
                        },
                        "workTime": 0,
                        "skin": None
                    }
                    processed_roles.add(role_id)
            
            # 保留没有但建筑中存在的角色（可能正在工作中）
            for role_id, inst_list in role_to_inst.items():
                if role_id not in processed_roles:
                    inst_id = inst_list[0]
                    original_data = building_data["chars"].get(inst_id, {})
                    # 检查是否有重要的状态数据（如在工作中）
                    if (original_data.get("roomSlotId") or 
                        original_data.get("index") != -1 or
                        original_data.get("workTime", 0) > 0):
                        new_chars[role_id] = {
                            "charId": original_data.get("charId", f"char_{role_id}_unknown"),
                            "ap": original_data.get("ap", 8640000),
                            "lastApAddTime": original_data.get("lastApAddTime", ts),
                            "roomSlotId": original_data.get("roomSlotId", ""),
                            "index": original_data.get("index", -1),
                            "changeScale": original_data.get("changeScale", 0),
                            "bubble": original_data.get("bubble", {
                                "normal": {"add": -1, "ts": 0},
                                "assist": {"add": -1, "ts": 0},
                                "private": {"add": -1, "ts": 0}
                            }),
                            "workTime": original_data.get("workTime", 0),
                            "skin": original_data.get("skin")
                        }
            
            return new_chars
        
        # 更新roomSlots中的charInstIds（将实例ID转换为角色ID）
        def update_room_slots_mapping():
            """更新房间插槽中的角色实例ID为角色ID"""
            inst_to_role, _ = extract_id_mapping()
            
            for slot_id, slot_data in building_data["roomSlots"].items():
                if "charInstIds" in slot_data:
                    new_char_ids = []
                    for inst_id in slot_data["charInstIds"]:
                        if inst_id == -1:
                            new_char_ids.append(-1)
                        else:
                            inst_id_str = str(inst_id)
                            if inst_id_str in inst_to_role:
                                new_char_ids.append(int(inst_to_role[inst_id_str]))
                            else:
                                new_char_ids.append(inst_id)
                    slot_data["charInstIds"] = new_char_ids
        
        # 修复presetQueue中的角色ID
        def update_preset_queues():
            """更新所有预设队列中的角色ID"""
            inst_to_role, _ = extract_id_mapping()
            
            def convert_queue(queue):
                """转换单个队列"""
                if not queue or not isinstance(queue, list):
                    return queue
                new_queue = []
                for item in queue:
                    if isinstance(item, list):
                        new_queue.append(convert_queue(item))
                    elif isinstance(item, (int, str)) and str(item) in inst_to_role:
                        new_queue.append(int(inst_to_role[str(item)]))
                    else:
                        new_queue.append(item)
                return new_queue
            
            # 遍历所有房间
            for room_id, room_data in building_data.get("rooms", {}).items():
                for slot_id, slot_data in room_data.items():
                    if isinstance(slot_data, dict):
                        if "presetQueue" in slot_data:
                            slot_data["presetQueue"] = convert_queue(slot_data["presetQueue"])
                        
                        for field in ["trainee", "trainer"]:
                            if field in slot_data and isinstance(slot_data[field], dict):
                                for key in ["charInstId", "charInstId"]:
                                    if key in slot_data[field]:
                                        inst_id = str(slot_data[field][key])
                                        if inst_id in inst_to_role:
                                            slot_data[field][key] = int(inst_to_role[inst_id])
        
        # 执行重建流程
        new_chars = rebuild_chars_dict()
        building_data["chars"] = new_chars
        
        # 更新映射关系
        update_room_slots_mapping()
        update_preset_queues()
        
        return building_data

    try:
        for i in building_data["roomSlots"]:
            for j, k in enumerate(building_data["roomSlots"][i]["charInstIds"]):
                if k == -1:
                    continue
                k = str(k)
                building_data["chars"][k]["roomSlotId"] = i
                building_data["chars"][k]["index"] = j
    except (KeyError, IndexError, TypeError) as e:
        # 重建
        process_building_data(building_data, user_data, ts)
    
    # 读取基建table数据
    building_table = get_memory("building_data")
    # 创建家具字典
    furniture = {
        i: {"count": 9999, "inUse": 0}
        for i in building_table["customData"]["furnitures"]
    }
    building_data["furniture"] = furniture
    # 将基建数据写入文件
    run_after_response(write_json, user_data, USER_JSON_PATH)
    
    result = {
        "playerDataDelta": {
            "modified": {
                "building": building_data
            },
            "deleted": {}
        }
    }
    
    return result

def GetRecentVisitors():

    result = {
        "visitors": []
    }
    return result

def GetInfoShareVisitorsNum():

    result = {
        "num":0
    }
    return result

def AssignChar():

    json_body = json.loads(request.data)
    roomSlotId = json_body["roomSlotId"]
    char_inst_id_list = json_body["charInstIdList"]

    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    room_slots = user_sync_data["user"]["building"]["roomSlots"]

    for key, value in room_slots.items():
        room_char_inst_ids = value["charInstIds"]
        for i in range(len(room_char_inst_ids)):
            for n in range(len(char_inst_id_list)):
                if char_inst_id_list[n] == room_char_inst_ids[i]:
                    room_char_inst_ids[i] = -1

    user_sync_data["user"]["building"]["roomSlots"][roomSlotId]["charInstIds"] = char_inst_id_list

    if roomSlotId == "slot_13":
        trainer = char_inst_id_list[0]
        trainee = char_inst_id_list[1]

        training_room = user_sync_data["user"]["building"]["rooms"]["TRAINING"][roomSlotId]
        training_room["trainee"]["charInstId"] = trainee
        training_room["trainee"]["targetSkill"] = -1
        training_room["trainee"]["speed"] = 1000
        training_room["trainer"]["charInstId"] = trainer

        if trainee == -1:
            training_room["trainee"]["state"] = 0
        else:
            training_room["trainee"]["state"] = 3

        if trainer == -1:
            training_room["trainer"]["state"] = 0
        else:
            training_room["trainer"]["state"] = 3

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
    run_after_response(write_json ,user_sync_data, USER_JSON_PATH)

    player_data_delta = {
        "modified": {
            "building": user_sync_data["building"],
            "event": user_sync_data["event"]
        },
        "deleted": {}
    }

    result = {
        "playerDataDelta": player_data_delta
    }

    return result

def ChangeDiySolution():

    json_body = request.get_json()

    roomSlotId = json_body["roomSlotId"]
    solution = json_body["solution"]

    user_json_data = read_json(USER_JSON_PATH)

    if roomSlotId == "slot_36":
        user_json_data["user"]["building"]["rooms"]["MEETING"]["slot_36"]["diySolution"] = solution
        building_modified = {
            "rooms": {
                "MEETING": {
                    "slot_36": {
                        "diySolution": solution
                    }
                }
            }
        }
    else:
        for roomId in user_json_data["user"]["building"]["roomSlots"].keys():
            if roomId == roomSlotId:
                rooms_type = user_json_data["user"]["building"]["roomSlots"][roomId]["roomId"]
                user_json_data["user"]["building"]["rooms"][rooms_type][roomSlotId]["diySolution"] = solution
                building_modified = {
                    "rooms": {
                        rooms_type: {
                            roomSlotId: {
                                "diySolution": solution 
                            }
                        }
                    }
                }
                break

    run_after_response(write_json ,user_json_data, USER_JSON_PATH)

    result = {
        "playerDataDelta": {
            "modified": {
                "building": building_modified,
                "event": user_json_data["user"]["event"]
            },
            "deleted": {}
        }
    }

    return result

def ChangeManufactureSolution():

    json_body = json.loads(request.data)

    roomSlotId = str(json_body["roomSlotId"])
    target_FormulaId = str(json_body["targetFormulaId"])
    solution_count = str(json_body["solutionCount"])
    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    outputSolutionCnt = user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['outputSolutionCnt']
    FormulaId = user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['formulaId']

    if outputSolutionCnt != 0:
        if 5 <= int(FormulaId) <= 12:
            item_id = None
            if int(FormulaId) == 5:
                item_id = "3212"
            elif int(FormulaId) == 6:
                item_id = "3222"
            elif int(FormulaId) == 7:
                item_id = "3232"
            elif int(FormulaId) == 8:
                item_id = "3242"
            elif int(FormulaId) == 9:
                item_id = "3252"
            elif int(FormulaId) == 10:
                item_id = "3262"
            elif int(FormulaId) == 11:
                item_id = "3272"
            elif int(FormulaId) == 12:
                item_id = "3282"
            
            user_sync_data["user"]['inventory'][FormulaId] += outputSolutionCnt
            user_sync_data["user"]['inventory'][item_id] -= 2 * outputSolutionCnt
            user_sync_data["user"]['inventory']["32001"] -= 1 * outputSolutionCnt

        elif int(FormulaId) > 12:
            item_id = None
            if int(FormulaId) == 13:
                item_id = "30012"
                user_sync_data['status']['gold'] -= 1600 * outputSolutionCnt
            elif int(FormulaId) == 14:
                item_id = "30062"
                user_sync_data['status']['gold'] -= 1000 * outputSolutionCnt

            user_sync_data["user"]['inventory'][FormulaId] += outputSolutionCnt
            user_sync_data["user"]['inventory'][item_id] -= 2 * outputSolutionCnt

        else:
            user_sync_data["user"]['inventory'][FormulaId] += outputSolutionCnt

    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['state'] = 1
    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['formulaId'] = target_FormulaId
    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['lastUpdateTime'] = int(time())
    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['completeWorkTime'] = -1
    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['remainSolutionCnt'] = 0
    user_sync_data["user"]['building']['rooms']['MANUFACTURE'][roomSlotId]['outputSolutionCnt'] = solution_count

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)

    result = {
        "playerDataDelta": {
            "modified": {
                "building": user_sync_data['building'],
                "event": user_sync_data['event'],
                "inventory": user_sync_data['inventory'],
                "status": user_sync_data['status']
            },
            "deleted": {}
        }
    }

    return result

def SettleManufacture():

    json_body = json.loads(request.data)
    roomSlotId = json_body["roomSlotId"]
    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    outputSolutionCnt = user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["outputSolutionCnt"]
    FormulaId = user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["formulaId"]

    if outputSolutionCnt != 0:
            if 5 <= int(FormulaId) <= 12:
                item_id = None
                if int(FormulaId) == 5:
                    item_id = "3212"
                elif int(FormulaId) == 6:
                    item_id = "3222"
                elif int(FormulaId) == 7:
                    item_id = "3232"
                elif int(FormulaId) == 8:
                    item_id = "3242"
                elif int(FormulaId) == 9:
                    item_id = "3252"
                elif int(FormulaId) == 10:
                    item_id = "3262"
                elif int(FormulaId) == 11:
                    item_id = "3272"
                elif int(FormulaId) == 12:
                    item_id = "3282"
                user_sync_data["user"]["inventory"][FormulaId] += outputSolutionCnt
                user_sync_data["user"]["inventory"][item_id] -= 2 * outputSolutionCnt
                user_sync_data["user"]["inventory"]["32001"] -= 1 * outputSolutionCnt
            elif int(FormulaId) > 12:
                item_id = None
                if int(FormulaId) == 13:
                    item_id = "30012"
                    user_sync_data["user"]["status"]["gold"] -= 1600 * outputSolutionCnt
                elif int(FormulaId) == 14:
                    item_id = "30062"
                    user_sync_data["user"]["status"]["gold"] -= 1000 * outputSolutionCnt
                user_sync_data["user"]["inventory"][FormulaId] += outputSolutionCnt
                user_sync_data["user"]["inventory"][item_id] -= 2 * outputSolutionCnt
            else:
                user_sync_data["user"]["inventory"][FormulaId] += outputSolutionCnt

    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["state"] = 0
    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["formulaId"] = ""
    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["lastUpdateTime"] = int(time.time())
    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["completeWorkTime"] = -1
    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["remainSolutionCnt"] = 0
    user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["outputSolutionCnt"] = 0

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
    run_after_response(write_json ,user_sync_data, USER_JSON_PATH)

    result = {
        "playerDataDelta": {
        "modified": {
            "building": user_sync_data["building"],
            "event": user_sync_data["event"],
            "inventory": user_sync_data["inventory"],
            "status": user_sync_data["status"]
        },
        "deleted": {}
    }
    }

    return result

def WorkshopSynthesis():

    json_body = json.loads(request.data)
    roomSlotId = json_body["roomSlotId"]
    work_count = json_body["times"]

    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    workshop_formulas = user_sync_data["user"]["building"]["rooms"]["MANUFACTURE"][roomSlotId]["formulaId"]

    costs = workshop_formulas["costs"]
    for cost in costs:
        item_id = cost["id"]
        item_count = cost["count"]
        user_sync_data["inventory"][item_id] -= item_count * work_count

    user_sync_data["user"]["inventory"][workshop_formulas["itemId"]] += workshop_formulas["costs"] * work_count
    user_sync_data["user"]["status"]["gold"] -= workshop_formulas["goldCost"] * work_count

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
    run_after_response(write_json ,user_sync_data, USER_JSON_PATH)

    result = {
        "playerDataDelta": {
        "modified": {
            "building": user_sync_data["building"],
            "event": user_sync_data["event"],
            "inventory": user_sync_data["inventory"],
            "status": user_sync_data["status"]
        },
        "deleted": {}
        },
        "results": {
        "type": "MATERIAL",
        "id": workshop_formulas["itemId"],
        "count": work_count
        }
    }

    return result

def UpgradeSpecialization():

    json_body = json.loads(request.data)
    


    data = request.data

    return data

def CompleteUpgradeSpecialization():

    data = request.data

    return data

def DeliveryOrder():

    json_body = json.loads(request.data)
    slotId = json_body["slotId"]
    orderId = json_body["orderId"]

    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    gold_num = user_sync_data["user"]["building"]["rooms"]["TRADING"][slotId]["stock"]["count"]

    user_sync_data["user"]["inventory"]["3003"] -= gold_num
    user_sync_data["user"]["status"]["gold"] += gold_num * 500

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
        
    modified = {
        "building": user_sync_data["building"],
        "inventory": user_sync_data["inventory"],
        "status": user_sync_data["status"]
    }
    
    result = {
        "palyerDataDelta":{
            "modified": modified,
            "deleted": {}
        }
    }

    return result

def DeliveryBatchOrder():

    json_body = json.loads(request.data)
    slotId = json_body["slotId"]
    orderId = json_body["orderId"]

    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    gold_num = user_sync_data["user"]["building"]["rooms"]["TRADING"][slotId]["stock"]["count"]

    user_sync_data["user"]["inventory"]["3003"] -= gold_num
    user_sync_data["user"]["status"]["gold"] += gold_num * 500
    # if slotId == "slot_24":
    #     user_sync_data["user"]["inventory"]["3003"] -= 2
    #     user_sync_data["user"]["status"]["gold"] += 1000

    # elif slotId == "slot_14":
    #     user_sync_data["user"]["inventory"]["3003"] -= 4
    #     user_sync_data["user"]["status"]["gold"] += 2000

    # elif slotId == "slot_5":
    #     user_sync_data["user"]["inventory"]["3003"] -= 6
    #     user_sync_data["user"]["status"]["gold"] += 3000

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
        
    modified = {
        "building": user_sync_data["building"],
        "inventory": user_sync_data["inventory"],
        "status": user_sync_data["status"]
    }
    
    result = {
        "palyerDataDelta":{
            "modified": modified,
            "deleted": {}
        }
    }

    return result

def CleanRoomSlot():

    result = request.data

    return result
 
def getAssistReport():

    result = {
        "reports": [
            {
            "ts": time(),
            "manufacture": {},
            "trading": {},
            "favor": []
            },
            {
            "ts": time() - 86400,
            "manufacture": {},
            "trading": {},
            "favor": []
            },
            {
            "ts": time() - 172800,
            "manufacture": {},
            "trading": {},
            "favor": []
            },
            {
            "ts": time() - 345600,
            "manufacture": {},
            "trading": {},
            "favor": []
            }
        ],
        "playerDataDelta": {
            "deleted": {},
            "modified": {}
        }
    }
    
    return result

def setBuildingAssist():
    
    # 解析请求数据
    json_body = json.loads(request.data)
    type = int(json_body["type"])
    char_inst_id = str(json_body["charInstId"])
    # 读取 SYNC_DATA_TEMPLATE_PATH 对应的文件内容并转换为字典
    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    # 检查 assist 中是否已经存在相同的 charInstId，如果有，将其位置修改为 -1
    for index, value in enumerate(user_sync_data["user"]["building"]["assist"]):
        if value == char_inst_id:
            user_sync_data["user"]["building"]["assist"][index] = -1

    # 在传入的 type 位置写入 charInstId
    user_sync_data["user"]["building"]["assist"][type] = char_inst_id

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)

    # 处理 modified 数据
    user_sync_data_building = user_sync_data["user"]["building"]
    user_sync_data_event = user_sync_data["user"]['event']

    # 返回结果
    result = {
        "reports": [],
        "playerDataDelta": {
            "deleted": {},
            "modified": {
                "building": user_sync_data_building,
                "event": user_sync_data_event
            }
        }
    }

    return result

def changeStrategy():

    json_body = json.loads(request.data)

    slot_id = json_body["slotId"]
    strategy = json_body["strategy"]
    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    user_sync_data["user"]["building"]["rooms"]["TRADING"][slot_id]["type"] = strategy
    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)

    modified = user_sync_data["user"]["building"]["rooms"]["TRADING"][slot_id]
    result = {
        "playerDataDelta": {
            "deleted": {},
            "modified": modified
        }
    }

    return result

def changRoomLevel():

    json_body = request.get_json()
    roomSlotId = json_body["roomSlotId"]
    targetLevel = json_body["targetLevel"]
    user_sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)

    user_sync_data["user"]["building"]["roomSlots"][roomSlotId]["level"] = targetLevel

    run_after_response(write_json ,user_sync_data, SYNC_DATA_TEMPLATE_PATH)
    modified = user_sync_data["user"]["building"]["roomSlots"][roomSlotId]

    result = {
        "playerDataDelta": {
            "deleted": {},
            "modified": modified
        }
    }

    return result

def addPresetQueue():
    json_body = request.get_json()
    # {'slotId': 'slot_36'}

    result = {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "chars": {},
                    "roomSlots": {},
                    "rooms": {},
                    "status": {}
                }
            },
            "deleted": {}
        }
    }

    return result

def deletePresetQueue():
    json_body = request.get_json()

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "chars": {},
                    "roomSlots": {},
                    "rooms": {},
                    "status": {}
                }
            },
            "deleted": {}
        }
    }

def editPresetQueue():
    json_body = request.get_json()

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "chars": {},
                    "roomSlots": {},
                    "rooms": {},
                    "status": {}
                }
            },
            "deleted": {}
        }
    }

def usePresetQueue():
    json_body = request.get_json()

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "chars": {},
                    "roomSlots": {},
                    "rooms": {},
                    "status": {}
                }
            },
            "deleted": {}
        }
    }

def editLockQueue():
    json_body = request.get_json()
    # {'lockPos': {'slot_28': [0, 0, 0, 0, 1], 'slot_20': [0, 0, 0, 0, 0], 'slot_9': [0, 0, 0, 0, 0], 'slot_3': [0, 0, 0, 0, 0]}}
    building_data = get_memory("building_data")

    # TODO: 待编写

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    
                }
            }
        }
    }

def batchRestChar():
    json_body = request.get_json()

    user_data = read_json(USER_JSON_PATH)
    building_data = user_data["user"]["building"]

    # TODO: 待编写

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    
                }
            }
        }
    }

def buildRoom():
    json_body = request.get_json()

    # {'roomSlotId': 'slot_47', 'roomId': 'PRIVATE'}
    user_data = read_json(USER_JSON_PATH)
    building_data = user_data["user"]["building"]

    # TODO: 待编写

    return {
        "playerDataDelta": {
            "modified": {
                "building": {

                }
            }
        }
    }

def setPrivateDormOwner():
    json_body = request.get_json()

    user_data = read_json(USER_JSON_PATH)
    target_slot_id = json_body["slotId"]
    owners_id = json_body["charInsId"]

    user_data["user"]["building"]["rooms"]["PRIVATE"][target_slot_id]["owners"] = [owners_id]

    run_after_response(write_json ,user_data, USER_JSON_PATH)

    return {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "rooms": {
                        "PRIVATE": {
                            target_slot_id: {
                                "owners": [owners_id]
                            }
                        }
                    }
                }
            },
            "deleted": {}
        }
    }

def changeBGM():
    json_body = request.get_json()

    user_data = read_json(USER_JSON_PATH)

    music_id = json_body["musicId"]

    user_data["user"]["building"]["music"]["selected"] = music_id

    result = {
        "playerDataDelta": {
            "modified": {
                "building": {
                    "music": {
                        "selected": music_id
                    }
                }
            },
            "deleted": {}
        }
    }
    return result

def getClueBox():

    return {
        "box": []
    }

def getClueFriendList():

    return {
        "result": []
    }


def confirmPrivateDormIntimacy():
    json_body = request.get_json()

    user_data = read_json(USER_JSON_PATH)
    building_data = user_data["user"]["building"]
    troop = user_data["user"]["troop"]
    charInstId = str(json_body.get("charInstId"))  # 转换为字符串以匹配键

    char_info = user_data["user"]["troop"]["chars"].get(charInstId)

    char_id = char_info["charId"]

    modified = {
        "building": {
            "roomSlots": building_data["roomSlots"],
            "rooms": building_data["rooms"],
            "chars": building_data["chars"],
            "status": building_data["status"]
        },
        "troop": {
            "charGroup": {
                char_id: {
                    "favorPoint": 25570
                }
            },
            "chars": {
                charInstId: {
                    "favorPoint": 25570
                }
            }
        }
    }
    result = {
        "palyerDataDelta":{
            "modified": modified,
            "deleted": {}
        }
    }

    return result

def gainIntimacy():
    return {}, 202

def gainAssistIntimacy():
    return {}, 202

def gainAllIntimacy():
    return {}, 202

def visitBuilding():
    return {}, 202

def completeUpgradeRoom():
    return {}, 202

def changeSaleSolution():
    return {}, 202

def settleSale():
    return {}, 202

def upgradeDiyLevel():
    return {}, 202

def saveDiyPresetSolution():
    return {}, 202

def changePresetName():
    return {}, 202

def getThumbnailUrl():
    return {}, 202

def workshopDecomposition():
    return {}, 202

def deleteOrder():
    return {}, 202

def accelerateOrder():
    return {}, 202

def accelerateSolution():
    return {}, 202

def buyLabor():
    return {}, 202

def deleteOwnClue():
    return {}, 202

def deleteReceiveClue():
    return {}, 202

def putClueToTheBoard():
    return {}, 202

def putClueToTheBoardAuto():
    return {}, 202

def sendClueAuto():
    return {}, 202

def sendClue():
    return {}, 202

def getMeetingroomReward():
    
    result = {
        "palyerDataDelta":{
            "modified": {},
            "deleted": {}
        },
        "rewards": []
    }

    return result

def receiveClueToStock():
    return {}, 202

def startInfoShare():
    return {}, 202

def getDailyClue():
    return {}, 202

def getOthersMessageBoardContent():
    return {}, 202

def confirmMessageBoardReward():
    return {}, 202

def sendEmoji():
    return {}, 202

def batchChangeWorkChar():
    return {}, 202

def useOnePresetQueue():
    return {}, 202

    return result
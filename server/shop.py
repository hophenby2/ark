from datetime import datetime

from flask import request

from constants import SHOP_PATH, SYNC_DATA_TEMPLATE_PATH
from utils import read_json, write_json, run_after_response, get_memory, writeLog


def getGoodPurchaseState():

    data = request.data
    data = {
    "playerDataDelta": {
        "modified": {},
        "deleted": {}
    },
    "result": {}
    }

    return data

# 获取json的内容并返回

def getShopGoodList(shop_type):
    try:
        result = get_memory("shop")[shop_type.lower()]
        return result
    except:
        writeLog(f"{shop_type} 数据未找到")
        return {}
  
def buyShopGood(shop_type: str):

    json_body = request.get_json()
    # 商品ID
    good_id = str(json_body["goodId"])
    # 购买数量
    count = int(json_body["count"])

    if shop_type == "Classic":
        return {}

    # 皮肤购买
    if shop_type == "Skin":
        good_id = json_body["goodId"]

        skin_good_list = get_memory("shop")["skin"]
        sync_data_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    
        # 遍历goodList列表
        for good in skin_good_list["goodList"]:
            # 获取价格
            origin_price = good["originPrice"]
    
        # 扣除Diamond货币并添加皮肤
        sync_data_data["user"]["skin"]["characterSkins"][good_id[3:]] = 1
        sync_data_data["user"]["skin"]["skinTs"][good_id[3:]] = int(datetime.now().timestamp())
        sync_data_data["user"]["status"]["androidDiamond"] -= origin_price
        sync_data_data["user"]["status"]["iosDiamond"] -= origin_price

        # 返回内容
        result = {
            "playerDataDelta": {
                "deleted": {},
                "modified": {
                    "skin": sync_data_data["user"]["skin"],
                    "status": {
                        "androidDiamond": sync_data_data["user"]["status"]["androidDiamond"]
                    }
                }
            },
            "result": 0
        }
        
        # run_after_response(write_json, sync_data_data, SYNC_DATA_TEMPLATE_PATH)
        return result

    def bomb():
        return {}, 500

    items = []
    modified = {
        "status": {},
        "inventory": {},
        "troop": {}
    }

    sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    good_list = get_memory("shop")[shop_type.lower()]["goodList"]
    gacha_map = {
        "TKT_GACHA": "gachaTicket",
        "TKT_GACHA_10": "tenGachaTicket",
        "CLASSIC_TKT_GACHA": "classicGachaTicket",
        "CLASSIC_TKT_GACHA_10": "classicTenGachaTicket"
    }
    currency_map = {
        "low": "lggShard",
        "high": "hggShard",
        "extra": "4006",
        "classic": "classicShard",
        "epgs": "EPGS_COIN",
        "Rep": "REP_COIN",
        "Social": ""
    }

    # 从good_list中获取 goodId
    good = next((g for g in good_list if g["goodId"] == good_id), None)
    # 没有就跟客户端爆了
    if not good:
        return bomb()

    # 要扣的数值
    price = good["price"] * count

    currency = None
    inventory = None

    # 获取货币类型
    match shop_type.lower():
        case "low"|"high"|"classic":
            currency = currency_map[shop_type.lower()]
            inventory:dict = sync_data["user"]["status"]
        case "extra"|"epgs"|"Rep":
            currency = currency_map[shop_type.lower()]
            inventory:dict = sync_data["user"]["inventory"]
        case _:
            return bomb()
    
    # 如果货币不足
    if inventory.get(currency, 0) < price:
        return bomb()
    else:
        # 否则正常扣除
        inventory[currency] -= price

    item = good["item"]
    user = sync_data["user"]

    if item is not None:
        reward_item = {
            "id": item["id"],
            "type": item["type"],
            "count": item.get("count", 1) * count
        }
        _apply_reward_item(user, reward_item, modified, items)

    # 返回内容
    result = {
        "playerDataDelta": {
            "deleted": {},
            # 只返回有变动的数据块
            "modified": {k: v for k, v in modified.items() if v}
        },
        "items": items,
        "result": 0
    }
    # run_after_response(write_json, sync_data_data, SYNC_DATA_TEMPLATE_PATH)
    return result

def buyShopGoodWithTicket(shop_type: str):
    json_body = request.get_json()

    ticket_id = json_body["ticketId"]
    good_id = json_body["goodId"]
    parts = json_body["goodId"].split("_")
    shop_type = parts[0]
    good_type = parts[1]
    good_list = get_memory("shop")[shop_type.lower()]

    sync_data = read_json(SYNC_DATA_TEMPLATE_PATH)
    user = sync_data["user"]

    # 手动控制是否通用(即main_class的内容是否为list类型)
    general = False
    config_items = []
    result_items = []
    modified = {
        "status": {},
        "inventory": {},
        "troop": {}
    }

    # shop 礼包分类的映射表
    main_class_map = {
        "Once": "oneTimeGP",
        "NpOne": "chooseGroup",
    }

    # 每月礼包位于 packages 中, 类型为dict, 不需要遍历查找, 直接引用即可
    if good_type == "gM":
        general = False
        main_class = "monthlyGroup"
        good_info = good_list[main_class]["packages"][good_id]
        config_items = good_info["items"]

    if config_items == []:
        general = True
        main_class = main_class_map[good_type]

    if general:
        for good_info in good_list[main_class]:
            if good_info["goodId"] == json_body["goodId"]:
                config_items = good_info["items"]
                break

    for item in config_items:
        _apply_reward_item(user, item, modified, result_items)

    result = {
        "playerDataDelta": {
            "modified": {k: v for k, v in modified.items() if v},
            "deleted": {}
        },
        "items": result_items
    }
    # run_after_response(write_json, sync_data_data, SYNC_DATA_TEMPLATE_PATH)
    return result

def _apply_reward_item(user: dict, reward_item: dict, modified: dict, result_items: list):
    '''
    处理奖励物品，没有返回内容，直接修改 user 和 modified，作为运算函数使用
    :param user: 用户数据
    :param reward_item: 奖励物品
    :param modified: 修改后的用户数据
    :param result_items: 返回的物品列表
    '''
    gacha_map = {
        "TKT_GACHA": "gachaTicket",
        "TKT_GACHA_10": "tenGachaTicket",
        "CLASSIC_TKT_GACHA": "classicGachaTicket",
        "CLASSIC_TKT_GACHA_10": "classicTenGachaTicket"
    }

    def build_char_data(char_id: str) -> tuple[str, dict]:
        # 角色实例ID直接取 char_xxx 中的数字段，项目内保证唯一
        inst_id = char_id.split("_")[1]

        char_data = {
            "instId": int(inst_id),
            "charId": char_id,
            "favorPoint": 0,
            "potentialRank": 0,
            "mainSkillLvl": 1,
            "skin": f"{char_id}#1",
            "level": 1,
            "exp": 0,
            "evolvePhase": 0,
            "gainTime": int(datetime.now().timestamp()),
            "skills": [],
            "defaultSkillIndex": -1,
            "currentEquip": None
        }
        return inst_id, char_data

    item_type = reward_item["type"]
    item_id = reward_item["id"]
    item_count = reward_item.get("count", 1)

    # 角色奖励
    if item_type == "CHAR":
        chars = user["troop"]["chars"]
        char_id = item_id
        inst_id = char_id.split("_")[1]

        # 直接用实例ID判断是否已拥有, 避免扫描整个 chars
        if inst_id not in chars:
            inst_id, char_data = build_char_data(char_id)
            chars[inst_id] = char_data
            modified["troop"].setdefault("chars", {})[inst_id] = char_data
            is_new = 1
        else:
            is_new = 0

        result_items.append({
            "id": char_id,
            "type": "CHAR",
            "charGet": {
                "charInstId": int(inst_id),
                "charId": char_id,
                "isNew": is_new
            }
        })

    # 合成玉
    elif item_type == "DIAMOND_SHD":
        user["status"]["diamondShard"] += item_count
        if user["status"]["diamondShard"] > 2147483647:
            user["status"]["diamondShard"] = 2147483647
        modified["status"] = user["status"]

        result_items.append({
            "id": item_id,
            "type": item_type,
            "count": item_count
        })

    # 源石
    elif item_type == "DIAMOND":
        user["status"]["diamondShard"] += item_count
        if user["status"]["diamondShard"] > 2147483647:
            user["status"]["androidDiamond"] = 2147483647
        modified["status"] = user["status"]

        result_items.append({
            "id": item_id,
            "type": item_type,
            "count": item_count
        })

    # 龙门币
    elif item_type == "GOLD":
        user["status"]["gold"] += item_count
        if user["status"]["gold"] > 18446744073709551616:
            user["status"]["gold"] = 18446744073709551616
        modified["status"] = user["status"]

        result_items.append({
            "id": item_id,
            "type": item_type,
            "count": item_count
        })

    # 寻访券
    elif item_type in gacha_map:
        key = gacha_map[item_type]
        user["status"][key] += item_count
        if user["status"][key] > 2147483647:
            user["status"][key] = 2147483647
        modified["status"] = user["status"]

        result_items.append({
            "id": item_id,
            "type": item_type,
            "count": item_count
        })

    # 其它物品默认进入 inventory
    else:
        inv = user.setdefault("inventory", {})
        inv[item_id] = inv.get(item_id, 0) + item_count
        modified["inventory"][item_id] = inv[item_id]

        result_items.append({
            "id": item_id,
            "type": item_type,
            "count": item_count
        })

def decomposePotentialItem():
    result = {
        "playerDataDelta": {
            "modified": {},
            "deleted": {}
        },
        "items": []
    }

    return result

def decomposeClassicPotentialItem():
    return {}, 202

def getCashGoodPurchaseResult():
    return {}, 202

def getVoucherSkinGoodList():
    return {}, 202

def useVoucherSkin():
    return {}, 202

def checkForbidden():
    return {}, 202

from virtualtime import time
from utils import get_memory

def GiveItem(user_data, reward_id, reward_type, reward_count, items):
    """给予玩家物品的"""
    chars = user_data["troop"]["chars"]
    troop = {}
    character_table = get_memory("character_table")
    charword_table = get_memory("charword_table")
    uniequip_table = get_memory("uniequip_table")
    
    def handle_char_reward():
        """处理角色奖励"""
        # 查找是否已拥有该角色
        repeat_char_id = 0
        for j in range(len(user_data["troop"]["chars"])):
            if user_data["troop"]["chars"][str(j + 1)]["charId"] == reward_id:
                repeat_char_id = j + 1
                break
        
        if repeat_char_id == 0:
            # 添加新角色
            skills_array = character_table[reward_id]["skills"]
            skills = []
            
            for m in range(len(skills_array)):
                new_skills = {
                    "skillId": skills_array[m]["skillId"],
                    "state": 0,
                    "specializeLevel": 0,
                    "completeUpgradeTime": -1,
                    "unlock": 1 if skills_array[m]["unlockCond"]["phase"] == 0 else 0
                }
                skills.append(new_skills)
            
            inst_id = len(user_data["troop"]["chars"]) + 1
            
            char_data = {
                "instId": inst_id,
                "charId": reward_id,
                "favorPoint": 0,
                "potentialRank": 0,
                "mainSkillLvl": 1,
                "skin": f"{reward_id}#1",
                "level": 1,
                "exp": 0,
                "evolvePhase": 0,
                "gainTime": int(time()),
                "skills": skills,
                "voiceLan": charword_table["charDefaultTypeDict"][reward_id],
                "defaultSkillIndex": 0 if skills else -1
            }
            
            # 处理装备
            char_name = reward_id.split("_")[-1]
            if f"uniequip_001_{char_name}" in uniequip_table["equipDict"].keys():
                equip = {
                    f"uniequip_001_{char_name}": {"hide": 0, "locked": 0, "level": 1},
                    f"uniequip_002_{char_name}": {"hide": 0, "locked": 0, "level": 1}
                }
                char_data["equip"] = equip
                char_data["currentEquip"] = f"uniequip_001_{char_name}"
            else:
                char_data["currentEquip"] = None
            
            # 更新用户数据
            user_data["troop"]["chars"][str(inst_id)] = char_data
            user_data["troop"]["curCharInstId"] = inst_id + 1
            
            # 创建角色组
            char_group = {"favorPoint": 0}
            user_data["troop"]["charGroup"][reward_id] = char_group
            
            # 创建基建角色数据
            building_char = {
                "charId": reward_id,
                "lastApAddTime": int(time()),
                "ap": 8640000,
                "roomSlotId": "",
                "index": -1,
                "changeScale": 0,
                "bubble": {
                    "normal": {"add": -1, "ts": 0},
                    "assist": {"add": -1, "ts": -1}
                },
                "workTime": 0
            }
            user_data["building"]["chars"][str(inst_id)] = building_char
            
            # 创建获取角色信息
            get_char = {
                "charInstId": inst_id,
                "charId": reward_id,
                "isNew": 1,
                "itemGet": [
                    {"type": "HGG_SHD", "id": "4004", "count": 1}
                ]
            }
            
            user_data["status"]["hggShard"] += 1
            user_data["inventory"][f"p_{reward_id}"] = 0
            
            chars[str(inst_id)] = char_data
            troop["chars"] = {str(inst_id): char_data}
            
            item = {
                "id": reward_id,
                "type": reward_type,
                "charGet": get_char
            }
            items.append(item)
            
        else:
            # 处理重复角色
            repeat_char = user_data["troop"]["chars"][str(repeat_char_id)]
            potential_rank = repeat_char["potentialRank"]
            rarity = character_table[reward_id]["rarity"]
            
            # 根据稀有度确定补偿物品
            match rarity:
                case 0:
                    item_name, item_type, item_id, item_count = "lggShard", "LGG_SHD", "4005", 1
                case 1:
                    item_name, item_type, item_id, item_count = "lggShard", "LGG_SHD", "4005", 1
                case 2:
                    item_name, item_type, item_id, item_count = "lggShard", "LGG_SHD", "4005", 5
                case 3:
                    item_name, item_type, item_id, item_count = "lggShard", "LGG_SHD", "4005", 30
                case 4:
                    item_name, item_type, item_id = "hggShard", "HGG_SHD", "4004"
                    item_count = 5 if potential_rank != 5 else 8
                case 5:
                    item_name, item_type, item_id = "hggShard", "HGG_SHD", "4004"
                    item_count = 10 if potential_rank != 5 else 15
                case _:
                    item_name, item_type, item_id, item_count = "lggShard", "LGG_SHD", "4005", 1
            
            item_get = [
                {"type": item_type, "id": item_id, "count": item_count},
                {"type": "MATERIAL", "id": f"p_{reward_id}", "count": 1}
            ]
            
            user_data["status"][item_name] += item_count
            user_data["inventory"][f"p_{reward_id}"] += 1
            
            get_char = {
                "charInstId": repeat_char_id,
                "charId": reward_id,
                "isNew": 0,
                "itemGet": item_get
            }
            
            chars[str(repeat_char_id)] = repeat_char
            troop["chars"] = {str(repeat_char_id): repeat_char}
            
            item = {
                "type": reward_type,
                "id": reward_id,
                "charGet": get_char
            }
            items.append(item)
    
    def handle_other_rewards():
        """处理其他类型的奖励"""
        match reward_type:
            case "HGG_SHD":
                user_data["status"]["hggShard"] += reward_count
            case "LGG_SHD":
                user_data["status"]["lggShard"] += reward_count
            case "SOCIAL_PT":
                user_data["status"]["socialPoint"] += reward_count
            case "AP_GAMEPLAY":
                user_data["status"]["ap"] += reward_count
            case "AP_ITEM":
                if "60" in reward_id:
                    user_data["status"]["ap"] += 60
                elif "200" in reward_id:
                    user_data["status"]["ap"] += 200
                else:
                    user_data["status"]["ap"] += 100
            case "TKT_TRY":
                user_data["status"]["practiceTicket"] += reward_count
            case "DIAMOND":
                user_data["status"]["androidDiamond"] += reward_count
                user_data["status"]["iosDiamond"] = user_data["status"]["androidDiamond"]
            case "DIAMOND_SHD":
                user_data["status"]["diamondShard"] += reward_count
            case "GOLD":
                user_data["status"]["gold"] += reward_count
            case "TKT_RECRUIT":
                user_data["status"]["recruitLicense"] += reward_count
            case "TKT_INST_FIN":
                user_data["status"]["instantFinishTicket"] += reward_count
            case "TKT_GACHA_10":
                user_data["status"]["tenGachaTicket"] += reward_count
            case "TKT_GACHA":
                user_data["status"]["gachaTicket"] += reward_count
            case "CHAR_SKIN":
                user_data["skin"]["characterSkins"][reward_id] = 1
                user_data["skin"]["skinTs"][reward_id] = int(time())
            # case "MATERIAL" | "CARD_EXP" | "TKT_GACHA_PRSV" | "RENAMING_CARD" | "RETRO_COIN" | "AP_SUPPLY":
            #     user_data["inventory"][reward_id] += reward_count
            case _:
                # 处理代券类型奖励（包含"VOUCHER"字符串的）
                if "VOUCHER" in reward_type:
                    if reward_id not in user_data["consumable"]:
                        user_data["consumable"][reward_id] = {"0": {"ts": -1, "count": 0}}
                    user_data["consumable"][reward_id]["0"]["count"] += reward_count
                else:
                    user_data["inventory"][reward_id] += reward_count
        
        # 添加物品到列表（角色奖励已在其他方法中处理）
        if reward_type != "CHAR":
            item = {
                "id": reward_id,
                "type": reward_type,
                "count": reward_count
            }
            items.append(item)
    
    # 主逻辑
    if reward_type == "CHAR":
        handle_char_reward()
    else:
        handle_other_rewards()

    return user_data

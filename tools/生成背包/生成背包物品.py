import json
import os


def generate_item_template(item_table_path):
    """
    读取item_table.json，分别找出所有classifyType为CONSUME, NORMAL, MATERIAL的物品，
    CONSUME的物品生成到 consumable 字段下，格式为 { "itemId": { "0": { "ts": -1, "count": 999 } } }
    NORMAL 和 MATERIAL 的物品生成到 inventory 字段下，格式为 { "itemId": 999 }
    """
    try:
        # 1. 读取 item_table.json 文件
        with open(item_table_path, 'r', encoding='utf-8') as f:
            item_data = json.load(f)

        items = item_data.get("items", {})

        # 初始化结果字典的两个主要部分
        consumable_dict = {}
        inventory_dict = {}

        # 2. 遍历所有物品并分类处理
        renaming_card_items = [] # 临时存储所有 renamingCard 类型的物品

        for item_id, item_info in items.items():
            classify_type = item_info.get("classifyType")
            sort_id = item_info.get("sortId", 0)

            # 处理 CONSUME 类型
            if classify_type == "CONSUME":
                # 收集所有 renamingCard 类型的物品，稍后处理
                if item_info.get("iconId") == "renamingCard":
                    renaming_card_items.append((item_id, item_info))
                else:
                    # 其他 CONSUME 类型直接添加
                    if sort_id > 0: # 通常只处理 sortId > 0 的有效物品
                        consumable_dict[item_id] = {
                            "0": {
                                "ts": -1,
                                "count": 999
                            }
                        }

            # 处理 NORMAL 和 MATERIAL 类型
            elif classify_type in ["NORMAL", "MATERIAL"]:
                 if sort_id > 0: # 通常只处理 sortId > 0 的有效物品
                    inventory_dict[item_id] = 999

        # 3. 特殊处理 iconId 为 "renamingCard" 的物品，只保留 sortId 最小的一个
        if renaming_card_items:
            # 按 sortId 排序
            renaming_card_items.sort(key=lambda x: x[1].get("sortId", 0))
            # 取 sortId 最小的一个（即列表第一个）
            selected_item_id, selected_item_info = renaming_card_items[0]
            # 添加到 consumable 字典中
            if selected_item_info.get("sortId", 0) > 0:
                 consumable_dict[selected_item_id] = {
                    "0": {
                        "ts": -1,
                        "count": 999
                    }
                }


        # 4. 组合最终结果
        result = {
            "consumable": consumable_dict,
            "inventory": inventory_dict
        }

        return result

    except FileNotFoundError:
        print(f"错误：找不到文件 {item_table_path}")
        return None
    except json.JSONDecodeError:
        print(f"错误：无法解析JSON文件 {item_table_path}")
        return None
    except Exception as e:
        print(f"发生未知错误: {e}")
        return None

base_path = os.path.dirname(__file__)
item_table_file_path = os.path.join(base_path, "../../data/excel/item_table.json")

# 生成模板
generated_template = generate_item_template(item_table_file_path)

# 保存为JSON文件
if generated_template is not None:
    # 为了和用户上下文中的格式保持一致，我们不使用 indent
    # 如果需要美化格式，可以设置 indent=4
    with open('item_template_output.json', 'w', encoding='utf-8') as f:
        json.dump(generated_template, f, ensure_ascii=False, indent=4) # <- 美化格式用这行替换上一行
    print("模板已保存为 item_template_output.json")
else:
    print("生成模板失败")

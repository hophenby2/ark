from copy import deepcopy
from random import Random
from typing import Any


RECRUIT_COST = {
    "TIER_1": 0,
    "TIER_2": 0,
    "TIER_3": 0,
    "TIER_4": 2,
    "TIER_5": 3,
    "TIER_6": 6,
}

UPGRADE_COST = {
    "TIER_1": 0,
    "TIER_2": 0,
    "TIER_3": 0,
    "TIER_4": 1,
    "TIER_5": 2,
    "TIER_6": 3,
}

LATE_THEME_RECRUIT_COST = {
    **RECRUIT_COST,
    "TIER_4": 0,
    "TIER_5": 2,
}

LATE_THEME_UPGRADE_COST = {
    **UPGRADE_COST,
    "TIER_5": 1,
}

GOPNIK_SPAWN_PERCENT = 10

PROFESSION_SUFFIXES = (
    "pioneer",
    "warrior",
    "tank",
    "sniper",
    "caster",
    "support",
    "medic",
    "special",
)

MELEE_PROFESSION_SUFFIXES = ("pioneer", "warrior", "tank", "special")
RANGED_PROFESSION_SUFFIXES = ("sniper", "caster", "support", "medic")

RECRUIT_GROUPS = {
    "recruit_group_1": ("pioneer", "sniper", "special"),
    "recruit_group_2": ("tank", "caster", "sniper"),
    "recruit_group_3": ("warrior", "support", "medic"),
    "recruit_group_4": ("pioneer", "support", "special"),
    "recruit_group_5": ("tank", "caster", "medic"),
}

SPECIAL_RECRUIT_GROUPS = {
    "recruit_group_c4": (
        "sniper",
        "sniper_sp",
        "caster",
        "caster_sp",
    ),
    "recruit_group_c5": (
        "warrior",
        "warrior_sp",
        "tank",
        "tank_sp",
    ),
    "recruit_group_c9": (
        "warrior",
        "warrior_sp",
        "tank",
        "tank_sp",
    ),
    "recruit_group_c10": (
        "support",
        "support_sp",
        "medic",
        "medic_sp",
    ),
    "ro3_recruit_group_c1": ("all", "all"),
}

# Each zone contains (normal, emergency), and each reward is (exp, gold).
# Source: PRTS roguelike theme pages, revisions 408420-408424 (2026-07-13).
BATTLE_BASE_REWARDS = {
    "rogue_1": (
        ((10, 3), (12, 4)),
        ((12, 3), (18, 4)),
        ((16, 3), (24, 5)),
        ((20, 4), (30, 5)),
        ((25, 4), (38, 6)),
        ((25, 4), (45, 6)),
    ),
    "rogue_2": (
        ((10, 2), (12, 3)),
        ((12, 2), (18, 3)),
        ((14, 2), (24, 4)),
        ((16, 3), (30, 4)),
        ((20, 3), (36, 5)),
        ((20, 3), (36, 5)),
    ),
    "rogue_3": (
        ((10, 2), (12, 3)),
        ((12, 2), (18, 3)),
        ((14, 2), (24, 4)),
        ((16, 3), (30, 4)),
        ((20, 3), (36, 5)),
        ((20, 3), (36, 5)),
    ),
    "rogue_4": (
        ((10, 1), (12, 2)),
        ((12, 2), (18, 2)),
        ((13, 2), (25, 3)),
        ((15, 3), (30, 3)),
        ((20, 3), (36, 5)),
        ((20, 5), (36, 5)),
    ),
    "rogue_5": (
        ((10, 1), (12, 2)),
        ((12, 2), (18, 2)),
        ((13, 2), (25, 3)),
        ((15, 2), (30, 3)),
        ((20, 2), (36, 5)),
        ((20, 5), (36, 5)),
    ),
}

BATTLE_REWARD_ZONE_ALIASES = {
    ("rogue_4", 7): 6,
    ("rogue_5", 7): 6,
}


def select_init_config(
    topic_table: dict,
    theme: str,
    mode: str,
    mode_grade: int,
    predefined: str | None = None,
) -> dict:
    """Return the exact client-table initialization row for a run."""
    try:
        rows = topic_table["details"][theme]["init"]
    except KeyError as exc:
        raise ValueError(f"unsupported roguelike theme: {theme}") from exc

    matches = [
        row
        for row in rows
        if row["modeId"] == mode and row["modeGrade"] == mode_grade
    ]
    if predefined is not None:
        matches = [row for row in matches if row["predefinedId"] == predefined]
    else:
        regular = [row for row in matches if row["predefinedId"] is None]
        if regular:
            matches = regular
        elif mode in {"MONTH_TEAM", "CHALLENGE"} or len(matches) > 1:
            raise ValueError(
                f"predefinedId is required for roguelike mode: "
                f"{theme}/{mode}/{mode_grade}"
            )

    if not matches:
        suffix = f", predefined={predefined}" if predefined else ""
        raise ValueError(
            f"unsupported roguelike mode: {theme}/{mode}/{mode_grade}{suffix}"
        )
    return deepcopy(matches[0])


def select_equivalent_grade(
    topic_table: dict, theme: str, mode: str, mode_grade: int
) -> int:
    for difficulty in topic_table["details"][theme]["difficulties"]:
        if (
            difficulty["modeDifficulty"] == mode
            and difficulty["grade"] == mode_grade
        ):
            return difficulty["equivalentGrade"]
    return mode_grade


def select_player_level_table(
    theme_data: dict,
    mode: str,
    mode_grade: int,
    predefined: str | None,
) -> tuple[dict, int]:
    predefined_key = f"{mode}_{mode_grade}_{predefined}"
    predefined_table = theme_data["detailConst"].get(
        "predefinedLevelTable", {}
    )
    if predefined is not None and predefined_key in predefined_table:
        levels = predefined_table[predefined_key]["levels"]
        return levels, max(map(int, levels))

    levels = theme_data["detailConst"]["playerLevelTable"]
    return levels, min(max(map(int, levels)), 10)


def build_initial_property(
    init_config: dict, player_level_table: dict, max_level: int | None = None
) -> dict:
    initial_hp = init_config["initialHp"]
    initial_max_hp = init_config["initialMaxHp"] or initial_hp
    levels = [int(level) for level in player_level_table]
    return {
        "exp": 0,
        "level": min(levels),
        "maxLevel": max_level if max_level is not None else min(max(levels), 10),
        "hp": {"current": initial_hp, "max": initial_max_hp},
        "gold": init_config["initialGold"],
        "shield": init_config["initialShield"],
        "capacity": init_config["initialSquadCapacity"],
        "population": {"cost": 0, "max": init_config["initialPopulation"]},
        "conPerfectBattle": 0,
    }


def resolve_player_levels(
    player_property: dict, player_level_table: dict
) -> dict[str, int]:
    """Consume accumulated experience and apply table-defined level gains."""
    gains = {
        "populationMax": 0,
        "squadCapacity": 0,
        "maxHpUp": 0,
        "battleCharLimitUp": 0,
    }
    player_property["exp"] = max(0, player_property["exp"])

    while player_property["level"] < player_property["maxLevel"]:
        next_level = player_property["level"] + 1
        level_data = player_level_table.get(str(next_level))
        if level_data is None:
            break
        required_exp = int(level_data["exp"])
        if player_property["exp"] < required_exp:
            break

        player_property["exp"] -= required_exp
        player_property["level"] = next_level
        population_up = int(level_data.get("populationUp", 0))
        capacity_up = int(level_data.get("squadCapacityUp", 0))
        max_hp_up = int(level_data.get("maxHpUp", 0))
        battle_limit_up = int(level_data.get("battleCharLimitUp", 0))
        player_property["population"]["max"] += population_up
        player_property["capacity"] += capacity_up
        player_property["hp"]["max"] += max_hp_up
        player_property["hp"]["current"] += max_hp_up
        gains["populationMax"] += population_up
        gains["squadCapacity"] += capacity_up
        gains["maxHpUp"] += max_hp_up
        gains["battleCharLimitUp"] += battle_limit_up

    clamp_player_property(player_property)
    return gains


def apply_numeric_delta(target: dict, delta: dict, sign: int = 1) -> None:
    """Apply a sparse nested numeric delta without walking unrelated state."""
    if sign not in (-1, 1):
        raise ValueError("sign must be -1 or 1")

    for key, value in delta.items():
        if isinstance(value, dict):
            current = target.get(key)
            if current is None:
                current = {}
                target[key] = current
            if not isinstance(current, dict):
                raise TypeError(f"delta path {key!r} does not target an object")
            apply_numeric_delta(current, value, sign)
            continue

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"delta value at {key!r} must be numeric")
        current = target.get(key, 0)
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise TypeError(f"target value at {key!r} must be numeric")
        target[key] = current + sign * value


def has_numeric_cost(target: dict, cost: dict) -> bool:
    """Return whether a sparse cost can be paid without crossing a hard bound."""
    for key, value in cost.items():
        current = target.get(key)
        if isinstance(value, dict):
            if not isinstance(current, dict) or not has_numeric_cost(current, value):
                return False
            continue
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isinstance(current, (int, float))
            or isinstance(current, bool)
        ):
            return False
        if value >= 0 and current < value:
            return False
        if value < 0 and key == "cost" and "max" in target:
            if current - value > target["max"]:
                return False
    return True


def clamp_player_property(player_property: dict) -> None:
    hp = player_property["hp"]
    hp["max"] = max(0, hp["max"])
    hp["current"] = min(max(0, hp["current"]), hp["max"])
    player_property["gold"] = max(0, player_property["gold"])
    player_property["shield"] = max(0, player_property["shield"])
    player_property["capacity"] = max(0, player_property["capacity"])
    player_property["level"] = min(
        max(1, player_property["level"]), player_property["maxLevel"]
    )
    population = player_property["population"]
    population["max"] = max(0, population["max"])
    population["cost"] = min(max(0, population["cost"]), population["max"])


def collect_difficulty_buffs(theme_buffs: list, mode_grade: int) -> list[dict]:
    if not theme_buffs:
        return []
    max_grade = min(mode_grade, len(theme_buffs) - 1)
    disabled_grades = set()
    for grade in range(max_grade + 1):
        disabled_grades.update(theme_buffs[grade][1])

    result = []
    for grade in range(max_grade + 1):
        if grade not in disabled_grades:
            result.extend(deepcopy(theme_buffs[grade][0]))
    return result


def recruit_group_ticket_ids(
    theme: str, group_id: str, rng: Random | None = None
) -> list[str]:
    rng = rng or Random()
    if group_id == "recruit_group_random":
        melee = rng.choice(MELEE_PROFESSION_SUFFIXES)
        ranged = rng.choice(RANGED_PROFESSION_SUFFIXES)
        premium = rng.choice(
            [suffix for suffix in PROFESSION_SUFFIXES if suffix not in {melee, ranged}]
        )
        suffixes = [melee, ranged, premium]
    elif group_id.startswith("recruit_group_m"):
        suffixes = rng.sample(PROFESSION_SUFFIXES, 2)
    elif group_id in SPECIAL_RECRUIT_GROUPS:
        suffixes = SPECIAL_RECRUIT_GROUPS[group_id]
    else:
        try:
            suffixes = RECRUIT_GROUPS[group_id]
        except KeyError as exc:
            raise ValueError(f"unsupported recruit group: {group_id}") from exc
    ticket_ids = []
    for index, suffix in enumerate(suffixes):
        if group_id == "recruit_group_random" and index == 2:
            if theme in {"rogue_1", "rogue_2", "rogue_3"}:
                suffix = f"{suffix}_sp"
            elif theme == "rogue_4":
                suffix = f"{suffix}_vip"
            elif theme == "rogue_5":
                suffix = f"{suffix}_vip_init"
        elif theme == "rogue_5" and suffix in PROFESSION_SUFFIXES:
            suffix = f"{suffix}_init"
        ticket_ids.append(f"{theme}_recruit_ticket_{suffix}")
    return ticket_ids


def prepare_predefined_characters(
    candidates: list[dict], team_chars: list[dict]
) -> list[dict]:
    """Build the table-defined monthly squad from the player's operators."""
    result = []
    for team_char in team_chars:
        char_id = team_char["teamCharId"]
        template_id = team_char.get("teamTmplId")
        matches = [
            candidate
            for candidate in candidates
            if candidate["charId"] == char_id
            and (
                template_id is None
                or candidate.get("currentTmpl") == template_id
            )
        ]
        if not matches:
            template = f"/{template_id}" if template_id else ""
            raise ValueError(f"monthly squad operator is unavailable: {char_id}{template}")

        selected = deepcopy(
            max(
                matches,
                key=lambda char: (char["evolvePhase"], char["level"]),
            )
        )
        selected["instId"] = str(len(result) + 1)
        selected["type"] = "FREE"
        selected["population"] = 0
        selected["isUpgrade"] = False
        result.append(selected)
    return result


def battle_base_reward(theme: str, zone: int, node_type: int) -> tuple[int, int]:
    """Return the verified base EXP and gold for a normal or emergency battle."""
    if not isinstance(theme, str) or theme not in BATTLE_BASE_REWARDS:
        raise ValueError(f"unsupported roguelike theme: {theme}")
    if type(zone) is not int:
        raise ValueError(f"unsupported battle reward zone: {theme}/{zone}")
    if type(node_type) is not int or node_type not in {1, 2}:
        raise ValueError(f"unsupported battle reward node type: {node_type}")

    reward_zone = BATTLE_REWARD_ZONE_ALIASES.get((theme, zone), zone)
    zones = BATTLE_BASE_REWARDS[theme]
    if reward_zone < 1 or reward_zone > len(zones):
        raise ValueError(f"unsupported battle reward zone: {theme}/{zone}")
    return zones[reward_zone - 1][node_type - 1]


def battle_resource_item_ids(theme_data: dict) -> dict[str, str]:
    """Return table-defined battle resource IDs after validating their item types."""
    try:
        game_const = theme_data["gameConst"]
        items = theme_data["items"]
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid roguelike theme resource table") from exc
    if not isinstance(game_const, dict) or not isinstance(items, dict):
        raise ValueError("invalid roguelike theme resource table")

    resource_ids = {}
    for resource, expected_type in (("exp", "EXP"), ("gold", "GOLD")):
        item_id = game_const.get(f"{resource}ItemId")
        item_data = items.get(item_id)
        if (
            not isinstance(item_id, str)
            or not item_id
            or not isinstance(item_data, dict)
            or item_data.get("type") != expected_type
        ):
            raise ValueError(
                f"invalid roguelike {resource} item: {item_id}"
            )
        resource_ids[resource] = item_id
    return resource_ids


def enforce_emergency_node_limits(
    theme: str,
    zone: int,
    nodes: dict,
    normal_stages: list[str],
    elite_stages: list[str],
    rng: Random | None = None,
) -> None:
    """Apply the verified Mizuki emergency-node constraints in place."""
    if theme != "rogue_3" or not elite_stages:
        return

    rng = rng or Random()
    combat_nodes = [
        node
        for node in nodes.values()
        if not node.get("zone_end") and node.get("type") in {1, 2}
    ]
    emergency_nodes = [node for node in combat_nodes if node["type"] == 2]

    if zone == 1 and len(combat_nodes) >= 2 and not emergency_nodes:
        promoted = rng.choice(combat_nodes)
        promoted["type"] = 2
        promoted["stage"] = rng.choice(elite_stages)
        return

    limit = 1 if zone == 2 else 2 if 3 <= zone <= 6 else None
    if limit is None or len(emergency_nodes) <= limit or not normal_stages:
        return

    for node in rng.sample(emergency_nodes, len(emergency_nodes) - limit):
        node["type"] = 1
        node["stage"] = rng.choice(normal_stages)


def settle_battle_life(
    player_property: dict,
    run_buff: dict,
    theme: str,
    left_hp: int | None,
) -> dict[str, int]:
    """Reconcile battle life points with persistent HP and shields."""
    result = {"damage": 0, "hp": 0, "shield": 0}
    if left_hp is None:
        return result

    current_hp = player_property["hp"]["current"]
    protection = (
        int(run_buff.get("tmpHP", 0))
        if theme == "rogue_1"
        else int(player_property.get("shield", 0))
    )
    damage = max(0, current_hp + protection - max(0, int(left_hp)))
    protection_loss = min(protection, damage)
    hp_loss = min(current_hp, damage - protection_loss)

    if theme != "rogue_1":
        player_property["shield"] -= protection_loss
        result["shield"] = -protection_loss
    player_property["hp"]["current"] -= hp_loss
    player_property["conPerfectBattle"] = (
        player_property["conPerfectBattle"] + 1 if hp_loss == 0 else 0
    )
    clamp_player_property(player_property)
    result.update({"damage": damage, "hp": -hp_loss})
    return result


def prepare_recruit_candidates(
    candidates: list[dict],
    character_table: dict,
    ticket_data: dict,
    troop_chars: dict,
    rng: Random | None = None,
) -> list[dict]:
    """Filter a ticket's candidates and expose either recruit or upgrade entries."""
    allowed_professions = set(ticket_data["professionList"])
    allowed_rarities = set(ticket_data["rarityList"])
    extra_char_ids = set(ticket_data.get("extraCharIds", []))
    recruited_phase: dict[str, int] = {}
    for char in troop_chars.values():
        char_id = char["charId"]
        recruited_phase[char_id] = max(
            recruited_phase.get(char_id, -1), char["evolvePhase"]
        )

    variants: dict[tuple[str, Any], list[dict]] = {}
    for candidate in candidates:
        char_id = candidate["charId"]
        character = character_table.get(candidate.get("currentTmpl"))
        if character is None:
            character = character_table.get(char_id)
        if character is None:
            continue
        if char_id not in extra_char_ids and (
            character["profession"] not in allowed_professions
            or character["rarity"] not in allowed_rarities
        ):
            continue
        variant_key = (char_id, candidate.get("currentTmpl"))
        variants.setdefault(variant_key, []).append(candidate)

    result = []
    late_theme = ticket_data["id"].startswith(("rogue_4_", "rogue_5_"))
    recruit_cost = LATE_THEME_RECRUIT_COST if late_theme else RECRUIT_COST
    upgrade_cost = LATE_THEME_UPGRADE_COST if late_theme else UPGRADE_COST
    for (char_id, _), options in variants.items():
        existing_phase = recruited_phase.get(char_id)
        if existing_phase is None:
            selected = min(options, key=lambda char: char["evolvePhase"])
            is_upgrade = False
        else:
            upgrades = [
                char for char in options if char["evolvePhase"] > existing_phase
            ]
            if not upgrades:
                continue
            selected = max(upgrades, key=lambda char: char["evolvePhase"])
            is_upgrade = True

        selected = deepcopy(selected)
        selected_character = character_table.get(selected.get("currentTmpl"))
        if selected_character is None:
            selected_character = character_table[char_id]
        rarity = selected_character["rarity"]
        selected["isUpgrade"] = is_upgrade
        selected["population"] = (
            upgrade_cost[rarity] if is_upgrade else recruit_cost[rarity]
        )
        result.append(selected)

    result.sort(key=lambda char: (char["population"], char["charId"]))
    for index, char in enumerate(result):
        char["instId"] = str(index)

    free_rarities = set(ticket_data.get("extraFreeRarity", []))
    free_candidates = [
        char
        for char in result
        if (
            character_table.get(char.get("currentTmpl"))
            or character_table[char["charId"]]
        )["rarity"]
        in free_rarities
        and not char["isUpgrade"]
    ]
    if free_candidates:
        selected = (rng or Random()).choice(free_candidates)
        selected["type"] = "FREE"
        selected["population"] = 0

    return result


def _protocol_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping_values(value: Any) -> list[dict]:
    if isinstance(value, dict):
        values = value.values()
    elif isinstance(value, list):
        values = value
    else:
        return []
    return [item for item in values if isinstance(item, dict)]


def build_ending_result(
    run: dict, success: bool, end_ts: int
) -> dict[str, dict]:
    """Build the GAME_SETTLE payload represented by the current client model."""
    player = run.get("player") if isinstance(run, dict) else None
    player = player if isinstance(player, dict) else {}
    game = run.get("game") if isinstance(run, dict) else None
    game = game if isinstance(game, dict) else {}
    prop = player.get("property")
    prop = prop if isinstance(prop, dict) else {}
    cursor = player.get("cursor")
    cursor = cursor if isinstance(cursor, dict) else {}

    inventory = run.get("inventory") if isinstance(run, dict) else None
    inventory = inventory if isinstance(inventory, dict) else {}
    relics = _mapping_values(inventory.get("relic"))
    band = next(
        (
            item.get("id")
            for item in relics
            if isinstance(item.get("id"), str) and "_band_" in item["id"]
        ),
        None,
    )

    zone_id = None
    dungeon = run.get("map") if isinstance(run, dict) else None
    zones = dungeon.get("zones") if isinstance(dungeon, dict) else None
    if isinstance(zones, dict):
        zone = zones.get(str(cursor.get("zone")))
        if isinstance(zone, dict):
            zone_id = zone.get("id")

    buff = run.get("buff") if isinstance(run, dict) else None
    buff = buff if isinstance(buff, dict) else {}
    capsule = buff.get("capsule")
    capsule_ids = (
        [capsule["id"]]
        if isinstance(capsule, dict) and isinstance(capsule.get("id"), str)
        else []
    )

    troop = run.get("troop") if isinstance(run, dict) else None
    troop = troop if isinstance(troop, dict) else {}
    char_buffs = []
    for char in _mapping_values(troop.get("chars")):
        buffs = char.get("charBuff")
        if isinstance(buffs, list):
            char_buffs.extend(item for item in buffs if isinstance(item, str))

    module = run.get("module") if isinstance(run, dict) else None
    module = module if isinstance(module, dict) else {}
    totem = module.get("totem")
    totem_pieces = (
        _mapping_values(totem.get("totemPiece"))
        if isinstance(totem, dict)
        else []
    )
    fragment = module.get("fragment")
    fragments = (
        _mapping_values(fragment.get("fragments"))
        if isinstance(fragment, dict)
        else []
    )

    copper_counter: dict[str, int] = {}
    copper = module.get("copper")
    copper_items = (
        _mapping_values(copper.get("bag"))
        if isinstance(copper, dict)
        else []
    )
    for item in copper_items:
        item_id = item.get("id")
        if isinstance(item_id, str):
            copper_counter[item_id] = copper_counter.get(item_id, 0) + max(
                1, _protocol_int(item.get("count"), 1)
            )

    scrap_counter: dict[str, int] = {}
    scrap = module.get("scrap")
    scrap_items = (
        _mapping_values(scrap.get("inventory"))
        if isinstance(scrap, dict)
        else []
    )
    for item in scrap_items:
        item_id = item.get("id")
        if isinstance(item_id, str):
            scrap_counter[item_id] = scrap_counter.get(item_id, 0) + 1

    ending = player.get("toEnding") if success else None
    brief = {
        "level": _protocol_int(prop.get("level")),
        "success": int(bool(success)),
        "ending": ending,
        "failEnding": None,
        "theme": game.get("theme"),
        "mode": game.get("mode") or "NONE",
        "predefined": game.get("predefined"),
        "band": band,
        "startTs": _protocol_int(game.get("start")),
        "endTs": _protocol_int(end_ts),
        "endZoneId": zone_id,
        "modeGrade": _protocol_int(
            game.get("modeGrade", game.get("eGrade", 0))
        ),
        "seed": game.get("seed"),
        "activity": game.get("activity"),
    }
    squad_buffs = buff.get("squadBuff")
    squad_buffs = squad_buffs if isinstance(squad_buffs, list) else []
    record = {
        "cntZone": _protocol_int(cursor.get("zone")),
        "relicList": [
            item["id"] for item in relics if isinstance(item.get("id"), str)
        ],
        "capsuleList": capsule_ids,
        "activeToolList": [],
        "charBuff": char_buffs,
        "squadBuff": [
            item for item in squad_buffs if isinstance(item, str)
        ],
        "totemList": [
            item["id"]
            for item in totem_pieces
            if isinstance(item.get("id"), str)
        ],
        "exploreToolList": [
            item["id"]
            for item in _mapping_values(inventory.get("exploreTool"))
            if isinstance(item.get("id"), str)
        ],
        "fragmentList": [
            item["id"]
            for item in fragments
            if isinstance(item.get("id"), str)
        ],
        "copperCounter": copper_counter,
        "scrapCounter": scrap_counter,
        "legacyList": [],
    }
    return {"brief": brief, "record": record}


def queue_game_settlement(
    run: dict,
    success: bool,
    reason: str,
    end_ts: int,
) -> dict[str, dict]:
    """Move a finished run into the only terminal state understood by the client."""
    result = build_ending_result(run, success, end_ts)
    player = run["player"]
    player["state"] = "PENDING"
    player["pending"] = [
        {
            "type": "GAME_SETTLE",
            "content": {"result": deepcopy(result), "done": False},
        }
    ]
    player["trace"] = []
    status = player.get("status")
    if not isinstance(status, dict):
        status = {}
        player["status"] = status
    status.pop("gameResult", None)
    run["record"] = {
        "brief": deepcopy(result["brief"]),
        "record": deepcopy(result["record"]),
        "reason": reason,
    }
    return result


def normalize_current_run(run: dict, end_ts: int) -> bool:
    """Upgrade persisted response shapes that older server revisions emitted."""
    if not isinstance(run, dict):
        return False
    player = run.get("player")
    if not isinstance(player, dict):
        return False

    changed = False
    pending = player.get("pending")
    first_pending = (
        pending[0]
        if isinstance(pending, list)
        and pending
        and isinstance(pending[0], dict)
        else None
    )
    if isinstance(first_pending, dict) and first_pending.get("type") == "BATTLE_REWARD":
        content = first_pending.get("content")
        reward = content.get("battleReward") if isinstance(content, dict) else None
        if isinstance(reward, dict):
            if "state" not in reward:
                reward["state"] = 3
                changed = True
            if "isPerfect" not in reward:
                earn = reward.get("earn")
                hp_earn = earn.get("hp") if isinstance(earn, dict) else None
                reward["isPerfect"] = int(hp_earn == 0)
                changed = True
            if reward.get("show") == "1" or "show" not in reward:
                reward["show"] = None
                changed = True

    if isinstance(first_pending, dict) and first_pending.get("type") == "BATTLE":
        content = first_pending.get("content")
        battle = content.get("battle") if isinstance(content, dict) else None
        if isinstance(battle, dict) and battle.get("goldTrapCnt") == 100:
            battle["goldTrapCnt"] = GOPNIK_SPAWN_PERCENT
            changed = True

    status = player.get("status")
    game_result = status.get("gameResult") if isinstance(status, dict) else None
    if player.get("state") == "GAME_OVER":
        success = bool(
            game_result.get("success") if isinstance(game_result, dict) else False
        )
        reason = (
            game_result.get("reason", "LEGACY_GAME_OVER")
            if isinstance(game_result, dict)
            else "LEGACY_GAME_OVER"
        )
        queue_game_settlement(run, success, str(reason), end_ts)
        return True

    if isinstance(first_pending, dict) and first_pending.get("type") == "GAME_SETTLE":
        content = first_pending.get("content")
        content = content if isinstance(content, dict) else {}
        result = content.get("result")
        valid_result = (
            isinstance(result, dict)
            and isinstance(result.get("brief"), dict)
            and isinstance(result.get("record"), dict)
        )
        if not valid_result:
            success = bool(
                game_result.get("success")
                if isinstance(game_result, dict)
                else False
            )
            reason = (
                game_result.get("reason", "LEGACY_GAME_SETTLE")
                if isinstance(game_result, dict)
                else "LEGACY_GAME_SETTLE"
            )
            queue_game_settlement(run, success, str(reason), end_ts)
            return True
        if player.get("state") != "PENDING":
            player["state"] = "PENDING"
            changed = True
        if "done" not in content:
            content["done"] = False
            changed = True
        status = player.get("status")
        if isinstance(status, dict) and "gameResult" in status:
            status.pop("gameResult")
            changed = True

    return changed

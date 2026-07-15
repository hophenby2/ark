from flask import request
from copy import deepcopy
from collections import deque
from contextvars import ContextVar
from functools import wraps
from virtualtime import time
import random
import os
import re

from constants import (
    SYNC_DATA_TEMPLATE_PATH,
    RLV2_USER_SETTINGS_PATH,
    CONFIG_PATH,
    RLV2_SETTINGS_PATH,
)

from utils import read_json, decrypt_battle_data, writeLog, get_memory
from rlv2_logic import (
    apply_numeric_delta,
    apply_battle_reward_modifiers,
    battle_mimic_group_count,
    battle_base_reward,
    battle_resource_item_ids,
    build_ending_result,
    build_initial_property,
    clamp_player_property,
    clamp_sanity_module,
    collect_difficulty_buffs,
    enforce_emergency_node_limits,
    event_relic_pool_candidates,
    event_probability_succeeds,
    has_numeric_cost,
    normalize_current_run,
    prepare_recruit_candidates,
    prepare_predefined_characters,
    public_run_value,
    recruit_group_ticket_ids,
    sample_event_choices,
    select_weighted_event_branch,
    queue_game_settlement,
    resolve_player_levels,
    select_equivalent_grade,
    select_init_config,
    select_player_level_table,
    settle_battle_life,
    shop_item_pool_candidates,
)
from rlv2_ending_rules import (
    boss_ending_for_zone,
    build_route_plan,
    default_ending,
    ending_branch_reset_for_acquired_item,
    ending_for_acquired_item,
    ending_priority,
    is_overlay_ending,
    is_supported_ending,
    patch_current_boss,
    route_plan_is_valid,
    route_next_zone,
)
from rlv2_event_rules import (
    contextual_event_choices,
    fixed_scene_for_zone,
    runtime_event_rules,
)
from rlv2_repository import (
    InvalidUserIdError,
    LegacyMirrorError,
    MissingUserIdError,
    RunRepositoryError,
    empty_run,
    get_run_repository,
)
from rlv2_rules import (
    area_column_specs,
    area_layout,
    boss_stage_ids,
    event_scene_candidates,
    event_scene_is_repeatable,
    terminal_depth,
)
import data.rlv2_data


_ACTIVE_RUN_TRANSACTION = ContextVar("active_rlv2_transaction", default=None)


def _map_battle_mimic_count(
    server_seed: str | None,
    theme: str,
    stage_id: str,
    cursor: dict,
) -> int:
    position = cursor.get("position") or {}
    rng = random.Random(
        f"{server_seed}:gopnik:{theme}:{stage_id}:{cursor.get('zone')}:"
        f"{position.get('x')}:{position.get('y')}"
    )
    return battle_mimic_group_count(theme, stage_id, rng)


def _response_status(result) -> int:
    if isinstance(result, tuple) and len(result) >= 2:
        status = result[1]
        if isinstance(status, int):
            return status
    return 200


def _serialized_run(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if _ACTIVE_RUN_TRANSACTION.get() is not None:
            return func(*args, **kwargs)

        try:
            repository = get_run_repository()
            uid = repository.uid_from_headers(request.headers)
            result = None
            try:
                with repository.transaction(uid) as transaction:
                    token = _ACTIVE_RUN_TRANSACTION.set(transaction)
                    try:
                        result = func(*args, **kwargs)
                        if _response_status(result) < 400:
                            transaction.commit()
                    finally:
                        _ACTIVE_RUN_TRANSACTION.reset(token)
            except LegacyMirrorError as exc:
                writeLog(f"Roguelike legacy mirror update failed: {exc}")
            return public_run_value(result)
        except (MissingUserIdError, InvalidUserIdError) as exc:
            return {"error": str(exc)}, 400
        except RunRepositoryError as exc:
            writeLog(f"Roguelike repository error: {exc}")
            return {"error": "roguelike storage is unavailable"}, 503

    return wrapper


def _active_transaction():
    transaction = _ACTIVE_RUN_TRANSACTION.get()
    if transaction is None:
        raise RunRepositoryError("roguelike action has no active transaction")
    return transaction


def _load_run() -> dict:
    run = _active_transaction().run
    game = run.get("game") if isinstance(run, dict) else None
    theme = game.get("theme") if isinstance(game, dict) else None
    event_choices = get_memory("event_choices")
    choice_rules = runtime_event_rules(
        theme, event_choices.get(theme, {})
    ).get("choices", {})
    disabled_choice_ids = {
        choice_id
        for choice_id, rule in choice_rules.items()
        if isinstance(rule, dict) and rule.get("runtimeEnabled") is False
    }
    normalize_current_run(run, int(time()), disabled_choice_ids)
    return run


def _load_server_data() -> dict:
    return _active_transaction().server_data


def _persist_run(rlv2: dict, server_data: dict | None = None) -> None:
    transaction = _active_transaction()
    transaction.run = rlv2
    if server_data is not None:
        transaction.server_data = server_data


def _current_run_delta(rlv2: dict) -> dict:
    return {
        "playerDataDelta": {
            "modified": {"rlv2": {"current": public_run_value(rlv2)}},
            "deleted": {},
        },
        "pushMessage": [],
    }


def _recycle_active_seed(server_data: dict) -> None:
    seed = server_data.get("rlv2_seed")
    if seed is not None:
        seeds = deque(server_data.get("seed_list", []))
        seeds.appendleft(seed)
        server_data["seed_list"] = list(seeds)
    server_data["rlv2_seed"] = None


def _ending_result(rlv2: dict) -> dict:
    player = rlv2.get("player") if isinstance(rlv2, dict) else None
    pending = player.get("pending") if isinstance(player, dict) else None
    if (
        isinstance(pending, list)
        and pending
        and isinstance(pending[0], dict)
        and pending[0].get("type") == "GAME_SETTLE"
    ):
        content = pending[0].get("content")
        result = content.get("result") if isinstance(content, dict) else None
        if (
            isinstance(result, dict)
            and isinstance(result.get("brief"), dict)
            and isinstance(result.get("record"), dict)
        ):
            return deepcopy(result)

    record = rlv2.get("record") if isinstance(rlv2, dict) else None
    if (
        isinstance(record, dict)
        and isinstance(record.get("brief"), dict)
        and isinstance(record.get("record"), dict)
    ):
        return {
            "brief": deepcopy(record["brief"]),
            "record": deepcopy(record["record"]),
        }
    return build_ending_result(rlv2, False, int(time()))


def _zero_settlement_bp() -> dict:
    return {"cnt": 0.0, "from": 0, "to": 0}


def _settlement_game(rlv2: dict) -> dict:
    result = _ending_result(rlv2)
    ending_brief = result["brief"]
    ending_record = result["record"]
    mode = ending_brief.get("mode") or "NONE"

    month_team = None
    if mode == "MONTH_TEAM":
        month_team = {
            "bp": _zero_settlement_bp(),
            "gp": 0,
            "items": [],
            "mission": {"before": False, "complete": False, "process": []},
        }

    challenge = None
    if mode == "CHALLENGE":
        challenge = {
            "items": [],
            "before": False,
            "complete": False,
            "tasks": [],
            "score": 0,
            "isHighScore": False,
        }

    return {
        "brief": {
            "success": int(bool(ending_brief.get("success"))),
            "ending": ending_brief.get("ending"),
            "theme": ending_brief.get("theme"),
            "mode": mode,
            "band": ending_brief.get("band"),
            "level": int(ending_brief.get("level", 0) or 0),
        },
        "record": {
            "cntZone": int(ending_record.get("cntZone", 0) or 0),
            "cntBattle": int(ending_record.get("cntBattle", 0) or 0),
            "cntBattleElite": int(
                ending_record.get("cntBattleElite", 0) or 0
            ),
            "cntBattleBoss": int(ending_record.get("cntBattleBoss", 0) or 0),
            "cntArrivedNode": int(
                ending_record.get("cntArrivedNode", 0) or 0
            ),
            "cntRecruitChar": int(
                ending_record.get("cntRecruitChar", 0) or 0
            ),
            "cntUpgradeChar": int(
                ending_record.get("cntUpgradeChar", 0) or 0
            ),
        },
        "score": {
            "detail": [],
            "scoreFactor": 1.0,
            "score": 0.0,
            "buff": 0.0,
            "bp": _zero_settlement_bp(),
            "gp": 0,
            "accumulation": [],
        },
        "monthTeam": month_team,
        "challenge": challenge,
    }


def _settlement_outer() -> dict:
    return {
        "mission": {"before": [], "after": []},
        "missionBp": _zero_settlement_bp(),
        "relicBp": _zero_settlement_bp(),
        "totemBp": _zero_settlement_bp(),
        "fragmentBp": _zero_settlement_bp(),
        "copperBp": _zero_settlement_bp(),
        "relicUnlock": [],
        "totemUnlock": [],
        "fragmentUnlock": [],
        "copperUnlock": [],
        "scrapUnlock": [],
        "gp": 0,
        "spOperatorInfo": [],
        "items": [],
    }


def _game_settle_response(rlv2: dict, current: dict) -> dict:
    response = _current_run_delta(current)
    response["game"] = _settlement_game(rlv2)
    response["outer"] = _settlement_outer()
    return response


def _battle_finish_response(rlv2: dict) -> dict:
    response = _current_run_delta(rlv2)
    response.update(
        {
            "result": 0,
            "apFailReturn": 0,
            "itemReturn": [],
            "rewards": [],
            "unusualRewards": [],
            "overrideRewards": [],
            "additionalRewards": [],
            "diamondMaterialRewards": [],
            "furnitureRewards": [],
        }
    )
    return response


def _is_battle_victory(complete_state) -> bool:
    return complete_state in (2, 3)


def _is_game_settle_pending(player: dict) -> bool:
    pending = player.get("pending")
    return (
        isinstance(pending, list)
        and bool(pending)
        and isinstance(pending[0], dict)
        and pending[0].get("type") == "GAME_SETTLE"
    )


@_serialized_run
def rlv2GiveUpGame():
    server_data = _load_server_data()
    _recycle_active_seed(server_data)
    cleared_run = empty_run()
    _persist_run(cleared_run, server_data)
    result = _current_run_delta(cleared_run)
    result["result"] = "ok"
    return result


@_serialized_run
def rlv2FinishGame():
    rlv2 = _load_run()
    player = rlv2.get("player") if isinstance(rlv2, dict) else None
    if player is None:
        return _current_run_delta(empty_run())
    if not isinstance(player, dict):
        return {"error": "invalid roguelike run state"}, 409

    if _is_game_settle_pending(player):
        _persist_run(rlv2)
        return _current_run_delta(rlv2)
    return {"error": "the run is not ready for settlement"}, 409


@_serialized_run
def rlv2GameSettle():
    rlv2 = _load_run()
    player = rlv2.get("player") if isinstance(rlv2, dict) else None
    if player is None:
        cleared_run = empty_run()
        return _game_settle_response(cleared_run, cleared_run)
    if not isinstance(player, dict):
        return {"error": "invalid roguelike run state"}, 409
    if not _is_game_settle_pending(player):
        return {"error": "the run is not ready for settlement"}, 409

    cleared_run = empty_run()
    response = _game_settle_response(rlv2, cleared_run)
    server_data = _load_server_data()
    _recycle_active_seed(server_data)
    _persist_run(cleared_run, server_data)
    return response


@_serialized_run
def rlv2CreateGame():
    request_data = request.get_json()

    theme = request_data["theme"]
    mode = request_data["mode"]
    mode_grade = request_data["modeGrade"]
    predefined = request_data.get("predefined", request_data.get("predefinedId"))
    if isinstance(predefined, dict):
        predefined = predefined.get("id")

    rlv2_table = get_memory("roguelike_topic_table")
    try:
        init_config = select_init_config(
            rlv2_table, theme, mode, mode_grade, predefined
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400

    theme_data = rlv2_table["details"][theme]
    bands = init_config["initialBandRelic"] or []
    recruit_groups = init_config["initialRecruitGroup"] or []
    if mode == "CHALLENGE" and not recruit_groups:
        return {
            "error": (
                "this challenge requires a server-defined initial roster "
                f"that is unavailable: {predefined}"
            )
        }, 400

    ending = min(
        theme_data["endings"].values(),
        key=lambda item: item.get("priority", 999),
    )["id"]
    player_level_table, max_player_level = select_player_level_table(
        theme_data, mode, mode_grade, init_config["predefinedId"]
    )
    initial_property = build_initial_property(
        init_config, player_level_table, max_player_level
    )

    predefined_chars = []
    if mode == "MONTH_TEAM":
        month_squad = theme_data["monthSquad"].get(init_config["predefinedId"])
        if month_squad is None:
            return {"error": f"unknown monthly squad: {predefined}"}, 400
        try:
            predefined_chars = prepare_predefined_characters(
                _rlv2.getChars(), month_squad["teamChars"]
            )
        except ValueError as exc:
            return {"error": str(exc)}, 400

    total_steps = 1 + int(bool(recruit_groups)) + int(bool(recruit_groups))
    pending = [
        {
            "type": "GAME_INIT_RELIC",
            "content": {
                "initRelic": {
                    "step": [1, total_steps],
                    "items": {
                        str(i): {"id": band, "count": 1}
                        for i, band in enumerate(bands)
                    },
                }
            },
        }
    ]
    if recruit_groups:
        pending.extend(
            [
                {
                    "type": "GAME_INIT_RECRUIT_SET",
                    "content": {
                        "initRecruitSet": {
                            "step": [2, total_steps],
                            "option": recruit_groups,
                        }
                    },
                },
                {
                    "type": "GAME_INIT_RECRUIT",
                    "content": {
                        "initRecruit": {
                            "step": [3, total_steps],
                            "tickets": [],
                            "showChar": [],
                            "team": [char["instId"] for char in predefined_chars]
                            or None,
                        }
                    },
                },
            ]
        )

    rlv2 = {
        "_server": {
            "schemaVersion": 1,
            "events": {},
            "route": build_route_plan(theme, ending),
        },
        "player": {
            "state": "INIT",
            "property": initial_property,
            "cursor": {"zone": 0, "position": None},
            "trace": [],
            "pending": pending,
            "status": {"bankPut": 0},
            "toEnding": ending,
            "chgEnding": False,
        },
        "record": {"brief": None},
        "map": {"zones": {}},
        "troop": {
            "chars": {},
            "expedition": [],
            "expeditionReturn": None,
            "hasExpeditionReturn": False,
        },
        "inventory": {
            "relic": {},
            "recruit": {},
            "trap": None,
            "consumable": {},
            "exploreTool": {},
        },
        "game": {
            "mode": mode,
            "predefined": init_config["predefinedId"],
            "theme": theme,
            "outer": {"support": False},
            "start": time(),
            "eGrade": mode_grade,
            "equivalentGrade": select_equivalent_grade(
                rlv2_table, theme, mode, mode_grade
            ),
        },
        "buff": {"tmpHP": 0, "capsule": None, "squadBuff": []},
        "module": {
            "san": None,
            "dice": None,
            "totem": None,
            "vision": None,
            "chaos": None,
            "fragment": None,
            "disaster": None,
            "nodeUpgrade": None,
            "copper": None,
            "wrath": None,
            "candle": None,
            "sky": None
        }
    }

    for char in predefined_chars:
        rlv2["troop"]["chars"][char["instId"]] = char

    match theme:
        case "rogue_1":
            pass
        case "rogue_2":
            rlv2["module"]["san"] = {"sanity": 100}
            rlv2["module"]["dice"] = {"id": "", "count": 1}
        case "rogue_3":
            rlv2["module"]["totem"] = {"totemPiece": [], "predictTotemId": "rogue_3_totem_B_E2"}
            rlv2["module"]["vision"] = {"value": 3, "isMax": False}
            rlv2["module"]["chaos"] = {
                "value": 0,
                "level": 0,
                "curMaxValue": 4,
                "chaosList": [],
                "predict": "",
                "deltaChaos": {
                    "dValue": 0,
                    "preLevel": 0,
                    "afterLevel": 0,
                    "dChaos": []
                },
                "lastBattleGain": 0
            }
        case "rogue_4":
            rlv2["module"]["fragment"] = {
                "totalWeight": 0,
                "limitWeight": 3,
                "overWeight": 4,
                "fragments": {},
                "troopWeights": {}, # 转到 _rlv2.ro4_troopWeights_calculate() 处理
                "troopCarry": [],
                "sellCount": 0,
                "currInspiration": None
            }
            rlv2["module"]["disaster"] = {
                "curDisasterId": None,
                "disperseStep": 0
            }
            rlv2["module"]["nodeUpgrade"] = {
                "nodeTypeInfoMap": {
                    "REST": {
                        "tempUpgrade": "temp_update_3",
                        "upgradeList": []
                    },
                    "BATTLE_SHOP": {
                        "tempUpgrade": "temp_update_4",
                        "upgradeList": []
                    },
                    "ALCHEMY": {
                        "tempUpgrade": "temp_update_8",
                        "upgradeList": []
                    }
                }
            }
        case "rogue_5":
            rlv2["module"]["copper"] = None # 转到 _rlv2.ro5_drawCopper() 处理
            rlv2["module"]["wrath"] = {
                "wraths": [],
                "newWrath": -1
            }
            rlv2["module"]["sky"] = {"zones": {}}
        case _:
            pass

    initial_key = init_config.get("initialKey", 0)
    key_item_id = theme_data["gameConst"].get("keyItemId")
    if initial_key and key_item_id:
        rlv2["inventory"]["consumable"][key_item_id] = initial_key

    server_data = _load_server_data()
    if not server_data.get("rlv2_seed"):
        server_data["rlv2_seed"] = os.urandom(16).hex()
    _persist_run(rlv2, server_data)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2ChooseInitialRelic():
    request_data = request.get_json()
    select = request_data["select"]

    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "GAME_INIT_RELIC":
        return {"error": "initial relic selection is not pending"}, 409
    items = pending[0]["content"]["initRelic"]["items"]
    if str(select) not in items:
        return {"error": f"invalid initial relic: {select}"}, 400
    band = items[str(select)]["id"]
    rlv2["player"]["pending"].pop(0)
    _rlv2.add_item(rlv2, band)
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2SelectChoice():
    json_body = request.get_json()
    choice: str = json_body["choice"]
    rlv2 = _load_run()
    server_data = _load_server_data()
    rlv2_table = get_memory("roguelike_topic_table")
    event_choices = get_memory("event_choices")
    theme = rlv2["game"]["theme"]
    theme_events = runtime_event_rules(theme, event_choices.get(theme, {}))
    choice_rules = theme_events.get("choices", {})
    scene_rules = theme_events.get("sceneRules", {})
    pending = rlv2["player"]["pending"]
    if (
        rlv2["player"]["state"] != "PENDING"
        or not pending
        or pending[0].get("type") != "SCENE"
    ):
        return {"error": "scene choice is not pending"}, 409
    current_choices = pending[0]["content"]["scene"].get("choices", {})
    if not current_choices.get(choice):
        return {"error": f"choice is not available in the current scene: {choice}"}, 400

    choice_data = choice_rules.get(choice)
    if choice == "choice_leave" and choice_data is None:
        choice_data = {"choices": [], "lose": None, "get": None}
    table_choice = rlv2_table["details"][theme]["choices"].get(choice)
    if choice_data is None or table_choice is None:
        return {"error": f"invalid roguelike choice: {choice}"}, 400
    if choice_data.get("runtimeEnabled") is False:
        return {"error": f"roguelike choice is disabled: {choice}"}, 400

    cursor = rlv2["player"]["cursor"]
    rng = random.Random(
        f"{server_data.get('rlv2_seed')}_{theme}_{cursor['zone']}_"
        f"{cursor.get('position')}_{choice}"
    )

    def leave():
        rlv2["player"]["state"] = "WAIT_MOVE"
        _rlv2.finishNode(rlv2, server_data)

    def add_scene_event(scene_id: str, choices: list):
        choices = [
            choice_id
            for choice_id in choices
            if choice_id == "choice_leave"
            or choice_rules.get(choice_id, {}).get("runtimeEnabled") is not False
        ]
        choices = sample_event_choices(choices, scene_rules.get(scene_id), rng)
        if not choices:
            leave()
            return
        pending_event = {
            "type": "SCENE",
            "content": {
                "scene": {
                    "id": scene_id,
                    "choices": {},
                    "choiceAdditional": {}
                },
                "done": False,
                "popReport": False
            }
        }
        for choice_id in choices:
            available = choice_id == "choice_leave" or _rlv2.canPayChoice(
                rlv2,
                choice_rules.get(choice_id, {}),
            )
            pending_event["content"]["scene"]["choices"][choice_id] = available
            pending_event["content"]["scene"]["choiceAdditional"][choice_id] = {
                "rewards": []
            }
        if not any(pending_event["content"]["scene"]["choices"].values()):
            pending_event["content"]["scene"]["choices"]["choice_leave"] = True
            pending_event["content"]["scene"]["choiceAdditional"][
                "choice_leave"
            ] = {"rewards": []}
        rlv2["player"]["pending"].insert(0, pending_event)

    def resolve_item(item_pattern: str, curse: bool = False) -> str:
        item_ids = rlv2_table["details"][theme]["items"]
        if item_pattern in item_ids:
            candidates = [item_pattern]
        elif item_pattern in {
            f"{theme}_relic_",
            f"{theme}_relic_curse_",
        }:
            candidates = event_relic_pool_candidates(
                theme, item_ids, curse
            )
        elif item_pattern.endswith("_"):
            candidates = [
                item_id for item_id in item_ids if item_id.startswith(item_pattern)
            ]
        else:
            candidates = []
        if "_relic_" in item_pattern:
            candidates = [
                item_id
                for item_id in candidates
                if item_ids[item_id].get("type") == "RELIC"
            ]
        elif "_recruit_ticket_" in item_pattern:
            candidates = [
                item_id
                for item_id in candidates
                if item_ids[item_id].get("type") == "RECRUIT_TICKET"
            ]
        if (
            theme == "rogue_2"
            and "_relic_" in item_pattern
            and item_pattern not in {f"{theme}_relic_", f"{theme}_relic_curse_"}
        ):
            if curse:
                candidates = [item_id for item_id in candidates if "curse_" in item_id]
            else:
                candidates = [item_id for item_id in candidates if "curse_" not in item_id]
        if not candidates:
            raise ValueError(f"no item matches event reward: {item_pattern}")
        return rng.choice(candidates)

    created_tickets = []

    def add_event_item(item_id: str):
        result = _rlv2.add_item(rlv2, item_id)
        if isinstance(result, list):
            created_tickets.extend(result)

    def grant_event_items(item_spec):
        if isinstance(item_spec, str):
            item_id = resolve_item(item_spec, choice_data.get("curse", False))
            add_event_item(item_id)
        elif isinstance(item_spec, list):
            if item_spec:
                add_event_item(rng.choice(item_spec))
        elif isinstance(item_spec, int) and not isinstance(item_spec, bool):
            item_specs = choice_data.get("get_id", [])
            for item_info in item_specs[:item_spec]:
                item_id = resolve_item(
                    item_info["get"], item_info.get("curse", False)
                )
                add_event_item(item_id)

    try:
        probability_succeeded = (
            event_probability_succeeds(choice_data["probability"], rng)
            if "probability" in choice_data
            else True
        )
        selected_branch = (
            select_weighted_event_branch(choice_data["branches"], rng)
            if "branches" in choice_data
            else None
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400

    if not _rlv2.canPayChoice(rlv2, choice_data):
        return {"error": f"choice cost cannot be paid: {choice}"}, 400

    rlv2["player"]["pending"].pop(0)

    if choice == "choice_leave":
        leave()
    elif isinstance(choice_data.get("choices"), str):
        stage_id = choice_data["choices"]
        if stage_id.endswith("_"):
            stage_candidates = [
                candidate
                for candidate in rlv2_table["details"][theme]["stages"]
                if stage_id in candidate
            ]
            if not stage_candidates:
                return {"error": f"no stage matches event choice: {choice}"}, 400
            stage_id = rng.choice(stage_candidates)

        position = rlv2["player"]["cursor"]["position"]
        node_id = str(position["x"] * 100 + position["y"])
        zone = str(rlv2["player"]["cursor"]["zone"])
        rlv2["map"]["zones"][zone]["nodes"][node_id]["stage"] = stage_id
        event_battle_reward = choice_data.get("eventBattleReward")
        if isinstance(event_battle_reward, str):
            private = rlv2.setdefault("_server", {})
            events = private.setdefault("events", {})
            events["pendingBattleReward"] = {
                "choiceId": choice,
                "stageId": stage_id,
                "itemId": event_battle_reward,
                "required": choice_data.get("eventBattleRewardRequired") is True,
                "zone": int(zone),
                "nodeId": node_id,
            }
        rlv2["player"]["pending"].insert(
            0,
            {
                "type": "BATTLE",
                "content": {
                    "battle": {
                        "boxInfo": [],
                        "chestCnt": _map_battle_mimic_count(
                            server_data.get("rlv2_seed"),
                            theme,
                            stage_id,
                            rlv2["player"]["cursor"],
                        ),
                        "diceRoll": [],
                        "goldTrapCnt": 100,
                        "sanity": 0,
                        "state": 1,
                        "tmpChar": [],
                        "unKeepBuff": _rlv2.getBuffs(rlv2, stage_id),
                    },
                    "done": False,
                    "popReport": False,
                },
            },
        )
    else:
        for key, target, sign in (
            ("m_lose", rlv2["module"], -1),
            ("m_get", rlv2["module"], 1),
            ("i_lose", rlv2["inventory"]["consumable"], -1),
            ("i_get", rlv2["inventory"]["consumable"], 1),
        ):
            if choice_data.get(key):
                apply_numeric_delta(target, choice_data[key], sign)

        lose = choice_data.get("lose")
        if isinstance(lose, dict):
            apply_numeric_delta(rlv2["player"]["property"], lose, -1)
        elif isinstance(lose, str):
            _rlv2.remove_item(rlv2, lose)

        for property_key in choice_data.get("lose_all", []):
            rlv2["player"]["property"][property_key] = 0

        reward = choice_data.get("get") if probability_succeeded else None
        if isinstance(reward, dict):
            apply_numeric_delta(rlv2["player"]["property"], reward)
        elif reward is not None:
            grant_event_items(reward)
        get_all = choice_data.get("getAll", [])
        if isinstance(get_all, list):
            for item_id in get_all:
                if isinstance(item_id, str):
                    add_event_item(resolve_item(item_id))

        player_level_table, _ = select_player_level_table(
            rlv2_table["details"][theme],
            rlv2["game"]["mode"],
            rlv2["game"]["eGrade"],
            rlv2["game"].get("predefined"),
        )
        resolve_player_levels(rlv2["player"]["property"], player_level_table)
        clamp_player_property(rlv2["player"]["property"])
        clamp_sanity_module(rlv2["module"])
        if rlv2["player"]["property"]["hp"]["current"] <= 0:
            _rlv2.endRun(rlv2, False, "LIFE_POINT_ZERO")
        elif selected_branch is not None:
            add_scene_event(
                selected_branch["scene"], selected_branch["choices"]
            )
        else:
            scene_id = table_choice["nextSceneId"]
            if scene_id is None:
                leave()
            else:
                add_scene_event(scene_id, choice_data.get("choices", []))

    if created_tickets and not _is_game_settle_pending(rlv2["player"]):
        for ticket_id in reversed(created_tickets):
            _rlv2.activateTicket(rlv2, ticket_id)
        rlv2["player"]["state"] = "PENDING"

    _persist_run(rlv2, server_data)

    return {
        "playerDataDelta": {
            "modified": {"rlv2": {"current": rlv2}},
            "deleted": {},
        }
    }


@_serialized_run
def rlv2ChooseInitialRecruitSet():
    request_data = request.get_json() or {}
    rlv2 = _load_run()
    player_pending = rlv2["player"]["pending"]
    if not player_pending or player_pending[0].get("type") != "GAME_INIT_RECRUIT_SET":
        return {"error": "initial recruit set selection is not pending"}, 409
    pending = player_pending[0]["content"]["initRecruitSet"]
    if not pending["option"]:
        return {"error": "this run has no initial recruit group"}, 409
    selected_group = request_data.get("select")
    if isinstance(selected_group, int):
        if selected_group < 0 or selected_group >= len(pending["option"]):
            return {"error": f"invalid initial recruit group: {selected_group}"}, 400
        selected_group = pending["option"][selected_group]
    if selected_group is None:
        selected_group = pending["option"][0]
    if selected_group not in pending["option"]:
        return {"error": f"invalid initial recruit group: {selected_group}"}, 400
    rlv2["player"]["pending"].pop(0)

    theme = rlv2["game"]["theme"]
    server_data = _load_server_data()
    rng = random.Random(
        f"{server_data.get('rlv2_seed')}_{theme}_{selected_group}"
    )
    try:
        ticket_item_ids = recruit_group_ticket_ids(theme, selected_group, rng)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    ticket_table = get_memory("roguelike_topic_table")["details"][theme][
        "recruitTickets"
    ]

    for ticket_item_id in ticket_item_ids:
        if ticket_item_id not in ticket_table:
            return {"error": f"unknown initial recruit ticket: {ticket_item_id}"}, 500
        ticket_id = _rlv2.getNextTicketIndex(rlv2)
        _rlv2.addTicket(rlv2, ticket_id, ticket_item_id)
        rlv2["player"]["pending"][0]["content"]["initRecruit"]["tickets"].append(
            ticket_id
        )

    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data



@_serialized_run
def rlv2ActiveRecruitTicket():
    request_data = request.get_json()
    ticket_id = request_data["id"]

    rlv2 = _load_run()
    ticket = rlv2["inventory"]["recruit"].get(ticket_id)
    if ticket is None or ticket["state"] != 0:
        return {"error": f"recruit ticket is unavailable: {ticket_id}"}, 400
    pending = rlv2["player"]["pending"]
    if (
        not pending
        or pending[0].get("type") != "GAME_INIT_RECRUIT"
        or ticket_id not in pending[0]["content"]["initRecruit"]["tickets"]
    ):
        return {"error": "recruit ticket cannot be activated in this context"}, 409
    _rlv2.activateTicket(rlv2, ticket_id)
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


def getNextCharId(rlv2):
    config = read_json(CONFIG_PATH)
    if not config["rlv2Config"]["allChars"]:
        i = 1
    else:
        i = 10000
    while str(i) in rlv2["troop"]["chars"]:
        i += 1
    return str(i)


@_serialized_run
def rlv2RecruitChar():
    request_data = request.get_json()
    ticket_id = request_data["ticketIndex"]
    option_id = int(request_data["optionId"])

    rlv2 = _load_run()
    ticket = rlv2["inventory"]["recruit"].get(ticket_id)
    if ticket is None or ticket["state"] != 1:
        return {"error": f"recruit ticket is not active: {ticket_id}"}, 400
    if option_id < 0:
        return {"error": f"invalid recruit option: {option_id}"}, 400
    try:
        char = deepcopy(ticket["list"][option_id])
    except IndexError:
        return {"error": f"invalid recruit option: {option_id}"}, 400

    population = rlv2["player"]["property"]["population"]
    recruit_cost = int(char.get("population", 0))
    if recruit_cost > population["max"] - population["cost"]:
        return {"error": "not enough hope for recruit"}, 400

    if char.get("isUpgrade"):
        char_id = next(
            (
                inst_id
                for inst_id, recruited in rlv2["troop"]["chars"].items()
                if recruited["charId"] == char["charId"]
                and recruited["evolvePhase"] < char["evolvePhase"]
            ),
            None,
        )
        if char_id is None:
            return {"error": "recruit upgrade target is missing"}, 400
    else:
        char_id = getNextCharId(rlv2)

    pending = rlv2["player"]["pending"]
    if (
        not pending
        or pending[0].get("type") != "RECRUIT"
        or pending[0]["content"]["recruit"]["ticket"] != ticket_id
    ):
        return {"error": "recruit selection is not pending"}, 409
    population["cost"] += recruit_cost
    pending.pop(0)
    if not pending:
        rlv2["player"]["state"] = "WAIT_MOVE"
    char["instId"] = char_id
    rlv2["inventory"]["recruit"][ticket_id]["state"] = 2
    rlv2["inventory"]["recruit"][ticket_id]["list"] = []
    rlv2["inventory"]["recruit"][ticket_id]["result"] = char
    rlv2["troop"]["chars"][char_id] = char
    _persist_run(rlv2)

    data = {
        "chars": [char],
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        },
    }

    return data


@_serialized_run
def rlv2CloseRecruitTicket():
    request_data = request.get_json()
    ticket_id = request_data["id"]

    rlv2 = _load_run()
    ticket = rlv2["inventory"]["recruit"].get(ticket_id)
    pending = rlv2["player"]["pending"]
    if (
        ticket is None
        or ticket["state"] != 1
        or not pending
        or pending[0].get("type") != "RECRUIT"
        or pending[0]["content"]["recruit"]["ticket"] != ticket_id
    ):
        return {"error": f"recruit ticket is not active: {ticket_id}"}, 400
    pending.pop(0)
    if not pending:
        rlv2["player"]["state"] = "WAIT_MOVE"
    rlv2["inventory"]["recruit"][ticket_id]["state"] = 2
    rlv2["inventory"]["recruit"][ticket_id]["list"] = []
    rlv2["inventory"]["recruit"][ticket_id]["result"] = None
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2FinishEvent():
    server_data = _load_server_data()
    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if rlv2["player"]["state"] != "INIT":
        return {"error": "initialization is not active"}, 409
    if pending:
        if len(pending) != 1 or pending[0].get("type") != "GAME_INIT_RECRUIT":
            return {"error": "initial selections are not complete"}, 409
        ticket_ids = pending[0]["content"]["initRecruit"]["tickets"]
        if any(
            rlv2["inventory"]["recruit"].get(ticket_id, {}).get("state") != 2
            for ticket_id in ticket_ids
        ):
            return {"error": "initial recruit tickets are not complete"}, 409
    rlv2["player"]["state"] = "WAIT_MOVE"
    rlv2["player"]["cursor"]["zone"] = 1
    rlv2["player"]["pending"] = []
    theme = rlv2["game"]["theme"]

    # 可用节点类型测试用
    if theme == "rogue_0":
        zone = theme.split("_")[1]
        rlv2["map"]["zones"] = data.rlv2_data.test_data(zone)
    else:
        # too large, do not send it every time
        # rlv2["map"]["zones"] = _rlv2.getMap(theme)
        rlv2["map"]["zones"], seed = _rlv2.getMap_new(
            theme,
            server_data["rlv2_seed"],
            rlv2["player"]["cursor"]["zone"],
            rlv2["player"].get("toEnding"),
        )
        server_data["rlv2_seed"] = seed
        
        match theme:
            case "rogue_4":
                troopWeights = _rlv2.ro4_troopWeights_calculate(rlv2)
                rlv2["module"]["fragment"]["troopWeights"] = troopWeights
            case "rogue_5":
                coppper_bag, drawn_list = _rlv2.ro5_drawCopper(seed)
                rlv2["player"]["state"] = "PENDING"
                rlv2["module"]["copper"] = {}
                rlv2["module"]["copper"]["bag"] = {}
                rlv2["module"]["copper"]["bag"] = coppper_bag
                rlv2["module"]["copper"]["redrawCost"] = 0
                rlv2["player"]["pending"].insert(
                    0,
                    {
                        "type": "DRAW_COPPER",
                        "content": {
                            "drawCopper": {
                                "copper": drawn_list,
                                "divineEventId": "rogue_5_levelEVE_2"
                            }, 
                            "done": False
                        }
                    }
                )

            case _:
                pass

    _persist_run(rlv2, server_data)

    result = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return result


@_serialized_run
def rlv2MoveAndBattleStart():
    request_data = request.get_json()
    stage_id = request_data["stageId"]

    rlv2 = _load_run()
    previous_cursor = deepcopy(rlv2["player"]["cursor"])
    if request_data["to"] is not None:
        if rlv2["player"]["state"] != "WAIT_MOVE" or rlv2["player"]["pending"]:
            return {"error": "the run is not waiting for a map move"}, 409
        zone_nodes = rlv2["map"]["zones"][str(previous_cursor["zone"])]["nodes"]
        target = request_data["to"]
        target_id = str(target["x"] * 100 + target["y"])
        target_node = zone_nodes.get(target_id)
        route_edge = None
        if target_node is None or target_node.get("stage") != stage_id:
            return {"error": "battle target does not match the generated map"}, 400
        if target_node.get("type") not in {1, 2, 4}:
            return {"error": "target node is not a battle node"}, 400
        if previous_cursor["position"] is not None:
            current_id = str(
                previous_cursor["position"]["x"] * 100
                + previous_cursor["position"]["y"]
            )
            route_edge = next(
                (
                    edge
                    for edge in zone_nodes[current_id].get("next", [])
                    if edge["x"] == target["x"] and edge["y"] == target["y"]
                ),
                None,
            )
            if route_edge is None:
                return {"error": "battle target is not reachable"}, 400
        elif target["x"] != 0:
            return {"error": "the first battle node must be in the first column"}, 400
        if target_node.get("visited"):
            return {"error": "battle node was already visited"}, 409
        if route_edge is not None and not _rlv2.unlockRoute(rlv2, route_edge):
            return {"error": "not enough resources to unlock this route"}, 400
        target_node["visited"] = True
    else:
        pending = rlv2["player"]["pending"]
        if (
            rlv2["player"]["state"] != "PENDING"
            or not pending
            or pending[0].get("type") != "BATTLE"
        ):
            return {"error": "event battle is not pending"}, 409
        cursor = previous_cursor.get("position")
        if cursor is None:
            return {"error": "event battle has no current map node"}, 409
        current_node = rlv2["map"]["zones"][str(previous_cursor["zone"])][
            "nodes"
        ].get(str(cursor["x"] * 100 + cursor["y"]))
        if current_node is None or current_node.get("stage") != stage_id:
            return {"error": "event battle stage does not match the current node"}, 400
    rlv2["player"]["state"] = "PENDING"
    can_box = False
    box_info = {}
    if request_data["to"] is not None:
        x = request_data["to"]["x"]
        y = request_data["to"]["y"]
        rlv2["player"]["cursor"]["position"] = {"x": x, "y": y}
        can_box = True
    else:
        rlv2["player"]["pending"].pop(0)
    rlv2["player"]["trace"].append(previous_cursor)
    buffs = _rlv2.getBuffs(rlv2, stage_id)
    theme = rlv2["game"]["theme"]
    server_data = _load_server_data()
    rng = random.Random(
        f"{server_data.get('rlv2_seed')}_{theme}_{stage_id}_"
        f"{rlv2['player']['cursor']}"
    )
    if can_box:
        game_const = get_memory("roguelike_topic_table")["details"][theme][
            "gameConst"
        ]
        box_ids = [
            game_const.get("normBoxTrapId"),
            game_const.get("rareBoxTrapId"),
            game_const.get("badBoxTrapId"),
        ]
        box_ids = [box_id for box_id in box_ids if box_id]
        if box_ids:
            box_info = {rng.choice(box_ids): 100}
    dice_roll = []
    if theme == "rogue_2":
        dice_upgrade_count = 0
        first_relic = rlv2["inventory"]["relic"].get("r_0")
        band = first_relic["id"] if first_relic else ""
        if (
            band == "rogue_2_band_16"
            or band == "rogue_2_band_17"
            or band == "rogue_2_band_18"
        ):
            dice_upgrade_count += 1
        for i in rlv2["inventory"]["relic"]:
            if rlv2["inventory"]["relic"][i]["id"] == "rogue_2_relic_grace_63":
                dice_upgrade_count += 1
        if dice_upgrade_count == 0:
            dice_face_count = 6
            dice_id = "trap_067_dice"
        elif dice_upgrade_count == 1:
            dice_face_count = 8
            dice_id = "trap_088_dice2"
        else:
            dice_face_count = 12
            dice_id = "trap_089_dice3"
        dice_roll = [rng.randint(1, dice_face_count) for i in range(100)]
        buffs.append(
            {
                "key": "misc_insert_token_card",
                "blackboard": [
                    {"key": "token_key", "value": 0, "valueStr": dice_id},
                    {"key": "level", "value": 1, "valueStr": None},
                    {"key": "skill", "value": 0, "valueStr": None},
                    {"key": "cnt", "value": 100, "valueStr": None},
                ],
            }
        )
    rlv2["player"]["pending"].insert(
        0,
        {
            "type": "BATTLE",
            "content": {
                "battle": {
                    "state": 1,
                    "chestCnt": _map_battle_mimic_count(
                        server_data.get("rlv2_seed"),
                        theme,
                        stage_id,
                        rlv2["player"]["cursor"],
                    ),
                    "goldTrapCnt": 100,
                    "diceRoll": dice_roll,
                    "boxInfo": box_info,
                    "tmpChar": [],
                    "sanity": 0,
                    "unKeepBuff": buffs,
                },
                "done": False,
                "popReport": False
            }
        }
    )
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": {
                        "player": rlv2["player"]
                    },
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2BattleFinish():
    request_data = request.get_json()
    battle_data = decrypt_battle_data(request_data["data"])

    if "completeState" not in battle_data:
        return {"error": "invalid encrypted battle result"}, 400

    rlv2 = _load_run()
    player = rlv2.get("player") if isinstance(rlv2, dict) else None
    if not isinstance(player, dict):
        return {"error": "battle result is not pending"}, 409
    pending = player.get("pending")
    if not pending or pending[0].get("type") != "BATTLE":
        complete_state = battle_data.get("completeState")
        repeated_success = (
            _is_battle_victory(complete_state)
            and isinstance(pending, list)
            and bool(pending)
            and isinstance(pending[0], dict)
            and pending[0].get("type") == "BATTLE_REWARD"
        )
        repeated_abort = (
            not _is_battle_victory(complete_state)
            and _is_game_settle_pending(player)
            and not bool(
                player["pending"][0]["content"]["result"]["brief"].get(
                    "success"
                )
            )
        )
        if repeated_success or repeated_abort:
            return _battle_finish_response(rlv2)
        return {"error": "battle result is not pending"}, 409

    theme = rlv2["game"]["theme"]
    if _is_battle_victory(battle_data.get("completeState")):
        stats = battle_data.get("battleData", {}).get("stats", {})
        if not isinstance(stats.get("leftHp"), (int, float)):
            return {"error": "successful battle result is missing leftHp"}, 400
        life_earn = settle_battle_life(
            rlv2["player"]["property"],
            rlv2["buff"],
            theme,
            stats.get("leftHp"),
        )
        rlv2["player"]["pending"].pop(0)
        rlv2_table = get_memory("roguelike_topic_table")
        theme_data = rlv2_table["details"][theme]
        cursor = rlv2["player"]["cursor"]
        node_id = str(cursor["position"]["x"] * 100 + cursor["position"]["y"])
        zone = rlv2["map"]["zones"][str(cursor["zone"])]
        node = zone["nodes"][node_id]
        node_type = node.get("type")
        perfect_battle = bool(
            battle_data["completeState"] == 3 and life_earn["hp"] == 0
        )
        for relic in rlv2["inventory"]["relic"].values():
            relic_data = theme_data.get("relics", {}).get(relic.get("id"), {})
            for buff in relic_data.get("buffs", []):
                key = buff.get("key")
                if key == "gain_on_perfect" and not perfect_battle:
                    continue
                if key not in {"battle_extra_reward", "gain_on_perfect"}:
                    continue
                blackboard = {
                    entry.get("key"): entry
                    for entry in buff.get("blackboard", [])
                    if isinstance(entry, dict)
                }
                item_id = blackboard.get("id", {}).get("valueStr")
                count = int(blackboard.get("count", {}).get("value", 0))
                if isinstance(item_id, str):
                    _rlv2.grant_resource(rlv2, item_id, count)
        clamp_sanity_module(rlv2["module"])
        if rlv2["player"]["property"]["hp"]["current"] <= 0:
            _rlv2.endRun(rlv2, False, "LIFE_POINT_ZERO")
            _persist_run(rlv2)
            return _battle_finish_response(rlv2)
        exp_gain = 0
        gold_gain = 0
        resource_ids = None
        is_standard_zone = zone.get("id") == f"zone_{cursor['zone']}"
        # Boss, portal, and event-battle rewards have separate conditional rules.
        if node_type in {1, 2} and is_standard_zone:
            try:
                exp_gain, gold_gain = battle_base_reward(
                    theme, cursor["zone"], node_type
                )
                resource_ids = battle_resource_item_ids(theme_data)
            except ValueError as exc:
                return {"error": str(exc)}, 500
            exp_gain = apply_battle_reward_modifiers(
                exp_gain,
                resource_ids["exp"],
                rlv2["inventory"]["relic"],
                theme_data.get("relics", {}),
            )
            gold_gain = apply_battle_reward_modifiers(
                gold_gain,
                resource_ids["gold"],
                rlv2["inventory"]["relic"],
                theme_data.get("relics", {}),
            )
            if not _rlv2.grant_resource(
                rlv2, resource_ids["exp"], exp_gain
            ):
                return {"error": "failed to grant roguelike battle EXP"}, 500
        player_level_table, _ = select_player_level_table(
            theme_data,
            rlv2["game"]["mode"],
            rlv2["game"]["eGrade"],
            rlv2["game"].get("predefined"),
        )
        level_earn = resolve_player_levels(
            rlv2["player"]["property"], player_level_table
        )
        ticket = f"{theme}_recruit_ticket_all"
        rewards = []
        if gold_gain:
            rewards.append(
                {
                    "index": "0",
                    "items": [
                        {
                            "sub": 0,
                            "id": resource_ids["gold"],
                            "count": gold_gain,
                        }
                    ],
                    "done": False,
                }
            )
        special_rewards = {}
        private_events = rlv2.get("_server", {}).get("events", {})
        pending_event_reward = private_events.get("pendingBattleReward")
        if (
            isinstance(pending_event_reward, dict)
            and pending_event_reward.get("stageId") == node.get("stage")
            and pending_event_reward.get("zone") == cursor["zone"]
            and pending_event_reward.get("nodeId") == node_id
        ):
            item_id = pending_event_reward.get("itemId")
            if isinstance(item_id, str):
                special_rewards[item_id] = (
                    pending_event_reward.get("required") is True
                )
            private_events.pop("pendingBattleReward", None)

        if (
            theme == "rogue_1"
            and cursor["zone"] == 3
            and node_type == 4
            and _rlv2.hasItem(rlv2, "rogue_1_relic_m19")
            and not _rlv2.hasItem(rlv2, "rogue_1_relic_m20")
        ):
            special_rewards.setdefault("rogue_1_relic_m20", False)

        game_const = theme_data.get("gameConst", {})
        special_trap_id = game_const.get("specialTrapId")
        trap_reward_relic_id = game_const.get("trapRewardRelicId")
        extra_battle_info = stats.get("extraBattleInfo", {})
        knight_killed = (
            extra_battle_info.get(f"SIMPLE,{special_trap_id},killed")
            if isinstance(extra_battle_info, dict)
            and isinstance(special_trap_id, str)
            else None
        )
        if (
            theme == "rogue_2"
            and isinstance(trap_reward_relic_id, str)
            and isinstance(knight_killed, (int, float))
            and not isinstance(knight_killed, bool)
            and knight_killed > 0
            and _rlv2.hasItem(rlv2, "rogue_2_relic_grace_83")
            and not _rlv2.hasItem(rlv2, trap_reward_relic_id)
        ):
            special_rewards[trap_reward_relic_id] = True

        required_reward_indexes = []
        for item_id, required in special_rewards.items():
            if item_id not in theme_data["items"]:
                return {"error": f"unknown event battle reward: {item_id}"}, 500
            reward_index = str(len(rewards))
            rewards.append(
                {
                    "index": reward_index,
                    "items": [{"sub": 0, "id": item_id, "count": 1}],
                    "done": False,
                }
            )
            if required:
                required_reward_indexes.append(reward_index)
        if required_reward_indexes:
            private_events["requiredBattleRewardIndexes"] = required_reward_indexes
        else:
            private_events.pop("requiredBattleRewardIndexes", None)
        rewards.append(
            {
                "index": str(len(rewards)),
                "items": [{"sub": 0, "id": ticket, "count": 1}],
                "done": False,
            }
        )
        rlv2["player"]["pending"].insert(
            0,
            {
                "type": "BATTLE_REWARD",
                "content": {
                    "battleReward": {
                        "earn": {
                            "exp": exp_gain,
                            "populationMax": level_earn["populationMax"],
                            "squadCapacity": level_earn["squadCapacity"],
                            "hp": life_earn["hp"],
                            "shield": life_earn["shield"],
                            "maxHpUp": level_earn["maxHpUp"],
                        },
                        "rewards": rewards,
                        "show": None,
                        "state": int(battle_data["completeState"]),
                        "isPerfect": int(
                            battle_data["completeState"] == 3
                            and life_earn["hp"] == 0
                        ),
                    }
                },
            },
        )
    else:
        _rlv2.endRun(rlv2, False, "BATTLE_ABORTED")
    _persist_run(rlv2)

    return _battle_finish_response(rlv2)


@_serialized_run
def rlv2FinishBattleReward():
    server_data = _load_server_data()
    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "BATTLE_REWARD":
        return {"error": "battle reward settlement is not pending"}, 409
    rewards = pending[0]["content"]["battleReward"].get("rewards", [])
    private_events = rlv2.get("_server", {}).get("events", {})
    required_indexes = (
        private_events.get("requiredBattleRewardIndexes", [])
        if isinstance(private_events, dict)
        else []
    )
    required_indexes = {
        str(index)
        for index in required_indexes
        if isinstance(index, (str, int)) and not isinstance(index, bool)
    }
    has_unclaimed_required_reward = any(
        not reward.get("done")
        and str(reward.get("index")) in required_indexes
        for reward in rewards
    )
    if has_unclaimed_required_reward:
        return {"error": "required event battle reward must be claimed first"}, 409
    if isinstance(private_events, dict):
        private_events.pop("requiredBattleRewardIndexes", None)
    rlv2["player"]["state"] = "WAIT_MOVE"
    rlv2["player"]["pending"] = []
    if rlv2["player"]["trace"]:
        rlv2["player"]["trace"].pop()
    _rlv2.finishNode(rlv2, server_data)
    _persist_run(rlv2, server_data)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2MoveTo():
    request_data = request.get_json()
    x = request_data["to"]["x"]
    y = request_data["to"]["y"]

    server_data = _load_server_data()
    rlv2 = _load_run()
    rlv2_table = get_memory("roguelike_topic_table")
    event_choices = get_memory("event_choices")
    cursor = rlv2["player"]["cursor"]
    if rlv2["player"]["state"] != "WAIT_MOVE" or rlv2["player"]["pending"]:
        return {"error": "the run is not waiting for a map move"}, 409
    zone_nodes = rlv2["map"]["zones"][str(cursor["zone"])]["nodes"]
    node_id = str(x * 100 + y)
    target_node = zone_nodes.get(node_id)
    if target_node is None:
        return {"error": "target node does not exist"}, 400
    if target_node.get("type") in {1, 2, 4} or target_node.get("stage"):
        return {"error": "battle nodes must use moveAndBattleStart"}, 400
    if target_node.get("visited"):
        return {"error": "target node was already visited"}, 409
    if cursor["position"] is None:
        route_edge = None
        if x != 0:
            return {"error": "the first node must be in the first column"}, 400
    else:
        current_id = str(cursor["position"]["x"] * 100 + cursor["position"]["y"])
        route_edge = next(
            (
                edge
                for edge in zone_nodes[current_id].get("next", [])
                if edge["x"] == x and edge["y"] == y
            ),
            None,
        )
        if route_edge is None:
            return {"error": "target node is not reachable"}, 400

    if route_edge is not None and not _rlv2.unlockRoute(rlv2, route_edge):
        return {"error": "not enough resources to unlock this route"}, 400

    rlv2["player"]["state"] = "PENDING"
    cursor["position"] = {"x": x, "y": y}
    target_node["visited"] = True
    theme = rlv2["game"]["theme"]
    randomseed = server_data["rlv2_seed"]
    zone = rlv2["player"]["cursor"]["zone"]
    rng = random.Random(f"{randomseed}_{zone}_{theme}_{x}{y}")

    def getGoods():
        ticket = f"{theme}_recruit_ticket_all"
        price_id = f"{theme}_gold"
        theme_data = rlv2_table["details"][theme]
        item_pool = list(theme_data["archiveComp"]["relic"]["relic"])
        item_pool += list(theme_data["archiveComp"]["trap"]["trap"])
        item_pool = shop_item_pool_candidates(
            theme, list(dict.fromkeys(item_pool))
        )
        sampled_items = rng.sample(item_pool, min(5, len(item_pool)))
        shop_items = [ticket, *sampled_items]
        rarity_price = {"NORMAL": 8, "RARE": 12, "SUPER_RARE": 16}
        goods = []
        for index, item_id in enumerate(shop_items):
            item_data = theme_data["items"][item_id]
            if item_id == "rogue_3_relic_boss_4a":
                price = 1
            else:
                price = (
                    4
                    if item_data["type"] == "RECRUIT_TICKET"
                    else rarity_price.get(item_data["rarity"], 8)
                )
            goods.append(
                {
                    "index": str(index),
                    "itemId": item_id,
                    "count": 1,
                    "priceId": price_id,
                    "priceCount": price,
                    "origCost": price,
                    "displayPriceChg": False,
                    "_retainDiscount": 1,
                }
            )
        return goods
        
    zone = str(rlv2["player"]["cursor"]["zone"])
    node_type:int = rlv2["map"]["zones"][zone]["nodes"][node_id]["type"]
    match node_type:
        case 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048 | 8192 | 16384 | 32768 | 65536 | 262144 | 524288 | 1048576:
            choices = {}
            choiceAdditional = {}
            theme_events = runtime_event_rules(
                theme, event_choices.get(theme, {})
            )
            choice_rules = theme_events.get("choices", {})
            scene_rules = theme_events.get("sceneRules", {})
            raw_enter_scenes = theme_events.get("enter", {})
            table_choices = rlv2_table["details"][theme]["choices"]

            def executable_entry(scene_id, choice_ids):
                scene_rule = scene_rules.get(scene_id, {})
                if (
                    not isinstance(choice_ids, list)
                    or not choice_ids
                    or scene_rule.get("runtimeEnabled") is False
                ):
                    return None
                enabled = [
                    choice_id
                    for choice_id in choice_ids
                    if choice_rules.get(choice_id, {}).get("runtimeEnabled")
                    is not False
                ]
                if not enabled or not all(
                    choice_id in choice_rules and choice_id in table_choices
                    for choice_id in enabled
                ):
                    return None
                requirement = scene_rule.get("require")
                if requirement is not None and not _rlv2.canPayChoice(
                    rlv2, {"require": requirement}
                ):
                    return None
                enabled = contextual_event_choices(
                    theme,
                    scene_id,
                    enabled,
                    lambda item_id: _rlv2.hasItem(rlv2, item_id),
                )
                if not enabled:
                    return None
                return enabled

            enter_scenes = {
                scene_id: enabled
                for scene_id, choice_ids in raw_enter_scenes.items()
                if (enabled := executable_entry(scene_id, choice_ids)) is not None
            }
            fixed_scene_id = target_node.get("scene")
            if fixed_scene_id in enter_scenes:
                scene_id_list = [fixed_scene_id]
            else:
                seen_scene_ids = {
                    node.get("scene")
                    for zone_data in rlv2["map"]["zones"].values()
                    for node in zone_data.get("nodes", {}).values()
                    if node is not target_node
                    and node.get("visited")
                    and isinstance(node.get("scene"), str)
                }
                scene_id_list = event_scene_candidates(
                    theme,
                    int(zone),
                    node_type,
                    enter_scenes,
                )
                scene_id_list = [
                    scene_id
                    for scene_id in scene_id_list
                    if scene_id not in seen_scene_ids
                    or event_scene_is_repeatable(theme, scene_id)
                ]
            if not scene_id_list:
                rlv2["player"]["state"] = "WAIT_MOVE"
                _rlv2.finishNode(rlv2, server_data)
            else:
                scene_id: str = rng.choice(scene_id_list)
                target_node["scene"] = scene_id
                choices_list = sample_event_choices(
                    enter_scenes[scene_id], scene_rules.get(scene_id), rng
                )
                # 添加全部可选项
                for choices_id in choices_list:
                    available = choices_id == "choice_leave" or _rlv2.canPayChoice(
                        rlv2,
                        choice_rules.get(choices_id, {}),
                    )
                    choices.update({choices_id: available})
                    choiceAdditional.update({choices_id: {"rewards": []}})
                if not any(choices.values()):
                    choices["choice_leave"] = True
                    choiceAdditional["choice_leave"] = {"rewards": []}
                pending_event = {
                    "type": "SCENE",
                    "content": {
                        "scene": {
                            "id": scene_id,
                            "choices": choices,
                            "choiceAdditional": choiceAdditional,
                            "popReport": False,
                            "done": False
                        }
                    }
                }
                rlv2["player"]["pending"].insert(0, pending_event)
        case 131072:
            fragment = rlv2.get("module", {}).get("fragment")
            fragments = fragment.get("fragments") if isinstance(fragment, dict) else {}
            pending_event = {
                "type": "ALCHEMY",
                "content": {
                    "alchemy": {"canAlchemy": len(fragments) >= 2},
                    "done": False,
                    "popReport": False,
                },
            }
            rlv2["player"]["pending"].insert(0, pending_event)
        case 8 | 4096:
            goods = getGoods()
            pending_event = {
                "type": "SHOP",
                "content": {
                    "shop": {
                        "bank": {
                            "open": True,
                            "canPut": False,
                            "canWithdraw": False,
                            "withdraw": 0,
                            "cost": 1,
                        },
                        "id": "just_a_shop",
                        "goods": goods,
                        "popReport": False,
                        "done": False,
                    }
                },
            }
            rlv2["player"]["pending"].insert(0, pending_event)
        case _:
            rlv2["player"]["state"] = "WAIT_MOVE"

    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2LeaveShop():
    server_data = _load_server_data()
    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "SHOP":
        return {"error": "shop is not pending"}, 409
    rlv2["player"]["state"] = "WAIT_MOVE"
    rlv2["player"]["pending"] = []
    _rlv2.finishNode(rlv2, server_data)
    
    _persist_run(rlv2, server_data)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data

@_serialized_run
def rlv2BuyGoods(select: int=None):
    if select is None:
        request_data = request.get_json()
        select = int(request_data["select"][0])

    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "SHOP":
        return {"error": "shop purchase is not pending"}, 409
    if select < 0:
        return {"error": f"shop item is unavailable: {select}"}, 400
    shop = pending[0]["content"]["shop"]
    goods = shop["goods"]
    good = next((item for item in goods if int(item["index"]) == select), None)
    if good is None:
        return {"error": f"shop item is unavailable: {select}"}, 400

    price = int(good.get("priceCount", 0))
    if rlv2["player"]["property"]["gold"] < price:
        return {"error": "not enough ingots for shop purchase"}, 400

    rlv2["player"]["property"]["gold"] -= price
    created = _rlv2.add_item(rlv2, good["itemId"], int(good.get("count", 1)))
    goods.remove(good)
    if isinstance(created, list) and created:
        for ticket_id in reversed(created):
            _rlv2.activateTicket(rlv2, ticket_id)
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2shopAction():

    json_body = request.get_json()

    try:
        select = int(json_body["buy"][0])
        return rlv2BuyGoods(select)
    except (KeyError, IndexError):
        return rlv2LeaveShop()


@_serialized_run
def rlv2ChooseBattleReward():
    request_data = request.get_json()
    if not isinstance(request_data, dict):
        return {"error": "invalid battle reward selection"}, 400
    index = request_data.get("index")
    sub = request_data.get("sub")
    if type(index) is not int or type(sub) is not int:
        return {"error": "invalid battle reward selection"}, 400

    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "BATTLE_REWARD":
        return {"error": "battle reward selection is not pending"}, 409
    rewards = pending[0]["content"]["battleReward"]["rewards"]
    reward = next(
        (item for item in rewards if item.get("index") in (index, str(index))),
        None,
    )
    if reward is None or reward.get("done"):
        return {"error": f"battle reward is unavailable: {index}"}, 400
    selected_items = [
        item
        for item in reward.get("items", [])
        if item.get("sub", 0) in (sub, str(sub))
    ]
    if not selected_items:
        return {
            "error": f"battle reward option is unavailable: {index}/{sub}"
        }, 400
    reward["done"] = True
    created = []
    for item in selected_items:
        result = _rlv2.add_item(rlv2, item["id"], int(item.get("count", 1)))
        if isinstance(result, list):
            created.extend(result)
    if created:
        for ticket_id in reversed(created):
            _rlv2.activateTicket(rlv2, ticket_id)
    _persist_run(rlv2)

    data = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": rlv2,
                }
            },
            "deleted": {},
        }
    }

    return data


@_serialized_run
def rlv2CopperConfirmDraw():
    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "DRAW_COPPER":
        return {"error": "copper draw is not pending"}, 409
    rlv2["player"]["pending"].pop(0)
    rlv2["player"]["state"] = "WAIT_MOVE"

    _persist_run(rlv2)

    result = {
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current":{
                        "player": rlv2["player"]
                    }
                }
            },
            "deleted": {}
        }
    }

    return result 


@_serialized_run
def rlv2CopperRedraw():

    rlv2_data = _load_run()
    pending = rlv2_data["player"]["pending"]
    if not pending or pending[0].get("type") != "DRAW_COPPER":
        return {"error": "copper draw is not pending"}, 409
    copper_module = rlv2_data["module"].get("copper")
    if not copper_module or len(copper_module.get("bag", {})) < 3:
        return {"error": "copper bag is unavailable"}, 409
    bag = copper_module["bag"]
    for key, value in bag.items():
        value["isDrawn"] = False

    server_data = _load_server_data()
    redraw_count = int(copper_module.get("redrawCount", 0))
    rng = random.Random(
        f"{server_data.get('rlv2_seed')}_copper_redraw_{redraw_count}"
    )
    copper = rng.sample(list(bag), 3)
    for key in copper:
        bag[key]["isDrawn"] = True
    copper_module["redrawCount"] = redraw_count + 1

    _persist_run(rlv2_data)

    data = {
        "copper": copper,
        "divineEventId": "rogue_5_levelEVE_2",
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": {
                        "module": {
                            "copper": {
                                "bag": bag,
                            }
                        }
                    }
                }
            },
            "deleted": {},
        }
    }

    return data

def rlv2SetTroopCarry():
    result = {}

    return result


def rlv2getReward():
    result = {}

    return result

def rlv2BankPut():
    return {}, 202

def rlv2BankWithdraw():
    return {}, 202

def rlv2NodeMissionConfirm():
    return {}, 202

def rlv2NodeMissionGiveUp():
    return {}, 202

def rlv2NodeMissionCloseTip():
    return {}, 202

@_serialized_run
def rlv2ReadEndingChange():
    rlv2 = _load_run()
    player = rlv2.get("player") if isinstance(rlv2, dict) else None
    if not isinstance(player, dict):
        return {"error": "there is no active roguelike run"}, 409
    player["chgEnding"] = False
    _persist_run(rlv2)
    return _current_run_delta(rlv2)


@_serialized_run
def rlv2Alchemy():
    request_data = request.get_json() or {}
    fragment_indexes = request_data.get("fragmentIndex")
    leave = request_data.get("leave")
    if not isinstance(leave, bool) or not isinstance(fragment_indexes, list):
        return {"error": "invalid alchemy request"}, 400
    if any(not isinstance(index, str) for index in fragment_indexes):
        return {"error": "invalid alchemy fragment index"}, 400

    rlv2 = _load_run()
    player = rlv2.get("player")
    pending = player.get("pending") if isinstance(player, dict) else None
    if (
        not isinstance(player, dict)
        or player.get("state") != "PENDING"
        or not isinstance(pending, list)
        or not pending
        or pending[0].get("type") != "ALCHEMY"
    ):
        return {"error": "alchemy is not pending"}, 409

    server_data = _load_server_data()
    if leave:
        if fragment_indexes:
            return {"error": "leaving alchemy cannot consume fragments"}, 400
        pending.pop(0)
        player["state"] = "WAIT_MOVE"
        _rlv2.finishNode(rlv2, server_data)
        _persist_run(rlv2, server_data)
        return _current_run_delta(rlv2)

    if len(fragment_indexes) != 2 or len(set(fragment_indexes)) != 2:
        return {"error": "alchemy requires two distinct fragment instances"}, 400
    fragment = rlv2.get("module", {}).get("fragment")
    fragments = fragment.get("fragments") if isinstance(fragment, dict) else None
    if not isinstance(fragments, dict):
        return {"error": "fragment module is unavailable"}, 409
    selected = [fragments.get(index) for index in fragment_indexes]
    if any(not isinstance(entry, dict) or entry.get("used") for entry in selected):
        return {"error": "alchemy fragment is unavailable"}, 400
    if any(not isinstance(entry.get("id"), str) for entry in selected):
        return {"error": "alchemy fragment has an invalid item id"}, 500

    theme = rlv2.get("game", {}).get("theme")
    topic_table = get_memory("roguelike_topic_table")
    fragment_rules = (
        topic_table.get("modules", {})
        .get(theme, {})
        .get("fragment", {})
    )
    selected_ids = sorted(entry["id"] for entry in selected)
    formula = next(
        (
            value
            for value in fragment_rules.get("alchemyFormulaData", {}).values()
            if isinstance(value, dict)
            and sorted(value.get("fragmentIds", [])) == selected_ids
        ),
        None,
    )
    if formula is None:
        return {
            "error": "random alchemy outcomes are not supported without a verified pool"
        }, 501

    reward_id = formula.get("rewardId")
    reward_count = formula.get("rewardCount")
    theme_items = topic_table.get("details", {}).get(theme, {}).get("items", {})
    if (
        not isinstance(reward_id, str)
        or type(reward_count) is not int
        or reward_count <= 0
        or reward_id not in theme_items
    ):
        return {"error": "invalid alchemy formula reward"}, 500

    for index in fragment_indexes:
        fragments.pop(index)
    _rlv2.recalculateFragmentWeight(rlv2)
    events = rlv2.setdefault("_server", {}).setdefault("events", {})
    events["pendingAlchemyReward"] = {
        "itemId": reward_id,
        "count": reward_count,
    }
    pending[0] = {
        "type": "ALCHEMY_REWARD",
        "content": {
            "alchemyReward": {
                "items": [{"id": reward_id, "count": reward_count}],
                "isSSR": theme_items[reward_id].get("rarity") == "SUPER_RARE",
                "isFail": False,
            },
            "done": False,
            "popReport": False,
        },
    }
    _persist_run(rlv2, server_data)
    return _current_run_delta(rlv2)


@_serialized_run
def rlv2AlchemyReward():
    request_data = request.get_json() or {}
    reward_index = request_data.get("index")
    if type(reward_index) is not int:
        return {"error": "invalid alchemy reward index"}, 400

    rlv2 = _load_run()
    player = rlv2.get("player")
    pending = player.get("pending") if isinstance(player, dict) else None
    events = rlv2.get("_server", {}).get("events", {})
    reward = events.get("pendingAlchemyReward") if isinstance(events, dict) else None
    if (
        not isinstance(player, dict)
        or player.get("state") != "PENDING"
        or not isinstance(pending, list)
        or not pending
        or pending[0].get("type") != "ALCHEMY_REWARD"
        or not isinstance(reward, dict)
    ):
        return {"error": "alchemy reward is not pending"}, 409
    if reward_index != 0:
        return {"error": "alchemy reward index is out of range"}, 400

    item_id = reward.get("itemId")
    count = reward.get("count")
    if not isinstance(item_id, str) or type(count) is not int or count <= 0:
        return {"error": "invalid pending alchemy reward"}, 500

    _rlv2.add_item(rlv2, item_id, count)
    events.pop("pendingAlchemyReward", None)
    pending.pop(0)
    player["state"] = "WAIT_MOVE"
    server_data = _load_server_data()
    _rlv2.finishNode(rlv2, server_data)
    _persist_run(rlv2, server_data)
    return _current_run_delta(rlv2)


def rlv2RerollNode():
    return {}, 202

def rlv2UpgradeNode():
    return {}, 202

def rlv2GetTicketAssistList():
    return {}, 202

def rlv2RecruitAssistChar():
    return {}, 202

def rlv2DiceChoice():
    return {}, 202

def rlv2SacrificeChoice():
    return {}, 202

def rlv2CopperGild():
    return {}, 202

def rlv2ExpeditionChoice():
    return {}, 202

def rlv2ConfirmExpeditonReturn():
    return {}, 202

def rlv2ShopBattleStart():
    return {}, 202

def rlv2RefreshShop():
    return {}, 202

def rlv2SetPinned():
    return {}, 202

def rlv2ConfirmZoneReward():
    return {}, 202

def rlv2ConfirmTraderReturn():
    return {}, 202

def rlv2UseStashedTicket():
    return {}, 202

def rlv2StashRecruitTicket():
    return {}, 202

def rlv2SpecialZoneLeave():
    return {}, 202

def rlv2ChooseInitialExploreTool():
    return {}, 202

def rlv2getRewardgetReward():
    return {}, 202


class _rlv2:
    def endRun(rlv2: dict, success: bool, reason: str) -> None:
        queue_game_settlement(rlv2, success, reason, int(time()))

    def unlockRoute(rlv2: dict, edge: dict) -> bool:
        if not edge.get("key"):
            return True

        theme = rlv2["game"]["theme"]
        theme_data = get_memory("roguelike_topic_table")["details"][theme]
        item_id = theme_data["gameConst"].get("unlockRouteItemId")
        required = int(theme_data["gameConst"].get("unlockRouteItemCount", 1))
        if not item_id or required <= 0:
            edge.pop("key", None)
            return True

        consumable = rlv2["inventory"]["consumable"]
        ledger_count = int(consumable.get(item_id, 0))
        module_count = 0
        item_type = theme_data["items"].get(item_id, {}).get("type")
        if item_type == "VISION" and rlv2["module"].get("vision") is not None:
            module_count = int(rlv2["module"]["vision"].get("value", 0))
        if ledger_count + module_count < required:
            return False

        ledger_cost = min(ledger_count, required)
        if ledger_cost:
            remaining = ledger_count - ledger_cost
            if remaining:
                consumable[item_id] = remaining
            else:
                consumable.pop(item_id, None)
        module_cost = required - ledger_cost
        if module_cost:
            rlv2["module"]["vision"]["value"] -= module_cost
        edge.pop("key", None)
        return True

    def hasItem(rlv2: dict, item: str, count: int = 1) -> bool:
        if rlv2["inventory"]["consumable"].get(item, 0) >= count:
            return True
        relic_count = sum(
            relic.get("count", 1)
            for relic in rlv2["inventory"]["relic"].values()
            if relic["id"] == item
        )
        if relic_count >= count:
            return True
        trap = rlv2["inventory"].get("trap")
        if trap and trap.get("id") == item and trap.get("count", 1) >= count:
            return True
        fragment = rlv2.get("module", {}).get("fragment")
        fragments = fragment.get("fragments") if isinstance(fragment, dict) else None
        if isinstance(fragments, dict):
            fragment_count = sum(
                max(1, int(entry.get("count", 1)))
                for entry in fragments.values()
                if isinstance(entry, dict) and entry.get("id") == item
            )
            if fragment_count >= count:
                return True
        return any(
            tool["id"] == item and tool.get("count", 1) >= count
            for tool in rlv2["inventory"].get("exploreTool", {}).values()
        )

    def canPayChoice(rlv2: dict, choice_data: dict) -> bool:
        if not isinstance(choice_data, dict):
            return False
        requirement = choice_data.get("require")
        if requirement is not None:
            if not isinstance(requirement, dict) or set(requirement) - {
                "items",
                "itemsAny",
                "notItems",
                "moduleMin",
            }:
                return False
            items = requirement.get("items", {})
            if not isinstance(items, dict) or any(
                not isinstance(item_id, str)
                or type(count) is not int
                or count <= 0
                or not _rlv2.hasItem(rlv2, item_id, count)
                for item_id, count in items.items()
            ):
                return False
            any_items = requirement.get("itemsAny", {})
            if not isinstance(any_items, dict) or any(
                not isinstance(item_id, str)
                or type(count) is not int
                or count <= 0
                for item_id, count in any_items.items()
            ):
                return False
            if any_items and not any(
                _rlv2.hasItem(rlv2, item_id, count)
                for item_id, count in any_items.items()
            ):
                return False
            excluded_items = requirement.get("notItems", {})
            if not isinstance(excluded_items, dict) or any(
                not isinstance(item_id, str)
                or type(count) is not int
                or count <= 0
                or _rlv2.hasItem(rlv2, item_id, count)
                for item_id, count in excluded_items.items()
            ):
                return False
            module_minimum = requirement.get("moduleMin", {})
            if not isinstance(module_minimum, dict) or not has_numeric_cost(
                rlv2["module"], module_minimum
            ):
                return False

        lose_all = choice_data.get("lose_all", [])
        if not isinstance(lose_all, list) or any(
            property_key != "gold" for property_key in lose_all
        ):
            return False
        lose = choice_data.get("lose")
        if isinstance(lose, dict) and not has_numeric_cost(
            rlv2["player"]["property"], lose
        ):
            return False
        if isinstance(lose, str) and not _rlv2.hasItem(rlv2, lose):
            return False
        for key, target in (
            ("m_lose", rlv2["module"]),
            ("i_lose", rlv2["inventory"]["consumable"]),
        ):
            cost = choice_data.get(key)
            if isinstance(cost, dict) and not has_numeric_cost(target, cost):
                return False
        return True

    def routeState(rlv2: dict) -> dict | None:
        game = rlv2.get("game")
        player = rlv2.get("player")
        if not isinstance(game, dict) or not isinstance(player, dict):
            return None
        theme = game.get("theme")
        ending = player.get("toEnding")
        if not is_supported_ending(theme, ending):
            return None

        cursor = player.get("cursor")
        zone = cursor.get("zone", 1) if isinstance(cursor, dict) else 1
        zone = zone if type(zone) is int and zone > 0 else 1
        private = rlv2.setdefault("_server", {})
        private.setdefault("schemaVersion", 1)
        private.setdefault("events", {})
        route = private.get("route")
        if not route_plan_is_valid(theme, ending, route, zone):
            route = build_route_plan(
                theme,
                ending,
                zone,
                route if isinstance(route, dict) else None,
            )
            if route is None:
                return None
            private["route"] = route
        return route

    def patchCurrentBoss(rlv2: dict, route: dict) -> None:
        patch_current_boss(rlv2, route)

    def rebaseBaseEnding(rlv2: dict, base_ending: str, source: str) -> bool:
        game = rlv2.get("game")
        player = rlv2.get("player")
        if not isinstance(game, dict) or not isinstance(player, dict):
            return False
        theme = game.get("theme")
        current_ending = player.get("toEnding")
        if not is_supported_ending(theme, current_ending) or not is_supported_ending(
            theme, base_ending
        ):
            return False

        cursor = player.get("cursor")
        zone = cursor.get("zone", 1) if isinstance(cursor, dict) else 1
        zone = zone if type(zone) is int and zone > 0 else 1
        base_route = build_route_plan(theme, base_ending, zone)
        route = build_route_plan(theme, current_ending, zone, base_route)
        if route is None or zone not in route.get("orderedZones", []):
            return False
        route["source"] = source
        player["chgEnding"] = True
        rlv2.setdefault("_server", {})["route"] = route
        _rlv2.patchCurrentBoss(rlv2, route)
        return True

    def setEnding(
        rlv2: dict,
        ending: str,
        source: str,
        allow_downgrade: bool = False,
    ) -> bool:
        game = rlv2.get("game")
        player = rlv2.get("player")
        if not isinstance(game, dict) or not isinstance(player, dict):
            return False
        theme = game.get("theme")
        if not is_supported_ending(theme, ending):
            return False

        current_ending = player.get("toEnding")
        if current_ending == ending:
            return True
        cursor = player.get("cursor")
        zone = cursor.get("zone", 1) if isinstance(cursor, dict) else 1
        zone = zone if type(zone) is int and zone > 0 else 1
        previous = _rlv2.routeState(rlv2)
        target_priority = ending_priority(theme, ending)
        if (
            is_overlay_ending(theme, current_ending)
            and not is_overlay_ending(theme, ending)
        ):
            underlay_ending = (
                previous.get("underlayEndingId")
                if isinstance(previous, dict)
                else None
            )
            if (
                underlay_ending == ending
            ):
                return True
            underlay_priority = ending_priority(theme, underlay_ending)
            if (
                underlay_priority is not None
                and target_priority is not None
                and target_priority <= underlay_priority
                and not allow_downgrade
            ):
                return True
            underlay = build_route_plan(theme, ending, zone, previous)
            route = build_route_plan(theme, current_ending, zone, underlay)
            if route is None or zone not in route.get("orderedZones", []):
                return False
            route["source"] = source
            player["chgEnding"] = True
            rlv2.setdefault("_server", {})["route"] = route
            _rlv2.patchCurrentBoss(rlv2, route)
            return True
        current_priority = ending_priority(theme, current_ending)
        if (
            current_priority is not None
            and target_priority is not None
            and target_priority <= current_priority
            and not allow_downgrade
        ):
            return True

        route = build_route_plan(theme, ending, zone, previous)
        if route is None or zone not in route.get("orderedZones", []):
            return False
        route["source"] = source
        player["toEnding"] = ending
        # The client exposes this flag and an explicit acknowledgement endpoint.
        # No route change is reported for an idempotent assignment.
        player["chgEnding"] = True
        rlv2.setdefault("_server", {})["route"] = route
        _rlv2.patchCurrentBoss(rlv2, route)
        return True

    def applyEndingItem(rlv2: dict, item_id: str) -> None:
        theme = rlv2.get("game", {}).get("theme")
        branch_reset = ending_branch_reset_for_acquired_item(theme, item_id)
        if branch_reset is not None:
            cancelled_ending, fallback_ending = branch_reset
            current_ending = rlv2.get("player", {}).get("toEnding")
            if current_ending == cancelled_ending:
                _rlv2.setEnding(
                    rlv2,
                    fallback_ending,
                    f"item:{item_id}",
                    allow_downgrade=True,
                )
            else:
                current_priority = ending_priority(theme, current_ending)
                cancelled_priority = ending_priority(theme, cancelled_ending)
                if (
                    current_priority is not None
                    and cancelled_priority is not None
                    and current_priority > cancelled_priority
                ):
                    _rlv2.rebaseBaseEnding(
                        rlv2,
                        fallback_ending,
                        f"item:{item_id}",
                    )
            return

        ending = ending_for_acquired_item(theme, item_id)
        if ending is not None:
            _rlv2.setEnding(
                rlv2,
                ending,
                f"item:{item_id}",
            )

    def finishNode(rlv2: dict, server_data: dict) -> bool:
        cursor = rlv2["player"]["cursor"]
        position = cursor.get("position")
        if position is None:
            return False
        zone_id = str(cursor["zone"])
        node_id = str(position["x"] * 100 + position["y"])
        node = rlv2["map"]["zones"].get(zone_id, {}).get("nodes", {}).get(node_id)
        if not node or not node.get("zone_end"):
            return False
        ending = rlv2["player"].get("toEnding")
        route = _rlv2.routeState(rlv2)
        if route is None:
            _rlv2.endRun(rlv2, False, "INVALID_ENDING_ROUTE")
            return True
        ordered_zones = route.get("orderedZones", [])
        next_zone = route_next_zone(route, cursor["zone"])
        if next_zone is None:
            if not ordered_zones or cursor["zone"] != ordered_zones[-1]:
                _rlv2.endRun(rlv2, False, "INVALID_ENDING_ROUTE")
                return True
            _rlv2.endRun(rlv2, True, "ENDING_REACHED")
            return True

        cursor["zone"] = next_zone
        cursor["position"] = None
        zones, seed = _rlv2.getMap_new(
            rlv2["game"]["theme"],
            server_data.get("rlv2_seed"),
            cursor["zone"],
            ending,
            boss_ending_for_zone(route, cursor["zone"]),
        )
        rlv2["map"].setdefault("zones", {}).update(zones)
        server_data["rlv2_seed"] = seed
        return True

    def getNextRelicIndex(rlv2):
        d = set()
        for e in rlv2["inventory"]["relic"]:
            d.add(int(e[2:]))
        i = 0
        while i in d:
            i += 1
        return f"r_{i}"

    def getNextExploreToolIndex(rlv2):
        d = set()
        for e in rlv2["inventory"]["exploreTool"]:
            d.add(int(e[2:]))
        i = 0
        while i in d:
            i += 1
        return f"e_{i}"

    def getNextFragmentIndex(rlv2):
        fragment = rlv2.get("module", {}).get("fragment")
        fragments = fragment.get("fragments") if isinstance(fragment, dict) else {}
        used = {
            int(index[2:])
            for index in fragments
            if isinstance(index, str)
            and index.startswith("f_")
            and index[2:].isdigit()
        }
        index = 0
        while index in used:
            index += 1
        return f"f_{index}"

    def recalculateFragmentWeight(rlv2):
        fragment = rlv2.get("module", {}).get("fragment")
        if not isinstance(fragment, dict):
            return
        fragments = fragment.get("fragments")
        if not isinstance(fragments, dict):
            return
        fragment["totalWeight"] = sum(
            max(0, int(entry.get("weight", 0)))
            for entry in fragments.values()
            if isinstance(entry, dict) and not entry.get("used")
        )
    
    def getChars(
        use_user_defaults=False, rlv2_data: dict = None, ticket_item_id: str = None
    ):
        user_data = read_json(SYNC_DATA_TEMPLATE_PATH)
        chars = [
            user_data["user"]["troop"]["chars"][i]
            for i in user_data["user"]["troop"]["chars"]
        ]
        if use_user_defaults:
            rlv2_user_settings = read_json(RLV2_USER_SETTINGS_PATH)
            initialChars = set(rlv2_user_settings["initialChars"])
            chars_tmp = []
            for char in chars:
                if char["charId"] in initialChars:
                    chars_tmp.append(char)
            chars = chars_tmp
        for i in range(len(chars)):
            char = chars[i]
            if char["evolvePhase"] == 2:
                char_alt = deepcopy(char)
                char_alt["evolvePhase"] = 1
                char_alt["level"] -= 10
                if len(char_alt["skills"]) == 3:
                    char_alt["defaultSkillIndex"] = 1
                    char_alt["skills"][-1]["unlock"] = 0
                for skill in char_alt["skills"]:
                    skill["specializeLevel"] = 0
                char_alt["currentEquip"] = None
                chars.append(char_alt)
                if char["charId"] == "char_002_amiya":
                    tmpls = list(char_alt["tmpl"].keys())
                    for j in tmpls:
                        if len(char_alt["tmpl"][j]["skills"]) == 3:
                            char_alt["tmpl"][j]["defaultSkillIndex"] = 1
                            char_alt["tmpl"][j]["skills"][-1]["unlock"] = 0
                        for skill in char_alt["tmpl"][j]["skills"]:
                            skill["specializeLevel"] = 0
                        char_alt["tmpl"][j]["currentEquip"] = None
                    char["currentTmpl"] = tmpls[0]
                    char_alt["currentTmpl"] = tmpls[0]
                    for j in range(1, len(tmpls)):
                        for k in [char, char_alt]:
                            char_alt_alt = deepcopy(k)
                            char_alt_alt["currentTmpl"] = tmpls[j]
                            chars.append(char_alt_alt)
        for i, char in enumerate(chars):
            char.update(
                {
                    "instId": str(i),
                    "type": "NORMAL",
                    "upgradeLimited": False,
                    "upgradePhase": 1,
                    "isUpgrade": False,
                    "isCure": False,
                    "population": 0,
                    "charBuff": [],
                    "troopInstId": "0",
                }
            )
            if char["evolvePhase"] < 2:
                char["upgradeLimited"] = True
                char["upgradePhase"] = 0
        if rlv2_data is not None and ticket_item_id is not None:
            rlv2_table = get_memory("roguelike_topic_table")
            theme_data = rlv2_table["details"][rlv2_data["game"]["theme"]]
            ticket_data = theme_data["recruitTickets"].get(ticket_item_id)
            if ticket_data is None:
                ticket_data = theme_data["upgradeTickets"].get(ticket_item_id)
            if ticket_data is None:
                return []
            chars = prepare_recruit_candidates(
                chars,
                {
                    **get_memory("character_table"),
                    **get_memory("char_patch_table").get("patchChars", {}),
                },
                ticket_data,
                rlv2_data["troop"]["chars"],
            )
        return chars

    def addTicket(rlv2_data, ticket_id, item_id=None):
        theme = rlv2_data["game"]["theme"]
        ticket = item_id or f"{theme}_recruit_ticket_all"
        rlv2_data["inventory"]["recruit"][ticket_id] = {
            "index": ticket_id,
            "id": ticket,
            "state": 0,
            "list": [],
            "result": None,
            "ts": time(),
            "from": "initial",
            "mustExtra": 0,
            "needAssist": True,
        }

    def getMap(theme):
        rlv2_table = get_memory("roguelike_topic_table")
        stages = [i for i in rlv2_table["details"][theme]["stages"]]

        # 商店类型
        if theme != "rogue_1":
            shop = 4096
        else:
            shop = 8

        map = {}
        zone = 1
        j = 0
        while j < len(stages):
            zone_map = {"id": f"zone_{zone}", "index": zone, "nodes": {}, "variation": []}
            nodes_list = [
                {
                    "index": "0",
                    "pos": {"x": 0, "y": 0},
                    "next": [{"x": 1, "y": 0}],
                    "type": shop,
                },
                {"index": "100", "pos": {"x": 1, "y": 0}, "next": [], "type": shop},
            ]
            x_max = 9
            y_max = 3
            x = 1
            y = 1
            while j < len(stages):
                stage = stages[j]
                if y > y_max:
                    if x + 1 == x_max:
                        break
                    x += 1
                    y = 0
                node_type = 1
                if rlv2_table["details"][theme]["stages"][stage]["isElite"]:
                    node_type = 2
                elif rlv2_table["details"][theme]["stages"][stage]["isBoss"]:
                    node_type = 4
                nodes_list.append(
                    {
                        "index": str(x * 100 + y),
                        "pos": {"x": x, "y": y},
                        "next": [],
                        "type": node_type,
                        "stage": stage,
                    }
                )
                nodes_list[0]["next"].append({"x": x, "y": y})
                y += 1
                j += 1
            x += 1
            nodes_list[0]["next"].append({"x": x, "y": 0})
            nodes_list.append(
                {
                    "index": f"{x}00",
                    "pos": {"x": x, "y": 0},
                    "next": [],
                    "type": shop,
                    "zone_end": True,
                }
            )

            for node in nodes_list:
                zone_map["nodes"][node["index"]] = node
            map[str(zone)] = zone_map
            zone += 1
        return map
        
    def getMap_new(
        theme: str,
        seed: str = None,
        zone: int = 1,
        ending: str = None,
        boss_ending: str = None,
    ):
        theme_data = get_memory("roguelike_topic_table")["details"][theme]
        layout = area_layout(theme, zone)
        column_specs = area_column_specs(theme, zone)
        if layout is None or column_specs is None:
            raise ValueError(
                f"unsupported core roguelike area: {theme}/zone_{zone}"
            )

        randomseed = seed or os.urandom(16).hex()
        if ending is None:
            ending = min(
                theme_data["endings"].values(),
                key=lambda item: item.get("priority", 999),
            )["id"]
        rng = random.Random(f"{randomseed}_{zone}_{theme}_{ending}")

        ro_num = theme.removeprefix("rogue_")
        stage_table = theme_data["stages"]
        shop_type = 8 if theme == "rogue_1" else 4096
        refresh_count = 1 if theme == "rogue_4" else 0
        branch_limit = int(layout["maximumBranches"])
        final_depth = terminal_depth(theme, ending)

        def stage_pool(node_type: int, logical_depth: int) -> list[str]:
            kind = "n" if node_type == 1 else "e"
            prefix = f"ro{ro_num}_{kind}_{logical_depth}_"
            return [
                stage_id
                for stage_id in stage_table
                if stage_id.startswith(prefix)
            ]

        def mid_boss_pool() -> list[str]:
            last_index = 5 if theme == "rogue_1" else 3
            pattern = re.compile(rf"ro{ro_num}_b_([1-{last_index}])")
            return [
                stage_id
                for stage_id, stage in stage_table.items()
                if stage.get("isBoss") and pattern.fullmatch(stage_id)
            ]

        def boss_pool() -> list[str]:
            resolved_ending = boss_ending
            if resolved_ending is None and zone == final_depth:
                resolved_ending = ending
            elif (
                resolved_ending is None
                and zone == 5
                and isinstance(final_depth, int)
                and final_depth > 5
            ):
                resolved_ending = default_ending(theme)
            candidates = (
                boss_stage_ids(theme, resolved_ending)
                if resolved_ending is not None
                else mid_boss_pool()
            )
            verified = [
                stage_id
                for stage_id in candidates
                if stage_id in stage_table
                and stage_table[stage_id].get("isBoss")
            ]
            # Shared specialNodeId only proves boss identity. Variant selection
            # needs difficulty/event state that this generator does not model.
            return verified[:1] if resolved_ending is not None else verified

        def weighted_type(kind: str) -> int:
            type_weights = {
                "default": {1: 60, 2: 15, 32: 25},
                "battle": {1: 80, 2: 20},
                "battle_or_incident": {1: 60, 2: 15, 32: 25},
                "battle_incident_wish": {
                    1: 50,
                    2: 10,
                    32: 25,
                    512: 15,
                },
                "non_battle": {16: 20, 32: 60, 512: 20},
                "shop": {shop_type: 1},
                "rest": {16: 1},
                "incident": {32: 1},
                "entertainment": {128: 1},
                "gift": {64: 1},
                "wish": {512: 1},
                "sacrifice": {1024: 1},
                "story": {65536: 1},
                "alchemy": {131072: 1},
                "duel": {262144: 1},
                "stashed_recruit": {524288: 1},
                "special_zone": {
                    1048576 if zone == 1 else 8192: 1
                },
                "boss": {4: 1},
            }.get(kind)
            if type_weights is None:
                raise ValueError(
                    f"unsupported roguelike column kind: {kind}"
                )
            return rng.choices(
                list(type_weights),
                weights=list(type_weights.values()),
                k=1,
            )[0]

        zone_data = {
            "id": layout["zoneId"],
            "nodes": {},
            "variation": [],
        }
        nodes_by_x: dict[int, list[int]] = {}

        for x, reviewed_spec in enumerate(column_specs):
            spec = reviewed_spec or {
                "minimum": 1,
                "maximum": branch_limit,
                "kinds": ("default",),
            }
            count = rng.randint(spec["minimum"], spec["maximum"])
            forced_battle_rows = set(
                rng.sample(
                    range(count),
                    min(int(spec.get("minimum_battle_nodes", 0)), count),
                )
            )
            nodes_by_x[x] = list(range(count))
            for y in range(count):
                kind = (
                    "battle"
                    if y in forced_battle_rows
                    else rng.choice(spec["kinds"])
                )
                node_type = weighted_type(kind)
                node = {
                    "index": str(x * 100 + y),
                    "pos": {"x": x, "y": y},
                    "next": [],
                    "type": node_type,
                    "refresh": {
                        "usedCount": 0,
                        "count": refresh_count,
                        "cost": 1,
                    },
                }
                if x == len(column_specs) - 1:
                    node["zone_end"] = True
                scene_id = spec.get("scene_id")
                if scene_id is None and node_type == 65536:
                    scene_id = fixed_scene_for_zone(theme, zone)
                if scene_id:
                    node["scene"] = scene_id

                if node_type in {1, 2}:
                    logical_depths = spec.get("stage_depths")
                    if logical_depths is None:
                        logical_depths = (int(spec.get("stage_depth", zone)),)
                    candidates = [
                        stage_id
                        for logical_depth in logical_depths
                        for stage_id in stage_pool(
                            node_type, int(logical_depth)
                        )
                    ]
                    if not candidates and node_type == 2:
                        node_type = 1
                        node["type"] = 1
                        candidates = [
                            stage_id
                            for logical_depth in logical_depths
                            for stage_id in stage_pool(
                                1, int(logical_depth)
                            )
                        ]
                    if not candidates:
                        raise ValueError(
                            f"no stage pool for "
                            f"{theme}/zone_{zone}/type_{node_type}"
                        )
                    node["stage"] = rng.choice(candidates)
                elif node_type == 4:
                    candidates = boss_pool()
                    if not candidates:
                        raise ValueError(
                            f"no verified boss for "
                            f"{theme}/zone_{zone}/{ending}"
                        )
                    node["stage"] = rng.choice(candidates)

                zone_data["nodes"][node["index"]] = node

        normal_stages = stage_pool(1, zone)
        elite_stages = stage_pool(2, zone)
        enforce_emergency_node_limits(
            theme,
            zone,
            zone_data["nodes"],
            normal_stages,
            elite_stages,
            rng,
        )

        for x in range(len(column_specs) - 1):
            next_y_values = nodes_by_x[x + 1]
            for y in nodes_by_x[x]:
                node = zone_data["nodes"][str(x * 100 + y)]
                ordered = sorted(
                    next_y_values,
                    key=lambda next_y: (abs(next_y - y), next_y),
                )
                edge_count = rng.randint(1, min(2, len(ordered)))
                for next_y in rng.sample(ordered, edge_count):
                    node["next"].append(
                        {"x": x + 1, "y": next_y}
                    )

            reached = {
                edge["y"]
                for y in nodes_by_x[x]
                for edge in zone_data["nodes"][
                    str(x * 100 + y)
                ]["next"]
            }
            for next_y in next_y_values:
                if next_y in reached:
                    continue
                previous_y = min(
                    nodes_by_x[x],
                    key=lambda value: abs(value - next_y),
                )
                zone_data["nodes"][
                    str(x * 100 + previous_y)
                ]["next"].append(
                    {"x": x + 1, "y": next_y}
                )

        for node in zone_data["nodes"].values():
            unique_edges = {
                (edge["x"], edge["y"]): edge
                for edge in node["next"]
            }
            node["next"] = [
                unique_edges[key] for key in sorted(unique_edges)
            ]

        return {str(zone): zone_data}, randomseed

    def activateTicket(rlv2, ticket_id):
        rlv2["player"]["pending"].insert(
            0,
            {
                "type": "RECRUIT",
                "content": {"recruit": {"ticket": ticket_id}},
            },
        )
        ticket_item_id = rlv2["inventory"]["recruit"][ticket_id]["id"]
        chars = _rlv2.getChars(
            rlv2_data=rlv2, ticket_item_id=ticket_item_id
        )
        rlv2["inventory"]["recruit"][ticket_id]["state"] = 1
        rlv2["inventory"]["recruit"][ticket_id]["list"] = chars

    def getNextTicketIndex(rlv2):
        d = set()
        for e in rlv2["inventory"]["recruit"]:
            d.add(int(e[2:]))
        config = read_json(CONFIG_PATH)
        if not config["rlv2Config"]["allChars"]:
            i = 0
        else:
            i = 10000 - 1
        while i in d:
            i += 1
        return f"t_{i}"

    def getBuffs(rlv2:dict, stage_id:str):
        rlv2_table:dict = get_memory("roguelike_topic_table")
        theme:str = rlv2["game"]["theme"]
        buffs = []

        for relic in rlv2["inventory"]["relic"].values():
            item_id = relic["id"]
            if item_id in rlv2_table["details"][theme]["relics"]:
                buffs += rlv2_table["details"][theme]["relics"][item_id]["buffs"]
        if rlv2["inventory"]["trap"] is not None:
            item_id = rlv2["inventory"]["trap"]["id"]
            if item_id in rlv2_table["details"][theme]["relics"]:
                buffs += rlv2_table["details"][theme]["relics"][item_id]["buffs"]
        for i in rlv2["inventory"]["exploreTool"]:
            item_id = rlv2["inventory"]["exploreTool"][i]["id"]
            if item_id in rlv2_table["details"][theme]["relics"]:
                buffs += rlv2_table["details"][theme]["relics"][item_id]["buffs"]

        for i in rlv2["buff"]["squadBuff"]:
            if i in rlv2_table["details"][theme]["squadBuffData"]:
                buffs += rlv2_table["details"][theme]["squadBuffData"][i]["buffs"]

        mode_grade:int = rlv2["game"]["eGrade"]
        theme_buffs = data.rlv2_data.rogue_buffs.get(theme, [])
        
        buffs += collect_difficulty_buffs(theme_buffs, mode_grade)

        def getZone():
            rlv2_settings = read_json(RLV2_SETTINGS_PATH)
            if stage_id in rlv2_settings["stageZone"]:
                return rlv2_settings["stageZone"][stage_id]
            if stage_id.find("_n_") != -1 or stage_id.find("_e_") != -1:
                try:
                    return int(stage_id.split("_")[2])
                except Exception:
                    pass
            return -1

        zone = getZone()
        match theme:
            case "rogue_2":
                if zone == -1:
                    pass
                elif 16 > mode_grade > 0:
                    value = 1 + 0.01 * mode_grade
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": value},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": value},
                                ],
                            },
                        ]
                elif mode_grade == 15:
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": 1.2},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": 1.2},
                                ],
                            },
                        ]
                elif mode_grade > 16:
                    value = 1 + 0.01 * (5 * mode_grade - 60)
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": 1.2},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": value},
                                ],
                            },
                        ]
            case "rogue_3":
                if zone == -1:
                    pass
                if mode_grade > 4:
                    value = 1 + 0.16 * (mode_grade - 4) / 11 #(15 - 4)
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": value},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": value},
                                ],
                            },
                        ]
            case "rogue_4":
                if zone == -1:
                    pass
                if mode_grade > 4:
                    if mode_grade < 8:
                        value = mode_grade - 4
                    elif 7 < mode_grade < 12:
                        value = mode_grade - 3
                    elif 11 < mode_grade < 15:
                        value = 3 * mode_grade - 26 #10 + (mode_grade - 12) * 3
                    else:
                        value = mode_grade + 5
                    value = 1 + value * 0.01
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": value},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": value},
                                ],
                            },
                        ]
            case "rogue_5":
                if zone == -1:
                    pass
                if mode_grade > 3:
                    if mode_grade < 11:
                        value = mode_grade - 3
                    elif 10 < mode_grade < 15:
                        value = mode_grade - 1
                    else:
                        value = mode_grade
                    value = 1 + value * 0.01
                    for i in range(zone):
                        buffs += [
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_atk_down"},
                                    {"key": "atk", "value": value},
                                ],
                            },
                            {
                                "key": "global_buff_normal",
                                "blackboard": [
                                    {"key": "key", "valueStr": "enemy_max_hp_down"},
                                    {"key": "max_hp", "value": value},
                                ],
                            },
                        ]
            case _:
                pass

        return buffs
    
    def grant_resource(rlv2: dict, item: str, count: int, cover: bool = False):
        theme = rlv2["game"]["theme"]
        item_data = get_memory("roguelike_topic_table")["details"][theme][
            "items"
        ].get(item)
        if item_data is None:
            return False

        item_type = item_data["type"]
        prop = rlv2["player"]["property"]
        if item_type == "HP":
            prop["hp"]["current"] = count if cover else prop["hp"]["current"] + count
        elif item_type == "HPMAX":
            if cover:
                prop["hp"] = {"current": count, "max": count}
            else:
                prop["hp"]["max"] += count
                prop["hp"]["current"] += count
        elif item_type == "GOLD":
            prop["gold"] = count if cover else prop["gold"] + count
        elif item_type == "POPULATION":
            population = prop["population"]
            if cover:
                population["max"] = max(population["cost"], count)
            elif count < 0:
                population["max"] = max(
                    population["cost"], population["max"] + count
                )
            else:
                population["max"] += count
        elif item_type == "SQUAD_CAPACITY":
            prop["capacity"] = count if cover else prop["capacity"] + count
        elif item_type == "EXP":
            prop["exp"] = count if cover else prop["exp"] + count
        elif item_type == "SHIELD":
            prop["shield"] = count if cover else prop["shield"] + count
        elif item_type == "SAN_POINT" and rlv2["module"].get("san") is not None:
            sanity = rlv2["module"]["san"]
            sanity["sanity"] = count if cover else sanity["sanity"] + count
        elif item_type == "DICE_POINT" and rlv2["module"].get("dice") is not None:
            dice = rlv2["module"]["dice"]
            dice["count"] = count if cover else dice["count"] + count
        elif item_type == "VISION" and rlv2["module"].get("vision") is not None:
            vision = rlv2["module"]["vision"]
            vision["value"] = count if cover else vision["value"] + count
        elif item_type == "CHAOS_PURIFY" and rlv2["module"].get("chaos") is not None:
            chaos = rlv2["module"]["chaos"]
            current = chaos.get("value", 0)
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                return False
            # Earning purification lowers collapse; spending it raises collapse.
            chaos["value"] = max(0, -count if cover else current - count)
        elif item_type == "MAX_WEIGHT" and rlv2["module"].get("fragment") is not None:
            fragment = rlv2["module"]["fragment"]
            current = fragment.get("limitWeight", 0)
            if type(current) is not int:
                return False
            fragment["limitWeight"] = max(0, count if cover else current + count)
        else:
            return False

        clamp_player_property(prop)
        return True

    def add_item(rlv2: dict, item: str, count: int = 1):
        theme = rlv2["game"]["theme"]
        topic_table = get_memory("roguelike_topic_table")
        theme_data = topic_table["details"][theme]
        item_data = theme_data["items"].get(item)
        if item_data is None:
            raise ValueError(f"unknown roguelike item: {item}")

        item_type = item_data["type"]
        if item_type in {"RECRUIT_TICKET", "UPGRADE_TICKET", "CUSTOM_TICKET"}:
            created = []
            for _ in range(count):
                ticket_id = _rlv2.getNextTicketIndex(rlv2)
                _rlv2.addTicket(rlv2, ticket_id, item)
                created.append(ticket_id)
            return created

        if item_type in {"RELIC", "BAND"}:
            created_tickets = []
            relic_id = _rlv2.getNextRelicIndex(rlv2)
            rlv2["inventory"]["relic"][relic_id] = {
                "index": relic_id,
                "id": item,
                "count": count,
                "ts": time(),
            }
            relic_data = get_memory("roguelike_topic_table")["details"][theme][
                "relics"
            ].get(item, {})
            for buff in relic_data.get("buffs", []):
                if buff["key"] == "level_life_point_add":
                    blackboard = {
                        entry["key"]: entry for entry in buff["blackboard"]
                    }
                    trigger = blackboard.get("trig_type", {}).get("valueStr")
                    if trigger is None:
                        rlv2["buff"]["tmpHP"] += int(
                            blackboard.get("value", {}).get("value", 0)
                        )
                    continue
                if buff["key"] not in {
                    "immediate_reward",
                    "immediate_cost",
                    "item_cover_set",
                }:
                    continue
                blackboard = {entry["key"]: entry for entry in buff["blackboard"]}
                reward_id = blackboard.get("id", {}).get("valueStr")
                reward_count = int(blackboard.get("count", {}).get("value", 0))
                if buff["key"] == "immediate_cost":
                    if reward_id is None or reward_count <= 0:
                        continue
                    if _rlv2.grant_resource(rlv2, reward_id, -reward_count):
                        continue
                    if reward_id in theme_data["items"]:
                        if not _rlv2.remove_item(rlv2, reward_id, reward_count):
                            raise ValueError(
                                f"failed to consume immediate item cost: {reward_id}"
                            )
                    continue
                if reward_id is not None and reward_count > 0:
                    granted = _rlv2.grant_resource(
                        rlv2,
                        reward_id,
                        reward_count,
                        cover=buff["key"] == "item_cover_set",
                    )
                    if not granted:
                        items = get_memory("roguelike_topic_table")["details"][theme][
                            "items"
                        ]
                        if reward_id in items:
                            result = _rlv2.add_item(
                                rlv2, reward_id, reward_count
                            )
                            if isinstance(result, list):
                                created_tickets.extend(result)
                        else:
                            unresolved = rlv2["inventory"]["consumable"]
                            unresolved[reward_id] = (
                                reward_count
                                if buff["key"] == "item_cover_set"
                                else unresolved.get(reward_id, 0) + reward_count
                            )
            _rlv2.applyEndingItem(rlv2, item)
            clamp_sanity_module(rlv2["module"])
            return created_tickets or relic_id

        if item_type == "ACTIVE_TOOL":
            rlv2["inventory"]["trap"] = {
                "index": item,
                "id": item,
                "count": count,
                "ts": time(),
            }
            return item

        if item_type == "EXPLORE_TOOL":
            tool_id = _rlv2.getNextExploreToolIndex(rlv2)
            rlv2["inventory"]["exploreTool"][tool_id] = {
                "index": tool_id,
                "id": item,
                "count": count,
                "ts": time(),
            }
            return tool_id

        if item_type == "FRAGMENT":
            fragment = rlv2.get("module", {}).get("fragment")
            if not isinstance(fragment, dict) or not isinstance(
                fragment.get("fragments"), dict
            ):
                raise ValueError("fragment item requires the RO4 fragment module")
            fragment_data = (
                topic_table.get("modules", {})
                .get(theme, {})
                .get("fragment", {})
                .get("fragmentData", {})
                .get(item)
            )
            if not isinstance(fragment_data, dict):
                raise ValueError(f"missing fragment data: {item}")
            created = []
            for _ in range(count):
                fragment_id = _rlv2.getNextFragmentIndex(rlv2)
                fragment["fragments"][fragment_id] = {
                    "id": item,
                    "index": fragment_id,
                    "used": False,
                    "ts": time(),
                    "weight": int(fragment_data.get("weight", 0)),
                    "value": int(fragment_data.get("value", 0)),
                    "price": 0,
                }
                created.append(fragment_id)
            _rlv2.recalculateFragmentWeight(rlv2)
            return created[0] if created else None

        if _rlv2.grant_resource(rlv2, item, count):
            return item

        consumable = rlv2["inventory"]["consumable"]
        consumable[item] = consumable.get(item, 0) + count
        _rlv2.applyEndingItem(rlv2, item)
        return item

    def remove_item(rlv2: dict, item: str, count: int = 1):
        if not isinstance(item, str) or type(count) is not int or count <= 0:
            return False
        inventory = rlv2["inventory"]
        relics = inventory["relic"]
        recruit = inventory["recruit"]
        consumable = inventory["consumable"]
        tools = inventory["exploreTool"]
        trap = inventory.get("trap")
        fragment = rlv2.get("module", {}).get("fragment")
        fragments = fragment.get("fragments") if isinstance(fragment, dict) else None
        available = consumable.get(item, 0)
        available += sum(
            relic.get("count", 1)
            for relic in relics.values()
            if relic.get("id") == item
        )
        available += sum(
            ticket.get("count", 1)
            for ticket in recruit.values()
            if ticket.get("id") == item
        )
        available += sum(
            tool.get("count", 1)
            for tool in tools.values()
            if tool.get("id") == item
        )
        if isinstance(trap, dict) and trap.get("id") == item:
            available += trap.get("count", 1)
        if isinstance(fragments, dict):
            available += sum(
                max(1, int(entry.get("count", 1)))
                for entry in fragments.values()
                if isinstance(entry, dict) and entry.get("id") == item
            )
        if available < count:
            return False

        remaining = count
        for collection in (relics, recruit):
            for index, entry in list(collection.items()):
                if remaining <= 0 or entry.get("id") != item:
                    continue
                entry_count = max(1, int(entry.get("count", 1)))
                removed = min(entry_count, remaining)
                if removed == entry_count:
                    del collection[index]
                else:
                    entry["count"] = entry_count - removed
                remaining -= removed

        if remaining and item in consumable:
            removed = min(int(consumable[item]), remaining)
            consumable[item] -= removed
            remaining -= removed
            if consumable[item] <= 0:
                consumable.pop(item, None)

        if remaining and isinstance(trap, dict) and trap.get("id") == item:
            trap_count = max(1, int(trap.get("count", 1)))
            removed = min(trap_count, remaining)
            remaining -= removed
            if removed == trap_count:
                inventory["trap"] = None
            else:
                trap["count"] = trap_count - removed

        for index, tool in list(tools.items()):
            if remaining <= 0 or tool.get("id") != item:
                continue
            tool_count = max(1, int(tool.get("count", 1)))
            removed = min(tool_count, remaining)
            remaining -= removed
            if removed == tool_count:
                del tools[index]
            else:
                tool["count"] = tool_count - removed
        if remaining and isinstance(fragments, dict):
            for index, entry in list(fragments.items()):
                if remaining <= 0 or not isinstance(entry, dict):
                    continue
                if entry.get("id") != item:
                    continue
                del fragments[index]
                remaining -= 1
            _rlv2.recalculateFragmentWeight(rlv2)
        return remaining == 0

    def ro5_drawCopper(randomseed:str):
        coppper_bag = {}

        rng = random.Random(f"{randomseed}_initial_copper")
        copper_list = [
            "rogue_5_copper_B_01_a",
            "rogue_5_copper_B_01_a",
            "rogue_5_copper_B_01_a",
            "rogue_5_copper_B_02_a",
            "rogue_5_copper_B_03_a",
            "rogue_5_copper_B_04_a",
            "rogue_5_copper_B_05_a",
        ]

        for i in range(7):
            copper_data = {
                "id": copper_list[i],
                "isDrawn": False,
                "layer": -1,
                "countDown": -1,
                "ts": time()
                }
                
            coppper_bag[f"c_{i}"] = copper_data
        
        drawn_list = rng.sample(list(coppper_bag.keys()), 3)

        for copper in drawn_list:#wz
            coppper_bag[copper]["isDrawn"] = True

        return coppper_bag, drawn_list
    
    def ro4_troopWeights_calculate(rlv2:dict):
        character_star = get_memory("character_star")
        troopWeights = {}
        char_load_data = {"6": 6, "5": 5, "4": 4, "3": 2, "2": 2, "1": 2}

        for key, value in rlv2["troop"]["chars"].items():
            if value["charId"] == "char_4151_tinman":#wz
                troopWeights[key] = 10
            else:
                char_id = value["charId"]
                char_star = str(character_star[char_id])
                cahr_load = char_load_data[char_star]
                troopWeights[key] = cahr_load

        return troopWeights

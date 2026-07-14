from flask import request
from copy import deepcopy
from collections import deque
from contextvars import ContextVar
from functools import wraps
from virtualtime import time
import random
import os
import re
import hashlib

from constants import (
    SYNC_DATA_TEMPLATE_PATH,
    RLV2_USER_SETTINGS_PATH,
    CONFIG_PATH,
    RLV2_SETTINGS_PATH,
)

from utils import read_json, decrypt_battle_data, writeLog, get_memory
from rlv2_logic import (
    apply_numeric_delta,
    battle_base_reward,
    battle_resource_item_ids,
    build_initial_property,
    clamp_player_property,
    collect_difficulty_buffs,
    enforce_emergency_node_limits,
    has_numeric_cost,
    prepare_recruit_candidates,
    prepare_predefined_characters,
    recruit_group_ticket_ids,
    resolve_player_levels,
    select_equivalent_grade,
    select_init_config,
    select_player_level_table,
    settle_battle_life,
)
from rlv2_repository import (
    InvalidUserIdError,
    LegacyMirrorError,
    MissingUserIdError,
    RunRepositoryError,
    get_run_repository,
)
import data.rlv2_data


_ACTIVE_RUN_TRANSACTION = ContextVar("active_rlv2_transaction", default=None)


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
            return result
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
    return _active_transaction().run


def _load_server_data() -> dict:
    return _active_transaction().server_data


def _persist_run(rlv2: dict, server_data: dict | None = None) -> None:
    transaction = _active_transaction()
    transaction.run = rlv2
    if server_data is not None:
        transaction.server_data = server_data


@_serialized_run
def rlv2GiveUpGame():
    server_data = _load_server_data()
    seed = server_data["rlv2_seed"]
    deque_seed = deque(server_data["seed_list"])
    if seed is not None:
        deque_seed.appendleft(seed)
    server_data["seed_list"] = list(deque_seed)
    server_data["rlv2_seed"] = None

    empty_run = {
        "player": None,
        "record": None,
        "map": None,
        "troop": None,
        "inventory": None,
        "game": None,
        "buff": None,
        "module": None,
    }
    _persist_run(empty_run, server_data)
    return {
        "result": "ok",
        "playerDataDelta": {
            "modified": {
                "rlv2": {
                    "current": {
                        "player": None,
                        "record": None,
                        "map": None,
                        "troop": None,
                        "inventory": None,
                        "game": None,
                        "buff": None,
                        "module": None,
                    }
                }
            },
            "deleted": {},
        },
    }


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

    config = read_json(CONFIG_PATH)
    if config["rlv2Config"]["allChars"]:
        chars = _rlv2.getChars(use_user_defaults=True)
        unique_chars = {}
        for char in chars:
            key = (char["charId"], char.get("currentTmpl"))
            if (
                key not in unique_chars
                or char["evolvePhase"] > unique_chars[key]["evolvePhase"]
            ):
                unique_chars[key] = char
        for i, char in enumerate(unique_chars.values()):
            char_id = getNextCharId(rlv2)
            char["instId"] = char_id
            rlv2["troop"]["chars"][char_id] = char

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

    choice_data = event_choices.get(theme, {}).get("choices", {}).get(choice)
    if choice == "choice_leave" and choice_data is None:
        choice_data = {"choices": [], "lose": None, "get": None}
    table_choice = rlv2_table["details"][theme]["choices"].get(choice)
    if choice_data is None or table_choice is None:
        return {"error": f"invalid roguelike choice: {choice}"}, 400

    cursor = rlv2["player"]["cursor"]
    rng = random.Random(
        f"{server_data.get('rlv2_seed')}_{theme}_{cursor['zone']}_"
        f"{cursor.get('position')}_{choice}"
    )

    def leave():
        rlv2["player"]["state"] = "WAIT_MOVE"
        _rlv2.finishNode(rlv2, server_data)

    def add_scene_event(scene_id: str, choices: list):
        if not choices:
            choices = ["choice_leave"]
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
                event_choices.get(theme, {}).get("choices", {}).get(choice_id, {}),
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
        candidates = [item_id for item_id in item_ids if item_pattern in item_id]
        if theme == "rogue_2" and "_relic_" in item_pattern:
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
        rlv2["player"]["pending"].insert(
            0,
            {
                "type": "BATTLE",
                "content": {
                    "battle": {
                        "boxInfo": [],
                        "chestCnt": 100,
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

        reward = choice_data.get("get")
        if isinstance(reward, dict):
            apply_numeric_delta(rlv2["player"]["property"], reward)
        elif reward is not None:
            grant_event_items(reward)

        player_level_table, _ = select_player_level_table(
            rlv2_table["details"][theme],
            rlv2["game"]["mode"],
            rlv2["game"]["eGrade"],
            rlv2["game"].get("predefined"),
        )
        resolve_player_levels(rlv2["player"]["property"], player_level_table)
        clamp_player_property(rlv2["player"]["property"])
        if rlv2["player"]["property"]["hp"]["current"] <= 0:
            _rlv2.endRun(rlv2, False, "LIFE_POINT_ZERO")
        else:
            scene_id = table_choice["nextSceneId"]
            if scene_id is None:
                leave()
            else:
                add_scene_event(scene_id, choice_data.get("choices", []))

    if created_tickets and rlv2["player"]["state"] != "GAME_OVER":
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

    config = read_json(CONFIG_PATH)
    if not config["rlv2Config"]["allChars"]:
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
        rlv2["map"]["zones"], seed = _rlv2.getMap_new(theme, server_data["rlv2_seed"], rlv2["player"]["cursor"]["zone"])
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
                    "chestCnt": 100,
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
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "BATTLE":
        return {"error": "battle result is not pending"}, 409

    theme = rlv2["game"]["theme"]
    if battle_data.get("completeState") == 3:
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
                        "show": "1",
                    }
                },
            },
        )
    else:
        _rlv2.endRun(rlv2, False, "BATTLE_ABORTED")
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
def rlv2FinishBattleReward():
    server_data = _load_server_data()
    rlv2 = _load_run()
    pending = rlv2["player"]["pending"]
    if not pending or pending[0].get("type") != "BATTLE_REWARD":
        return {"error": "battle reward settlement is not pending"}, 409
    theme = rlv2["game"]["theme"]
    theme_data = get_memory("roguelike_topic_table")["details"][theme]
    try:
        gold_item_id = battle_resource_item_ids(theme_data)["gold"]
    except ValueError as exc:
        return {"error": str(exc)}, 500
    rewards = pending[0]["content"]["battleReward"].get("rewards", [])
    has_unclaimed_gold = any(
        not reward.get("done")
        and len(reward.get("items", [])) == 1
        and reward["items"][0].get("id") == gold_item_id
        for reward in rewards
    )
    if has_unclaimed_gold:
        return {"error": "battle gold reward must be claimed first"}, 409
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
        item_pool = list(dict.fromkeys(item_pool))
        sampled_items = rng.sample(item_pool, min(5, len(item_pool)))
        shop_items = [ticket, *sampled_items]
        rarity_price = {"NORMAL": 8, "RARE": 12, "SUPER_RARE": 16}
        goods = []
        for index, item_id in enumerate(shop_items):
            item_data = theme_data["items"][item_id]
            price = 4 if item_data["type"] == "RECRUIT_TICKET" else rarity_price.get(
                item_data["rarity"], 8
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
        case 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048 | 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 | 1048576:
            choices = {}
            choiceAdditional = {}
            scene_id_list = []
            # 获取当前theme全部不期而遇事件
            scene_id_list = list(event_choices[theme]["enter"].keys())
            # 抽一个不期而遇事件
            scene_id:str = rng.choice(scene_id_list)
            # 获取当前不期而遇事件所有选项
            choices_list:list = event_choices[theme]["enter"][scene_id]
            if not choices_list:
                choices_list = ["choice_leave"]
            # 添加全部可选项
            for choices_id in choices_list:
                available = choices_id == "choice_leave" or _rlv2.canPayChoice(
                    rlv2,
                    event_choices[theme]["choices"].get(choices_id, {}),
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

def rlv2ReadEndingChange():
    return {}, 202

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
        rlv2["player"]["state"] = "GAME_OVER"
        rlv2["player"]["pending"] = []
        rlv2["player"]["trace"] = []
        rlv2["player"]["status"]["gameResult"] = {
            "success": success,
            "reason": reason,
            "ending": rlv2["player"].get("toEnding") if success else None,
        }

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
        return any(
            tool["id"] == item and tool.get("count", 1) >= count
            for tool in rlv2["inventory"].get("exploreTool", {}).values()
        )

    def canPayChoice(rlv2: dict, choice_data: dict) -> bool:
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
        if cursor["zone"] >= 5:
            _rlv2.endRun(rlv2, True, "ENDING_REACHED")
            return True

        cursor["zone"] += 1
        cursor["position"] = None
        zones, seed = _rlv2.getMap_new(
            rlv2["game"]["theme"], server_data.get("rlv2_seed"), cursor["zone"]
        )
        rlv2["map"]["zones"] = zones
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
        
    def getMap_new(theme: str, seed: str = None, zone: int = 1):
        rlv2_table = get_memory("roguelike_topic_table")
        theme_data = rlv2_table["details"][theme]
        stages_list: list[str] = theme_data["stages"].keys()

        # 随机种子
        if seed is None:
            randomseed = os.urandom(16).hex()
            writeLog(f"本次种子：{randomseed}")
        else:
            randomseed = seed

        rng = random.Random(f"{randomseed}_{zone}_{theme}")

        # 商店类型
        shop = 4096 if theme != "rogue_1" else 8
        wish = 512 if theme != "rogue_1" else 64

        zone_map = {
            str(zone): {
                "id": f"zone_{zone}",
                "nodes": {},
                "variation": []
            }
        }

        refresh_count = 1 if theme == "rogue_4" else 0
        nodetemp = {
            "pos": {"x": 0, "y": 0},
            "next": [],
            "type": 0,
            "refresh": {"usedCount": 0, "count": refresh_count, "cost": 1}
        }

        # 节点类型权重
        type_weight: dict[int, int] = {}
        type_weight.update({1:60, 2:15, 32:20, wish:20})

        if zone > 1:
            type_weight.setdefault(16, 20)
            match theme:
                case "rogue_1":
                    type_weight.update({
                        4: 10, 8: 10, 64: 10, 128: 10, 256: 10
                    })
                case "rogue_2":
                    type_weight.update({
                        4: 10, 1024: 10, 2048: 10, 4096: 10, 8192: 10, 16384: 10
                    })
                case "rogue_3":
                    type_weight.update({
                        4: 10, 1024: 10, 2048: 10, 4096: 10, 8192: 10, 65536: 10
                    })
                case "rogue_4":
                    type_weight.update({
                        4: 10, 128: 10, 256: 10, 1024: 10, 2048: 10, 
                        4096: 10, 8192: 10, 131072: 10, 262144: 10
                    })
                case "rogue_5":
                    type_weight.update({
                        4: 10, 1024: 10, 2048: 10, 4096: 10, 8192: 10, 
                        262144: 10, 524288: 10
                    })
                case _:
                    pass

        items = sorted(type_weight.items())
        type_list = [k for k, _ in items]
        type_weight = [v for _, v in items]


        # 坐标最大值
        y_max = [None, 2, 3, 4, 4, 4, 4, 4, 4]

        ro_num = theme.split("_")[1]
        normal_list = [s for s in stages_list if s.startswith(f"ro{ro_num}_n_{zone}_")]
        elite_list  = [s for s in stages_list if s.startswith(f"ro{ro_num}_e_{zone}_")]
        boss_list   = [
            s for s in stages_list
            if re.fullmatch(rf"ro{ro_num}_b_[1-9]", s)
        ]

        # 路径数据
        nodes_by_x: dict[int, list[int]] = {}
        can_add_shop = True
        zone_1 = True if zone == 1 else False

        # 可复现非random随机
        def rand_by_key(seed: str, *keys, mod: int) -> int:
            h = hashlib.md5(f"{seed}_{'_'.join(map(str, keys))}".encode()).hexdigest()
            return int(h, 16) % mod

        # 随机节点生成
        for x in range(0, zone * 2):
            nodes_by_x[x] = []
            is_end_col = (not zone_1 and x == zone * 2 - 1)

            # end_node 单独生成
            if is_end_col:
                match zone:
                    case 2:
                        end_type = wish
                        end_count = 2
                    case 3 | 5:
                        end_type = 4
                        end_count = 1
                    case 4:
                        end_type = wish
                        end_count = 1
                    case _:
                        end_type = 0
                        end_count = 1

                for y in range(end_count):
                    node = deepcopy(nodetemp)
                    node_index = x * 100 + y

                    node["pos"]["x"] = x
                    node["pos"]["y"] = y
                    node["index"] = str(node_index)
                    node["type"] = end_type
                    node["zone_end"] = True

                    if end_type == 4:
                        node["stage"] = rng.choice(boss_list)

                    zone_map[str(zone)]["nodes"][node["index"]] = node
                    nodes_by_x[x].append(y)

                continue

            #普通列，正常 y_size 随机
            y_size = rand_by_key(randomseed, zone, x, mod=y_max[zone]) + 1

            if can_add_shop and x > 0:
                type_list.append(shop)
                type_weight.append(10)
                can_add_shop = False

            for y in range(y_size):
                node = deepcopy(nodetemp)
                node_index = x * 100 + y

                node_type = rng.choices(type_list, weights=type_weight, k=1)[0]

                node["pos"]["x"] = x
                node["pos"]["y"] = y
                node["index"] = str(node_index)
                node["type"] = node_type

                match node_type:
                    case 1:
                        node["stage"] = rng.choice(normal_list)
                    case 2:
                        node["stage"] = rng.choice(elite_list)

                zone_map[str(zone)]["nodes"][node["index"]] = node
                nodes_by_x[x].append(y)

        # 第一层固定节点
        if zone_1:
            end_type = 1048576 if ro_num == "5" else shop
            z1_node = shop if ro_num == "5" else 32
            zone1_nodes = {
                "200": {
                    "index": "200",
                    "pos": {"x": 2, "y": 0},
                    "next": [{"x": 3, "y": 0}],
                    "type": z1_node,
                    "refresh": {"usedCount": 0, "count": refresh_count, "cost": 1}
                },
                "201": {
                    "index": "201",
                    "pos": {"x": 2, "y": 1},
                    "next": [{"x": 3, "y": 0}],
                    "type": z1_node,
                    "refresh": {"usedCount": 0, "count": refresh_count, "cost": 1}
                },
                "300": {
                    "index": "300",
                    "pos": {"x": 3, "y": 0},
                    "next": [],
                    "type": end_type,
                    "zone_end": True
                }
            }

            zone_map[str(zone)]["nodes"].update(zone1_nodes)
            nodes_by_x[2] = [0, 1]
            nodes_by_x[3] = [0]

        enforce_emergency_node_limits(
            theme,
            zone,
            zone_map[str(zone)]["nodes"],
            normal_list,
            elite_list,
            rng,
        )

        # 路径分配
        for idx, node in zone_map[str(zone)]["nodes"].items():
            x:int = node["pos"]["x"]
            y:int = node["pos"]["y"]

            # zone1 固定节点，跳过
            if zone == 1 and x >= 2:
                continue

            node["next"] = []

            # 横向
            if x + 1 in nodes_by_x:
                candidates = []
                for ny in (y - 1, y, y + 1):
                    if ny in nodes_by_x[x + 1]:
                        candidates.append({"x": x + 1, "y": ny})

                if candidates:
                    k = rng.randint(1, min(2, len(candidates)))
                    node["next"].extend(rng.sample(candidates, k))

            # 纵向
            if x != 0:
                for ny in (y - 1, y + 1):
                    if ny in nodes_by_x.get(x, []):
                        if rng.random() < 0.3:
                            edge = {"x": x, "y": ny}
                            if (
                                theme_data["gameConst"].get("unlockRouteItemId")
                                and rng.random() < 0.5
                            ):
                                edge["key"] = True
                            node["next"].append(edge)

        # 路径检查
        incoming = {idx: False for idx in zone_map[str(zone)]["nodes"]}

        for src in zone_map[str(zone)]["nodes"].values():
            sx = src["pos"]["x"]
            for e in src.get("next", []):
                if e["x"] == sx + 1:
                    tidx = str(e["x"] * 100 + e["y"])
                    if tidx in incoming:
                        incoming[tidx] = True
        def has_outgoing(node):
            x = node["pos"]["x"]
            return any(e["x"] == x + 1 for e in node.get("next", []))
        x_last = max(nodes_by_x.keys())
        for idx, node in zone_map[str(zone)]["nodes"].items():
            x = node["pos"]["x"]
            y = node["pos"]["y"]

            in_ok  = incoming.get(idx, False)
            out_ok = has_outgoing(node)
            # x为0时只要求 outgoing
            if x == 0:
                if out_ok:
                    continue

                ny = min(nodes_by_x[x + 1], key=lambda v: abs(v - y))
                node["next"].append({"x": x + 1, "y": ny})
                continue

            # x为last时只要求 incoming
            if x == x_last:
                if in_ok:
                    continue

                py = min(nodes_by_x[x - 1], key=lambda v: abs(v - y))
                prev_idx = str((x - 1) * 100 + py)
                zone_map[str(zone)]["nodes"][prev_idx]["next"].append({
                    "x": x,
                    "y": y
                })
                continue

            # 中间列的 incoming 和 outgoing 都要有横向连接
            if not in_ok:
                py = min(nodes_by_x[x - 1], key=lambda v: abs(v - y))
                prev_idx = str((x - 1) * 100 + py)
                zone_map[str(zone)]["nodes"][prev_idx]["next"].append({
                    "x": x,
                    "y": y
                })

            if not out_ok:
                ny = min(nodes_by_x[x + 1], key=lambda v: abs(v - y))
                node["next"].append({
                    "x": x + 1,
                    "y": ny
                })


        # 节点排序
        for node in zone_map[str(zone)]["nodes"].values():
            if "next" in node and node["next"]:
                node["next"].sort(key=lambda e: (e["x"], e["y"]))

        return zone_map, randomseed

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
            prop["population"]["max"] = (
                count if cover else prop["population"]["max"] + count
            )
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
        else:
            return False

        clamp_player_property(prop)
        return True

    def add_item(rlv2: dict, item: str, count: int = 1):
        theme = rlv2["game"]["theme"]
        item_data = get_memory("roguelike_topic_table")["details"][theme][
            "items"
        ].get(item)
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
                if buff["key"] not in {"immediate_reward", "item_cover_set"}:
                    continue
                blackboard = {entry["key"]: entry for entry in buff["blackboard"]}
                reward_id = blackboard.get("id", {}).get("valueStr")
                reward_count = int(blackboard.get("count", {}).get("value", 0))
                if reward_id is not None:
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

        if _rlv2.grant_resource(rlv2, item, count):
            return item

        consumable = rlv2["inventory"]["consumable"]
        consumable[item] = consumable.get(item, 0) + count
        return item

    def remove_item(rlv2: dict, item: str, count: int = 1):
        for index, relic in list(rlv2["inventory"]["relic"].items()):
            if relic["id"] != item:
                continue
            if relic["count"] > count:
                relic["count"] -= count
            else:
                del rlv2["inventory"]["relic"][index]
            return True

        for index, ticket in list(rlv2["inventory"]["recruit"].items()):
            if ticket["id"] == item:
                del rlv2["inventory"]["recruit"][index]
                return True

        consumable = rlv2["inventory"]["consumable"]
        if item in consumable:
            consumable[item] = max(0, consumable[item] - count)
            if consumable[item] == 0:
                del consumable[item]
            return True

        if rlv2["inventory"]["trap"] is not None:
            if rlv2["inventory"]["trap"]["id"] == item:
                rlv2["inventory"]["trap"] = None
                return True

        for index, tool in list(rlv2["inventory"]["exploreTool"].items()):
            if tool["id"] == item:
                del rlv2["inventory"]["exploreTool"][index]
                return True
        return False

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

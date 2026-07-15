"""Strict runtime overlay for event rules backed by client and fixed PRTS data."""

from __future__ import annotations

from copy import deepcopy


_RUNTIME_EVENT_RULES = {
    "rogue_1": {
        "sceneRules": {
            "scene_side1_enter": {"runtimeEnabled": True},
            "scene_hidden1_enter": {"runtimeEnabled": True},
            "scene_writer1_enter": {"runtimeEnabled": True},
            "scene_writer2_enter": {
                "runtimeEnabled": True,
                "require": {"items": {"rogue_1_relic_n01": 1}},
            },
        },
        "choices": {
            "choice_writer1_3": {
                "eventBattleReward": "rogue_1_relic_n01",
            },
            "choice_writer2_3": {
                "eventBattleReward": "rogue_1_relic_n02",
            },
        },
    },
    "rogue_2": {
        "sceneRules": {
            "scene_ro2_bossa1_enter": {"runtimeEnabled": True},
            "scene_ro2_bossa2_enter": {
                "runtimeEnabled": True,
                "require": {
                    "items": {"rogue_2_relic_grace_83": 1},
                    "notItems": {"rogue_2_relic_grace_84": 1},
                },
            },
            "scene_ro2_bossb1_enter": {"runtimeEnabled": True},
            "scene_ro2_bossb2_enter": {
                "runtimeEnabled": True,
                "sample": 4,
                "required": ["choice_ro2_bossb2_6"],
                "require": {
                    "items": {"rogue_2_relic_curse_7": 1},
                    "moduleMin": {"san": {"sanity": 20}},
                },
            },
        },
        "choices": {
            # The client table proves the dice threshold, but not the pending
            # response shape for its two outcomes. Keep only this option off.
            "choice_ro2_bossa1_2": {"runtimeEnabled": False},
            "choice_ro2_bossb2_6": {"m_lose": None},
        },
    },
    "rogue_3": {
        "enter": {
            "scene_ro3_story1_enter": [
                "choice_ro3_story1_1",
                "choice_ro3_story1_2",
            ],
            "scene_ro3_story2_enter": [
                "choice_ro3_story2_1",
                "choice_ro3_story2_2",
            ],
            "scene_ro3_story3_enter": [
                "choice_ro3_story3_1",
                "choice_ro3_story3_2",
            ],
            "scene_ro3_ex1_enter": [
                "choice_ro3_ex1_1",
                "choice_ro3_ex1_2",
            ],
            "scene_ro3_ex2_enter": [
                "choice_ro3_ex2_1",
                "choice_ro3_ex2_2",
                "choice_ro3_ex2_3",
            ],
            # The fixed page says the result is random but gives no weights.
            "scene_ro3_ex3_enter": ["choice_leave"],
        },
        "sceneRules": {
            "scene_ro3_story1_enter": {"runtimeEnabled": True},
            "scene_ro3_story2_enter": {"runtimeEnabled": True},
            "scene_ro3_story3_enter": {
                "runtimeEnabled": True,
                "require": {"items": {"rogue_3_relic_boss_2b": 1}},
            },
            "scene_ro3_ex1_enter": {
                "runtimeEnabled": True,
                "require": {"items": {"rogue_3_relic_boss_4a": 1}},
            },
            "scene_ro3_ex2_enter": {"runtimeEnabled": True},
            "scene_ro3_ex3_enter": {"runtimeEnabled": True},
        },
        "choices": {
            "choice_ro3_story1_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro3_story1_2": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_3_relic_boss_1": 1}},
                "lose": None,
                "get": "rogue_3_feature_ending_2",
            },
            "choice_ro3_story2_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_3_relic_boss_1",
            },
            "choice_ro3_story2_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": {"hp": {"current": 3}},
            },
            "choice_ro3_story3_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_3_relic_boss_2",
            },
            "choice_ro3_story3_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
                "m_lose": {"chaos": {"value": 3}},
            },
            "choice_ro3_ex1_1": {
                "choices": ["choice_ro3_ex1_3"],
                "lose": None,
                "get": None,
            },
            "choice_ro3_ex1_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro3_ex1_3": {
                "choices": "ro3_ev_8",
                "lose": None,
                "get": None,
                "eventBattleReward": "rogue_3_relic_boss_4b",
            },
            "choice_ro3_ex2_1": {
                "choices": [
                    "choice_ro3_ex2_4",
                    "choice_ro3_ex2_5",
                    "choice_ro3_ex2_6",
                    "choice_ro3_ex2_7",
                ],
                "lose": None,
                "get": "rogue_3_relic_curse_1",
            },
            "choice_ro3_ex2_2": {
                "choices": [
                    "choice_ro3_ex2_4",
                    "choice_ro3_ex2_5",
                    "choice_ro3_ex2_6",
                    "choice_ro3_ex2_7",
                ],
                "lose": None,
                "m_lose": {"vision": {"value": 3}},
                "get": None,
            },
            "choice_ro3_ex2_3": {
                "choices": [
                    "choice_ro3_ex2_4",
                    "choice_ro3_ex2_5",
                    "choice_ro3_ex2_6",
                    "choice_ro3_ex2_7",
                ],
                "lose": "rogue_3_relic_explore_6",
                "get": None,
            },
            "choice_ro3_ex2_4": {
                "choices": [
                    "choice_ro3_ex2_8",
                    "choice_ro3_ex2_9",
                    "choice_ro3_ex2_10",
                    "choice_ro3_ex2_11",
                ],
                "lose": None,
                "get": "rogue_3_relic_curse_2",
            },
            "choice_ro3_ex2_5": {
                "choices": [
                    "choice_ro3_ex2_8",
                    "choice_ro3_ex2_9",
                    "choice_ro3_ex2_10",
                    "choice_ro3_ex2_11",
                ],
                "lose": {"gold": 50},
                "get": None,
            },
            "choice_ro3_ex2_6": {
                "choices": [
                    "choice_ro3_ex2_8",
                    "choice_ro3_ex2_9",
                    "choice_ro3_ex2_10",
                    "choice_ro3_ex2_11",
                ],
                "lose": "rogue_3_relic_boss_1",
                "get": None,
            },
            "choice_ro3_ex2_7": {
                "choices": [
                    "choice_ro3_ex2_8",
                    "choice_ro3_ex2_9",
                    "choice_ro3_ex2_10",
                    "choice_ro3_ex2_11",
                ],
                "lose": "rogue_3_relic_explore_6",
                "get": None,
            },
            "choice_ro3_ex2_8": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_3_relic_curse_3",
            },
            "choice_ro3_ex2_9": {
                "choices": ["choice_leave"],
                "lose": {"population": {"max": 20}},
                "get": None,
            },
            "choice_ro3_ex2_10": {
                "choices": ["choice_leave"],
                "lose": "rogue_3_relic_boss_2",
                "get": None,
            },
            "choice_ro3_ex2_11": {
                "choices": ["choice_leave"],
                "lose": "rogue_3_relic_explore_6",
                "get": None,
            },
        },
    },
    "rogue_4": {
        "enter": {
            "scene_ro4_fin1_enter": [
                "choice_ro4_fin1_1",
                "choice_ro4_fin1_2",
            ],
            "scene_ro4_end1_enter": [
                "choice_ro4_end1_1",
                "choice_ro4_end1_2",
            ],
            "scene_ro4_end2_enter": [
                "choice_ro4_end2_1",
                "choice_ro4_end2_2",
            ],
            "scene_ro4_fin3_enter": [
                "choice_ro4_fin3_1",
                "choice_ro4_fin3_2",
            ],
            "scene_ro4_fin4_enter": [
                "choice_ro4_fin4_1",
                "choice_ro4_fin4_4",
                "choice_ro4_fin5_1",
                "choice_ro4_fin5_4",
                "choice_ro4_fin6_1",
                "choice_ro4_fin6_4",
                "choice_leave",
            ],
        },
        "sceneRules": {
            "scene_ro4_fin1_enter": {"runtimeEnabled": True},
            "scene_ro4_end1_enter": {"runtimeEnabled": True},
            "scene_ro4_end2_enter": {
                "runtimeEnabled": True,
                "require": {"items": {"rogue_4_relic_final_2": 1}},
            },
            "scene_ro4_fin3_enter": {"runtimeEnabled": True},
            "scene_ro4_fin4_enter": {
                "runtimeEnabled": True,
                "require": {
                    "itemsAny": {
                        "rogue_4_fragment_D_20": 1,
                        "rogue_4_fragment_D_21": 1,
                        "rogue_4_fragment_D_22": 1,
                    }
                },
            },
        },
        "choices": {
            "choice_ro4_fin1_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
                "getAll": [
                    "rogue_4_fragment_D_01",
                    "rogue_4_fragment_D_02",
                ],
            },
            "choice_ro4_fin1_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_4_relic_",
            },
            "choice_ro4_end1_1": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_relic_final_1": 1}},
                "lose": None,
                "get": "rogue_4_feature_ending_2",
            },
            "choice_ro4_end1_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro4_end2_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_4_relic_final_4",
            },
            "choice_ro4_end2_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro4_fin3_1": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_4_relic_final_7",
            },
            "choice_ro4_fin3_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": "rogue_4_relic_",
            },
            "choice_ro4_fin4_1": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_20": 1}},
                "lose": "rogue_4_fragment_D_20",
                "getAll": [
                    "rogue_4_relic_final_8",
                    "rogue_4_relic_final_11",
                ],
            },
            "choice_ro4_fin4_4": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_20": 1}},
                "lose": "rogue_4_fragment_D_20",
                "getAll": ["rogue_4_relic_final_8"],
            },
            "choice_ro4_fin5_1": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_21": 1}},
                "lose": "rogue_4_fragment_D_21",
                "getAll": [
                    "rogue_4_relic_final_9",
                    "rogue_4_relic_final_11",
                ],
            },
            "choice_ro4_fin5_4": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_21": 1}},
                "lose": "rogue_4_fragment_D_21",
                "getAll": ["rogue_4_relic_final_9"],
            },
            "choice_ro4_fin6_1": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_22": 1}},
                "lose": "rogue_4_fragment_D_22",
                "getAll": [
                    "rogue_4_relic_final_10",
                    "rogue_4_relic_final_11",
                ],
            },
            "choice_ro4_fin6_4": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_4_fragment_D_22": 1}},
                "lose": "rogue_4_fragment_D_22",
                "getAll": ["rogue_4_relic_final_10"],
            },
        },
    },
    "rogue_5": {
        "enter": {
            "scene_ro5_end1_enter": [
                "choice_ro5_end1_1",
                "choice_ro5_end1_2",
            ],
            "scene_ro5_end2_enter": ["choice_leave"],
            "scene_ro5_end3_enter": ["choice_leave"],
            "scene_ro5_end4_enter": [
                "choice_ro5_end4_2",
                "choice_leave",
            ],
            "scene_ro5_portalboss_enter": ["choice_ro5_portalboss_5"],
        },
        "sceneRules": {
            "scene_ro5_end1_enter": {"runtimeEnabled": True},
            "scene_ro5_end2_enter": {"runtimeEnabled": True},
            "scene_ro5_end3_enter": {"runtimeEnabled": True},
            "scene_ro5_end4_enter": {"runtimeEnabled": True},
            "scene_ro5_portalboss_enter": {
                "runtimeEnabled": True,
                "require": {"items": {"rogue_5_relic_final_7": 1}},
            },
        },
        "choices": {
            "choice_ro5_end1_1": {
                "choices": ["choice_leave"],
                "require": {"items": {"rogue_5_relic_final_4": 1}},
                "lose": None,
                "get": "rogue_5_feature_ending_2",
            },
            "choice_ro5_end1_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro5_end4_2": {
                "choices": ["choice_leave"],
                "lose": None,
                "get": None,
            },
            "choice_ro5_portalboss_5": {
                "choices": ["choice_ro5_portalboss_6"],
                "require": {"items": {"rogue_5_relic_final_7": 1}},
                "lose": None,
                "get": None,
            },
            "choice_ro5_portalboss_6": {
                "choices": "ro5_b_8",
                "lose": None,
                "get": None,
                "eventBattleReward": "rogue_5_relic_final_8",
                "eventBattleRewardRequired": True,
            },
        },
    },
}


FIXED_SCENES = {
    ("rogue_3", 5): "scene_ro3_story1_enter",
    ("rogue_4", 5): "scene_ro4_end1_enter",
    ("rogue_5", 5): "scene_ro5_end1_enter",
    ("rogue_5", 6): "scene_ro5_end2_enter",
    ("rogue_5", 7): "scene_ro5_end3_enter",
    ("rogue_5", 8): "scene_ro5_end4_enter",
}

_RO4_ENDING_WISH_CHOICES = (
    (
        "rogue_4_fragment_D_20",
        "rogue_4_relic_final_8",
        "choice_ro4_fin4_1",
        "choice_ro4_fin4_4",
    ),
    (
        "rogue_4_fragment_D_21",
        "rogue_4_relic_final_9",
        "choice_ro4_fin5_1",
        "choice_ro4_fin5_4",
    ),
    (
        "rogue_4_fragment_D_22",
        "rogue_4_relic_final_10",
        "choice_ro4_fin6_1",
        "choice_ro4_fin6_4",
    ),
)


def _merge_mapping(target: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_mapping(target[key], value)
        else:
            target[key] = deepcopy(value)


def runtime_event_rules(theme: str, base: dict | None) -> dict:
    """Return the legacy event table plus the reviewed executable overlay."""
    base = base if isinstance(base, dict) else {}
    result = dict(base)
    overlay = _RUNTIME_EVENT_RULES.get(theme) if isinstance(theme, str) else None
    if overlay is None:
        return result
    for section_name, section_overlay in overlay.items():
        base_section = base.get(section_name)
        if not isinstance(section_overlay, dict) or not isinstance(base_section, dict):
            result[section_name] = deepcopy(section_overlay)
            continue
        merged_section = dict(base_section)
        for key, value in section_overlay.items():
            existing = base_section.get(key)
            if isinstance(value, dict) and isinstance(existing, dict):
                merged = deepcopy(existing)
                _merge_mapping(merged, value)
                merged_section[key] = merged
            else:
                merged_section[key] = deepcopy(value)
        result[section_name] = merged_section
    return result


def fixed_scene_for_zone(theme: str, zone: int) -> str | None:
    if not isinstance(theme, str) or type(zone) is not int:
        return None
    return FIXED_SCENES.get((theme, zone))


def contextual_event_choices(
    theme: str,
    scene_id: str,
    choice_ids: list[str],
    has_item,
) -> list[str]:
    """Select inventory-dependent protocol variants for reviewed scenes."""
    if (
        theme != "rogue_4"
        or scene_id != "scene_ro4_fin4_enter"
        or not isinstance(choice_ids, list)
        or not callable(has_item)
    ):
        return list(choice_ids) if isinstance(choice_ids, list) else []

    available = set(choice_ids)
    has_key = has_item("rogue_4_relic_final_11")
    resolved = []
    for wish_id, result_id, first_choice, repeat_choice in (
        _RO4_ENDING_WISH_CHOICES
    ):
        if not has_item(wish_id) or has_item(result_id):
            continue
        choice_id = repeat_choice if has_key else first_choice
        if choice_id in available:
            resolved.append(choice_id)
    if resolved and "choice_leave" in available:
        resolved.append("choice_leave")
    return resolved

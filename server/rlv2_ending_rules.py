"""Reviewed runtime rules for RLV2 ending selection and zone routing."""

from __future__ import annotations

from copy import deepcopy

from rlv2_rules import boss_stage_ids


DEFAULT_ENDINGS = {
    "rogue_1": "ro_ending_1",
    "rogue_2": "ro2_ending_1",
    "rogue_3": "ro3_ending_1",
    "rogue_4": "ro4_ending_1",
    "rogue_5": "ro5_ending_1",
}

ENDING_PRIORITIES = {
    "rogue_1": {
        "ro_ending_1": 0,
        "ro_ending_2": 1,
        "ro_ending_3": 2,
        "ro_ending_4": 3,
    },
    "rogue_2": {
        "ro2_ending_1": 0,
        "ro2_ending_2": 1,
        "ro2_ending_3": 2,
        "ro2_ending_4": 3,
    },
    "rogue_3": {
        "ro3_ending_1": 0,
        "ro3_ending_2": 1,
        "ro3_ending_3": 2,
        "ro3_ending_4": 3,
    },
    "rogue_4": {
        "ro4_ending_1": 0,
        "ro4_ending_2": 1,
        "ro4_ending_3": 2,
        "ro4_ending_4": 3,
        "ro4_ending_5": 4,
    },
    "rogue_5": {
        "ro5_ending_1": 0,
        "ro5_ending_2": 1,
        "ro5_ending_3": 2,
        "ro5_ending_4": 3,
        "ro5_ending_5": 4,
    },
}

TERMINAL_ZONES = {
    "rogue_1": {
        "ro_ending_1": 5,
        "ro_ending_2": 5,
        "ro_ending_3": 6,
        "ro_ending_4": 6,
    },
    "rogue_2": {
        "ro2_ending_1": 5,
        "ro2_ending_2": 5,
        "ro2_ending_3": 6,
        "ro2_ending_4": 6,
    },
    "rogue_3": {
        "ro3_ending_1": 5,
        "ro3_ending_2": 5,
        "ro3_ending_3": 6,
        "ro3_ending_4": 7,
    },
    "rogue_4": {
        "ro4_ending_1": 5,
        "ro4_ending_2": 5,
        "ro4_ending_3": 6,
        "ro4_ending_4": 7,
        "ro4_ending_5": 8,
    },
    "rogue_5": {
        "ro5_ending_1": 5,
        "ro5_ending_2": 5,
        "ro5_ending_3": 6,
        "ro5_ending_4": 7,
        "ro5_ending_5": 8,
    },
}

OVERLAY_ENDINGS = frozenset({"ro4_ending_5", "ro5_ending_5"})

# These are the final, unambiguous triggers from the fixed PRTS entry text.
ENDING_ON_ACQUIRE = {
    "rogue_1": {
        "rogue_1_relic_m16": "ro_ending_2",
        "rogue_1_relic_m21": "ro_ending_3",
        "rogue_1_relic_n02": "ro_ending_4",
    },
    "rogue_2": {
        "rogue_2_relic_grace_83": "ro2_ending_2",
        "rogue_2_relic_curse_8": "ro2_ending_3",
        "rogue_2_relic_grace_88": "ro2_ending_4",
        "rogue_2_relic_grace_89": "ro2_ending_4",
        "rogue_2_relic_grace_90": "ro2_ending_4",
    },
    "rogue_3": {
        "rogue_3_feature_ending_2": "ro3_ending_2",
        "rogue_3_relic_boss_2": "ro3_ending_3",
        "rogue_3_relic_boss_4b": "ro3_ending_4",
    },
    "rogue_4": {
        "rogue_4_feature_ending_2": "ro4_ending_2",
        "rogue_4_feature_ending_2_sp": "ro4_ending_2",
        "rogue_4_feature_ending_2_hard": "ro4_ending_2",
        "rogue_4_feature_ending_2_hard_sp": "ro4_ending_2",
        "rogue_4_relic_final_4": "ro4_ending_3",
        "rogue_4_relic_final_6": "ro4_ending_4",
        "rogue_4_relic_final_11": "ro4_ending_5",
    },
    "rogue_5": {
        "rogue_5_feature_ending_2": "ro5_ending_2",
        "rogue_5_feature_ending_2_sp": "ro5_ending_2",
        "rogue_5_relic_final_1": "ro5_ending_3",
        "rogue_5_relic_final_6": "ro5_ending_4",
        "rogue_5_relic_final_8": "ro5_ending_5",
    },
}

# The retreat relic cancels only the knight branch. A concurrently active
# higher-priority RO2 ending remains selected, but its zone-5 base boss must
# be rebuilt from the default route instead of the knight route.
ENDING_BRANCH_RESETS = {
    "rogue_2": {
        "rogue_2_relic_grace_84": (
            "ro2_ending_2",
            "ro2_ending_1",
        ),
    },
}

# Narrative items must only come from their reviewed event, battle, or route.
# rogue_3_relic_boss_4a is intentionally absent: PRTS explicitly allows it
# through normal acquisition and sells it in the trader for one ingot.
EVENT_ONLY_ITEM_IDS = frozenset(
    {
        *(f"rogue_1_relic_m{index:02d}" for index in range(1, 22)),
        "rogue_1_relic_n01",
        "rogue_1_relic_n02",
        *(f"rogue_2_relic_grace_{index}" for index in range(83, 91)),
        *(f"rogue_2_relic_curse_{index}" for index in range(7, 11)),
        "rogue_3_feature_ending_2",
        "rogue_3_relic_boss_1",
        "rogue_3_relic_boss_2",
        "rogue_3_relic_boss_2b",
        "rogue_3_relic_boss_4b",
        *(f"rogue_4_relic_final_{index}" for index in range(1, 12)),
        *(f"rogue_5_relic_final_{index}" for index in range(1, 11)),
    }
)


def is_supported_ending(theme: str, ending: str) -> bool:
    return (
        isinstance(theme, str)
        and isinstance(ending, str)
        and ending in ENDING_PRIORITIES.get(theme, {})
    )


def default_ending(theme: str) -> str | None:
    return DEFAULT_ENDINGS.get(theme) if isinstance(theme, str) else None


def ending_priority(theme: str, ending: str) -> int | None:
    if not isinstance(theme, str) or not isinstance(ending, str):
        return None
    return ENDING_PRIORITIES.get(theme, {}).get(ending)


def ending_for_acquired_item(theme: str, item_id: str) -> str | None:
    if not isinstance(theme, str) or not isinstance(item_id, str):
        return None
    return ENDING_ON_ACQUIRE.get(theme, {}).get(item_id)


def ending_branch_reset_for_acquired_item(
    theme: str, item_id: str
) -> tuple[str, str] | None:
    if not isinstance(theme, str) or not isinstance(item_id, str):
        return None
    return ENDING_BRANCH_RESETS.get(theme, {}).get(item_id)


def is_overlay_ending(theme: str, ending: str) -> bool:
    return is_supported_ending(theme, ending) and ending in OVERLAY_ENDINGS


def terminal_zone(theme: str, ending: str) -> int | None:
    if not isinstance(theme, str) or not isinstance(ending, str):
        return None
    return TERMINAL_ZONES.get(theme, {}).get(ending)


def _base_ending(theme: str, previous: dict | None) -> str:
    default = DEFAULT_ENDINGS[theme]
    if not isinstance(previous, dict):
        return default
    previous_ending = previous.get("endingId")
    if terminal_zone(theme, previous_ending) == 5:
        return previous_ending
    candidate = previous.get("baseEndingId")
    if terminal_zone(theme, candidate) == 5:
        return candidate
    bosses = previous.get("bossEndings")
    candidate = bosses.get("5") if isinstance(bosses, dict) else None
    if terminal_zone(theme, candidate) == 5:
        return candidate
    return default


def _previous_ordered_zones(previous: dict | None) -> list[int]:
    if not isinstance(previous, dict):
        return []
    ordered = previous.get("orderedZones")
    if not isinstance(ordered, list):
        return []
    return [zone for zone in ordered if type(zone) is int]


def _previous_boss_endings(previous: dict | None) -> dict:
    if not isinstance(previous, dict):
        return {}
    bosses = previous.get("bossEndings")
    return bosses if isinstance(bosses, dict) else {}


def _standard_route_plan(
    theme: str,
    ending: str,
    current_zone: int,
    previous: dict | None,
) -> dict:
    terminal = TERMINAL_ZONES[theme][ending]
    if terminal == 5:
        return {
            "endingId": ending,
            "baseEndingId": ending,
            "orderedZones": [1, 2, 3, 4, 5],
            "bossEndings": {"5": ending},
        }

    base = _base_ending(theme, previous)
    if terminal == 6:
        return {
            "endingId": ending,
            "baseEndingId": base,
            "orderedZones": [1, 2, 3, 4, 5, 6],
            "bossEndings": {"5": base, "6": ending},
        }

    # RO3/4/5 zone 7 is an alternative final region. It normally follows
    # zone 5 directly. RO3 may enter it from zone 6 when the trigger is gained
    # there, so retain an already-entered zone 6 and its resolved boss.
    previous_ordered = _previous_ordered_zones(previous)
    include_zone_6 = current_zone == 6 or (
        current_zone > 6 and 6 in previous_ordered
    )
    ordered = [1, 2, 3, 4, 5]
    bosses = {"5": base, "7": ending}
    if include_zone_6:
        ordered.append(6)
        previous_boss = _previous_boss_endings(previous).get("6")
        if is_supported_ending(theme, previous_boss):
            bosses["6"] = previous_boss
    ordered.append(7)
    return {
        "endingId": ending,
        "baseEndingId": base,
        "orderedZones": ordered,
        "bossEndings": bosses,
    }


def _overlay_underlay_ending(theme: str, previous: dict | None) -> str:
    if not isinstance(previous, dict):
        return DEFAULT_ENDINGS[theme]

    candidates = [previous.get("underlayEndingId"), previous.get("endingId")]
    bosses = _previous_boss_endings(previous)
    for zone in reversed(_previous_ordered_zones(previous)):
        candidates.append(bosses.get(str(zone)))
    candidates.append(previous.get("baseEndingId"))

    for candidate in candidates:
        terminal = terminal_zone(theme, candidate)
        if terminal is not None and terminal < 8:
            return candidate
    return DEFAULT_ENDINGS[theme]


def build_route_plan(
    theme: str,
    ending: str,
    current_zone: int = 1,
    previous: dict | None = None,
) -> dict | None:
    """Build an explicit PRTS route without assuming numeric zone order."""
    if (
        not is_supported_ending(theme, ending)
        or type(current_zone) is not int
        or current_zone < 1
    ):
        return None

    if ending not in OVERLAY_ENDINGS:
        return _standard_route_plan(theme, ending, current_zone, previous)

    underlay_ending = _overlay_underlay_ending(theme, previous)
    previous = _standard_route_plan(
        theme,
        underlay_ending,
        current_zone,
        previous,
    )

    ordered = [
        zone for zone in previous.get("orderedZones", [])
        if type(zone) is int and zone < 8
    ]
    if current_zone not in ordered and current_zone < 8:
        ordered.append(current_zone)
        ordered.sort()
    if not ordered:
        ordered = [1, 2, 3, 4, 5]
    ordered.append(8)

    bosses = {
        str(zone): boss_ending
        for zone, boss_ending in _previous_boss_endings(previous).items()
        if str(zone).isdigit() and int(zone) < 8
        and is_supported_ending(theme, boss_ending)
    }
    bosses["8"] = ending
    return {
        "endingId": ending,
        "underlayEndingId": underlay_ending,
        "baseEndingId": previous.get("baseEndingId", DEFAULT_ENDINGS[theme]),
        "orderedZones": ordered,
        "bossEndings": bosses,
    }


def route_plan_is_valid(
    theme: str,
    ending: str,
    route: dict | None,
    current_zone: int = 1,
) -> bool:
    """Validate private route state against its canonical, idempotent rebuild."""
    if not isinstance(route, dict):
        return False
    expected = build_route_plan(theme, ending, current_zone, route)
    if expected is None:
        return False
    return all(route.get(key) == value for key, value in expected.items())


def boss_ending_for_zone(route: dict | None, zone: int) -> str | None:
    if not isinstance(route, dict) or type(zone) is not int:
        return None
    bosses = route.get("bossEndings")
    if not isinstance(bosses, dict):
        return None
    value = bosses.get(str(zone))
    return value if isinstance(value, str) else None


def patch_current_boss(run: dict, route: dict | None) -> bool:
    """Replace unvisited boss nodes after an ending route changes."""
    if not isinstance(run, dict) or not isinstance(route, dict):
        return False
    player = run.get("player")
    game = run.get("game")
    if not isinstance(player, dict) or not isinstance(game, dict):
        return False
    cursor = player.get("cursor")
    zone_number = cursor.get("zone") if isinstance(cursor, dict) else None
    if type(zone_number) is not int:
        return False

    ending = boss_ending_for_zone(route, zone_number)
    candidates = boss_stage_ids(game.get("theme"), ending)
    if not candidates:
        return False
    dungeon = run.get("map")
    zones = dungeon.get("zones") if isinstance(dungeon, dict) else None
    zone = zones.get(str(zone_number)) if isinstance(zones, dict) else None
    nodes = zone.get("nodes") if isinstance(zone, dict) else None
    if not isinstance(nodes, dict):
        return False
    changed = False
    for node in nodes.values():
        if (
            isinstance(node, dict)
            and node.get("type") == 4
            and not node.get("visited")
            and node.get("stage") != candidates[0]
        ):
            node["stage"] = candidates[0]
            changed = True
    return changed


def route_next_zone(route: dict | None, current_zone: int) -> int | None:
    if not isinstance(route, dict) or type(current_zone) is not int:
        return None
    ordered = route.get("orderedZones")
    if not isinstance(ordered, list):
        return None
    try:
        index = ordered.index(current_zone)
    except ValueError:
        return None
    return ordered[index + 1] if index + 1 < len(ordered) else None


def route_completed_zone_count(route: dict | None, current_zone: int) -> int | None:
    if not isinstance(route, dict) or type(current_zone) is not int:
        return None
    ordered = route.get("orderedZones")
    if not isinstance(ordered, list):
        return None
    try:
        return ordered.index(current_zone) + 1
    except ValueError:
        return None

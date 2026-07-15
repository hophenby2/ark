"""Read-only adapters for the versioned RLV2 rule catalog."""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from typing import Iterable


_ROOT = Path(__file__).resolve().parents[1]
_RULES_DIR = _ROOT / "data" / "rlv2" / "rules"

_BOSS_STAGE_ID_OVERRIDES = {
    # Fixed PRTS ending evidence and the client stage catalog identify ro1_b_6.
    ("rogue_1", "ro_ending_1"): ("ro1_b_6",),
}

# Numeric node types follow docs/DEVELOP.md. Labels are kept theme-specific
# because the same protocol value has different public names by theme.
_EVENT_TYPE_LABELS = {
    "rogue_1": {
        16: ("\u5b89\u5168\u7684\u89d2\u843d",),
        32: ("\u4e0d\u671f\u800c\u9047",),
        64: ("\u53e4\u5821\u9988\u8d60",),
        128: ("\u5e55\u95f4\u4f59\u5174",),
        256: ("\u8ff7\u96fe\u91cd\u91cd",),
    },
    "rogue_2": {
        16: ("\u5b89\u5168\u7684\u89d2\u843d",),
        32: ("\u4e0d\u671f\u800c\u9047",),
        128: ("\u5174\u81f4\u76ce\u7136",),
        256: ("\u8ff7\u96fe\u91cd\u91cd",),
        512: ("\u5f97\u507f\u6240\u613f",),
        1024: ("\u98ce\u96e8\u9645\u4f1a",),
        2048: ("\u7d27\u6025\u8fd0\u8f93",),
        8192: ("\u8bef\u5165\u5947\u5883",),
        16384: ("\u5730\u533a\u59d4\u6258",),
    },
    "rogue_3": {
        16: ("\u5b89\u5168\u7684\u89d2\u843d",),
        32: ("\u4e0d\u671f\u800c\u9047",),
        128: ("\u5174\u81f4\u76ce\u7136",),
        256: ("\u8ff7\u96fe\u91cd\u91cd",),
        512: ("\u5f97\u507f\u6240\u613f",),
        1024: ("\u5931\u4e0e\u5f97",),
        2048: ("\u5148\u884c\u4e00\u6b65",),
        8192: ("\u6811\u7bf1\u4e4b\u9014",),
        32768: ("\u547d\u8fd0\u6240\u6307",),
        65536: ("\u547d\u8fd0\u6240\u6307",),
    },
    "rogue_4": {
        16: ("\u5b89\u5168\u7684\u89d2\u843d",),
        32: ("\u4e0d\u671f\u800c\u9047",),
        128: ("\u5174\u81f4\u76ce\u7136",),
        256: ("\u8ff7\u96fe\u91cd\u91cd",),
        512: ("\u5f97\u507f\u6240\u613f",),
        1024: ("\u5931\u4e0e\u5f97",),
        2048: ("\u5148\u884c\u4e00\u6b65",),
        8192: ("\u601d\u7ef4\u8fb9\u754c",),
        32768: ("\u547d\u8fd0\u6240\u6307",),
        65536: ("\u547d\u8fd0\u6240\u6307",),
        131072: ("\u53bb\u4f2a\u5b58\u771f",),
        262144: ("\u72ed\u8def\u76f8\u9022",),
    },
    "rogue_5": {
        16: ("\u5b89\u5168\u7684\u89d2\u843d",),
        32: ("\u4e0d\u671f\u800c\u9047",),
        512: ("\u5f97\u507f\u6240\u613f",),
        1024: ("\u5931\u4e0e\u5f97",),
        2048: ("\u5148\u884c\u4e00\u6b65",),
        8192: ("\u8bef\u5165\u5947\u5883",),
        32768: ("\u547d\u8fd0\u6240\u6307",),
        65536: ("\u547d\u8fd0\u6240\u6307",),
        262144: ("\u72ed\u8def\u76f8\u9022",),
        524288: ("\u6307\u70b9\u8ff7\u6d25",),
        1048576: ("\u8bef\u5165\u5947\u5883",),
    },
}

_STANDARD_EVENT_EXCLUSIONS = {
    # Fixed PRTS descriptions place these scenes only in Deep Exploration.
    ("rogue_3", "scene_ro3_res2a_enter"),
    ("rogue_3", "scene_ro3_res3a_enter"),
    ("rogue_3", "scene_ro3_res5a_enter"),
    ("rogue_3", "scene_ro3_pick1_enter"),
    ("rogue_3", "scene_ro3_pick2_enter"),
}

_REPEATABLE_EVENT_SCENES = frozenset(
    {
        ("rogue_1", "scene_hp_enter"),
        ("rogue_1", "scene_gold_enter"),
        ("rogue_1", "scene_population_enter"),
        ("rogue_1", "scene_trade1_enter"),
        ("rogue_2", "scene_ro2_dice_enter"),
        ("rogue_2", "scene_ro2_hp_enter"),
        ("rogue_2", "scene_ro2_hp2_enter"),
        ("rogue_2", "scene_ro2_key_enter"),
        ("rogue_2", "scene_ro2_dice2_enter"),
    }
)


def _column(minimum: int, maximum: int, *kinds: str, **extra) -> dict:
    return {
        "minimum": minimum,
        "maximum": maximum,
        "kinds": kinds,
        **extra,
    }


# These are direct, manually reviewed translations of sourceLayoutText. None
# marks a PRTS question-mark column whose exact composition is not public.
_COLUMN_SPECS = {
    ("rogue_1", 1): (
        _column(1, 1, "battle"),
        _column(2, 3, "incident", "entertainment"),
        None,
        _column(1, 1, "shop"),
    ),
    ("rogue_1", 2): (None, None, None, _column(1, 3, "gift")),
    ("rogue_1", 3): (None, None, None, None, None, _column(1, 1, "boss")),
    ("rogue_1", 4): (None, None, None, None, None, _column(1, 3, "gift")),
    ("rogue_1", 5): (
        None, None, None, None, None, None, _column(1, 1, "boss")
    ),
    ("rogue_1", 6): (
        _column(1, 1, "shop"),
        _column(1, 1, "rest"),
        _column(1, 1, "battle"),
        _column(1, 1, "boss"),
    ),
    ("rogue_2", 1): (
        _column(1, 1, "battle"), None, None, None, _column(1, 1, "shop")
    ),
    ("rogue_2", 2): (
        _column(2, 2, "battle_or_incident"),
        None,
        None,
        None,
        _column(1, 3, "wish"),
    ),
    ("rogue_2", 3): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        None,
        _column(1, 1, "boss"),
    ),
    ("rogue_2", 4): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        None,
        _column(1, 4, "wish"),
    ),
    ("rogue_2", 5): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        None,
        None,
        _column(1, 1, "boss"),
    ),
    ("rogue_2", 6): (
        _column(1, 1, "shop"),
        _column(1, 1, "rest"),
        _column(1, 1, "battle"),
        _column(1, 1, "boss"),
    ),
    ("rogue_2", 7): (
        _column(2, 2, "wish"),
        _column(2, 2, "battle", stage_depth=6),
        _column(2, 2, "battle", stage_depth=6),
        _column(1, 1, "boss"),
    ),
    ("rogue_3", 1): (
        _column(2, 2, "battle"), None, None, _column(2, 2, "shop")
    ),
    ("rogue_3", 2): (
        _column(2, 2, "battle_or_incident"),
        None,
        None,
        _column(2, 2, "wish"),
    ),
    ("rogue_3", 3): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(1, 1, "boss"),
    ),
    ("rogue_3", 4): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(3, 3, "wish"),
    ),
    ("rogue_3", 5): (
        _column(3, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(1, 4, "story"),
        _column(1, 1, "boss"),
    ),
    ("rogue_3", 6): (
        _column(1, 1, "shop"),
        _column(2, 2, "non_battle"),
        _column(2, 2, "battle"),
        _column(1, 1, "boss"),
    ),
    ("rogue_3", 7): (
        _column(1, 1, "shop"),
        _column(1, 1, "story", scene_id="scene_ro3_ex2_enter"),
        _column(1, 1, "battle", stage_depth=6),
        _column(1, 1, "story", scene_id="scene_ro3_ex3_enter"),
        _column(1, 1, "boss"),
    ),
    ("rogue_4", 1): (
        _column(2, 2, "battle"),
        _column(1, 3, "battle_or_incident"),
        _column(1, 3, "battle_or_incident"),
        _column(1, 1, "shop"),
    ),
    ("rogue_4", 2): (
        _column(1, 1, "story", scene_id="scene_ro4_fin1_enter"),
        None,
        None,
        None,
        _column(1, 1, "alchemy"),
    ),
    ("rogue_4", 3): (
        _column(3, 3, "battle_or_incident"),
        _column(1, 1, "sacrifice"),
        None,
        None,
        _column(1, 4, "alchemy"),
        _column(1, 1, "boss"),
    ),
    ("rogue_4", 4): (
        _column(
            3,
            3,
            "battle_or_incident",
            minimum_battle_nodes=1,
        ),
        _column(1, 4, "battle"),
        _column(1, 4, "non_battle"),
        _column(1, 4, "non_battle"),
        _column(1, 4, "wish"),
        _column(1, 1, "alchemy"),
    ),
    ("rogue_4", 5): (
        _column(3, 3, "battle_or_incident"),
        _column(1, 1, "duel"),
        None,
        None,
        None,
        _column(1, 4, "alchemy"),
        _column(1, 4, "story"),
        _column(1, 1, "boss"),
    ),
    ("rogue_4", 6): (
        _column(1, 1, "shop"),
        _column(2, 2, "non_battle"),
        _column(2, 2, "battle"),
        _column(2, 2, "alchemy"),
        _column(1, 1, "boss"),
    ),
    ("rogue_4", 7): (
        _column(1, 1, "shop"),
        _column(2, 2, "non_battle"),
        _column(2, 2, "battle"),
        _column(2, 2, "alchemy"),
        _column(1, 1, "boss"),
    ),
    ("rogue_4", 8): (_column(1, 1, "boss"),),
    ("rogue_5", 1): (
        _column(2, 2, "battle"),
        _column(2, 3, "battle_incident_wish"),
        _column(1, 3, "shop"),
        _column(1, 1, "special_zone"),
    ),
    ("rogue_5", 2): (
        _column(2, 2, "stashed_recruit"),
        None,
        None,
        _column(2, 2, "wish"),
    ),
    ("rogue_5", 3): (
        _column(2, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(1, 1, "boss"),
    ),
    ("rogue_5", 4): (
        _column(2, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(2, 2, "special_zone"),
    ),
    ("rogue_5", 5): (
        _column(2, 3, "battle_or_incident"),
        None,
        None,
        None,
        _column(1, 4, "story"),
        _column(1, 1, "boss"),
    ),
    ("rogue_5", 6): (
        _column(2, 2, "non_battle"),
        _column(1, 2, "non_battle"),
        _column(1, 2, "battle", stage_depths=(6, 7)),
        _column(1, 2, "story"),
        _column(1, 1, "boss"),
    ),
    ("rogue_5", 7): (
        _column(1, 1, "stashed_recruit"),
        _column(1, 1, "battle", stage_depths=(6, 7)),
        _column(
            1,
            1,
            "special_zone",
            scene_id="scene_ro5_portalboss_enter",
        ),
        _column(1, 1, "shop"),
        _column(1, 1, "story"),
        _column(1, 1, "boss"),
    ),
    ("rogue_5", 8): (
        _column(1, 1, "story"),
        _column(1, 1, "boss"),
    ),
}


@lru_cache(maxsize=None)
def _read_rule_file(filename: str) -> dict:
    with (_RULES_DIR / filename).open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"invalid RLV2 rule document: {filename}")
    return value


@lru_cache(maxsize=1)
def _area_layout_index() -> dict[tuple[str, int], dict]:
    index = {}
    for record in _read_rule_file("zone_routes.json").get("areaLayouts", []):
        if not isinstance(record, dict):
            continue
        theme = record.get("theme")
        zone_id = record.get("zoneId")
        if not isinstance(theme, str) or not isinstance(zone_id, str):
            continue
        prefix, separator, depth_text = zone_id.rpartition("_")
        if prefix != "zone" or separator != "_" or not depth_text.isdigit():
            continue
        index[(theme, int(depth_text))] = record
    return index


@lru_cache(maxsize=1)
def _ending_route_index() -> dict[tuple[str, str], dict]:
    index = {}
    for record in _read_rule_file("zone_routes.json").get("endingRoutes", []):
        if not isinstance(record, dict):
            continue
        theme = record.get("theme")
        ending_id = record.get("endingId")
        if isinstance(theme, str) and isinstance(ending_id, str):
            index[(theme, ending_id)] = record
    return index


@lru_cache(maxsize=1)
def _event_annotation_index() -> dict[tuple[str, str], tuple[dict, ...]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    annotations = _read_rule_file("event_tags.json").get("annotations", {})
    if not isinstance(annotations, dict):
        return {}
    for record in annotations.values():
        if not isinstance(record, dict):
            continue
        theme = record.get("theme")
        label = record.get("sourceEventTypeLabel")
        if isinstance(theme, str) and isinstance(label, str):
            grouped.setdefault((theme, label), []).append(record)
    return {key: tuple(records) for key, records in grouped.items()}


@lru_cache(maxsize=1)
def _quarantined_scene_keys() -> frozenset[tuple[str, str]]:
    result = set()
    quarantine = _read_rule_file("event_tags.json").get("quarantine", [])
    if not isinstance(quarantine, list):
        return frozenset()
    for record in quarantine:
        if not isinstance(record, dict):
            continue
        theme = record.get("theme")
        if not isinstance(theme, str):
            continue
        for scene_id in record.get("candidateSceneIds") or ():
            if isinstance(scene_id, str):
                result.add((theme, scene_id))
    return frozenset(result)


def area_layout(theme: str, depth: int) -> dict | None:
    """Return a defensive copy of a verified core-area layout."""
    if not isinstance(theme, str) or type(depth) is not int:
        return None
    record = _area_layout_index().get((theme, depth))
    return deepcopy(record) if record is not None else None


def area_column_specs(theme: str, depth: int) -> list[dict | None] | None:
    """Return the reviewed per-column constraints for a core area."""
    if not isinstance(theme, str) or type(depth) is not int:
        return None
    specs = _COLUMN_SPECS.get((theme, depth))
    if specs is None:
        return None
    return deepcopy(list(specs))


def ending_route(theme: str, ending: str) -> dict | None:
    """Return a defensive copy of a verified ending route."""
    if not isinstance(theme, str) or not isinstance(ending, str):
        return None
    record = _ending_route_index().get((theme, ending))
    return deepcopy(record) if record is not None else None


def terminal_depth(theme: str, ending: str) -> int | None:
    """Return the logical terminal depth for an ending."""
    if not isinstance(theme, str) or not isinstance(ending, str):
        return None
    route = _ending_route_index().get((theme, ending))
    if route is None:
        return None
    zone_id = route.get("terminalZoneId")
    if not isinstance(zone_id, str):
        return None
    prefix, separator, depth_text = zone_id.rpartition("_")
    if prefix != "zone" or separator != "_" or not depth_text.isdigit():
        return None
    return int(depth_text)


def boss_stage_ids(theme: str, ending: str) -> list[str]:
    """Return verified boss stages, including explicit public-source overrides."""
    if not isinstance(theme, str) or not isinstance(ending, str):
        return []
    override = _BOSS_STAGE_ID_OVERRIDES.get((theme, ending))
    if override is not None:
        return list(override)
    route = _ending_route_index().get((theme, ending))
    if route is None:
        return []
    stage_ids = route.get("bossStageIds")
    if not isinstance(stage_ids, list):
        return []
    return [stage_id for stage_id in stage_ids if isinstance(stage_id, str)]


def event_scene_is_repeatable(theme: str, scene_id: str) -> bool:
    """Return whether fixed PRTS rules allow a scene to repeat in one run."""
    return (theme, scene_id) in _REPEATABLE_EVENT_SCENES


def event_scene_candidates(
    theme: str,
    depth: int,
    node_type: int,
    available_scene_ids: Iterable[str] | None,
) -> list[str]:
    """Filter canonical event scenes by theme, node category, and depth."""
    if (
        not isinstance(theme, str)
        or type(depth) is not int
        or type(node_type) is not int
    ):
        return []
    labels = _EVENT_TYPE_LABELS.get(theme, {}).get(node_type)
    if labels is None or available_scene_ids is None:
        return []
    if isinstance(available_scene_ids, str):
        available = {available_scene_ids}
    else:
        try:
            available = {
                scene_id
                for scene_id in available_scene_ids
                if isinstance(scene_id, str)
            }
        except TypeError:
            return []
    if not available:
        return []

    quarantined = _quarantined_scene_keys()
    result = []
    seen = set()
    for label in labels:
        for record in _event_annotation_index().get((theme, label), ()):
            scene_id = record.get("sceneId")
            eligibility = record.get("eligibility")
            depths = (
                eligibility.get("logicalDepths")
                if isinstance(eligibility, dict)
                else None
            )
            if (
                not isinstance(scene_id, str)
                or scene_id not in available
                or (theme, scene_id) in quarantined
                or (theme, scene_id) in _STANDARD_EVENT_EXCLUSIONS
                or not isinstance(depths, list)
                or depth not in depths
                or scene_id in seen
            ):
                continue
            result.append(scene_id)
            seen.add(scene_id)
    return result

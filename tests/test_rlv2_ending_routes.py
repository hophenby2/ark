import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_ending_rules import (  # noqa: E402
    boss_ending_for_zone,
    build_route_plan,
    route_plan_is_valid,
    route_next_zone,
)
from rlv2_logic import (  # noqa: E402
    normalize_current_run,
    public_run_value,
    shop_item_pool_candidates,
)
from rlv2_event_rules import runtime_event_rules  # noqa: E402


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_rlv2_runtime():
    request = types.SimpleNamespace(headers={}, get_json=lambda: {})
    stubs = {
        "flask": _module("flask", request=request),
        "virtualtime": _module("virtualtime", time=lambda: 1),
        "constants": _module(
            "constants",
            SYNC_DATA_TEMPLATE_PATH="data/user/user.json",
            RLV2_USER_SETTINGS_PATH="data/user/rlv2UserSettings.json",
            CONFIG_PATH="config/config.json",
            RLV2_SETTINGS_PATH="data/user/rlv2Settings.json",
        ),
        "utils": _module(
            "utils",
            read_json=lambda path: {},
            decrypt_battle_data=lambda value: {},
            writeLog=lambda value: None,
            get_memory=lambda key: {},
        ),
    }
    data_package = _module("data")
    data_package.__path__ = []
    data_module = _module("data.rlv2_data", rogue_buffs={})
    data_package.rlv2_data = data_module
    stubs["data"] = data_package
    stubs["data.rlv2_data"] = data_module

    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "_rlv2_ending_route_test_module", ROOT / "server/rlv2.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class EndingRouteRulesTest(unittest.TestCase):
    def test_zone_five_routes_directly_to_zone_seven(self):
        previous = build_route_plan("rogue_3", "ro3_ending_1")
        route = build_route_plan(
            "rogue_3", "ro3_ending_4", current_zone=5, previous=previous
        )

        self.assertEqual(route["orderedZones"], [1, 2, 3, 4, 5, 7])
        self.assertEqual(route_next_zone(route, 5), 7)
        self.assertEqual(boss_ending_for_zone(route, 5), "ro3_ending_1")
        self.assertEqual(boss_ending_for_zone(route, 7), "ro3_ending_4")

    def test_zone_six_is_retained_before_routing_to_zone_seven(self):
        zone_six_route = build_route_plan("rogue_3", "ro3_ending_3")
        route = build_route_plan(
            "rogue_3",
            "ro3_ending_4",
            current_zone=6,
            previous=zone_six_route,
        )

        self.assertEqual(route["orderedZones"], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(route_next_zone(route, 6), 7)
        self.assertEqual(boss_ending_for_zone(route, 5), "ro3_ending_1")
        self.assertEqual(boss_ending_for_zone(route, 6), "ro3_ending_3")
        self.assertEqual(boss_ending_for_zone(route, 7), "ro3_ending_4")

    def test_overlay_ending_appends_zone_eight_after_current_terminal(self):
        cases = (
            (
                "rogue_4",
                "ro4_ending_4",
                "ro4_ending_5",
                7,
                [1, 2, 3, 4, 5, 7, 8],
            ),
            (
                "rogue_5",
                "ro5_ending_3",
                "ro5_ending_5",
                6,
                [1, 2, 3, 4, 5, 6, 8],
            ),
        )
        for theme, prior_ending, overlay_ending, terminal, ordered in cases:
            with self.subTest(theme=theme, prior_ending=prior_ending):
                previous = build_route_plan(theme, prior_ending)
                route = build_route_plan(
                    theme,
                    overlay_ending,
                    current_zone=terminal,
                    previous=previous,
                )

                self.assertEqual(route["orderedZones"], ordered)
                self.assertEqual(route_next_zone(route, terminal), 8)
                self.assertEqual(
                    boss_ending_for_zone(route, terminal), prior_ending
                )
                self.assertEqual(
                    boss_ending_for_zone(route, 8), overlay_ending
                )

    def test_normalize_creates_a_private_route_for_manually_selected_ending(self):
        run = {
            "game": {"theme": "rogue_3"},
            "player": {
                "state": "WAIT_MOVE",
                "cursor": {"zone": 6, "position": None},
                "pending": [],
                "toEnding": "ro3_ending_4",
            },
        }

        self.assertTrue(normalize_current_run(run, end_ts=100))
        self.assertFalse(run["player"]["chgEnding"])
        self.assertEqual(run["_server"]["schemaVersion"], 1)
        self.assertEqual(run["_server"]["events"], {})
        self.assertEqual(
            run["_server"]["route"]["orderedZones"],
            [1, 2, 3, 4, 5, 6, 7],
        )
        self.assertEqual(route_next_zone(run["_server"]["route"], 6), 7)

    def test_normalize_manual_ending_change_replaces_unvisited_current_boss(self):
        run = {
            "player": {
                "toEnding": "ro_ending_2",
                "cursor": {"zone": 5, "position": None},
                "pending": [],
            },
            "game": {"theme": "rogue_1"},
            "map": {
                "zones": {
                    "5": {
                        "nodes": {
                            "0": {
                                "type": 4,
                                "stage": "ro1_b_6",
                                "visited": False,
                            }
                        }
                    }
                }
            },
            "_server": {
                "schemaVersion": 1,
                "events": {},
                "route": build_route_plan("rogue_1", "ro_ending_1"),
            },
        }

        self.assertTrue(normalize_current_run(run, 100))

        self.assertEqual(run["_server"]["route"]["endingId"], "ro_ending_2")
        self.assertEqual(
            run["map"]["zones"]["5"]["nodes"]["0"]["stage"],
            "ro1_b_7",
        )

    def test_normalize_repairs_a_corrupt_route_for_the_same_ending(self):
        run = {
            "game": {"theme": "rogue_5"},
            "player": {
                "cursor": {"zone": 5, "position": None},
                "pending": [],
                "toEnding": "ro5_ending_4",
                "chgEnding": False,
            },
            "_server": {
                "schemaVersion": 1,
                "events": {},
                "route": {
                    "endingId": "ro5_ending_4",
                    "baseEndingId": "ro5_ending_1",
                    "orderedZones": [1, 2, 3, 4, 5, 5, 7],
                    "bossEndings": [],
                },
            },
        }

        self.assertTrue(normalize_current_run(run, 100))

        route = run["_server"]["route"]
        self.assertTrue(
            route_plan_is_valid("rogue_5", "ro5_ending_4", route, 5)
        )
        self.assertEqual(route["orderedZones"], [1, 2, 3, 4, 5, 7])
        self.assertEqual(
            route["bossEndings"],
            {"5": "ro5_ending_1", "7": "ro5_ending_4"},
        )
        self.assertIsNone(boss_ending_for_zone({"bossEndings": []}, 7))

    def test_normalize_rejects_manual_ending_whose_terminal_is_behind_cursor(self):
        previous_route = build_route_plan("rogue_3", "ro3_ending_3")
        run = {
            "game": {"theme": "rogue_3"},
            "player": {
                "cursor": {"zone": 6, "position": None},
                "pending": [],
                "toEnding": "ro3_ending_2",
                "chgEnding": False,
            },
            "_server": {
                "schemaVersion": 1,
                "events": {},
                "route": previous_route,
            },
        }

        self.assertTrue(normalize_current_run(run, 100))

        self.assertEqual(run["player"]["toEnding"], "ro3_ending_3")
        self.assertEqual(run["_server"]["route"], previous_route)
        self.assertTrue(
            route_plan_is_valid(
                "rogue_3", "ro3_ending_3", run["_server"]["route"], 6
            )
        )

    def test_event_only_items_are_removed_from_generic_shop_pool(self):
        items = [
            "rogue_1_relic_m16",
            "rogue_2_relic_grace_83",
            "rogue_5_relic_final_8",
            "rogue_3_relic_boss_4a",
            "rogue_1_relic_normal_example",
            None,
        ]

        self.assertEqual(
            shop_item_pool_candidates("rogue_1", items),
            ["rogue_3_relic_boss_4a", "rogue_1_relic_normal_example"],
        )

    def test_public_state_recursively_strips_private_server_state(self):
        run = {
            "_server": {"route": {"endingId": "ro3_ending_4"}},
            "player": {
                "toEnding": "ro3_ending_4",
                "nested": {"_server": {"secret": True}, "visible": 1},
            },
            "history": ({"_server": {"secret": True}, "visible": 2},),
        }

        public = public_run_value(run)

        self.assertNotIn("_server", public)
        self.assertEqual(public["player"]["nested"], {"visible": 1})
        self.assertEqual(public["history"], ({"visible": 2},))
        public["player"]["nested"]["visible"] = 99
        self.assertEqual(run["player"]["nested"]["visible"], 1)


class EndingRouteRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rlv2 = _load_rlv2_runtime()

    @staticmethod
    def _zone_end_run(theme, ending, zone, route):
        return {
            "_server": {"schemaVersion": 1, "events": {}, "route": route},
            "game": {"theme": theme},
            "player": {
                "state": "WAIT_MOVE",
                "cursor": {"zone": zone, "position": {"x": 0, "y": 0}},
                "pending": [],
                "toEnding": ending,
                "chgEnding": False,
            },
            "map": {
                "zones": {
                    str(zone): {
                        "nodes": {"0": {"zone_end": True, "visited": True}}
                    }
                }
            },
        }

    def test_finish_node_uses_route_order_and_next_zone_boss_ending(self):
        default_route = build_route_plan("rogue_3", "ro3_ending_1")
        zone_six_route = build_route_plan("rogue_3", "ro3_ending_3")
        cases = (
            (
                5,
                build_route_plan(
                    "rogue_3",
                    "ro3_ending_4",
                    current_zone=5,
                    previous=default_route,
                ),
            ),
            (
                6,
                build_route_plan(
                    "rogue_3",
                    "ro3_ending_4",
                    current_zone=6,
                    previous=zone_six_route,
                ),
            ),
        )
        original = self.rlv2._rlv2.__dict__["getMap_new"]
        calls = []

        def fake_get_map(theme, seed, zone, ending, boss_ending):
            calls.append((theme, seed, zone, ending, boss_ending))
            return {str(zone): {"id": f"zone_{zone}", "nodes": {}}}, "next-seed"

        self.rlv2._rlv2.getMap_new = staticmethod(fake_get_map)
        try:
            for current_zone, route in cases:
                with self.subTest(current_zone=current_zone):
                    calls.clear()
                    run = self._zone_end_run(
                        "rogue_3", "ro3_ending_4", current_zone, route
                    )
                    server_data = {"rlv2_seed": "seed"}

                    self.assertTrue(self.rlv2._rlv2.finishNode(run, server_data))
                    self.assertEqual(run["player"]["cursor"], {
                        "zone": 7,
                        "position": None,
                    })
                    self.assertEqual(
                        calls,
                        [("rogue_3", "seed", 7, "ro3_ending_4", "ro3_ending_4")],
                    )
                    self.assertIn("7", run["map"]["zones"])
                    self.assertEqual(server_data["rlv2_seed"], "next-seed")
        finally:
            self.rlv2._rlv2.getMap_new = original

    def test_adding_ending_item_changes_ending_route_flag_and_current_boss(self):
        item_id = "rogue_1_relic_m16"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_1": {
                    "items": {item_id: {"type": "RELIC"}},
                    "relics": {item_id: {"buffs": []}},
                    "stages": {
                        "ro1_b_6": {"isBoss": True},
                        "ro1_b_7": {"isBoss": True},
                    },
                }
            }
        }
        run = {
            "_server": {
                "schemaVersion": 1,
                "events": {},
                "route": build_route_plan("rogue_1", "ro_ending_1"),
            },
            "game": {"theme": "rogue_1"},
            "player": {
                "cursor": {"zone": 5, "position": {"x": 0, "y": 0}},
                "toEnding": "ro_ending_1",
                "chgEnding": False,
            },
            "map": {
                "zones": {
                    "5": {
                        "nodes": {
                            "0": {
                                "type": 4,
                                "visited": False,
                                "stage": "ro1_b_6",
                            }
                        }
                    }
                }
            },
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {},
        }

        created = self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(created, "r_0")
        self.assertEqual(run["inventory"]["relic"]["r_0"]["id"], item_id)
        self.assertEqual(run["player"]["toEnding"], "ro_ending_2")
        self.assertTrue(run["player"]["chgEnding"])
        self.assertEqual(run["_server"]["route"]["endingId"], "ro_ending_2")
        self.assertEqual(run["_server"]["route"]["source"], f"item:{item_id}")
        self.assertEqual(
            boss_ending_for_zone(run["_server"]["route"], 5),
            "ro_ending_2",
        )
        self.assertEqual(
            run["map"]["zones"]["5"]["nodes"]["0"]["stage"],
            "ro1_b_7",
        )

    def test_overlay_route_rebases_when_underlay_item_is_acquired_later(self):
        cases = (
            (
                "rogue_4",
                "ro4_ending_5",
                "ro4_ending_3",
                [1, 2, 3, 4, 5, 6, 8],
                6,
            ),
            (
                "rogue_4",
                "ro4_ending_5",
                "ro4_ending_4",
                [1, 2, 3, 4, 5, 7, 8],
                7,
            ),
            (
                "rogue_5",
                "ro5_ending_5",
                "ro5_ending_3",
                [1, 2, 3, 4, 5, 6, 8],
                6,
            ),
            (
                "rogue_5",
                "ro5_ending_5",
                "ro5_ending_4",
                [1, 2, 3, 4, 5, 7, 8],
                7,
            ),
        )
        for theme, overlay, underlay, ordered, underlay_zone in cases:
            with self.subTest(theme=theme, underlay=underlay):
                run = {
                    "_server": {
                        "schemaVersion": 1,
                        "events": {},
                        "route": build_route_plan(theme, overlay),
                    },
                    "game": {"theme": theme},
                    "player": {
                        "cursor": {"zone": 1, "position": None},
                        "toEnding": overlay,
                        "chgEnding": False,
                    },
                    "map": {"zones": {}},
                }

                self.assertTrue(
                    self.rlv2._rlv2.setEnding(run, underlay, "test:underlay")
                )

                route = run["_server"]["route"]
                self.assertEqual(run["player"]["toEnding"], overlay)
                self.assertTrue(run["player"]["chgEnding"])
                self.assertEqual(route["underlayEndingId"], underlay)
                self.assertEqual(route["orderedZones"], ordered)
                self.assertEqual(
                    boss_ending_for_zone(route, underlay_zone), underlay
                )
                self.assertEqual(boss_ending_for_zone(route, 8), overlay)

    def test_overlay_underlay_does_not_regress_to_a_lower_priority_ending(self):
        for theme, overlay, high, low in (
            ("rogue_4", "ro4_ending_5", "ro4_ending_4", "ro4_ending_2"),
            ("rogue_5", "ro5_ending_5", "ro5_ending_4", "ro5_ending_2"),
        ):
            with self.subTest(theme=theme):
                run = {
                    "_server": {
                        "schemaVersion": 1,
                        "events": {},
                        "route": build_route_plan(theme, overlay),
                    },
                    "game": {"theme": theme},
                    "player": {
                        "cursor": {"zone": 1, "position": None},
                        "toEnding": overlay,
                        "chgEnding": False,
                    },
                    "map": {"zones": {}},
                }
                self.assertTrue(
                    self.rlv2._rlv2.setEnding(run, high, "test:high")
                )
                run["player"]["chgEnding"] = False
                expected_route = dict(run["_server"]["route"])

                self.assertTrue(
                    self.rlv2._rlv2.setEnding(run, low, "test:low")
                )

                self.assertFalse(run["player"]["chgEnding"])
                self.assertEqual(run["_server"]["route"], expected_route)
                self.assertEqual(
                    run["_server"]["route"]["underlayEndingId"], high
                )

    def test_ro2_deep_blue_heart_requires_twenty_light_but_garden_is_free(self):
        rules = runtime_event_rules("rogue_2", {})
        scene = rules["sceneRules"]["scene_ro2_bossb2_enter"]
        free_choice = rules["choices"]["choice_ro2_bossb2_6"]
        run = {
            "inventory": {
                "relic": {
                    "r_0": {
                        "id": "rogue_2_relic_curse_7",
                        "count": 1,
                    }
                },
                "recruit": {},
                "consumable": {},
                "exploreTool": {},
                "trap": None,
            },
            "player": {"property": {}},
            "module": {"san": {"sanity": 19}},
        }

        self.assertEqual(scene["required"], ["choice_ro2_bossb2_6"])
        self.assertFalse(
            self.rlv2._rlv2.canPayChoice(run, {"require": scene["require"]})
        )
        self.assertTrue(self.rlv2._rlv2.canPayChoice(run, free_choice))
        run["module"]["san"]["sanity"] = 20
        self.assertTrue(
            self.rlv2._rlv2.canPayChoice(run, {"require": scene["require"]})
        )

    def test_ro2_knight_followup_requires_living_knight(self):
        scene = runtime_event_rules("rogue_2", {})["sceneRules"][
            "scene_ro2_bossa2_enter"
        ]
        run = {
            "inventory": {
                "relic": {},
                "recruit": {},
                "consumable": {},
                "exploreTool": {},
                "trap": None,
            },
            "player": {"property": {}},
            "module": {},
        }

        self.assertEqual(
            scene["require"],
            {
                "items": {"rogue_2_relic_grace_83": 1},
                "notItems": {"rogue_2_relic_grace_84": 1},
            },
        )
        self.assertFalse(
            self.rlv2._rlv2.canPayChoice(run, {"require": scene["require"]})
        )
        run["inventory"]["relic"]["r_0"] = {
            "id": "rogue_2_relic_grace_83",
            "count": 1,
        }
        self.assertTrue(
            self.rlv2._rlv2.canPayChoice(run, {"require": scene["require"]})
        )
        run["inventory"]["relic"]["r_1"] = {
            "id": "rogue_2_relic_grace_84",
            "count": 1,
        }
        self.assertFalse(
            self.rlv2._rlv2.canPayChoice(run, {"require": scene["require"]})
        )

    def test_ro4_ending_two_choice_requires_babel_oath(self):
        choice = runtime_event_rules("rogue_4", {})["choices"][
            "choice_ro4_end1_1"
        ]
        run = {
            "inventory": {
                "relic": {},
                "recruit": {},
                "consumable": {},
                "exploreTool": {},
                "trap": None,
            },
            "player": {"property": {}},
            "module": {},
        }

        self.assertFalse(self.rlv2._rlv2.canPayChoice(run, choice))
        run["inventory"]["relic"]["r_0"] = {
            "id": "rogue_4_relic_final_1",
            "count": 1,
        }
        self.assertTrue(self.rlv2._rlv2.canPayChoice(run, choice))

    def test_hidden_ending_scenes_require_their_route_items(self):
        cases = (
            (
                "rogue_3",
                "scene_ro3_story3_enter",
                "rogue_3_relic_boss_2b",
            ),
            (
                "rogue_4",
                "scene_ro4_end2_enter",
                "rogue_4_relic_final_2",
            ),
        )
        for theme, scene_id, item_id in cases:
            with self.subTest(theme=theme, scene_id=scene_id):
                scene = runtime_event_rules(theme, {})["sceneRules"][scene_id]
                run = {
                    "inventory": {
                        "relic": {},
                        "recruit": {},
                        "consumable": {},
                        "exploreTool": {},
                        "trap": None,
                    },
                    "player": {"property": {}},
                    "module": {},
                }

                self.assertFalse(
                    self.rlv2._rlv2.canPayChoice(
                        run, {"require": scene["require"]}
                    )
                )
                run["inventory"]["relic"]["r_0"] = {
                    "id": item_id,
                    "count": 1,
                }
                self.assertTrue(
                    self.rlv2._rlv2.canPayChoice(
                        run, {"require": scene["require"]}
                    )
                )

    def test_ro5_memory_instrument_portal_branch_has_no_fake_leave(self):
        rules = runtime_event_rules("rogue_5", {})
        scene_id = "scene_ro5_portalboss_enter"
        scene = rules["sceneRules"][scene_id]

        self.assertEqual(
            rules["enter"][scene_id], ["choice_ro5_portalboss_5"]
        )
        self.assertEqual(
            scene["require"], {"items": {"rogue_5_relic_final_7": 1}}
        )
        self.assertTrue(
            rules["choices"]["choice_ro5_portalboss_6"][
                "eventBattleRewardRequired"
            ]
        )

    def test_ro5_memory_instrument_clears_available_hope_without_erasing_cost(self):
        item_id = "rogue_5_relic_final_7"
        immediate_costs = [
            {
                "key": "immediate_cost",
                "blackboard": [
                    {"key": "id", "valueStr": resource_id},
                    {"key": "count", "value": 99999},
                ],
            }
            for resource_id in ("rogue_5_gold", "rogue_5_population")
        ]
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_5": {
                    "items": {
                        item_id: {"type": "RELIC"},
                        "rogue_5_gold": {"type": "GOLD"},
                        "rogue_5_population": {"type": "POPULATION"},
                    },
                    "relics": {item_id: {"buffs": immediate_costs}},
                }
            }
        }
        run = {
            "game": {"theme": "rogue_5"},
            "player": {
                "property": {
                    "hp": {"current": 4, "max": 4},
                    "gold": 30,
                    "shield": 0,
                    "capacity": 6,
                    "level": 1,
                    "maxLevel": 10,
                    "population": {"max": 10, "cost": 6},
                }
            },
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {},
        }

        self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(run["player"]["property"]["gold"], 0)
        self.assertEqual(
            run["player"]["property"]["population"],
            {"max": 6, "cost": 6},
        )

    def test_immediate_item_cost_removes_self_without_recursive_negative_add(self):
        item_id = "rogue_4_band_22"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_4": {
                    "items": {item_id: {"type": "BAND"}},
                    "relics": {
                        item_id: {
                            "buffs": [
                                {
                                    "key": "immediate_reward",
                                    "blackboard": [
                                        {"key": "id", "valueStr": "pool_remix_band"},
                                        {"key": "count", "value": 1},
                                    ],
                                },
                                {
                                    "key": "immediate_cost",
                                    "blackboard": [
                                        {"key": "id", "valueStr": item_id},
                                        {"key": "count", "value": 1},
                                    ],
                                },
                            ]
                        }
                    },
                }
            }
        }
        run = {
            "game": {"theme": "rogue_4"},
            "player": {
                "property": {
                    "hp": {"current": 4, "max": 4},
                    "gold": 0,
                    "shield": 0,
                    "capacity": 6,
                    "level": 1,
                    "maxLevel": 10,
                    "population": {"max": 6, "cost": 0},
                }
            },
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {},
        }

        self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(run["inventory"]["relic"], {})
        self.assertEqual(
            run["inventory"]["consumable"], {"pool_remix_band": 1}
        )

    def test_chaos_purification_reward_and_cost_use_opposite_directions(self):
        item_id = "rogue_3_relic_res_3"
        purify_id = "rogue_3_chaos_purify"
        vision_id = "rogue_3_vision"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_3": {
                    "items": {
                        item_id: {"type": "RELIC"},
                        purify_id: {"type": "CHAOS_PURIFY"},
                        vision_id: {"type": "VISION"},
                    },
                    "relics": {
                        item_id: {
                            "buffs": [
                                {
                                    "key": "immediate_reward",
                                    "blackboard": [
                                        {"key": "id", "valueStr": vision_id},
                                        {"key": "count", "value": 2},
                                    ],
                                },
                                {
                                    "key": "immediate_cost",
                                    "blackboard": [
                                        {"key": "id", "valueStr": purify_id},
                                        {"key": "count", "value": 2},
                                    ],
                                },
                            ]
                        }
                    },
                }
            }
        }
        run = {
            "game": {"theme": "rogue_3"},
            "player": {
                "property": {
                    "hp": {"current": 4, "max": 4},
                    "gold": 0,
                    "shield": 0,
                    "capacity": 6,
                    "level": 1,
                    "maxLevel": 10,
                    "population": {"max": 6, "cost": 0},
                }
            },
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {
                "vision": {"value": 3},
                "chaos": {"value": 4},
            },
        }

        self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(run["module"]["vision"]["value"], 5)
        self.assertEqual(run["module"]["chaos"]["value"], 6)
        self.assertNotIn(purify_id, run["inventory"]["consumable"])
        self.assertTrue(self.rlv2._rlv2.grant_resource(run, purify_id, 2))
        self.assertEqual(run["module"]["chaos"]["value"], 4)

    def test_ro2_retreat_relic_restores_default_ending_and_boss(self):
        item_id = "rogue_2_relic_grace_84"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_2": {
                    "items": {item_id: {"type": "RELIC"}},
                    "relics": {item_id: {"buffs": []}},
                }
            }
        }
        run = {
            "_server": {
                "schemaVersion": 1,
                "events": {},
                "route": build_route_plan("rogue_2", "ro2_ending_2"),
            },
            "game": {"theme": "rogue_2"},
            "player": {
                "cursor": {"zone": 5, "position": None},
                "toEnding": "ro2_ending_2",
                "chgEnding": False,
            },
            "map": {
                "zones": {
                    "5": {
                        "nodes": {
                            "0": {
                                "type": 4,
                                "visited": False,
                                "stage": "ro2_b_5",
                            }
                        }
                    }
                }
            },
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {"san": {"sanity": 100}},
        }

        self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(run["player"]["toEnding"], "ro2_ending_1")
        self.assertTrue(run["player"]["chgEnding"])
        self.assertEqual(run["_server"]["route"]["endingId"], "ro2_ending_1")
        self.assertEqual(
            run["map"]["zones"]["5"]["nodes"]["0"]["stage"],
            "ro2_b_4",
        )

    def test_ro2_retreat_relic_is_idempotent_on_the_default_route(self):
        item_id = "rogue_2_relic_grace_84"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_2": {
                    "items": {item_id: {"type": "RELIC"}},
                    "relics": {item_id: {"buffs": []}},
                }
            }
        }
        route = build_route_plan("rogue_2", "ro2_ending_1")
        run = {
            "_server": {"schemaVersion": 1, "events": {}, "route": route},
            "game": {"theme": "rogue_2"},
            "player": {
                "cursor": {"zone": 5, "position": None},
                "toEnding": "ro2_ending_1",
                "chgEnding": False,
            },
            "map": {"zones": {}},
            "inventory": {
                "relic": {},
                "recruit": {},
                "trap": None,
                "consumable": {},
                "exploreTool": {},
            },
            "buff": {"tmpHP": 0},
            "module": {"san": {"sanity": 100}},
        }

        self.rlv2._rlv2.add_item(run, item_id)

        self.assertEqual(run["player"]["toEnding"], "ro2_ending_1")
        self.assertFalse(run["player"]["chgEnding"])
        self.assertEqual(run["_server"]["route"], route)

    def test_ro2_retreat_relic_rebases_but_keeps_higher_endings(self):
        item_id = "rogue_2_relic_grace_84"
        self.rlv2.get_memory = lambda key: {
            "details": {
                "rogue_2": {
                    "items": {item_id: {"type": "RELIC"}},
                    "relics": {item_id: {"buffs": []}},
                }
            }
        }
        knight_route = build_route_plan("rogue_2", "ro2_ending_2")
        for ending in ("ro2_ending_3", "ro2_ending_4"):
            with self.subTest(ending=ending):
                route = build_route_plan(
                    "rogue_2", ending, previous=knight_route
                )
                run = {
                    "_server": {
                        "schemaVersion": 1,
                        "events": {},
                        "route": route,
                    },
                    "game": {"theme": "rogue_2"},
                    "player": {
                        "cursor": {"zone": 5, "position": None},
                        "toEnding": ending,
                        "chgEnding": False,
                    },
                    "map": {
                        "zones": {
                            "5": {
                                "nodes": {
                                    "0": {
                                        "type": 4,
                                        "visited": False,
                                        "stage": "ro2_b_5",
                                    }
                                }
                            }
                        }
                    },
                    "inventory": {
                        "relic": {},
                        "recruit": {},
                        "trap": None,
                        "consumable": {},
                        "exploreTool": {},
                    },
                    "buff": {"tmpHP": 0},
                    "module": {"san": {"sanity": 100}},
                }

                self.rlv2._rlv2.add_item(run, item_id)

                rebased = run["_server"]["route"]
                self.assertEqual(run["player"]["toEnding"], ending)
                self.assertTrue(run["player"]["chgEnding"])
                self.assertEqual(rebased["endingId"], ending)
                self.assertEqual(rebased["baseEndingId"], "ro2_ending_1")
                self.assertEqual(
                    boss_ending_for_zone(rebased, 5), "ro2_ending_1"
                )
                self.assertEqual(boss_ending_for_zone(rebased, 6), ending)
                self.assertEqual(
                    run["map"]["zones"]["5"]["nodes"]["0"]["stage"],
                    "ro2_b_4",
                )


if __name__ == "__main__":
    unittest.main()

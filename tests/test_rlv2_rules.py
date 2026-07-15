import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_rules import (  # noqa: E402
    area_column_specs,
    area_layout,
    boss_stage_ids,
    ending_route,
    event_scene_candidates,
    event_scene_is_repeatable,
    terminal_depth,
)


class Rlv2RulesTest(unittest.TestCase):
    def test_all_36_area_layouts_match_the_verified_matrix(self):
        expected = {
            "rogue_1": ((4, 3), (4, 3), (6, 3), (6, 3), (7, 3), (4, 1)),
            "rogue_2": (
                (5, 3),
                (5, 3),
                (6, 4),
                (6, 4),
                (7, 4),
                (4, 1),
                (4, 2),
            ),
            "rogue_3": (
                (4, 3),
                (4, 3),
                (5, 4),
                (5, 4),
                (6, 4),
                (4, 2),
                (5, 1),
            ),
            "rogue_4": (
                (4, 3),
                (5, 3),
                (6, 4),
                (6, 4),
                (8, 4),
                (5, 2),
                (5, 2),
                (1, 1),
            ),
            "rogue_5": (
                (4, 3),
                (4, 4),
                (5, 4),
                (5, 4),
                (6, 4),
                (5, 2),
                (6, 1),
                (2, 1),
            ),
        }

        self.assertEqual(sum(map(len, expected.values())), 36)
        for theme, layouts in expected.items():
            for depth, (node_length, branches) in enumerate(layouts, 1):
                with self.subTest(theme=theme, depth=depth):
                    layout = area_layout(theme, depth)
                    self.assertIsNotNone(layout)
                    self.assertEqual(layout["zoneId"], f"zone_{depth}")
                    self.assertEqual(layout["baseNodeLength"], node_length)
                    self.assertEqual(layout["maximumBranches"], branches)

        self.assertIsNone(area_layout("rogue_1", 7))
        self.assertIsNone(area_layout("rogue_unknown", 1))
        self.assertIsNone(area_layout("rogue_1", True))

    def test_layout_and_route_results_are_defensive_copies(self):
        layout = area_layout("rogue_1", 1)
        layout["baseNodeLength"] = 999
        self.assertEqual(area_layout("rogue_1", 1)["baseNodeLength"], 4)

        route = ending_route("rogue_2", "ro2_ending_1")
        route["terminalZoneId"] = "zone_99"
        self.assertEqual(
            ending_route("rogue_2", "ro2_ending_1")["terminalZoneId"],
            "zone_5",
        )

        specs = area_column_specs("rogue_5", 1)
        specs[0]["minimum"] = 99
        self.assertEqual(
            area_column_specs("rogue_5", 1)[0]["minimum"], 2
        )

    def test_reviewed_column_specs_match_every_area_length(self):
        for theme in ("rogue_1", "rogue_2", "rogue_3", "rogue_4", "rogue_5"):
            depth = 1
            while (layout := area_layout(theme, depth)) is not None:
                with self.subTest(theme=theme, depth=depth):
                    specs = area_column_specs(theme, depth)
                    self.assertIsNotNone(specs)
                    self.assertEqual(len(specs), layout["baseNodeLength"])
                    for spec in specs:
                        if spec is None:
                            continue
                        self.assertGreaterEqual(spec["minimum"], 1)
                        self.assertGreaterEqual(spec["maximum"], spec["minimum"])
                        self.assertLessEqual(
                            spec["maximum"], layout["maximumBranches"]
                        )
                        self.assertTrue(spec["kinds"])
                depth += 1

        self.assertIsNone(area_column_specs("rogue_1", 7))

    def test_reviewed_fixed_column_constraints(self):
        ro1_first = area_column_specs("rogue_1", 1)
        self.assertEqual(ro1_first[1]["minimum"], 2)
        self.assertEqual(ro1_first[1]["maximum"], 3)
        self.assertEqual(
            ro1_first[1]["kinds"], ("incident", "entertainment")
        )

        ro4_third = area_column_specs("rogue_4", 3)
        self.assertEqual(ro4_third[-2]["kinds"], ("alchemy",))

        ro4_fourth = area_column_specs("rogue_4", 4)
        self.assertEqual(ro4_fourth[0]["minimum_battle_nodes"], 1)

        for depth, battle_column in ((6, 2), (7, 1)):
            with self.subTest(depth=depth):
                ro5_specs = area_column_specs("rogue_5", depth)
                self.assertEqual(
                    ro5_specs[battle_column]["stage_depths"], (6, 7)
                )

    def test_default_and_hidden_ending_routes(self):
        expected = {
            ("rogue_1", "ro_ending_1"): (5, ["ro1_b_6"]),
            ("rogue_1", "ro_ending_2"): (5, ["ro1_b_7"]),
            ("rogue_1", "ro_ending_3"): (6, ["ro1_b_8"]),
            ("rogue_1", "ro_ending_4"): (6, ["ro1_b_9"]),
            ("rogue_2", "ro2_ending_1"): (5, ["ro2_b_4"]),
            ("rogue_2", "ro2_ending_2"): (5, ["ro2_b_5"]),
            ("rogue_2", "ro2_ending_3"): (6, ["ro2_b_6"]),
            ("rogue_2", "ro2_ending_4"): (6, ["ro2_b_7"]),
            ("rogue_3", "ro3_ending_1"): (5, ["ro3_b_4", "ro3_b_4_b"]),
            ("rogue_3", "ro3_ending_2"): (5, ["ro3_b_5", "ro3_b_5_b"]),
            ("rogue_3", "ro3_ending_3"): (6, ["ro3_b_6", "ro3_b_6_b"]),
            ("rogue_3", "ro3_ending_4"): (7, ["ro3_b_7", "ro3_b_7_b"]),
            ("rogue_4", "ro4_ending_1"): (
                5,
                ["ro4_b_4", "ro4_b_4_b", "ro4_b_4_c", "ro4_b_4_d"],
            ),
            ("rogue_4", "ro4_ending_2"): (
                5,
                ["ro4_b_5", "ro4_b_5_b", "ro4_b_5_c", "ro4_b_5_d"],
            ),
            ("rogue_4", "ro4_ending_3"): (6, ["ro4_b_6"]),
            ("rogue_4", "ro4_ending_4"): (7, ["ro4_b_7"]),
            ("rogue_4", "ro4_ending_5"): (8, ["ro4_b_8"]),
            ("rogue_5", "ro5_ending_1"): (5, ["ro5_b_4", "ro5_b_4_b"]),
            ("rogue_5", "ro5_ending_2"): (5, ["ro5_b_5", "ro5_b_5_b"]),
            ("rogue_5", "ro5_ending_3"): (6, ["ro5_b_6"]),
            ("rogue_5", "ro5_ending_4"): (7, ["ro5_b_7"]),
            ("rogue_5", "ro5_ending_5"): (
                8,
                [
                    "ro5_b_10",
                    "ro5_b_10_b",
                    "ro5_b_9_a",
                    "ro5_b_9_b",
                    "ro5_b_9_c",
                    "ro5_b_9_d",
                    "ro5_b_9_e",
                ],
            ),
        }

        self.assertEqual(len(expected), 22)
        for (theme, ending), (depth, stages) in expected.items():
            with self.subTest(theme=theme, ending=ending):
                route = ending_route(theme, ending)
                self.assertIsNotNone(route)
                self.assertEqual(terminal_depth(theme, ending), depth)
                self.assertEqual(boss_stage_ids(theme, ending), stages)

        self.assertIsNone(ending_route("rogue_1", "missing"))
        self.assertIsNone(terminal_depth("rogue_1", "missing"))
        self.assertEqual(boss_stage_ids("rogue_1", "missing"), [])
        self.assertIsNone(terminal_depth([], "ro_ending_1"))
        self.assertEqual(boss_stage_ids("rogue_1", []), [])

    def test_event_candidates_require_an_explicit_matching_depth(self):
        available = [
            "scene_bat1_enter",
            "scene_1_enter",
            "scene_blood1_enter",
            "scene_ent1_enter",
        ]

        self.assertEqual(
            set(event_scene_candidates("rogue_1", 2, 32, available)),
            {"scene_bat1_enter", "scene_blood1_enter"},
        )
        self.assertEqual(
            set(event_scene_candidates("rogue_1", 3, 32, available)),
            {"scene_1_enter", "scene_blood1_enter"},
        )
        self.assertEqual(
            event_scene_candidates(
                "rogue_1", 3, 32, ["scene_bat1_enter"]
            ),
            [],
        )
        # Null logicalDepths means unknown, not eligible at every depth.
        self.assertEqual(
            event_scene_candidates(
                "rogue_1", 3, 128, ["scene_ent1_enter"]
            ),
            [],
        )

    def test_event_node_categories_and_quarantine_are_isolated(self):
        incident = "scene_blood1_enter"
        self.assertEqual(
            event_scene_candidates("rogue_1", 1, 32, [incident]),
            [incident],
        )
        self.assertEqual(
            event_scene_candidates("rogue_1", 1, 16, [incident]), []
        )
        self.assertEqual(
            event_scene_candidates("rogue_1", 1, 999999, [incident]), []
        )
        self.assertEqual(
            event_scene_candidates("rogue_1", 1, "32", [incident]), []
        )

        quarantined_rest_scenes = [
            "scene_ro3_month1_enter",
            "scene_ro3_rest1_enter",
            "scene_ro3_rest2_enter",
            "scene_ro3_rest3_enter",
            "scene_ro3_rest4_enter",
        ]
        self.assertEqual(
            event_scene_candidates(
                "rogue_3", 1, 16, quarantined_rest_scenes
            ),
            [],
        )

    def test_standard_incident_counts_match_fixed_prts_floors(self):
        expected = {
            "rogue_1": (8, 17, 25, 28, 27),
            "rogue_2": (9, 23, 24, 32, 27),
            "rogue_3": (11, 11, 14, 14, 14, 12, 11),
            "rogue_4": (7, 15, 25, 22, 15, 11),
            "rogue_5": (8, 15, 19, 20, 17, 8),
        }
        with (ROOT / "data/rlv2/rules/event_tags.json").open(
            encoding="utf-8"
        ) as file:
            annotations = json.load(file)["annotations"]
        scenes_by_theme = {
            theme: [
                record["sceneId"]
                for record in annotations.values()
                if record["theme"] == theme
            ]
            for theme in expected
        }

        for theme, counts in expected.items():
            actual = tuple(
                len(
                    event_scene_candidates(
                        theme,
                        depth,
                        32,
                        scenes_by_theme[theme],
                    )
                )
                for depth in range(1, len(counts) + 1)
            )
            self.assertEqual(actual, counts)

    def test_only_reviewed_resource_events_are_repeatable(self):
        repeatable = {
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
        for theme, scene_id in repeatable:
            with self.subTest(theme=theme, scene=scene_id):
                self.assertTrue(event_scene_is_repeatable(theme, scene_id))
        self.assertFalse(
            event_scene_is_repeatable("rogue_1", "scene_blood1_enter")
        )
        self.assertFalse(event_scene_is_repeatable("rogue_3", "scene_hp_enter"))


if __name__ == "__main__":
    unittest.main()

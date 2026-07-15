import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from random import Random


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_logic import (  # noqa: E402
    RO5_ALWAYS_FIVE_MIMIC_STAGES,
    apply_numeric_delta,
    apply_battle_reward_modifiers,
    battle_base_reward,
    battle_mimic_group_count,
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
    prepare_predefined_characters,
    prepare_recruit_candidates,
    recruit_group_ticket_ids,
    roll_mimic_group_count,
    sample_event_choices,
    select_weighted_event_branch,
    resolve_player_levels,
    select_equivalent_grade,
    select_init_config,
    select_player_level_table,
    settle_battle_life,
)


class Rlv2LogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "data/excel/roguelike_topic_table.json").open(
            encoding="utf-8"
        ) as file:
            cls.topic_table = json.load(file)
        with (ROOT / "data/rlv2/event_choices.json").open(
            encoding="utf-8"
        ) as file:
            cls.event_choices = json.load(file)

    def test_init_config_comes_from_current_client_table(self):
        expected = {
            "rogue_1": (4, 6, 6, 10),
            "rogue_2": (4, 6, 6, 22),
            "rogue_3": (8, 6, 6, 13),
            "rogue_4": (8, 6, 6, 27),
            "rogue_5": (8, 8, 6, 26),
        }
        for theme, values in expected.items():
            with self.subTest(theme=theme):
                config = select_init_config(
                    self.topic_table, theme, "NORMAL", 0
                )
                actual = (
                    config["initialHp"],
                    config["initialGold"],
                    config["initialPopulation"],
                    len(config["initialBandRelic"]),
                )
                self.assertEqual(actual, values)

    def test_legacy_game_over_is_migrated_to_client_settlement_state(self):
        run = {
            "player": {
                "state": "GAME_OVER",
                "pending": [],
                "trace": [{"zone": 1}],
                "status": {
                    "bankPut": 0,
                    "gameResult": {
                        "success": False,
                        "reason": "BATTLE_ABORTED",
                    },
                },
                "property": {"level": 2},
                "cursor": {"zone": 1, "position": {"x": 0, "y": 0}},
                "toEnding": "ro_ending_1",
            },
            "game": {
                "theme": "rogue_1",
                "mode": "NORMAL",
                "eGrade": 0,
                "start": 10,
            },
            "map": {"zones": {"1": {"id": "zone_1"}}},
            "inventory": {
                "relic": {
                    "r_0": {"id": "rogue_1_band_1", "count": 1}
                },
                "exploreTool": {},
            },
            "troop": {"chars": {}},
            "buff": {"squadBuff": []},
            "module": {},
        }

        self.assertTrue(normalize_current_run(run, 20))

        player = run["player"]
        self.assertEqual(player["state"], "PENDING")
        self.assertEqual(player["trace"], [])
        self.assertNotIn("gameResult", player["status"])
        pending = player["pending"][0]
        self.assertEqual(pending["type"], "GAME_SETTLE")
        result = pending["content"]["result"]
        self.assertEqual(result["brief"]["success"], 0)
        self.assertEqual(result["brief"]["mode"], "NORMAL")
        self.assertEqual(result["brief"]["band"], "rogue_1_band_1")
        self.assertEqual(result["record"]["cntZone"], 1)
        self.assertFalse(normalize_current_run(run, 21))

    def test_ending_record_counts_visited_route_zones_instead_of_zone_id(self):
        for zone, ordered_zones, expected_count in (
            (7, [1, 2, 3, 4, 5, 7], 6),
            (8, [1, 2, 3, 4, 5, 7, 8], 7),
        ):
            with self.subTest(zone=zone):
                run = {
                    "_server": {"route": {"orderedZones": ordered_zones}},
                    "player": {
                        "property": {"level": 1},
                        "cursor": {"zone": zone, "position": None},
                        "toEnding": "ro5_ending_5",
                    },
                    "game": {"theme": "rogue_5", "mode": "NORMAL"},
                    "map": {"zones": {str(zone): {"id": f"zone_{zone}"}}},
                    "inventory": {"relic": {}, "exploreTool": {}},
                    "troop": {"chars": {}},
                    "buff": {"squadBuff": []},
                    "module": {},
                }

                result = build_ending_result(run, True, 100)

                self.assertEqual(result["record"]["cntZone"], expected_count)

    def test_legacy_battle_reward_fields_are_normalized(self):
        run = {
            "player": {
                "state": "PENDING",
                "pending": [
                    {
                        "type": "BATTLE_REWARD",
                        "content": {
                            "battleReward": {
                                "earn": {"hp": 0},
                                "rewards": [],
                                "show": "1",
                            }
                        },
                    }
                ],
                "status": {},
            }
        }

        self.assertTrue(normalize_current_run(run, 1))

        reward = run["player"]["pending"][0]["content"]["battleReward"]
        self.assertIsNone(reward["show"])
        self.assertEqual(reward["state"], 3)
        self.assertEqual(reward["isPerfect"], 1)

    def test_legacy_battle_mimic_chance_is_normalized(self):
        run = {
            "player": {
                "state": "PENDING",
                "pending": [
                    {"type": "RECRUIT", "content": {}},
                    {
                        "type": "BATTLE",
                        "content": {
                            "battle": {
                                "chestCnt": 100,
                                "goldTrapCnt": 10,
                            }
                        },
                    }
                ],
                "status": {},
            }
        }

        self.assertTrue(normalize_current_run(run, 1))
        battle = run["player"]["pending"][1]["content"]["battle"]
        self.assertEqual(battle["chestCnt"], 0)
        self.assertEqual(battle["goldTrapCnt"], 100)
        self.assertFalse(normalize_current_run(run, 2))

    def test_legacy_mandatory_mimic_battle_preserves_one_group(self):
        run = {
            "player": {
                "state": "PENDING",
                "cursor": {"zone": 1, "position": {"x": 0, "y": 0}},
                "pending": [
                    {
                        "type": "BATTLE",
                        "content": {
                            "battle": {"chestCnt": 100, "goldTrapCnt": 100}
                        },
                    }
                ],
                "status": {},
            },
            "map": {
                "zones": {
                    "1": {"nodes": {"0": {"stage": "ro1_t_1"}}}
                }
            },
        }

        self.assertTrue(normalize_current_run(run, 1))
        battle = run["player"]["pending"][0]["content"]["battle"]
        self.assertEqual(battle["chestCnt"], 1)
        self.assertEqual(battle["goldTrapCnt"], 100)

    def test_legacy_scene_removes_disabled_choices_and_adds_leave(self):
        run = {
            "player": {
                "state": "PENDING",
                "pending": [
                    {
                        "type": "SCENE",
                        "content": {
                            "scene": {
                                "choices": {"choice_disabled": True},
                                "choiceAdditional": {
                                    "choice_disabled": {"rewards": []}
                                },
                            }
                        },
                    }
                ],
                "status": {},
            }
        }

        self.assertTrue(
            normalize_current_run(run, 1, {"choice_disabled"})
        )
        scene = run["player"]["pending"][0]["content"]["scene"]
        self.assertEqual(scene["choices"], {"choice_leave": True})
        self.assertEqual(
            scene["choiceAdditional"],
            {"choice_leave": {"rewards": []}},
        )

    def test_gopnik_target_rate_is_encoded_as_a_mimic_group_roll(self):
        class SequentialRolls:
            def __init__(self):
                self.value = 0
                self.stop = None

            def randrange(self, stop):
                self.stop = stop
                value = self.value
                self.value += 1
                return value

        expected_hits = {
            "rogue_1": 20,
            "rogue_2": 40,
            "rogue_3": 30,
            "rogue_4": 40,
            "rogue_5": 40,
        }
        for theme, expected in expected_hits.items():
            with self.subTest(theme=theme):
                rng = SequentialRolls()
                hits = sum(
                    roll_mimic_group_count(theme, rng) for _ in range(100)
                )
                self.assertEqual(rng.stop, 100)
                self.assertEqual(hits, expected)

    def test_mimic_group_count_distinguishes_random_and_event_stages(self):
        class FixedRoll:
            def __init__(self, value):
                self.value = value

            def randrange(self, stop):
                return self.value

        self.assertEqual(
            battle_mimic_group_count("rogue_1", "ro1_n_1_1", FixedRoll(19)),
            1,
        )
        self.assertEqual(
            battle_mimic_group_count("rogue_1", "ro1_n_1_1", FixedRoll(20)),
            0,
        )
        for stage_id in ("ro1_t_1", "ro1_t_2", "ro1_t_4", "ro2_t_1"):
            with self.subTest(stage=stage_id):
                theme = "rogue_1" if stage_id.startswith("ro1_") else "rogue_2"
                self.assertEqual(
                    battle_mimic_group_count(theme, stage_id, FixedRoll(99)),
                    1,
                )
        for stage_id in ("ro1_t_3", "ro2_t_3", "ro1_ev_1", "ro2_ev_1"):
            with self.subTest(stage=stage_id):
                theme = "rogue_1" if stage_id.startswith("ro1_") else "rogue_2"
                self.assertEqual(
                    battle_mimic_group_count(theme, stage_id, FixedRoll(0)),
                    0,
                )

        for stage_id in ("ro4_e_t_2", "ro5_e_t_1"):
            with self.subTest(stage=stage_id):
                theme = "rogue_4" if stage_id.startswith("ro4_") else "rogue_5"
                self.assertEqual(
                    battle_mimic_group_count(theme, stage_id, FixedRoll(0)),
                    0,
                )

    def test_ro5_always_five_mimic_stages_use_a_fifty_percent_group_roll(self):
        expected = {
            "ro5_n_1_5",
            "ro5_e_1_5",
            "ro5_n_1_6",
            "ro5_e_1_6",
            "ro5_n_2_5",
            "ro5_e_2_5",
            "ro5_n_2_6",
            "ro5_e_2_6",
            "ro5_n_3_6",
            "ro5_e_3_6",
            "ro5_n_4_7",
            "ro5_e_4_7",
            "ro5_n_5_7",
            "ro5_e_5_7",
            "ro5_n_7_1",
            "ro5_e_7_1",
            "ro5_n_7_2",
            "ro5_e_7_2",
        }
        self.assertEqual(RO5_ALWAYS_FIVE_MIMIC_STAGES, expected)

        class FixedRoll:
            def __init__(self, value):
                self.value = value

            def randrange(self, stop):
                self.assert_stop = stop
                return self.value

        for stage_id in expected:
            with self.subTest(stage=stage_id):
                self.assertEqual(
                    battle_mimic_group_count("rogue_5", stage_id, FixedRoll(49)),
                    1,
                )
                self.assertEqual(
                    battle_mimic_group_count("rogue_5", stage_id, FixedRoll(50)),
                    0,
                )

        self.assertEqual(
            battle_mimic_group_count("rogue_5", "ro5_n_1_1", FixedRoll(39)),
            1,
        )
        self.assertEqual(
            battle_mimic_group_count("rogue_5", "ro5_n_1_1", FixedRoll(40)),
            0,
        )

    def test_event_probability_only_applies_the_declared_get_effect(self):
        class FixedRoll:
            def __init__(self, value):
                self.value = value

            def randrange(self, stop):
                self.assert_stop = stop
                return self.value

        probability = {"percent": 70, "appliesTo": "get"}
        success = FixedRoll(69)
        failure = FixedRoll(70)
        self.assertTrue(event_probability_succeeds(probability, success))
        self.assertFalse(event_probability_succeeds(probability, failure))
        self.assertEqual(success.assert_stop, 100)

    def test_population_max_cost_requires_unspent_hope(self):
        self.assertFalse(
            has_numeric_cost({"cost": 6, "max": 6}, {"max": 2})
        )
        self.assertFalse(
            has_numeric_cost({"cost": 5, "max": 6}, {"max": 2})
        )
        self.assertTrue(
            has_numeric_cost({"cost": 4, "max": 6}, {"max": 2})
        )

    def test_sanity_module_is_clamped_to_client_range(self):
        module = {"san": {"sanity": 140}}
        clamp_sanity_module(module)
        self.assertEqual(module["san"]["sanity"], 100)
        module["san"]["sanity"] = -15
        clamp_sanity_module(module)
        self.assertEqual(module["san"]["sanity"], 0)

    def test_generic_event_relic_pool_excludes_route_and_explicit_rewards(self):
        ro1_items = self.topic_table["details"]["rogue_1"]["items"]
        ro1_candidates = event_relic_pool_candidates(
            "rogue_1", ro1_items
        )
        self.assertIn("rogue_1_relic_a01", ro1_candidates)
        self.assertNotIn("rogue_1_relic_m16", ro1_candidates)
        self.assertNotIn("rogue_1_relic_m20", ro1_candidates)
        self.assertNotIn("rogue_1_relic_n01", ro1_candidates)
        self.assertNotIn("rogue_1_relic_m07", ro1_candidates)
        self.assertFalse(
            any(
                item_id.startswith("rogue_1_relic_m")
                for item_id in ro1_candidates
            )
        )

        ro2_items = self.topic_table["details"]["rogue_2"]["items"]
        grace_candidates = event_relic_pool_candidates(
            "rogue_2", ro2_items, False
        )
        curse_candidates = event_relic_pool_candidates(
            "rogue_2", ro2_items, True
        )
        self.assertIn("rogue_2_relic_grace_1", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_83", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_84", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_60", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_76", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_79", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_80", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_81", grace_candidates)
        self.assertNotIn("rogue_2_relic_grace_82", grace_candidates)
        self.assertNotIn("rogue_2_relic_fight_38", grace_candidates)
        self.assertIn("rogue_2_relic_grace_77", grace_candidates)
        self.assertIn("rogue_2_relic_grace_78", grace_candidates)
        self.assertIn("rogue_2_relic_curse_1", curse_candidates)
        self.assertNotIn("rogue_2_relic_curse_7", curse_candidates)
        self.assertTrue(
            all("_relic_curse_" not in item_id for item_id in grace_candidates)
        )
        self.assertTrue(
            all("_relic_curse_" in item_id for item_id in curse_candidates)
        )

    def test_event_probability_branch_selects_only_one_outcome(self):
        class FixedRoll:
            def __init__(self, value):
                self.value = value

            def randrange(self, stop):
                self.assert_stop = stop
                return self.value

        branches = [
            {"weight": 20, "scene": "success", "choices": ["collect"]},
            {"weight": 80, "scene": "retry", "choices": ["again", "leave"]},
        ]
        self.assertEqual(
            select_weighted_event_branch(branches, FixedRoll(19))["scene"],
            "success",
        )
        self.assertEqual(
            select_weighted_event_branch(branches, FixedRoll(20))["scene"],
            "retry",
        )

    def test_event_scene_sampling_keeps_required_choices(self):
        choices = ["one", "two", "three", "four", "leave"]
        sampled = sample_event_choices(
            choices,
            {"sample": 4, "required": ["leave"]},
            Random(7),
        )
        self.assertEqual(len(sampled), 4)
        self.assertIn("leave", sampled)
        ranged = sample_event_choices(
            choices[:4], {"sample": [2, 3]}, Random(8)
        )
        self.assertIn(len(ranged), {2, 3})

    def test_init_property_uses_table_level_and_resource_limits(self):
        config = select_init_config(
            self.topic_table, "rogue_2", "NORMAL", 0
        )
        levels = self.topic_table["details"]["rogue_2"]["detailConst"][
            "playerLevelTable"
        ]
        prop = build_initial_property(config, levels)
        self.assertEqual(prop["level"], 1)
        self.assertEqual(prop["maxLevel"], 10)
        self.assertEqual(prop["hp"], {"current": 4, "max": 4})
        self.assertEqual(prop["gold"], 6)
        self.assertEqual(prop["capacity"], 6)

    def test_equivalent_grade_is_read_from_difficulty_table(self):
        self.assertEqual(
            select_equivalent_grade(
                self.topic_table, "rogue_5", "NORMAL", 18
            ),
            18,
        )

    def test_sparse_nested_delta_only_touches_declared_paths(self):
        target = {
            "exp": 0,
            "gold": 6,
            "hp": {"current": 4, "max": 4},
        }
        apply_numeric_delta(target, {"gold": 2}, -1)
        apply_numeric_delta(target, {"hp": {"current": 3}})
        self.assertEqual(
            target,
            {"exp": 0, "gold": 4, "hp": {"current": 7, "max": 4}},
        )
        clamp_player_property(
            {
                **target,
                "level": 1,
                "maxLevel": 10,
                "shield": 0,
                "capacity": 6,
                "population": {"cost": 0, "max": 6},
            }
        )

    def test_sparse_cost_validation_checks_nested_bounds(self):
        target = {
            "gold": 6,
            "hp": {"current": 4, "max": 4},
            "population": {"cost": 5, "max": 6},
        }
        self.assertTrue(has_numeric_cost(target, {"gold": 6}))
        self.assertFalse(has_numeric_cost(target, {"gold": 7}))
        self.assertTrue(
            has_numeric_cost(target, {"population": {"cost": -1}})
        )
        self.assertFalse(
            has_numeric_cost(target, {"population": {"cost": -2}})
        )

    def test_recruit_groups_match_their_documented_professions(self):
        self.assertEqual(
            recruit_group_ticket_ids(
                "rogue_5", "recruit_group_4", Random(1)
            ),
            [
                "rogue_5_recruit_ticket_pioneer_init",
                "rogue_5_recruit_ticket_support_init",
                "rogue_5_recruit_ticket_special_init",
            ],
        )
        random_group = recruit_group_ticket_ids(
            "rogue_2", "recruit_group_random", Random(1)
        )
        self.assertEqual(len(random_group), 3)
        self.assertEqual(len(set(random_group)), 3)

    def test_special_modes_require_an_explicit_predefined_id(self):
        for theme in self.topic_table["details"]:
            for mode in ("MONTH_TEAM", "CHALLENGE"):
                with self.subTest(theme=theme, mode=mode):
                    with self.assertRaisesRegex(
                        ValueError, "predefinedId is required"
                    ):
                        select_init_config(
                            self.topic_table, theme, mode, 0
                        )

    def test_ro3_challenge_uses_its_fifty_level_table(self):
        theme_data = self.topic_table["details"]["rogue_3"]
        predefined = "rogue_3_challenge_01"
        init = select_init_config(
            self.topic_table,
            "rogue_3",
            "CHALLENGE",
            0,
            predefined,
        )
        levels, max_level = select_player_level_table(
            theme_data, "CHALLENGE", 0, predefined
        )
        prop = build_initial_property(init, levels, max_level)

        self.assertEqual(max_level, 50)
        self.assertEqual(len(levels), 50)
        self.assertEqual(prop["maxLevel"], 50)

        _, normal_max_level = select_player_level_table(
            theme_data, "NORMAL", 0, None
        )
        self.assertEqual(normal_max_level, 10)

    def test_monthly_squad_requires_and_selects_amiya_template(self):
        team_chars = self.topic_table["details"]["rogue_4"][
            "monthSquad"
        ]["month_team_8"]["teamChars"]
        amiya_template = "char_1037_amiya3"
        candidates = [
            {
                "charId": "char_002_amiya",
                "currentTmpl": None,
                "evolvePhase": 2,
                "level": 90,
            },
            {
                "charId": "char_002_amiya",
                "currentTmpl": amiya_template,
                "evolvePhase": 1,
                "level": 80,
            },
            {
                "charId": "char_002_amiya",
                "currentTmpl": amiya_template,
                "evolvePhase": 2,
                "level": 60,
            },
        ]

        result = prepare_predefined_characters(candidates, team_chars)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["currentTmpl"], amiya_template)
        self.assertEqual(result[0]["evolvePhase"], 2)
        self.assertEqual(result[0]["type"], "FREE")
        self.assertEqual(result[0]["population"], 0)

        with self.assertRaisesRegex(ValueError, "monthly squad operator"):
            prepare_predefined_characters(candidates[:1], team_chars)

    def test_ro5_initial_tickets_are_init_only_and_not_stashable(self):
        theme_data = self.topic_table["details"]["rogue_5"]
        groups = {
            group
            for init in theme_data["init"]
            for group in (init.get("initialRecruitGroup") or [])
        }
        self.assertTrue(groups)

        for group in groups:
            with self.subTest(group=group):
                tickets = recruit_group_ticket_ids(
                    "rogue_5", group, Random(19)
                )
                self.assertTrue(tickets)
                for ticket in tickets:
                    self.assertTrue(ticket.endswith("_init"), ticket)
                    self.assertIn(ticket, theme_data["recruitTickets"])
                    self.assertNotIn(ticket, theme_data["stashableTickets"])

    def test_every_table_initial_group_resolves_to_known_tickets(self):
        for theme, theme_data in self.topic_table["details"].items():
            groups = {
                group
                for init in theme_data["init"]
                for group in (init.get("initialRecruitGroup") or [])
            }
            for group in groups:
                with self.subTest(theme=theme, group=group):
                    tickets = recruit_group_ticket_ids(
                        theme, group, Random(f"{theme}/{group}")
                    )
                    self.assertTrue(tickets)
                    self.assertTrue(
                        all(
                            ticket in theme_data["recruitTickets"]
                            for ticket in tickets
                        )
                    )

    def test_random_group_premium_ticket_varies_by_theme(self):
        tickets = {
            theme: recruit_group_ticket_ids(
                theme, "recruit_group_random", Random(17)
            )
            for theme in self.topic_table["details"]
        }
        base_professions = [
            ticket.split("recruit_ticket_", 1)[1].rsplit("_", 1)[0]
            for ticket in (tickets["rogue_1"][2], tickets["rogue_4"][2])
        ]

        self.assertEqual(base_professions[0], base_professions[1])
        for theme in ("rogue_1", "rogue_2", "rogue_3"):
            self.assertTrue(tickets[theme][2].endswith("_sp"))
        self.assertTrue(tickets["rogue_4"][2].endswith("_vip"))
        self.assertTrue(tickets["rogue_5"][2].endswith("_vip_init"))
        for theme, theme_tickets in tickets.items():
            self.assertIn(
                theme_tickets[2],
                self.topic_table["details"][theme]["recruitTickets"],
            )

    def test_challenge_recruit_groups_contain_two_special_tickets(self):
        cases = (
            ("rogue_1", "recruit_group_c4"),
            ("rogue_1", "recruit_group_c5"),
            ("rogue_4", "recruit_group_c9"),
            ("rogue_4", "recruit_group_c10"),
        )
        for theme, group in cases:
            with self.subTest(theme=theme, group=group):
                tickets = recruit_group_ticket_ids(theme, group, Random(1))
                self.assertEqual(len(tickets), 4)
                self.assertEqual(
                    sum(ticket.endswith("_sp") for ticket in tickets), 2
                )
                for ticket in tickets:
                    self.assertIn(
                        ticket,
                        self.topic_table["details"][theme]["recruitTickets"],
                    )

    def test_battle_base_rewards_match_the_verified_sixty_cell_matrix(self):
        expected = {
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

        checked = 0
        for theme, zones in expected.items():
            for zone, (normal, emergency) in enumerate(zones, start=1):
                for node_type, reward in ((1, normal), (2, emergency)):
                    with self.subTest(
                        theme=theme, zone=zone, node_type=node_type
                    ):
                        self.assertEqual(
                            battle_base_reward(theme, zone, node_type), reward
                        )
                        checked += 1
        self.assertEqual(checked, 60)

    def test_battle_base_reward_aliases_late_ro3_ro4_and_ro5_zones(self):
        for theme in ("rogue_3", "rogue_4", "rogue_5"):
            for node_type in (1, 2):
                with self.subTest(theme=theme, node_type=node_type):
                    self.assertEqual(
                        battle_base_reward(theme, 7, node_type),
                        battle_base_reward(theme, 6, node_type),
                    )

    def test_battle_reward_modifiers_multiply_and_floor_each_resource(self):
        final_relic = "rogue_5_relic_final_7"
        relic_table = self.topic_table["details"]["rogue_5"]["relics"]
        inventory = {"r_0": {"id": final_relic, "count": 1}}

        self.assertEqual(
            apply_battle_reward_modifiers(
                5, "rogue_5_exp", inventory, relic_table
            ),
            2,
        )
        self.assertEqual(
            apply_battle_reward_modifiers(
                5, "rogue_5_gold", inventory, relic_table
            ),
            2,
        )
        self.assertEqual(
            apply_battle_reward_modifiers(
                5, "rogue_5_hp", inventory, relic_table
            ),
            5,
        )

        synthetic_table = {
            "first": {
                "buffs": [
                    {
                        "key": "up_reward",
                        "blackboard": [
                            {"key": "id", "valueStr": "exp"},
                            {"key": "up", "value": 0.1},
                            {"key": "mask", "valueStr": "battle"},
                        ],
                    }
                ]
            },
            "second": {
                "buffs": [
                    {
                        "key": "up_reward",
                        "blackboard": [
                            {"key": "id", "valueStr": "exp"},
                            {"key": "up", "value": 0.1},
                            {"key": "mask", "valueStr": "battle"},
                        ],
                    }
                ]
            },
        }
        self.assertEqual(
            apply_battle_reward_modifiers(
                10,
                "exp",
                {"r_0": {"id": "first"}, "r_1": {"id": "second"}},
                synthetic_table,
            ),
            12,
        )

    def test_battle_base_reward_rejects_unknown_cells(self):
        for theme in (None, "", "rogue_0", "rogue_6"):
            with self.subTest(theme=theme):
                with self.assertRaises(ValueError):
                    battle_base_reward(theme, 1, 1)

        for theme in tuple(f"rogue_{index}" for index in range(1, 6)):
            invalid_zones = (-1, 0, 8, True, "1")
            if theme not in {"rogue_3", "rogue_4", "rogue_5"}:
                invalid_zones = (*invalid_zones, 7)
            for zone in invalid_zones:
                with self.subTest(theme=theme, zone=zone):
                    with self.assertRaises(ValueError):
                        battle_base_reward(theme, zone, 1)

            for node_type in (-1, 0, 3, 4, True, "1"):
                with self.subTest(theme=theme, node_type=node_type):
                    with self.assertRaises(ValueError):
                        battle_base_reward(theme, 1, node_type)

    def test_battle_resource_item_ids_match_all_theme_item_types(self):
        for theme in tuple(f"rogue_{index}" for index in range(1, 6)):
            with self.subTest(theme=theme):
                theme_data = self.topic_table["details"][theme]
                resource_ids = battle_resource_item_ids(theme_data)
                self.assertEqual(
                    resource_ids,
                    {
                        "exp": theme_data["gameConst"]["expItemId"],
                        "gold": theme_data["gameConst"]["goldItemId"],
                    },
                )
                self.assertEqual(
                    theme_data["items"][resource_ids["exp"]]["type"], "EXP"
                )
                self.assertEqual(
                    theme_data["items"][resource_ids["gold"]]["type"], "GOLD"
                )

    def test_battle_resource_item_ids_reject_invalid_item_references(self):
        theme_data = deepcopy(self.topic_table["details"]["rogue_1"])
        theme_data["gameConst"]["expItemId"] = "missing_exp"
        with self.assertRaisesRegex(ValueError, "exp item"):
            battle_resource_item_ids(theme_data)

        theme_data = deepcopy(self.topic_table["details"]["rogue_1"])
        gold_id = theme_data["gameConst"]["goldItemId"]
        theme_data["items"][gold_id]["type"] = "EXP"
        with self.assertRaisesRegex(ValueError, "gold item"):
            battle_resource_item_ids(theme_data)

    def test_player_experience_levels_up_with_table_defined_gains(self):
        theme_data = self.topic_table["details"]["rogue_3"]
        levels, max_level = select_player_level_table(
            theme_data, "NORMAL", 0, None
        )
        init = select_init_config(
            self.topic_table, "rogue_3", "NORMAL", 0
        )
        prop = build_initial_property(init, levels, max_level)

        prop["exp"] = 34
        gains = resolve_player_levels(prop, levels)
        self.assertEqual(prop["level"], 3)
        self.assertEqual(prop["exp"], 0)
        self.assertEqual(prop["population"]["max"], 14)
        self.assertEqual(prop["hp"], {"current": 9, "max": 9})
        self.assertEqual(
            gains,
            {
                "populationMax": 8,
                "squadCapacity": 0,
                "maxHpUp": 1,
                "battleCharLimitUp": 0,
            },
        )

    def test_battle_life_consumes_shield_before_hp(self):
        init = select_init_config(
            self.topic_table, "rogue_3", "NORMAL", 0
        )
        levels = self.topic_table["details"]["rogue_3"]["detailConst"][
            "playerLevelTable"
        ]
        prop = build_initial_property(init, levels)
        prop["shield"] = 3

        shield_only = settle_battle_life(
            prop, {}, "rogue_3", prop["hp"]["current"]
        )
        self.assertEqual(shield_only, {"damage": 3, "hp": 0, "shield": -3})
        self.assertEqual(prop["hp"]["current"], 8)
        self.assertEqual(prop["shield"], 0)
        self.assertEqual(prop["conPerfectBattle"], 1)

        hp_damage = settle_battle_life(prop, {}, "rogue_3", 5)
        self.assertEqual(hp_damage, {"damage": 3, "hp": -3, "shield": 0})
        self.assertEqual(prop["hp"]["current"], 5)
        self.assertEqual(prop["conPerfectBattle"], 0)

    def test_ro1_temporary_life_resets_each_battle(self):
        init = select_init_config(
            self.topic_table, "rogue_1", "NORMAL", 0
        )
        levels = self.topic_table["details"]["rogue_1"]["detailConst"][
            "playerLevelTable"
        ]
        prop = build_initial_property(init, levels)
        buff = {"tmpHP": 4}

        earn = settle_battle_life(
            prop, buff, "rogue_1", prop["hp"]["current"] + 2
        )
        self.assertEqual(earn, {"damage": 2, "hp": 0, "shield": 0})
        self.assertEqual(buff["tmpHP"], 4)
        self.assertEqual(prop["hp"]["current"], init["initialHp"])
        self.assertEqual(prop["conPerfectBattle"], 1)

    def test_ro3_emergency_node_limits_are_deterministic(self):
        nodes = {
            str(index): {"index": str(index), "type": 2, "stage": "elite"}
            for index in range(5)
        }
        enforce_emergency_node_limits(
            "rogue_3", 2, nodes, ["normal"], ["elite"], Random(7)
        )
        self.assertEqual(sum(node["type"] == 2 for node in nodes.values()), 1)
        self.assertTrue(
            all(
                node["stage"] == ("elite" if node["type"] == 2 else "normal")
                for node in nodes.values()
            )
        )

        first_floor = {
            "0": {"type": 1, "stage": "normal"},
            "1": {"type": 1, "stage": "normal"},
        }
        enforce_emergency_node_limits(
            "rogue_3", 1, first_floor, ["normal"], ["elite"], Random(7)
        )
        self.assertEqual(
            sum(node["type"] == 2 for node in first_floor.values()), 1
        )

    def test_difficulty_buff_replacements_do_not_mutate_global_rows(self):
        rows = [
            ([{"key": "grade_0"}], []),
            ([{"key": "grade_1"}], []),
            ([{"key": "grade_2"}], [1]),
        ]
        original = deepcopy(rows)
        self.assertEqual(
            collect_difficulty_buffs(rows, 2),
            [{"key": "grade_0"}, {"key": "grade_2"}],
        )
        self.assertEqual(rows, original)

    def test_recruit_candidates_filter_profession_and_offer_upgrade(self):
        candidates = [
            {"charId": "six", "evolvePhase": 2, "currentTmpl": None},
            {"charId": "six", "evolvePhase": 1, "currentTmpl": None},
            {"charId": "medic", "evolvePhase": 1, "currentTmpl": None},
        ]
        character_table = {
            "six": {"profession": "CASTER", "rarity": "TIER_6"},
            "medic": {"profession": "MEDIC", "rarity": "TIER_5"},
        }
        ticket = {
            "id": "rogue_3_recruit_ticket_caster",
            "professionList": ["CASTER"],
            "rarityList": ["TIER_1", "TIER_2", "TIER_3", "TIER_4", "TIER_5", "TIER_6"],
            "extraCharIds": [],
            "extraFreeRarity": [],
        }

        first = prepare_recruit_candidates(
            candidates, character_table, ticket, {}
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["evolvePhase"], 1)
        self.assertEqual(first[0]["population"], 6)
        self.assertFalse(first[0]["isUpgrade"])

        upgrade = prepare_recruit_candidates(
            candidates,
            character_table,
            ticket,
            {"1": {"charId": "six", "evolvePhase": 1}},
        )
        self.assertEqual(len(upgrade), 1)
        self.assertEqual(upgrade[0]["evolvePhase"], 2)
        self.assertEqual(upgrade[0]["population"], 3)
        self.assertTrue(upgrade[0]["isUpgrade"])

    def test_amiya_templates_use_their_patch_profession(self):
        candidates = [
            {
                "charId": "char_002_amiya",
                "currentTmpl": "char_1001_amiya2",
                "evolvePhase": 1,
            },
            {
                "charId": "char_002_amiya",
                "currentTmpl": "char_1037_amiya3",
                "evolvePhase": 1,
            },
        ]
        character_table = {
            "char_002_amiya": {"profession": "CASTER", "rarity": "TIER_5"},
            "char_1001_amiya2": {"profession": "WARRIOR", "rarity": "TIER_5"},
            "char_1037_amiya3": {"profession": "MEDIC", "rarity": "TIER_5"},
        }
        ticket = {
            "id": "rogue_5_recruit_ticket_warrior",
            "professionList": ["WARRIOR"],
            "rarityList": ["TIER_5"],
            "extraCharIds": [],
            "extraFreeRarity": [],
        }

        result = prepare_recruit_candidates(
            candidates, character_table, ticket, {}
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["currentTmpl"], "char_1001_amiya2")

    def test_late_themes_use_reduced_four_and_five_star_costs(self):
        candidates = [
            {"charId": "four", "evolvePhase": 1, "currentTmpl": None},
            {"charId": "five", "evolvePhase": 1, "currentTmpl": None},
        ]
        character_table = {
            "four": {"profession": "CASTER", "rarity": "TIER_4"},
            "five": {"profession": "CASTER", "rarity": "TIER_5"},
        }
        ticket = {
            "id": "rogue_4_recruit_ticket_caster",
            "professionList": ["CASTER"],
            "rarityList": ["TIER_4", "TIER_5"],
            "extraCharIds": [],
            "extraFreeRarity": [],
        }
        result = prepare_recruit_candidates(
            candidates, character_table, ticket, {}
        )
        self.assertEqual(
            {char["charId"]: char["population"] for char in result},
            {"four": 0, "five": 2},
        )

    def test_verified_ro1_event_entries_and_rewards(self):
        events = self.event_choices["rogue_1"]
        choices = events["choices"]
        self.assertEqual(
            choices["choice_hp_1"]["get"], {"hp": {"current": 3}}
        )
        self.assertEqual(choices["choice_gold_1"]["get"], {"gold": 5})
        self.assertEqual(
            choices["choice_population_1"]["get"],
            {"population": {"max": 2}},
        )
        self.assertEqual(
            events["enter"]["scene_bottle4_enter"],
            [
                "choice_bottle4_1",
                "choice_bottle4_2",
                "choice_bottle4_3",
                "choice_bottle4_4",
            ],
        )
        for index in range(1, 5):
            self.assertEqual(
                events["enter"][f"scene_t{index}_enter"],
                [
                    f"choice_t{index}_1",
                    f"choice_t{index}_2",
                ],
            )

        expected_items = {
            "choice_recruit2_2": "rogue_1_recruit_ticket_all_premium",
            "choice_6_6": "rogue_1_relic_m12",
            "choice_6_7": "rogue_1_relic_m10",
            "choice_6_8": "rogue_1_relic_m11",
        }
        table_choices = self.topic_table["details"]["rogue_1"]["choices"]
        for choice_id, item_id in expected_items.items():
            with self.subTest(choice=choice_id):
                self.assertEqual(choices[choice_id]["get"], item_id)
                self.assertEqual(
                    table_choices[choice_id]["displayData"]["itemId"],
                    item_id,
                )

    def test_verified_event_requirements_and_consume_all_are_explicit(self):
        ro1 = self.event_choices["rogue_1"]["choices"]
        expected_item_requirements = {
            "choice_blood2_1": {"rogue_1_relic_m07": 1},
            "choice_bottle3_1": {"rogue_1_relic_m13": 1},
            "choice_bottle4_1": {
                "rogue_1_relic_m13": 1,
                "rogue_1_relic_m14": 1,
            },
            "choice_bottle4_2": {"rogue_1_relic_m13": 1},
            "choice_bottle4_3": {"rogue_1_relic_m14": 1},
        }
        theme_items = self.topic_table["details"]["rogue_1"]["items"]
        for choice_id, items in expected_item_requirements.items():
            self.assertEqual(ro1[choice_id]["require"], {"items": items})
            for item_id in items:
                self.assertIn(item_id, theme_items)

        ro2 = self.event_choices["rogue_2"]["choices"]
        self.assertEqual(
            ro2["choice_ro2_san1_2"]["require"],
            {"moduleMin": {"san": {"sanity": 50}}},
        )
        self.assertIn(
            "50",
            self.topic_table["details"]["rogue_2"]["choices"]
            ["choice_ro2_san1_2"]["lockedCoverDesc"],
        )
        for choice in (ro1["choice_5_1"], ro2["choice_ro2_5_1"]):
            self.assertIsNone(choice["lose"])
            self.assertEqual(choice["lose_all"], ["gold"])

    def test_verified_ro2_trade_and_resource_effects(self):
        choices = self.event_choices["rogue_2"]["choices"]
        self.assertEqual(
            choices["choice_ro2_recruit2_2"]["get"],
            "rogue_2_recruit_ticket_all_premium",
        )
        self.assertEqual(
            self.topic_table["details"]["rogue_2"]["choices"]
            ["choice_ro2_recruit2_2"]["displayData"]["itemId"],
            choices["choice_ro2_recruit2_2"]["get"],
        )
        self.assertEqual(
            choices["choice_ro2_exchange_6"]["get"], {"shield": 4}
        )
        self.assertEqual(
            choices["choice_ro2_exchange_9"]["get"], {"shield": 3}
        )
        self.assertEqual(
            choices["choice_ro2_trade4_1"]["get"], {"gold": 2}
        )
        self.assertEqual(
            choices["choice_ro2_trade4_1"]["choices"],
            ["choice_ro2_trade4_2", "choice_ro2_trade4_4"],
        )
        self.assertEqual(
            choices["choice_ro2_trade4_2"]["choices"],
            ["choice_ro2_trade4_3", "choice_ro2_trade4_4"],
        )
        expected_probability = {
            "choice_ro2_trade4_2": (3, 8, 70),
            "choice_ro2_trade4_3": (10, 25, 50),
        }
        table_choices = self.topic_table["details"]["rogue_2"]["choices"]
        for choice_id, (cost, reward, percent) in expected_probability.items():
            with self.subTest(choice=choice_id):
                choice = choices[choice_id]
                self.assertEqual(choice["lose"], {"gold": cost})
                self.assertEqual(choice["get"], {"gold": reward})
                self.assertEqual(
                    choice["probability"],
                    {"percent": percent, "appliesTo": "get"},
                )
                self.assertEqual(table_choices[choice_id]["type"], "TRADE_PROB")
                self.assertIn(
                    f"{percent}%", table_choices[choice_id]["description"]
                )

    def test_verified_ro1_population_effects_use_available_hope(self):
        choices = self.event_choices["rogue_1"]["choices"]
        self.assertEqual(
            choices["choice_side1_1"]["lose"],
            {"population": {"max": 1}},
        )
        self.assertEqual(
            choices["choice_side1_2"]["get"],
            {"population": {"max": 1}},
        )

    def test_verified_event_menu_and_probability_rules_are_explicit(self):
        ro1 = self.event_choices["rogue_1"]
        self.assertEqual(
            ro1["enter"]["scene_3_enter"],
            ["choice_3_1", "choice_3_8"],
        )
        self.assertEqual(
            ro1["sceneRules"]["scene_exchange_enter"],
            {"sample": 4, "required": ["choice_exchange_6"]},
        )
        self.assertEqual(ro1["sceneRules"]["scene_6_1"], {"sample": 3})
        for index, percent in enumerate((20, 40, 60, 80, 100), 1):
            branches = ro1["choices"][f"choice_3_{index}"]["branches"]
            self.assertEqual(sum(branch["weight"] for branch in branches), 100)
            self.assertEqual(branches[0]["weight"], percent)
            self.assertEqual(branches[0]["scene"], "scene_3_5")
            self.assertEqual(branches[0]["choices"], ["choice_3_6"])

        ro2 = self.event_choices["rogue_2"]
        self.assertEqual(
            ro2["sceneRules"]["scene_ro2_6_1"], {"sample": [2, 3]}
        )
        self.assertEqual(
            ro2["sceneRules"]["scene_ro2_8_1"], {"sample": 3}
        )
        feed_branches = ro2["choices"]["choice_ro2_8_3"]["branches"]
        self.assertEqual([branch["weight"] for branch in feed_branches], [50, 50])
        self.assertEqual(
            {branch["scene"] for branch in feed_branches},
            {"scene_ro2_8_1", "scene_ro2_8_4"},
        )

    def test_random_two_profession_event_tickets_use_exact_client_pool(self):
        choice_ids = {
            "rogue_1": ["choice_recruit1_1", "choice_recruit2_1"],
            "rogue_2": [
                "choice_ro2_recruit1_1",
                "choice_ro2_recruit2_1",
                "choice_ro2_8_7",
            ],
        }
        for theme, theme_choice_ids in choice_ids.items():
            expected_pool = [
                f"{theme}_recruit_ticket_double_{index}"
                for index in range(1, 5)
            ]
            tickets = self.topic_table["details"][theme]["recruitTickets"]
            for item_id in expected_pool:
                self.assertEqual(len(tickets[item_id]["professionList"]), 2)
            for choice_id in theme_choice_ids:
                with self.subTest(theme=theme, choice=choice_id):
                    self.assertEqual(
                        self.event_choices[theme]["choices"][choice_id]["get"],
                        expected_pool,
                    )

    def test_all_implemented_event_deltas_match_runtime_shapes(self):
        module = {
            "san": {"sanity": 100},
            "dice": {"id": "", "count": 1},
        }
        for theme in ("rogue_1", "rogue_2"):
            init = select_init_config(self.topic_table, theme, "NORMAL", 0)
            levels = self.topic_table["details"][theme]["detailConst"][
                "playerLevelTable"
            ]
            prop = build_initial_property(init, levels)
            for choice_id, choice in self.event_choices[theme]["choices"].items():
                with self.subTest(theme=theme, choice=choice_id):
                    for key, target in (
                        ("lose", prop),
                        ("get", prop),
                        ("m_lose", module),
                        ("m_get", module),
                        ("i_lose", {}),
                        ("i_get", {}),
                    ):
                        delta = choice.get(key)
                        if isinstance(delta, dict):
                            apply_numeric_delta(deepcopy(target), delta)

    def test_event_delta_roots_target_the_correct_state_partition(self):
        property_roots = {
            "exp",
            "level",
            "maxLevel",
            "hp",
            "gold",
            "shield",
            "capacity",
            "population",
            "conPerfectBattle",
        }
        module_roots = {
            "san",
            "dice",
            "totem",
            "vision",
            "chaos",
            "fragment",
            "disaster",
            "nodeUpgrade",
            "copper",
            "wrath",
            "candle",
            "sky",
        }
        for theme, theme_events in self.event_choices.items():
            if not isinstance(theme_events, dict):
                continue
            for choice_id, choice in theme_events.get("choices", {}).items():
                with self.subTest(theme=theme, choice=choice_id):
                    for key in ("lose", "get"):
                        delta = choice.get(key)
                        if isinstance(delta, dict):
                            self.assertLessEqual(set(delta), property_roots)
                    for key in ("m_lose", "m_get"):
                        delta = choice.get(key)
                        if isinstance(delta, dict):
                            self.assertLessEqual(set(delta), module_roots)


if __name__ == "__main__":
    unittest.main()

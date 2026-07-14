import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from random import Random


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_logic import (  # noqa: E402
    apply_numeric_delta,
    battle_base_reward,
    battle_resource_item_ids,
    build_initial_property,
    clamp_player_property,
    collect_difficulty_buffs,
    enforce_emergency_node_limits,
    has_numeric_cost,
    normalize_current_run,
    prepare_predefined_characters,
    prepare_recruit_candidates,
    recruit_group_ticket_ids,
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

    def test_legacy_battle_gopnik_chance_is_normalized(self):
        run = {
            "player": {
                "state": "PENDING",
                "pending": [
                    {
                        "type": "BATTLE",
                        "content": {"battle": {"goldTrapCnt": 100}},
                    }
                ],
                "status": {},
            }
        }

        self.assertTrue(normalize_current_run(run, 1))
        battle = run["player"]["pending"][0]["content"]["battle"]
        self.assertEqual(battle["goldTrapCnt"], 10)
        self.assertFalse(normalize_current_run(run, 2))

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

    def test_battle_base_reward_aliases_late_ro4_and_ro5_zones(self):
        for theme in ("rogue_4", "rogue_5"):
            for node_type in (1, 2):
                with self.subTest(theme=theme, node_type=node_type):
                    self.assertEqual(
                        battle_base_reward(theme, 7, node_type),
                        battle_base_reward(theme, 6, node_type),
                    )

    def test_battle_base_reward_rejects_unknown_cells(self):
        for theme in (None, "", "rogue_0", "rogue_6"):
            with self.subTest(theme=theme):
                with self.assertRaises(ValueError):
                    battle_base_reward(theme, 1, 1)

        for theme in tuple(f"rogue_{index}" for index in range(1, 6)):
            invalid_zones = (-1, 0, 8, True, "1")
            if theme not in {"rogue_4", "rogue_5"}:
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

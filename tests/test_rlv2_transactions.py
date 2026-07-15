import importlib.util
import json
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_repository import RepositorySettings, RunRepository  # noqa: E402


class Rlv2TransactionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = types.SimpleNamespace(headers={})
        stubs = {
            "flask": cls._module("flask", request=cls.request),
            "virtualtime": cls._module("virtualtime", time=lambda: 1),
            "constants": cls._module(
                "constants",
                SYNC_DATA_TEMPLATE_PATH="data/user/user.json",
                RLV2_USER_SETTINGS_PATH="data/user/rlv2UserSettings.json",
                CONFIG_PATH="config/config.json",
                RLV2_SETTINGS_PATH="data/user/rlv2Settings.json",
            ),
            "utils": cls._module(
                "utils",
                read_json=lambda path: {},
                decrypt_battle_data=lambda value: {},
                writeLog=lambda value: None,
                get_memory=lambda key: {},
            ),
        }
        data_package = cls._module("data")
        data_package.__path__ = []
        data_module = cls._module("data.rlv2_data", rogue_buffs={})
        data_package.rlv2_data = data_module
        stubs["data"] = data_package
        stubs["data.rlv2_data"] = data_module

        previous = {name: sys.modules.get(name) for name in stubs}
        sys.modules.update(stubs)
        try:
            spec = importlib.util.spec_from_file_location(
                "_rlv2_transaction_test_module", ROOT / "server/rlv2.py"
            )
            cls.rlv2 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.rlv2)
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    @staticmethod
    def _module(name, **attributes):
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        return module

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        settings = RepositorySettings(
            enabled=True,
            database_path=root / "rlv2.sqlite3",
            mirror_legacy=False,
        )
        self.repository = RunRepository(
            settings,
            legacy_run_path=root / "rlv2.json",
            legacy_server_data_path=root / "serverData.json",
        )
        self.rlv2.get_run_repository = lambda: self.repository
        self.request.headers = {}
        self.request.get_json = lambda: {}
        self.rlv2.decrypt_battle_data = lambda value: {}
        self.rlv2.read_json = lambda path: {}
        self.topic_table = {
            "details": {"rogue_1": self._battle_theme_data()}
        }
        self.rlv2.get_memory = lambda key: (
            self.topic_table if key == "roguelike_topic_table" else {}
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def _battle_theme_data():
        return {
            "gameConst": {
                "expItemId": "rogue_1_exp",
                "goldItemId": "rogue_1_gold",
            },
            "items": {
                "rogue_1_exp": {"type": "EXP"},
                "rogue_1_gold": {"type": "GOLD"},
                "rogue_1_recruit_ticket_all": {"type": "RECRUIT_TICKET"},
            },
            "detailConst": {
                "playerLevelTable": {
                    "1": {
                        "exp": 0,
                        "populationUp": 0,
                        "squadCapacityUp": 0,
                        "maxHpUp": 0,
                        "battleCharLimitUp": 0,
                    },
                    "2": {
                        "exp": 10,
                        "populationUp": 2,
                        "squadCapacityUp": 1,
                        "maxHpUp": 1,
                        "battleCharLimitUp": 0,
                    },
                }
            },
        }

    @staticmethod
    def _player_property():
        return {
            "exp": 5,
            "level": 1,
            "maxLevel": 2,
            "hp": {"current": 4, "max": 4},
            "gold": 6,
            "shield": 0,
            "capacity": 6,
            "population": {"cost": 0, "max": 6},
            "conPerfectBattle": 0,
        }

    def _battle_run(self):
        return {
            "player": {
                "state": "PENDING",
                "pending": [{"type": "BATTLE"}],
                "property": self._player_property(),
                "cursor": {"zone": 1, "position": {"x": 0, "y": 0}},
                "trace": [],
                "status": {"bankPut": 0},
            },
            "game": {
                "theme": "rogue_1",
                "mode": "NORMAL",
                "eGrade": 0,
                "predefined": None,
            },
            "map": {
                "zones": {
                    "1": {
                        "id": "zone_1",
                        "nodes": {
                            "0": {
                                "index": "0",
                                "pos": {"x": 0, "y": 0},
                                "type": 1,
                                "stage": "ro1_n_1_test",
                            }
                        }
                    }
                }
            },
            "inventory": {
                "recruit": {},
                "relic": {},
                "consumable": {},
                "exploreTool": {},
                "trap": None,
            },
            "buff": {"tmpHP": 0, "squadBuff": []},
            "module": {},
            "record": {},
            "troop": {"chars": {}},
        }

    @staticmethod
    def _initial_recruit_run():
        return {
            "player": {
                "state": "INIT",
                "pending": [
                    {
                        "type": "GAME_INIT_RECRUIT_SET",
                        "content": {
                            "initRecruitSet": {
                                "option": ["recruit_group_1"]
                            }
                        },
                    },
                    {
                        "type": "GAME_INIT_RECRUIT",
                        "content": {
                            "initRecruit": {
                                "tickets": [],
                                "showChar": [],
                                "team": None,
                            }
                        },
                    },
                ],
            },
            "game": {"theme": "rogue_1"},
            "inventory": {"recruit": {}},
            "troop": {"chars": {}},
        }

    def _game_over_run(self):
        run = self._battle_run()
        run["player"]["state"] = "GAME_OVER"
        run["player"]["pending"] = []
        run["player"]["status"]["gameResult"] = {
            "success": False,
            "reason": "BATTLE_ABORTED",
            "ending": None,
        }
        run["record"] = {"brief": {"zone": 1}}
        return run

    def _battle_reward_run(self):
        run = self._battle_run()
        run["player"]["pending"] = [
            {
                "type": "BATTLE_REWARD",
                "content": {
                    "battleReward": {
                        "earn": {},
                        "rewards": [
                            {
                                "index": "4",
                                "items": [
                                    {
                                        "sub": 0,
                                        "id": "rogue_1_gold",
                                        "count": 3,
                                    },
                                    {
                                        "sub": 1,
                                        "id": "rogue_1_gold",
                                        "count": 7,
                                    },
                                ],
                                "done": False,
                            },
                            {
                                "index": "9",
                                "items": [
                                    {
                                        "sub": 0,
                                        "id": "rogue_1_gold",
                                        "count": 11,
                                    }
                                ],
                                "done": False,
                            },
                        ],
                    }
                },
            }
        ]
        return run

    def assert_battle_finish_response(self, response):
        self.assertEqual(
            set(response),
            {
                "result",
                "apFailReturn",
                "itemReturn",
                "rewards",
                "unusualRewards",
                "overrideRewards",
                "additionalRewards",
                "diamondMaterialRewards",
                "furnitureRewards",
                "playerDataDelta",
                "pushMessage",
            },
        )
        self.assertEqual(response["result"], 0)
        self.assertEqual(response["apFailReturn"], 0)
        for key in (
            "itemReturn",
            "rewards",
            "unusualRewards",
            "overrideRewards",
            "additionalRewards",
            "diamondMaterialRewards",
            "furnitureRewards",
            "pushMessage",
        ):
            self.assertEqual(response[key], [])

    @classmethod
    def _real_ro1_runtime_tables(cls):
        if not hasattr(cls, "_cached_real_topic_table"):
            with (ROOT / "data/excel/roguelike_topic_table.json").open(
                encoding="utf-8"
            ) as file:
                cls._cached_real_topic_table = json.load(file)
            with (ROOT / "data/rlv2/event_choices.json").open(
                encoding="utf-8"
            ) as file:
                cls._cached_real_event_choices = json.load(file)
        return cls._cached_real_topic_table, cls._cached_real_event_choices

    def _use_real_ro1_runtime_tables(self):
        topic_table, event_choices = self._real_ro1_runtime_tables()
        self.rlv2.get_memory = lambda key: (
            topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )

    @staticmethod
    def _queue_scene(run, scene_id, choice_id):
        run["player"]["state"] = "PENDING"
        run["player"]["pending"] = [
            {
                "type": "SCENE",
                "content": {
                    "scene": {
                        "id": scene_id,
                        "choices": {choice_id: True},
                        "choiceAdditional": {choice_id: {"rewards": []}},
                    },
                    "done": False,
                    "popReport": False,
                },
            }
        ]

    @staticmethod
    def _reward_index_for_item(run, item_id):
        rewards = run["player"]["pending"][0]["content"]["battleReward"][
            "rewards"
        ]
        reward = next(
            reward
            for reward in rewards
            if any(item.get("id") == item_id for item in reward.get("items", []))
        )
        return int(reward["index"])

    def _ro2_knight_battle_run(
        self,
        *,
        route_relic=True,
        retreat_relic=False,
    ):
        theme_data = self._battle_theme_data()
        theme_data["gameConst"] = {
            "expItemId": "rogue_2_exp",
            "goldItemId": "rogue_2_gold",
            "specialTrapId": "trap_079_allydonq",
            "trapRewardRelicId": "rogue_2_relic_grace_84",
        }
        theme_data["items"] = {
            "rogue_2_exp": {"type": "EXP"},
            "rogue_2_gold": {"type": "GOLD"},
            "rogue_2_recruit_ticket_all": {"type": "RECRUIT_TICKET"},
            "rogue_2_relic_grace_83": {"type": "RELIC"},
            "rogue_2_relic_grace_84": {"type": "RELIC"},
        }
        theme_data["relics"] = {
            "rogue_2_relic_grace_83": {"buffs": []},
            "rogue_2_relic_grace_84": {"buffs": []},
        }
        self.topic_table = {"details": {"rogue_2": theme_data}}

        run = self._battle_run()
        run["game"]["theme"] = "rogue_2"
        run["player"].update(
            {
                "cursor": {"zone": 5, "position": {"x": 0, "y": 0}},
                "toEnding": (
                    "ro2_ending_1" if retreat_relic else "ro2_ending_2"
                ),
                "chgEnding": False,
            }
        )
        run["map"]["zones"] = {
            "5": {
                "id": "zone_5",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 1,
                        "stage": "ro2_n_1",
                    },
                    "100": {
                        "index": "100",
                        "pos": {"x": 1, "y": 0},
                        "type": 4,
                        "stage": (
                            "ro2_b_4" if retreat_relic else "ro2_b_5"
                        ),
                        "visited": False,
                    },
                },
            }
        }
        run["_server"] = {
            "schemaVersion": 1,
            "events": {},
            "route": self.rlv2.build_route_plan(
                "rogue_2",
                "ro2_ending_1" if retreat_relic else "ro2_ending_2",
            ),
        }
        relic_ids = []
        if route_relic:
            relic_ids.append("rogue_2_relic_grace_83")
        if retreat_relic:
            relic_ids.append("rogue_2_relic_grace_84")
        run["inventory"]["relic"] = {
            f"r_{index}": {
                "index": f"r_{index}",
                "id": relic_id,
                "count": 1,
            }
            for index, relic_id in enumerate(relic_ids)
        }
        return run

    def test_give_up_only_changes_the_requesting_user(self):
        self.repository.save(
            "alice",
            {"player": {"gold": 6}},
            {"rlv2_seed": "alice-seed", "seed_list": ["old"]},
        )
        self.repository.save(
            "bob",
            {"player": {"gold": 18}},
            {"rlv2_seed": "bob-seed", "seed_list": []},
        )
        self.request.headers = {"Uid": "alice"}

        response = self.rlv2.rlv2GiveUpGame()

        self.assertEqual(response["result"], "ok")
        alice = self.repository.load("alice")
        bob = self.repository.load("bob")
        self.assertIsNone(alice.run["player"])
        self.assertEqual(alice.seed_list, ["alice-seed", "old"])
        self.assertIsNone(alice.rlv2_seed)
        self.assertEqual(bob.run["player"]["gold"], 18)
        self.assertEqual(bob.rlv2_seed, "bob-seed")

    def test_error_response_rolls_back_run_and_seed(self):
        initial = self.repository.save(
            "alice",
            {"value": 1},
            {"rlv2_seed": "before", "seed_list": []},
        )
        self.request.headers = {"Uid": "alice"}

        @self.rlv2._serialized_run
        def rejected_action():
            run = self.rlv2._load_run()
            server_data = self.rlv2._load_server_data()
            run["value"] = 2
            server_data["rlv2_seed"] = "after"
            self.rlv2._persist_run(run, server_data)
            return {"error": "rejected"}, 409

        self.assertEqual(rejected_action()[1], 409)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision)
        self.assertEqual(snapshot.run, {"value": 1})
        self.assertEqual(snapshot.rlv2_seed, "before")

    def test_success_and_nested_action_commit_once(self):
        initial = self.repository.save("alice", {"count": 0})
        self.request.headers = {"Uid": "alice"}

        @self.rlv2._serialized_run
        def inner_action():
            self.rlv2._load_run()["count"] += 1
            return {"inner": True}

        @self.rlv2._serialized_run
        def outer_action():
            inner_action()
            self.rlv2._load_run()["count"] += 1
            return {"ok": True}

        self.assertEqual(outer_action(), {"ok": True})
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.run["count"], 2)
        self.assertEqual(snapshot.revision, initial.revision + 1)

    def test_create_game_does_not_inject_configured_initial_operator(self):
        self.topic_table = {
            "details": {
                "rogue_1": {
                    "init": [
                        {
                            "modeId": "NORMAL",
                            "modeGrade": 0,
                            "predefinedId": None,
                            "initialBandRelic": [],
                            "initialRecruitGroup": ["recruit_group_1"],
                            "initialHp": 4,
                            "initialMaxHp": 4,
                            "initialGold": 6,
                            "initialShield": 0,
                            "initialSquadCapacity": 6,
                            "initialPopulation": 6,
                            "initialKey": 0,
                        }
                    ],
                    "endings": {
                        "ending": {"id": "ending", "priority": 0}
                    },
                    "detailConst": {
                        "playerLevelTable": {
                            "1": {
                                "exp": 0,
                                "populationUp": 0,
                                "squadCapacityUp": 0,
                                "maxHpUp": 0,
                                "battleCharLimitUp": 0,
                            }
                        }
                    },
                    "difficulties": [],
                    "gameConst": {},
                    "monthSquad": {},
                }
            }
        }
        self.rlv2.read_json = lambda path: {
            "rlv2Config": {"allChars": True}
        }
        original_get_chars = self.rlv2._rlv2.getChars
        self.addCleanup(
            setattr, self.rlv2._rlv2, "getChars", original_get_chars
        )
        self.rlv2._rlv2.getChars = lambda **kwargs: [
            {
                "charId": "char_4080_lin",
                "currentTmpl": None,
                "evolvePhase": 2,
                "instId": "1",
            }
        ]
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {
            "theme": "rogue_1",
            "mode": "NORMAL",
            "modeGrade": 0,
        }

        response = self.rlv2.rlv2CreateGame()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.run["troop"]["chars"], {})

    def test_initial_recruit_set_creates_three_tickets_with_all_chars(self):
        ticket_item_ids = [
            "rogue_1_recruit_ticket_pioneer",
            "rogue_1_recruit_ticket_sniper",
            "rogue_1_recruit_ticket_special",
        ]
        self.topic_table = {
            "details": {
                "rogue_1": {
                    "recruitTickets": {
                        ticket_item_id: {} for ticket_item_id in ticket_item_ids
                    }
                }
            }
        }
        self.rlv2.read_json = lambda path: {
            "rlv2Config": {"allChars": True}
        }
        initial = self.repository.save(
            "alice",
            self._initial_recruit_run(),
            {"rlv2_seed": "seed", "seed_list": []},
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"select": "recruit_group_1"}

        response = self.rlv2.rlv2ChooseInitialRecruitSet()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        pending = snapshot.run["player"]["pending"][0]
        self.assertEqual(pending["type"], "GAME_INIT_RECRUIT")
        ticket_ids = pending["content"]["initRecruit"]["tickets"]
        self.assertEqual(len(ticket_ids), 3)
        self.assertEqual(set(ticket_ids), set(snapshot.run["inventory"]["recruit"]))
        self.assertEqual(
            {
                ticket["id"]
                for ticket in snapshot.run["inventory"]["recruit"].values()
            },
            set(ticket_item_ids),
        )
        self.assertTrue(
            all(
                ticket["state"] == 0
                for ticket in snapshot.run["inventory"]["recruit"].values()
            )
        )

    def test_map_battle_start_rolls_a_zero_or_one_mimic_group_count(self):
        run = self._battle_run()
        run["player"]["state"] = "WAIT_MOVE"
        run["player"]["pending"] = []
        run["player"]["cursor"]["position"] = None
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        original_get_buffs = self.rlv2._rlv2.getBuffs
        self.addCleanup(
            setattr, self.rlv2._rlv2, "getBuffs", original_get_buffs
        )
        self.rlv2._rlv2.getBuffs = lambda run, stage_id: []
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {
            "stageId": "ro1_n_1_test",
            "to": {"x": 0, "y": 0},
        }

        response = self.rlv2.rlv2MoveAndBattleStart()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        battle = snapshot.run["player"]["pending"][0]["content"]["battle"]
        self.assertIn(battle["chestCnt"], {0, 1})
        self.assertEqual(battle["goldTrapCnt"], 100)

    def test_generic_event_battle_does_not_force_a_mimic_group(self):
        run = self._battle_run()
        run["player"]["pending"] = [
            {
                "type": "SCENE",
                "content": {
                    "scene": {"choices": {"choice_fight": True}}
                },
            }
        ]
        self.topic_table["details"]["rogue_1"].update(
            {
                "choices": {
                    "choice_fight": {"nextSceneId": None}
                },
                "stages": {"ro1_event_battle": {}},
            }
        )
        event_choices = {
            "rogue_1": {
                "choices": {
                    "choice_fight": {"choices": "ro1_event_battle"}
                }
            }
        }
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )
        original_can_pay = self.rlv2._rlv2.canPayChoice
        original_get_buffs = self.rlv2._rlv2.getBuffs
        self.addCleanup(
            setattr, self.rlv2._rlv2, "canPayChoice", original_can_pay
        )
        self.addCleanup(
            setattr, self.rlv2._rlv2, "getBuffs", original_get_buffs
        )
        self.rlv2._rlv2.canPayChoice = lambda run, choice: True
        self.rlv2._rlv2.getBuffs = lambda run, stage_id: []
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"choice": "choice_fight"}

        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        battle = snapshot.run["player"]["pending"][0]["content"]["battle"]
        self.assertEqual(battle["chestCnt"], 0)
        self.assertEqual(battle["goldTrapCnt"], 100)

    def test_event_requirements_check_items_and_module_without_consuming(self):
        run = self._battle_run()
        run["inventory"]["relic"]["r_0"] = {
            "id": "required_relic",
            "count": 1,
        }
        run["module"]["san"] = {"sanity": 49}
        choice = {
            "require": {
                "items": {"required_relic": 1},
                "moduleMin": {"san": {"sanity": 50}},
            }
        }

        self.assertFalse(self.rlv2._rlv2.canPayChoice(run, choice))
        run["module"]["san"]["sanity"] = 50
        self.assertTrue(self.rlv2._rlv2.canPayChoice(run, choice))
        self.assertIn("r_0", run["inventory"]["relic"])

    def test_event_consume_all_clears_gold(self):
        run = self._battle_run()
        run["player"]["pending"] = [
            {
                "type": "SCENE",
                "content": {"scene": {"choices": {"choice_all": True}}},
            }
        ]
        self.topic_table["details"]["rogue_1"].update(
            {"choices": {"choice_all": {"nextSceneId": None}}}
        )
        event_choices = {
            "rogue_1": {
                "choices": {
                    "choice_all": {
                        "choices": [],
                        "lose": None,
                        "lose_all": ["gold"],
                        "get": None,
                    }
                }
            }
        }
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"choice": "choice_all"}

        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        self.assertEqual(
            self.repository.load("alice").run["player"]["property"]["gold"],
            0,
        )

    def test_event_probability_always_pays_cost_and_only_rolls_reward(self):
        class FixedRandom:
            roll = 0

            def __init__(self, seed):
                self.seed = seed

            def randrange(self, stop):
                return self.roll

        original_random = self.rlv2.random.Random
        self.addCleanup(setattr, self.rlv2.random, "Random", original_random)
        self.rlv2.random.Random = FixedRandom
        event_choices = {
            "rogue_1": {
                "choices": {
                    "choice_prob": {
                        "choices": [],
                        "lose": {"gold": 3},
                        "get": {"gold": 8},
                        "probability": {"percent": 70, "appliesTo": "get"},
                    }
                }
            }
        }
        self.topic_table["details"]["rogue_1"].update(
            {"choices": {"choice_prob": {"nextSceneId": None}}}
        )
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )

        for uid, roll, expected_gold in (
            ("success", 69, 11),
            ("failure", 70, 3),
        ):
            with self.subTest(uid=uid):
                run = self._battle_run()
                run["player"]["pending"] = [
                    {
                        "type": "SCENE",
                        "content": {
                            "scene": {"choices": {"choice_prob": True}}
                        },
                    }
                ]
                FixedRandom.roll = roll
                self.repository.save(
                    uid, run, {"rlv2_seed": "seed", "seed_list": []}
                )
                self.request.headers = {"Uid": uid}
                self.request.get_json = lambda: {"choice": "choice_prob"}

                response = self.rlv2.rlv2SelectChoice()

                self.assertIn("playerDataDelta", response)
                gold = self.repository.load(uid).run["player"]["property"]["gold"]
                self.assertEqual(gold, expected_gold)

    def test_event_probability_branch_exposes_only_the_selected_result(self):
        class FixedRandom:
            roll = 0

            def __init__(self, seed):
                self.seed = seed

            def randrange(self, stop):
                return self.roll

        original_random = self.rlv2.random.Random
        self.addCleanup(setattr, self.rlv2.random, "Random", original_random)
        self.rlv2.random.Random = FixedRandom
        event_choices = {
            "rogue_1": {
                "choices": {
                    "choice_branch": {
                        "choices": [],
                        "lose": {"gold": 3},
                        "get": None,
                        "branches": [
                            {
                                "weight": 20,
                                "scene": "success_scene",
                                "choices": ["collect"],
                            },
                            {
                                "weight": 80,
                                "scene": "retry_scene",
                                "choices": ["again", "choice_leave"],
                            },
                        ],
                    },
                    "collect": {"choices": [], "lose": None, "get": None},
                    "again": {"choices": [], "lose": None, "get": None},
                }
            }
        }
        self.topic_table["details"]["rogue_1"].update(
            {"choices": {"choice_branch": {"nextSceneId": None}}}
        )
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )

        for uid, roll, expected_scene, expected_choices in (
            ("success", 19, "success_scene", {"collect"}),
            ("retry", 20, "retry_scene", {"again", "choice_leave"}),
        ):
            with self.subTest(uid=uid):
                run = self._battle_run()
                run["player"]["pending"] = [
                    {
                        "type": "SCENE",
                        "content": {
                            "scene": {"choices": {"choice_branch": True}}
                        },
                    }
                ]
                FixedRandom.roll = roll
                self.repository.save(
                    uid, run, {"rlv2_seed": "seed", "seed_list": []}
                )
                self.request.headers = {"Uid": uid}
                self.request.get_json = lambda: {"choice": "choice_branch"}

                response = self.rlv2.rlv2SelectChoice()

                self.assertIn("playerDataDelta", response)
                pending = self.repository.load(uid).run["player"]["pending"][0]
                scene = pending["content"]["scene"]
                self.assertEqual(scene["id"], expected_scene)
                self.assertEqual(set(scene["choices"]), expected_choices)

    def test_empty_event_data_completes_without_a_fake_leave_scene(self):
        run = self._battle_run()
        run["player"]["state"] = "WAIT_MOVE"
        run["player"]["pending"] = []
        run["player"]["cursor"]["position"] = None
        run["map"]["zones"]["1"]["nodes"]["0"].update(
            {"type": 32, "stage": None}
        )
        event_choices = {
            "rogue_1": {
                "enter": {"scene_empty_enter": []},
                "choices": {},
            }
        }
        self.topic_table["details"]["rogue_1"]["choices"] = {}
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"to": {"x": 0, "y": 0}}

        response = self.rlv2.rlv2MoveTo()

        self.assertIn("playerDataDelta", response)
        player = self.repository.load("alice").run["player"]
        self.assertEqual(player["state"], "WAIT_MOVE")
        self.assertEqual(player["pending"], [])

    def test_event_entry_requirements_filter_the_scene_pool(self):
        run = self._battle_run()
        run["player"]["state"] = "WAIT_MOVE"
        run["player"]["pending"] = []
        run["player"]["cursor"]["position"] = None
        run["map"]["zones"]["1"]["nodes"]["0"].update(
            {"type": 32, "stage": None}
        )
        choice_rule = {"choices": [], "lose": None, "get": None}
        event_choices = {
            "rogue_1": {
                "enter": {
                    "scene_locked_enter": ["choice_locked"],
                    "scene_safe_enter": ["choice_safe"],
                },
                "sceneRules": {
                    "scene_locked_enter": {
                        "require": {"items": {"missing_relic": 1}}
                    }
                },
                "choices": {
                    "choice_locked": choice_rule,
                    "choice_safe": choice_rule,
                },
            }
        }
        self.topic_table["details"]["rogue_1"]["choices"] = {
            "choice_locked": {"nextSceneId": None},
            "choice_safe": {"nextSceneId": None},
        }
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )
        original_candidates = self.rlv2.event_scene_candidates
        self.addCleanup(
            setattr,
            self.rlv2,
            "event_scene_candidates",
            original_candidates,
        )
        self.rlv2.event_scene_candidates = (
            lambda theme, depth, node_type, available: list(available)
        )
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"to": {"x": 0, "y": 0}}

        response = self.rlv2.rlv2MoveTo()

        self.assertIn("playerDataDelta", response)
        pending = self.repository.load("alice").run["player"]["pending"][0]
        self.assertEqual(
            pending["content"]["scene"]["id"], "scene_safe_enter"
        )

    def test_nonrepeatable_event_history_survives_across_zones(self):
        run = self._battle_run()
        run["player"]["state"] = "WAIT_MOVE"
        run["player"]["pending"] = []
        run["player"]["cursor"] = {"zone": 2, "position": None}
        current_node = deepcopy(run["map"]["zones"]["1"]["nodes"]["0"])
        current_node.update({"type": 32, "stage": None})
        run["map"]["zones"] = {
            "1": {
                "id": "zone_1",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "next": [],
                        "type": 32,
                        "visited": True,
                        "scene": "scene_once_enter",
                    }
                },
                "variation": [],
            },
            "2": {
                "id": "zone_2",
                "nodes": {"0": current_node},
                "variation": [],
            },
        }
        choice_rule = {"choices": [], "lose": None, "get": None}
        event_choices = {
            "rogue_1": {
                "enter": {
                    "scene_once_enter": ["choice_once"],
                    "scene_hp_enter": ["choice_repeat"],
                },
                "choices": {
                    "choice_once": choice_rule,
                    "choice_repeat": choice_rule,
                },
            }
        }
        self.topic_table["details"]["rogue_1"]["choices"] = {
            "choice_once": {"nextSceneId": None},
            "choice_repeat": {"nextSceneId": None},
        }
        self.rlv2.get_memory = lambda key: (
            self.topic_table
            if key == "roguelike_topic_table"
            else event_choices
            if key == "event_choices"
            else {}
        )
        original_candidates = self.rlv2.event_scene_candidates
        self.addCleanup(
            setattr,
            self.rlv2,
            "event_scene_candidates",
            original_candidates,
        )
        self.rlv2.event_scene_candidates = (
            lambda theme, depth, node_type, available: list(available)
        )
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"to": {"x": 0, "y": 0}}

        response = self.rlv2.rlv2MoveTo()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice").run
        scene = snapshot["player"]["pending"][0]["content"]["scene"]
        self.assertEqual(scene["id"], "scene_hp_enter")
        self.assertEqual(
            snapshot["map"]["zones"]["2"]["nodes"]["0"]["scene"],
            "scene_hp_enter",
        )

    def test_ro1_m16_changes_ending_and_read_ending_change_acknowledges_it(self):
        self._use_real_ro1_runtime_tables()
        run = self._battle_run()
        run["map"]["zones"]["1"]["nodes"]["0"].update(
            {"type": 32, "stage": None}
        )
        self._queue_scene(run, "scene_side1_enter", "choice_side1_1")
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}

        self.request.get_json = lambda: {"choice": "choice_side1_1"}
        response = self.rlv2.rlv2SelectChoice()
        self.assertIn("playerDataDelta", response)
        scene = self.repository.load("alice").run["player"]["pending"][0][
            "content"
        ]["scene"]
        self.assertEqual(scene["id"], "scene_side1_1")
        self.assertTrue(scene["choices"]["choice_side1_3"])

        self.request.get_json = lambda: {"choice": "choice_side1_3"}
        response = self.rlv2.rlv2SelectChoice()

        public_run = response["playerDataDelta"]["modified"]["rlv2"]["current"]
        self.assertNotIn("_server", public_run)
        snapshot = self.repository.load("alice")
        self.assertTrue(
            self.rlv2._rlv2.hasItem(snapshot.run, "rogue_1_relic_m16")
        )
        self.assertEqual(snapshot.run["player"]["toEnding"], "ro_ending_2")
        self.assertIs(snapshot.run["player"]["chgEnding"], True)
        self.assertEqual(
            snapshot.run["_server"]["route"]["source"],
            "item:rogue_1_relic_m16",
        )

        response = self.rlv2.rlv2ReadEndingChange()

        acknowledged = response["playerDataDelta"]["modified"]["rlv2"][
            "current"
        ]
        self.assertIs(acknowledged["player"]["chgEnding"], False)
        self.assertNotIn("_server", acknowledged)
        persisted = self.repository.load("alice")
        self.assertEqual(persisted.run["player"]["toEnding"], "ro_ending_2")
        self.assertIs(persisted.run["player"]["chgEnding"], False)
        self.assertEqual(
            persisted.run["_server"]["route"]["source"],
            "item:rogue_1_relic_m16",
        )

    def test_ro1_m19_boss_reward_and_m21_complete_the_hidden_chain(self):
        self._use_real_ro1_runtime_tables()
        run = self._battle_run()
        run["map"]["zones"]["1"]["nodes"]["0"].update(
            {"type": 32, "stage": None}
        )
        self._queue_scene(run, "scene_hidden1_enter", "choice_hidden1_1")
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"choice": "choice_hidden1_1"}

        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertTrue(
            self.rlv2._rlv2.hasItem(snapshot.run, "rogue_1_relic_m19")
        )
        self.assertEqual(snapshot.run["player"]["toEnding"], "ro_ending_1")

        run = snapshot.run
        run["player"]["state"] = "PENDING"
        run["player"]["pending"] = [{"type": "BATTLE", "content": {}}]
        run["player"]["cursor"] = {
            "zone": 3,
            "position": {"x": 0, "y": 0},
        }
        run["map"]["zones"] = {
            "3": {
                "id": "zone_3",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 4,
                        "stage": "ro1_b_1",
                        "next": [],
                    }
                },
            }
        }
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        battle_finished = self.repository.load("alice").run
        m20_index = self._reward_index_for_item(
            battle_finished, "rogue_1_relic_m20"
        )
        self.assertFalse(
            self.rlv2._rlv2.hasItem(battle_finished, "rogue_1_relic_m20")
        )

        self.request.get_json = lambda: {"index": m20_index, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()

        self.assertIn("playerDataDelta", response)
        claimed = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(claimed, "rogue_1_relic_m20")
        )
        self.assertEqual(claimed["player"]["toEnding"], "ro_ending_1")

        self._queue_scene(claimed, "scene_hidden2_enter", "choice_hidden2_1")
        self.repository.save(
            "alice", claimed, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.get_json = lambda: {"choice": "choice_hidden2_1"}
        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        completed = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(completed, "rogue_1_relic_m21")
        )
        self.assertEqual(completed["player"]["toEnding"], "ro_ending_3")
        self.assertIs(completed["player"]["chgEnding"], True)
        self.assertEqual(
            completed["_server"]["route"]["orderedZones"],
            [1, 2, 3, 4, 5, 6],
        )

    def test_ro1_writer_battles_offer_n01_then_n02_as_optional_rewards(self):
        self._use_real_ro1_runtime_tables()
        original_get_buffs = self.rlv2._rlv2.getBuffs
        self.addCleanup(
            setattr, self.rlv2._rlv2, "getBuffs", original_get_buffs
        )
        self.rlv2._rlv2.getBuffs = lambda run, stage_id: []
        run = self._battle_run()
        run["map"]["zones"]["1"]["nodes"]["0"].update(
            {"type": 32, "stage": None}
        )
        self._queue_scene(run, "scene_writer1_enter", "choice_writer1_1")
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}

        self.request.get_json = lambda: {"choice": "choice_writer1_1"}
        response = self.rlv2.rlv2SelectChoice()
        self.assertIn("playerDataDelta", response)
        self.request.get_json = lambda: {"choice": "choice_writer1_3"}
        response = self.rlv2.rlv2SelectChoice()

        self.assertNotIn(
            "_server",
            response["playerDataDelta"]["modified"]["rlv2"]["current"],
        )
        selected = self.repository.load("alice").run
        self.assertEqual(
            selected["_server"]["events"]["pendingBattleReward"]["itemId"],
            "rogue_1_relic_n01",
        )
        self.assertEqual(
            selected["map"]["zones"]["1"]["nodes"]["0"]["stage"],
            "ro1_ev_4",
        )

        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }
        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        writer1_finished = self.repository.load("alice").run
        self.assertNotIn(
            "pendingBattleReward", writer1_finished["_server"]["events"]
        )
        self.assertFalse(
            self.rlv2._rlv2.hasItem(writer1_finished, "rogue_1_relic_n01")
        )
        n01_index = self._reward_index_for_item(
            writer1_finished, "rogue_1_relic_n01"
        )

        self.request.get_json = lambda: {"index": n01_index, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()

        self.assertIn("playerDataDelta", response)
        writer2_run = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(writer2_run, "rogue_1_relic_n01")
        )
        writer2_run["player"]["state"] = "WAIT_MOVE"
        writer2_run["player"]["pending"] = []
        writer2_run["player"]["cursor"] = {"zone": 1, "position": None}
        writer2_run["map"]["zones"] = {
            "1": {
                "id": "zone_1",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 32,
                        "stage": None,
                        "scene": "scene_writer2_enter",
                        "next": [],
                    }
                },
                "variation": [],
            }
        }
        self.repository.save(
            "alice", writer2_run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.get_json = lambda: {"to": {"x": 0, "y": 0}}

        response = self.rlv2.rlv2MoveTo()

        self.assertIn("playerDataDelta", response)
        writer2_entry = self.repository.load("alice").run["player"]["pending"][0][
            "content"
        ]["scene"]
        self.assertEqual(writer2_entry["id"], "scene_writer2_enter")
        self.assertTrue(writer2_entry["choices"]["choice_writer2_1"])

        self.request.get_json = lambda: {"choice": "choice_writer2_1"}
        response = self.rlv2.rlv2SelectChoice()
        self.assertIn("playerDataDelta", response)
        self.request.get_json = lambda: {"choice": "choice_writer2_3"}
        response = self.rlv2.rlv2SelectChoice()
        self.assertIn("playerDataDelta", response)
        selected = self.repository.load("alice").run
        self.assertEqual(
            selected["_server"]["events"]["pendingBattleReward"]["itemId"],
            "rogue_1_relic_n02",
        )
        self.assertEqual(
            selected["map"]["zones"]["1"]["nodes"]["0"]["stage"],
            "ro1_ev_5",
        )

        self.request.get_json = lambda: {"data": "encrypted"}
        response = self.rlv2.rlv2BattleFinish()
        self.assert_battle_finish_response(response)
        writer2_finished = self.repository.load("alice").run
        self.assertFalse(
            self.rlv2._rlv2.hasItem(writer2_finished, "rogue_1_relic_n02")
        )
        n02_index = self._reward_index_for_item(
            writer2_finished, "rogue_1_relic_n02"
        )

        self.request.get_json = lambda: {"index": n02_index, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()

        self.assertIn("playerDataDelta", response)
        completed = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(completed, "rogue_1_relic_n02")
        )
        self.assertEqual(completed["player"]["property"]["population"]["max"], 9)
        self.assertEqual(completed["player"]["toEnding"], "ro_ending_4")
        self.assertIs(completed["player"]["chgEnding"], True)

    def test_ro4_crowning_fragments_alchemy_and_tail_page_complete_ending_two(self):
        self._use_real_ro1_runtime_tables()
        run = self._battle_run()
        run["game"]["theme"] = "rogue_4"
        run["player"].update(
            {
                "toEnding": "ro4_ending_1",
                "chgEnding": False,
                "cursor": {"zone": 2, "position": {"x": 0, "y": 0}},
            }
        )
        run["module"] = {
            "fragment": {
                "totalWeight": 0,
                "limitWeight": 3,
                "overWeight": 4,
                "fragments": {},
                "troopWeights": {},
                "troopCarry": [],
                "sellCount": 0,
                "currInspiration": None,
            }
        }
        run["_server"] = {
            "schemaVersion": 1,
            "events": {},
            "route": self.rlv2.build_route_plan("rogue_4", "ro4_ending_1"),
        }
        run["map"]["zones"] = {
            "2": {
                "id": "zone_2",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 65536,
                        "scene": "scene_ro4_fin1_enter",
                        "next": [],
                    }
                },
            }
        }
        self._queue_scene(run, "scene_ro4_fin1_enter", "choice_ro4_fin1_1")
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"choice": "choice_ro4_fin1_1"}

        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        crowned = self.repository.load("alice").run
        fragments = crowned["module"]["fragment"]["fragments"]
        self.assertEqual(
            {entry["id"] for entry in fragments.values()},
            {"rogue_4_fragment_D_01", "rogue_4_fragment_D_02"},
        )
        self.assertEqual(crowned["module"]["fragment"]["totalWeight"], 10)
        self.assertNotIn("rogue_4_fragment_D_01", crowned["inventory"]["consumable"])

        crowned["player"]["state"] = "WAIT_MOVE"
        crowned["player"]["pending"] = []
        crowned["player"]["cursor"] = {"zone": 2, "position": None}
        crowned["map"]["zones"] = {
            "2": {
                "id": "zone_2",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 131072,
                        "next": [],
                    }
                },
            }
        }
        self.repository.save(
            "alice", crowned, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.get_json = lambda: {"to": {"x": 0, "y": 0}}

        response = self.rlv2.rlv2MoveTo()

        self.assertIn("playerDataDelta", response)
        alchemy_run = self.repository.load("alice").run
        self.assertEqual(alchemy_run["player"]["pending"][0]["type"], "ALCHEMY")
        fragment_indexes = list(
            alchemy_run["module"]["fragment"]["fragments"]
        )
        self.request.get_json = lambda: {
            "fragmentIndex": fragment_indexes,
            "leave": False,
        }

        response = self.rlv2.rlv2Alchemy()

        self.assertIn("playerDataDelta", response)
        alchemized = self.repository.load("alice").run
        self.assertEqual(
            alchemized["player"]["pending"][0]["type"], "ALCHEMY_REWARD"
        )
        self.assertEqual(alchemized["module"]["fragment"]["fragments"], {})
        self.assertEqual(
            alchemized["_server"]["events"]["pendingAlchemyReward"],
            {"itemId": "rogue_4_relic_final_1", "count": 1},
        )
        self.assertNotIn(
            "_server",
            response["playerDataDelta"]["modified"]["rlv2"]["current"],
        )

        self.request.get_json = lambda: {"index": 0}
        response = self.rlv2.rlv2AlchemyReward()

        self.assertIn("playerDataDelta", response)
        oath_run = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(oath_run, "rogue_4_relic_final_1")
        )
        self.assertNotIn("pendingAlchemyReward", oath_run["_server"]["events"])

        oath_run["player"]["cursor"] = {
            "zone": 5,
            "position": {"x": 0, "y": 0},
        }
        oath_run["map"]["zones"] = {
            "5": {
                "id": "zone_5",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 65536,
                    },
                    "100": {
                        "index": "100",
                        "pos": {"x": 1, "y": 0},
                        "type": 4,
                        "stage": "ro4_b_4",
                        "visited": False,
                    },
                },
            }
        }
        self._queue_scene(oath_run, "scene_ro4_end1_enter", "choice_ro4_end1_1")
        self.repository.save(
            "alice", oath_run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.get_json = lambda: {"choice": "choice_ro4_end1_1"}

        response = self.rlv2.rlv2SelectChoice()

        self.assertIn("playerDataDelta", response)
        completed = self.repository.load("alice").run
        self.assertEqual(completed["player"]["toEnding"], "ro4_ending_2")
        self.assertTrue(completed["player"]["chgEnding"])
        self.assertEqual(
            completed["map"]["zones"]["5"]["nodes"]["100"]["stage"],
            "ro4_b_5",
        )

    def test_generated_maps_apply_reviewed_fixed_columns(self):
        with (ROOT / "data/excel/roguelike_topic_table.json").open(
            encoding="utf-8"
        ) as file:
            topic_table = json.load(file)
        self.rlv2.get_memory = lambda key: (
            topic_table if key == "roguelike_topic_table" else {}
        )

        def columns(theme, zone, ending, seed="fixed-column"):
            generated, _ = self.rlv2._rlv2.getMap_new(
                theme, seed, zone, ending
            )
            result = {}
            for node in generated[str(zone)]["nodes"].values():
                result.setdefault(node["pos"]["x"], []).append(node)
            return result

        ro1_first = columns("rogue_1", 1, "ro_ending_1")
        self.assertIn(len(ro1_first[1]), {2, 3})
        self.assertLessEqual(
            {node["type"] for node in ro1_first[1]}, {32, 128}
        )

        ro4_third = columns("rogue_4", 3, "ro4_ending_1")
        self.assertEqual(
            {node["type"] for node in ro4_third[4]}, {131072}
        )

        ro4_fourth = columns("rogue_4", 4, "ro4_ending_1")
        battle_columns = {
            x
            for x in range(4)
            if any(node["type"] in {1, 2} for node in ro4_fourth[x])
        }
        self.assertEqual(battle_columns, {0, 1})

        for theme, zone, ending, expected_scene in (
            ("rogue_3", 5, "ro3_ending_1", "scene_ro3_story1_enter"),
            ("rogue_4", 5, "ro4_ending_1", "scene_ro4_end1_enter"),
            ("rogue_5", 5, "ro5_ending_1", "scene_ro5_end1_enter"),
            ("rogue_5", 6, "ro5_ending_3", "scene_ro5_end2_enter"),
        ):
            for seed_index in range(32):
                generated = columns(
                    theme,
                    zone,
                    ending,
                    f"fixed-story-{seed_index}",
                )
                story_nodes = [
                    node
                    for nodes in generated.values()
                    for node in nodes
                    if node["type"] == 65536
                ]
                with self.subTest(
                    theme=theme, zone=zone, seed_index=seed_index
                ):
                    self.assertTrue(story_nodes)
                    self.assertTrue(
                        all(
                            node.get("scene") == expected_scene
                            for node in story_nodes
                        )
                    )

        for zone, ending, battle_column in (
            (6, "ro5_ending_3", 2),
            (7, "ro5_ending_4", 1),
        ):
            with self.subTest(zone=zone):
                stage_depths = set()
                for seed_index in range(64):
                    generated = columns(
                        "rogue_5",
                        zone,
                        ending,
                        f"stage-depth-{seed_index}",
                    )
                    stage_depths.update(
                        int(node["stage"].split("_")[2])
                        for node in generated[battle_column]
                    )
                self.assertEqual(stage_depths, {6, 7})

    def test_generated_bosses_do_not_randomize_conditional_variants(self):
        with (ROOT / "data/excel/roguelike_topic_table.json").open(
            encoding="utf-8"
        ) as file:
            topic_table = json.load(file)
        self.rlv2.get_memory = lambda key: (
            topic_table if key == "roguelike_topic_table" else {}
        )

        for theme, ending, depth, expected_stage in (
            ("rogue_3", "ro3_ending_1", 5, "ro3_b_4"),
            ("rogue_4", "ro4_ending_1", 5, "ro4_b_4"),
            ("rogue_5", "ro5_ending_1", 5, "ro5_b_4"),
        ):
            observed = set()
            for seed_index in range(32):
                generated, _ = self.rlv2._rlv2.getMap_new(
                    theme, f"boss-variant-{seed_index}", depth, ending
                )
                observed.update(
                    node["stage"]
                    for node in generated[str(depth)]["nodes"].values()
                    if node["type"] == 4
                )
            with self.subTest(theme=theme, ending=ending):
                self.assertEqual(observed, {expected_stage})

        for theme, ending in (
            ("rogue_2", "ro2_ending_1"),
            ("rogue_3", "ro3_ending_1"),
            ("rogue_4", "ro4_ending_1"),
            ("rogue_5", "ro5_ending_1"),
        ):
            observed = set()
            for seed_index in range(32):
                generated, _ = self.rlv2._rlv2.getMap_new(
                    theme, f"mid-boss-{seed_index}", 3, ending
                )
                observed.update(
                    node["stage"]
                    for node in generated["3"]["nodes"].values()
                    if node["type"] == 4
                )
            with self.subTest(theme=theme):
                self.assertTrue(observed)
                self.assertTrue(
                    all(stage_id.count("_") == 2 for stage_id in observed)
                )

    def test_all_verified_routes_generate_reachable_canonical_maps(self):
        with (ROOT / "data/excel/roguelike_topic_table.json").open(
            encoding="utf-8"
        ) as file:
            topic_table = json.load(file)
        self.rlv2.get_memory = lambda key: (
            topic_table if key == "roguelike_topic_table" else {}
        )

        checked = 0
        for theme, theme_data in topic_table["details"].items():
            for ending in theme_data["endings"]:
                final_depth = self.rlv2.terminal_depth(theme, ending)
                if final_depth is None:
                    continue
                for depth in range(1, final_depth + 1):
                    with self.subTest(
                        theme=theme, ending=ending, depth=depth
                    ):
                        generated, seed = self.rlv2._rlv2.getMap_new(
                            theme, "map-seed", depth, ending
                        )
                        repeated, repeated_seed = self.rlv2._rlv2.getMap_new(
                            theme, "map-seed", depth, ending
                        )
                        self.assertEqual(seed, "map-seed")
                        self.assertEqual(repeated_seed, seed)
                        self.assertEqual(repeated, generated)

                        zone = generated[str(depth)]
                        layout = self.rlv2.area_layout(theme, depth)
                        columns = {}
                        for node in zone["nodes"].values():
                            columns.setdefault(node["pos"]["x"], []).append(node)
                        self.assertEqual(
                            len(columns), layout["baseNodeLength"]
                        )
                        self.assertTrue(
                            all(
                                len(nodes) <= layout["maximumBranches"]
                                for nodes in columns.values()
                            )
                        )

                        last_x = max(columns)
                        incoming = {
                            node_id: 0 for node_id in zone["nodes"]
                        }
                        for node in zone["nodes"].values():
                            x = node["pos"]["x"]
                            self.assertEqual(
                                bool(node.get("zone_end")), x == last_x
                            )
                            if node["type"] in {1, 2, 4}:
                                self.assertIn(
                                    node.get("stage"), theme_data["stages"]
                                )
                            if node["type"] == 4:
                                self.assertEqual(x, last_x)
                            for edge in node["next"]:
                                self.assertEqual(edge["x"], x + 1)
                                target_id = str(
                                    edge["x"] * 100 + edge["y"]
                                )
                                self.assertIn(target_id, zone["nodes"])
                                incoming[target_id] += 1

                        for node_id, count in incoming.items():
                            if zone["nodes"][node_id]["pos"]["x"] > 0:
                                self.assertGreater(count, 0)
                        checked += 1

        self.assertEqual(checked, 129)

    def test_finish_node_uses_the_selected_ending_terminal_depth(self):
        with (ROOT / "data/excel/roguelike_topic_table.json").open(
            encoding="utf-8"
        ) as file:
            topic_table = json.load(file)
        self.rlv2.get_memory = lambda key: (
            topic_table if key == "roguelike_topic_table" else {}
        )
        run = self._battle_run()
        run["game"]["theme"] = "rogue_2"
        run["player"]["toEnding"] = "ro2_ending_3"
        run["player"]["cursor"] = {
            "zone": 5,
            "position": {"x": 0, "y": 0},
        }
        run["map"]["zones"] = {
            "5": {
                "id": "zone_5",
                "nodes": {
                    "0": {
                        "index": "0",
                        "pos": {"x": 0, "y": 0},
                        "type": 4,
                        "stage": "ro2_b_4",
                        "next": [],
                        "zone_end": True,
                    }
                },
            }
        }
        server_data = {"rlv2_seed": "seed"}

        self.assertTrue(self.rlv2._rlv2.finishNode(run, server_data))

        self.assertEqual(run["player"]["cursor"]["zone"], 6)
        self.assertIsNone(run["player"]["cursor"]["position"])
        self.assertIn("5", run["map"]["zones"])
        self.assertEqual(run["map"]["zones"]["6"]["id"], "zone_6")
        boss_nodes = [
            node
            for node in run["map"]["zones"]["6"]["nodes"].values()
            if node["type"] == 4
        ]
        self.assertTrue(boss_nodes)
        self.assertEqual(
            {node["stage"] for node in boss_nodes}, {"ro2_b_6"}
        )

    def test_battle_finish_grants_exp_and_queues_gold_as_a_separate_reward(self):
        initial = self.repository.save(
            "alice",
            self._battle_run(),
            {"rlv2_seed": "seed", "seed_list": []},
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        prop = snapshot.run["player"]["property"]
        self.assertEqual(prop["level"], 2)
        self.assertEqual(prop["exp"], 5)
        self.assertEqual(prop["population"]["max"], 8)
        self.assertEqual(prop["capacity"], 7)
        self.assertEqual(prop["hp"], {"current": 5, "max": 5})
        self.assertEqual(prop["gold"], 6)

        battle_reward = snapshot.run["player"]["pending"][0]["content"][
            "battleReward"
        ]
        self.assertEqual(
            set(battle_reward["earn"]),
            {
                "exp",
                "populationMax",
                "squadCapacity",
                "hp",
                "shield",
                "maxHpUp",
            },
        )
        self.assertEqual(
            battle_reward["earn"],
            {
                "exp": 10,
                "populationMax": 2,
                "squadCapacity": 1,
                "hp": 0,
                "shield": 0,
                "maxHpUp": 1,
            },
        )
        self.assertEqual(len(battle_reward["rewards"]), 2)
        self.assertIsNone(battle_reward["show"])
        self.assertEqual(battle_reward["state"], 3)
        self.assertEqual(battle_reward["isPerfect"], 1)
        gold_reward, ticket_reward = battle_reward["rewards"]
        self.assertEqual(gold_reward["index"], "0")
        self.assertEqual(
            gold_reward["items"],
            [{"sub": 0, "id": "rogue_1_gold", "count": 3}],
        )
        self.assertIs(gold_reward["done"], False)
        self.assertEqual(ticket_reward["index"], "1")
        self.assertEqual(
            ticket_reward["items"],
            [
                {
                    "sub": 0,
                    "id": "rogue_1_recruit_ticket_all",
                    "count": 1,
                }
            ],
        )
        self.assertIs(ticket_reward["done"], False)

        self.request.get_json = lambda: {"index": 0, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()
        self.assertIn("playerDataDelta", response)
        claimed = self.repository.load("alice")
        self.assertEqual(claimed.revision, snapshot.revision + 1)
        self.assertEqual(claimed.run["player"]["property"]["gold"], 9)
        self.assertIs(
            claimed.run["player"]["pending"][0]["content"]["battleReward"][
                "rewards"
            ][0]["done"],
            True,
        )

        response = self.rlv2.rlv2FinishBattleReward()
        self.assertIn("playerDataDelta", response)
        finished = self.repository.load("alice")
        self.assertEqual(finished.revision, claimed.revision + 1)
        self.assertEqual(finished.run["player"]["state"], "WAIT_MOVE")
        self.assertEqual(finished.run["player"]["pending"], [])
        self.assertEqual(finished.run["player"]["property"]["gold"], 9)

    def test_battle_extra_life_cost_ends_the_run_before_rewards(self):
        relic_id = "rogue_1_relic_life_cost"
        hp_item_id = "rogue_1_hp"
        theme_data = self.topic_table["details"]["rogue_1"]
        theme_data["items"].update(
            {
                hp_item_id: {"type": "HP"},
                relic_id: {"type": "RELIC"},
            }
        )
        theme_data["relics"] = {
            relic_id: {
                "buffs": [
                    {
                        "key": "battle_extra_reward",
                        "blackboard": [
                            {"key": "id", "valueStr": hp_item_id},
                            {"key": "count", "value": -2},
                        ],
                    }
                ]
            }
        }
        run = self._battle_run()
        run["player"]["property"]["hp"] = {"current": 1, "max": 4}
        run["inventory"]["relic"]["r_0"] = {
            "index": "r_0",
            "id": relic_id,
            "count": 1,
        }
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 1}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        finished = self.repository.load("alice").run
        self.assertEqual(finished["player"]["property"]["hp"]["current"], 0)
        self.assertEqual(finished["player"]["state"], "PENDING")
        self.assertEqual(finished["player"]["pending"][0]["type"], "GAME_SETTLE")
        self.assertEqual(finished["record"]["reason"], "LIFE_POINT_ZERO")

    def test_ro4_perfect_battle_increases_fragment_weight_limit(self):
        relic_id = "rogue_4_relic_res_5"
        max_weight_id = "rogue_4_max_weight"
        theme_data = self._battle_theme_data()
        theme_data["gameConst"] = {
            "expItemId": "rogue_4_exp",
            "goldItemId": "rogue_4_gold",
        }
        theme_data["items"] = {
            "rogue_4_exp": {"type": "EXP"},
            "rogue_4_gold": {"type": "GOLD"},
            "rogue_4_recruit_ticket_all": {"type": "RECRUIT_TICKET"},
            max_weight_id: {"type": "MAX_WEIGHT"},
            relic_id: {"type": "RELIC"},
        }
        theme_data["relics"] = {
            relic_id: {
                "buffs": [
                    {
                        "key": "gain_on_perfect",
                        "blackboard": [
                            {"key": "id", "valueStr": max_weight_id},
                            {"key": "count", "value": 1},
                        ],
                    }
                ]
            }
        }
        self.topic_table = {"details": {"rogue_4": theme_data}}
        run = self._battle_run()
        run["game"]["theme"] = "rogue_4"
        run["inventory"]["relic"]["r_0"] = {
            "index": "r_0",
            "id": relic_id,
            "count": 1,
        }
        run["module"] = {
            "fragment": {
                "totalWeight": 0,
                "limitWeight": 3,
                "overWeight": 4,
                "fragments": {},
            }
        }
        self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        finished = self.repository.load("alice").run
        self.assertEqual(finished["module"]["fragment"]["limitWeight"], 4)

    def test_aborted_battle_enters_client_game_settlement_and_can_be_settled(self):
        initial = self.repository.save(
            "alice",
            self._battle_run(),
            {"rlv2_seed": "active", "seed_list": ["old"]},
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {"completeState": 1}

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        game_settle = self.repository.load("alice")
        self.assertEqual(game_settle.revision, initial.revision + 1)
        player = game_settle.run["player"]
        self.assertEqual(player["state"], "PENDING")
        self.assertEqual(player["pending"][0]["type"], "GAME_SETTLE")
        self.assertNotIn("gameResult", player["status"])
        content = player["pending"][0]["content"]
        self.assertIs(content["done"], False)
        self.assertEqual(content["result"]["brief"]["success"], 0)
        self.assertEqual(content["result"]["brief"]["mode"], "NORMAL")
        self.assertEqual(content["result"]["brief"]["theme"], "rogue_1")
        self.assertIsInstance(content["result"]["record"], dict)

        retry = self.rlv2.rlv2BattleFinish()
        self.assert_battle_finish_response(retry)
        after_retry = self.repository.load("alice")
        self.assertEqual(after_retry.run, game_settle.run)

        response = self.rlv2.rlv2FinishGame()
        self.assertIn("playerDataDelta", response)
        pending = self.repository.load("alice")
        self.assertEqual(pending.run["player"]["state"], "PENDING")
        self.assertEqual(
            pending.run["player"]["pending"][0]["type"], "GAME_SETTLE"
        )

        response = self.rlv2.rlv2GameSettle()
        self.assertEqual(
            set(response["game"]["score"]),
            {
                "detail",
                "scoreFactor",
                "score",
                "buff",
                "bp",
                "gp",
                "accumulation",
            },
        )
        self.assertEqual(response["game"]["score"]["score"], 0.0)
        self.assertEqual(response["outer"]["items"], [])
        self.assertIn("playerDataDelta", response)
        self.assertEqual(response["pushMessage"], [])
        settled = self.repository.load("alice")
        self.assertIsNone(settled.run["player"])
        self.assertIsNone(settled.rlv2_seed)
        self.assertEqual(settled.seed_list, ["active", "old"])

    def test_successful_battle_finish_retry_returns_complete_response(self):
        initial = self.repository.save("alice", self._battle_reward_run())
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {"completeState": 3}

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        reward = snapshot.run["player"]["pending"][0]["content"][
            "battleReward"
        ]
        self.assertIsNone(reward["show"])
        self.assertEqual(reward["state"], 3)
        self.assertEqual(reward["isPerfect"], 0)

    def test_pass_rank_is_a_battle_victory(self):
        initial = self.repository.save("alice", self._battle_run())
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 2,
            "battleData": {"stats": {"leftHp": 3}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        player = snapshot.run["player"]
        self.assertEqual(player["state"], "PENDING")
        self.assertEqual(player["pending"][0]["type"], "BATTLE_REWARD")
        reward = player["pending"][0]["content"]["battleReward"]
        self.assertEqual(reward["state"], 2)
        self.assertEqual(reward["isPerfect"], 0)
        self.assertEqual(player["property"]["hp"]["current"], 4)

    def test_existing_game_over_run_settles_directly_and_retry_is_safe(self):
        self.repository.save(
            "alice",
            self._game_over_run(),
            {"rlv2_seed": "active", "seed_list": ["old"]},
        )
        self.request.headers = {"Uid": "alice"}

        response = self.rlv2.rlv2GameSettle()

        self.assertEqual(response["game"]["brief"]["success"], 0)
        self.assertEqual(response["game"]["brief"]["mode"], "NORMAL")
        self.assertEqual(response["game"]["record"]["cntZone"], 1)
        self.assertEqual(response["game"]["score"]["score"], 0.0)
        self.assertEqual(response["outer"]["gp"], 0)
        self.assertIn("playerDataDelta", response)
        settled = self.repository.load("alice")
        self.assertIsNone(settled.run["player"])
        self.assertEqual(settled.seed_list, ["active", "old"])

        retry = self.rlv2.rlv2GameSettle()
        self.assertEqual(retry["game"]["score"]["score"], 0.0)
        self.assertEqual(retry["outer"]["gp"], 0)
        after_retry = self.repository.load("alice")
        self.assertIsNone(after_retry.run["player"])
        self.assertIsNone(after_retry.rlv2_seed)
        self.assertEqual(after_retry.seed_list, ["active", "old"])

    def test_game_settlement_only_clears_the_requesting_user(self):
        self.repository.save(
            "alice",
            self._game_over_run(),
            {"rlv2_seed": "alice-seed", "seed_list": []},
        )
        bob_run = self._battle_run()
        self.repository.save(
            "bob",
            bob_run,
            {"rlv2_seed": "bob-seed", "seed_list": ["bob-old"]},
        )
        self.request.headers = {"Uid": "alice"}

        self.rlv2.rlv2FinishGame()
        self.rlv2.rlv2GameSettle()

        alice = self.repository.load("alice")
        bob = self.repository.load("bob")
        self.assertIsNone(alice.run["player"])
        self.assertEqual(alice.seed_list, ["alice-seed"])
        self.assertEqual(bob.run, bob_run)
        self.assertEqual(bob.rlv2_seed, "bob-seed")
        self.assertEqual(bob.seed_list, ["bob-old"])

    def test_finish_game_rejects_an_active_run_without_clearing_it(self):
        initial = self.repository.save("alice", self._battle_run())
        self.request.headers = {"Uid": "alice"}

        response, status = self.rlv2.rlv2FinishGame()

        self.assertEqual(status, 409)
        self.assertIn("not ready", response["error"])
        after = self.repository.load("alice")
        self.assertEqual(after.revision, initial.revision)
        self.assertEqual(after.run, initial.run)

    def test_settlement_routes_are_registered(self):
        app_source = (ROOT / "server/app.py").read_text(encoding="utf-8")

        self.assertIn('app.add_url_rule("/rlv2/finishGame"', app_source)
        self.assertIn('app.add_url_rule("/rlv2/gameSettle"', app_source)

    def test_battle_finish_excludes_nonstandard_zones_from_base_rewards(self):
        run = self._battle_run()
        run["map"]["zones"]["1"]["id"] = "portal_zone_1"
        initial = self.repository.save("alice", run)
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        prop = snapshot.run["player"]["property"]
        self.assertEqual(prop["exp"], 5)
        self.assertEqual(prop["gold"], 6)
        battle_reward = snapshot.run["player"]["pending"][0]["content"][
            "battleReward"
        ]
        self.assertEqual(battle_reward["earn"]["exp"], 0)
        self.assertEqual(len(battle_reward["rewards"]), 1)
        self.assertEqual(
            battle_reward["rewards"][0]["items"][0]["id"],
            "rogue_1_recruit_ticket_all",
        )

    def test_battle_finish_does_not_fall_back_for_boss_rewards(self):
        run = self._battle_run()
        run["map"]["zones"]["1"]["nodes"]["0"]["type"] = 4
        initial = self.repository.save("alice", run)
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {"stats": {"leftHp": 4}},
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        self.assertEqual(snapshot.run["player"]["property"]["exp"], 5)
        self.assertEqual(snapshot.run["player"]["property"]["gold"], 6)
        battle_reward = snapshot.run["player"]["pending"][0]["content"][
            "battleReward"
        ]
        self.assertEqual(battle_reward["earn"]["exp"], 0)
        self.assertEqual(len(battle_reward["rewards"]), 1)

    def test_ro2_knight_death_reward_is_required_and_restores_default_route(self):
        run = self._ro2_knight_battle_run()
        initial = self.repository.save(
            "alice", run, {"rlv2_seed": "seed", "seed_list": []}
        )
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"data": "encrypted"}
        self.rlv2.decrypt_battle_data = lambda value: {
            "completeState": 3,
            "battleData": {
                "stats": {
                    "leftHp": 4,
                    "extraBattleInfo": {
                        "SIMPLE,trap_079_allydonq,killed": 1,
                        "SIMPLE,trap_079_allydonq,born": 1,
                    },
                }
            },
        }

        response = self.rlv2.rlv2BattleFinish()

        self.assert_battle_finish_response(response)
        finished = self.repository.load("alice")
        self.assertEqual(finished.revision, initial.revision + 1)
        reward_index = self._reward_index_for_item(
            finished.run, "rogue_2_relic_grace_84"
        )
        self.assertEqual(
            finished.run["_server"]["events"][
                "requiredBattleRewardIndexes"
            ],
            [str(reward_index)],
        )

        retry_response = self.rlv2.rlv2BattleFinish()
        self.assert_battle_finish_response(retry_response)
        after_retry = self.repository.load("alice")
        self.assertEqual(after_retry.run, finished.run)

        blocked_response, status = self.rlv2.rlv2FinishBattleReward()
        self.assertEqual(status, 409)
        self.assertIn("required event battle reward", blocked_response["error"])

        self.request.get_json = lambda: {"index": reward_index, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()

        self.assertIn("playerDataDelta", response)
        claimed = self.repository.load("alice").run
        self.assertTrue(
            self.rlv2._rlv2.hasItem(claimed, "rogue_2_relic_grace_84")
        )
        self.assertEqual(claimed["player"]["toEnding"], "ro2_ending_1")
        self.assertIs(claimed["player"]["chgEnding"], True)
        self.assertEqual(
            claimed["_server"]["route"]["endingId"], "ro2_ending_1"
        )
        self.assertEqual(
            claimed["map"]["zones"]["5"]["nodes"]["100"]["stage"],
            "ro2_b_4",
        )
        self.assertEqual(
            sum(
                relic.get("count", 1)
                for relic in claimed["inventory"]["relic"].values()
                if relic.get("id") == "rogue_2_relic_grace_84"
            ),
            1,
        )

        duplicate_response, status = self.rlv2.rlv2ChooseBattleReward()
        self.assertEqual(status, 400)
        self.assertIn("unavailable", duplicate_response["error"])
        self.assertEqual(self.repository.load("alice").run, claimed)

    def test_ro2_knight_reward_uses_exact_death_key_and_route_inventory(self):
        killed_key = "SIMPLE,trap_079_allydonq,killed"
        cases = (
            (
                "born only",
                {"SIMPLE,trap_079_allydonq,born": 1},
                True,
                False,
            ),
            ("zero deaths", {killed_key: 0}, True, False),
            (
                "trap alias",
                {"SIMPLE,trap_079_allydonq#1,killed": 1},
                True,
                False,
            ),
            ("missing route relic", {killed_key: 1}, False, False),
            ("reward already owned", {killed_key: 1}, True, True),
        )

        for name, extra_battle_info, route_relic, retreat_relic in cases:
            with self.subTest(name=name):
                run = self._ro2_knight_battle_run(
                    route_relic=route_relic,
                    retreat_relic=retreat_relic,
                )
                self.repository.save(
                    "alice", run, {"rlv2_seed": "seed", "seed_list": []}
                )
                self.request.headers = {"Uid": "alice"}
                self.request.get_json = lambda: {"data": "encrypted"}
                self.rlv2.decrypt_battle_data = (
                    lambda value, info=extra_battle_info: {
                        "completeState": 3,
                        "battleData": {
                            "stats": {
                                "leftHp": 4,
                                "extraBattleInfo": info,
                            }
                        },
                    }
                )

                response = self.rlv2.rlv2BattleFinish()

                self.assert_battle_finish_response(response)
                finished = self.repository.load("alice").run
                rewards = finished["player"]["pending"][0]["content"][
                    "battleReward"
                ]["rewards"]
                self.assertFalse(
                    any(
                        item.get("id") == "rogue_2_relic_grace_84"
                        for reward in rewards
                        for item in reward.get("items", [])
                    )
                )
                self.assertNotIn(
                    "requiredBattleRewardIndexes",
                    finished["_server"]["events"],
                )

    def test_choose_battle_reward_selects_one_index_and_sub_only_once(self):
        initial = self.repository.save("alice", self._battle_reward_run())
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"index": 4, "sub": 1}

        response = self.rlv2.rlv2ChooseBattleReward()

        self.assertIn("playerDataDelta", response)
        selected = self.repository.load("alice")
        self.assertEqual(selected.revision, initial.revision + 1)
        self.assertEqual(selected.run["player"]["property"]["gold"], 13)
        rewards = selected.run["player"]["pending"][0]["content"][
            "battleReward"
        ]["rewards"]
        self.assertIs(rewards[0]["done"], True)
        self.assertIs(rewards[1]["done"], False)

        response, status = self.rlv2.rlv2ChooseBattleReward()
        self.assertEqual(status, 400)
        self.assertIn("unavailable", response["error"])
        after_retry = self.repository.load("alice")
        self.assertEqual(after_retry.revision, selected.revision)
        self.assertEqual(after_retry.run, selected.run)

    def test_choose_battle_reward_rejects_invalid_sub_without_committing(self):
        initial = self.repository.save("alice", self._battle_reward_run())
        self.request.headers = {"Uid": "alice"}
        self.request.get_json = lambda: {"index": 4, "sub": 99}

        response, status = self.rlv2.rlv2ChooseBattleReward()

        self.assertEqual(status, 400)
        self.assertIn("4/99", response["error"])
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision)
        self.assertEqual(snapshot.run, initial.run)

    def test_choose_battle_reward_rejects_non_integer_index_and_sub(self):
        initial = self.repository.save("alice", self._battle_reward_run())
        self.request.headers = {"Uid": "alice"}

        for selection in (
            {"index": True, "sub": 0},
            {"index": 4.9, "sub": 0},
            {"index": "4", "sub": 0},
            {"index": 4, "sub": "0"},
        ):
            with self.subTest(selection=selection):
                self.request.get_json = lambda selection=selection: selection
                response, status = self.rlv2.rlv2ChooseBattleReward()
                self.assertEqual(status, 400)
                self.assertIn("invalid", response["error"])

        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision)
        self.assertEqual(snapshot.run, initial.run)

    def test_finish_battle_reward_allows_unclaimed_base_gold(self):
        run = self._battle_reward_run()
        rewards = run["player"]["pending"][0]["content"]["battleReward"][
            "rewards"
        ]
        rewards[0]["items"] = [
            {"sub": 0, "id": "rogue_1_gold", "count": 3}
        ]
        initial = self.repository.save("alice", run)
        self.request.headers = {"Uid": "alice"}

        response = self.rlv2.rlv2FinishBattleReward()

        self.assertIn("playerDataDelta", response)
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision + 1)
        self.assertEqual(snapshot.run["player"]["state"], "WAIT_MOVE")
        self.assertEqual(snapshot.run["player"]["pending"], [])
        self.assertEqual(snapshot.run["player"]["property"]["gold"], 6)

    def test_finish_battle_reward_requires_marked_event_reward(self):
        run = self._battle_reward_run()
        run["_server"] = {
            "schemaVersion": 1,
            "events": {"requiredBattleRewardIndexes": ["4"]},
        }
        initial = self.repository.save("alice", run)
        self.request.headers = {"Uid": "alice"}

        response, status = self.rlv2.rlv2FinishBattleReward()

        self.assertEqual(status, 409)
        self.assertIn("required event battle reward", response["error"])
        blocked = self.repository.load("alice")
        self.assertEqual(blocked.revision, initial.revision)
        self.assertEqual(blocked.run, initial.run)

        self.request.get_json = lambda: {"index": 4, "sub": 0}
        response = self.rlv2.rlv2ChooseBattleReward()
        self.assertIn("playerDataDelta", response)
        response = self.rlv2.rlv2FinishBattleReward()
        self.assertIn("playerDataDelta", response)
        finished = self.repository.load("alice").run
        self.assertEqual(finished["player"]["state"], "WAIT_MOVE")
        self.assertEqual(finished["player"]["pending"], [])
        self.assertNotIn(
            "requiredBattleRewardIndexes", finished["_server"]["events"]
        )

    def test_multi_user_request_without_uid_is_rejected(self):
        self.request.headers = {}

        response, status = self.rlv2.rlv2GiveUpGame()

        self.assertEqual(status, 400)
        self.assertIn("requires the Uid header", response["error"])


if __name__ == "__main__":
    unittest.main()

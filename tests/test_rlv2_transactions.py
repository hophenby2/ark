import importlib.util
import sys
import tempfile
import types
import unittest
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

    def test_map_battle_start_uses_ten_percent_gopnik_chance(self):
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
        self.assertEqual(battle["goldTrapCnt"], 10)

    def test_event_battle_uses_ten_percent_gopnik_chance(self):
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
        self.assertEqual(battle["goldTrapCnt"], 10)

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

    def test_finish_battle_reward_requires_base_gold_to_be_claimed(self):
        run = self._battle_reward_run()
        rewards = run["player"]["pending"][0]["content"]["battleReward"][
            "rewards"
        ]
        rewards[0]["items"] = [
            {"sub": 0, "id": "rogue_1_gold", "count": 3}
        ]
        initial = self.repository.save("alice", run)
        self.request.headers = {"Uid": "alice"}

        response, status = self.rlv2.rlv2FinishBattleReward()

        self.assertEqual(status, 409)
        self.assertIn("must be claimed", response["error"])
        snapshot = self.repository.load("alice")
        self.assertEqual(snapshot.revision, initial.revision)
        self.assertEqual(snapshot.run, initial.run)

    def test_multi_user_request_without_uid_is_rejected(self):
        self.request.headers = {}

        response, status = self.rlv2.rlv2GiveUpGame()

        self.assertEqual(status, 400)
        self.assertIn("requires the Uid header", response["error"])


if __name__ == "__main__":
    unittest.main()

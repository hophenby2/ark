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

    def tearDown(self):
        self.temporary_directory.cleanup()

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

    def test_multi_user_request_without_uid_is_rejected(self):
        self.request.headers = {}

        response, status = self.rlv2.rlv2GiveUpGame()

        self.assertEqual(status, 400)
        self.assertIn("requires the Uid header", response["error"])


if __name__ == "__main__":
    unittest.main()

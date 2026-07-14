import json
import sys
import tempfile
import threading
import unittest
import uuid
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from rlv2_repository import (  # noqa: E402
    ConcurrentWriteError,
    InvalidUserIdError,
    LegacyRunAlreadyMigratedError,
    MissingUserIdError,
    RepositorySettings,
    RunRepository,
    SINGLE_USER_UID,
    uid_from_headers,
)


class RunRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.legacy_run = self.root / "data/user/rlv2.json"
        self.legacy_server = self.root / "data/user/serverData.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def repository(self, *, enabled=True, mirror_legacy=False):
        settings = RepositorySettings(
            enabled=enabled,
            database_path=self.root / "data/user/rlv2_runs.sqlite3",
            mirror_legacy=mirror_legacy,
        )
        return RunRepository(
            settings,
            legacy_run_path=self.legacy_run,
            legacy_server_data_path=self.legacy_server,
        )

    def write_legacy(self, run, server_data):
        self.legacy_run.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_run.write_text(json.dumps(run), encoding="utf-8")
        self.legacy_server.write_text(
            json.dumps(server_data), encoding="utf-8"
        )

    def test_multi_user_requires_and_canonicalizes_uid_header(self):
        settings = RepositorySettings(enabled=True, mirror_legacy=False)
        with self.assertRaises(MissingUserIdError):
            uid_from_headers({}, settings)
        with self.assertRaises(InvalidUserIdError):
            uid_from_headers({"Uid": SINGLE_USER_UID}, settings)

        user_id = uuid.uuid4()
        self.assertEqual(
            uid_from_headers({"uid": str(user_id).upper()}, settings),
            str(user_id),
        )

        single_user = RepositorySettings(enabled=False)
        self.assertEqual(uid_from_headers({}, single_user), SINGLE_USER_UID)

    def test_project_config_defaults_are_usable(self):
        config_path = self.root / "config/multiUserConfig.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text('{"enabled": false}', encoding="utf-8")

        settings = RepositorySettings.from_file(
            config_path, project_root=self.root
        )
        self.assertEqual(settings.single_user_uid, SINGLE_USER_UID)
        self.assertEqual(
            settings.database_path,
            self.root / "data/user/rlv2_runs.sqlite3",
        )

    def test_two_users_have_independent_run_and_seed_state(self):
        repository = self.repository()
        alice = repository.save(
            "alice",
            {"player": {"gold": 7}},
            {"rlv2_seed": "seed-a", "seed_list": [1]},
        )
        bob = repository.save(
            "bob",
            {"player": {"gold": 19}},
            {"rlv2_seed": "seed-b", "seed_list": [2, 3]},
        )

        self.assertEqual(alice.revision, 1)
        self.assertEqual(bob.revision, 1)
        self.assertEqual(repository.load("alice").run["player"]["gold"], 7)
        self.assertEqual(repository.load("alice").rlv2_seed, "seed-a")
        self.assertEqual(repository.load("bob").run["player"]["gold"], 19)
        self.assertEqual(repository.load("bob").seed_list, [2, 3])

    def test_compare_and_swap_rejects_stale_handler_result(self):
        repository = self.repository()
        first = repository.save("alice", {"value": 1})
        second = repository.save(
            "alice", {"value": 2}, expected_revision=first.revision
        )

        with self.assertRaises(ConcurrentWriteError) as raised:
            repository.save(
                "alice", {"value": 3}, expected_revision=first.revision
            )
        self.assertEqual(raised.exception.actual, second.revision)
        self.assertEqual(repository.load("alice").run, {"value": 2})

    def test_run_only_save_preserves_seed_state(self):
        repository = self.repository()
        first = repository.save(
            "alice",
            {"value": 1},
            {"rlv2_seed": "keep", "seed_list": [7]},
        )
        repository.save(
            "alice",
            {"value": 2},
            expected_revision=first.revision,
        )

        snapshot = repository.load("alice")
        self.assertEqual(snapshot.rlv2_seed, "keep")
        self.assertEqual(snapshot.seed_list, [7])

    def test_concurrent_transactions_do_not_lose_updates(self):
        repository = self.repository()
        repository.save("alice", {"count": 0})
        failures = []

        def increment():
            try:
                for _ in range(20):
                    with repository.transaction("alice") as transaction:
                        transaction.run["count"] += 1
                        transaction.commit()
            except BaseException as exc:
                failures.append(exc)

        workers = [threading.Thread(target=increment) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        self.assertEqual(failures, [])
        snapshot = repository.load("alice")
        self.assertEqual(snapshot.run["count"], 80)
        self.assertEqual(snapshot.revision, 81)

    def test_transaction_commits_run_and_seed_together(self):
        repository = self.repository()
        with repository.transaction("alice") as transaction:
            transaction.run = {"player": {"gold": 10}}
            transaction.server_data["rlv2_seed"] = "seed"
            transaction.server_data["seed_list"] = [4, 5]
            transaction.commit()

        self.assertIsNotNone(transaction.committed_snapshot)
        snapshot = repository.load("alice")
        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(snapshot.run["player"]["gold"], 10)
        self.assertEqual(snapshot.rlv2_seed, "seed")
        self.assertEqual(snapshot.seed_list, [4, 5])

    def test_transaction_rolls_back_without_explicit_commit(self):
        repository = self.repository()
        repository.save("alice", {"value": "before"})

        with repository.transaction("alice") as transaction:
            transaction.run["value"] = "after"
            transaction.server_data["rlv2_seed"] = "discarded"

        snapshot = repository.load("alice")
        self.assertEqual(snapshot.revision, 1)
        self.assertEqual(snapshot.run, {"value": "before"})
        self.assertIsNone(snapshot.rlv2_seed)

    def test_single_user_imports_and_mirrors_legacy_sidecars(self):
        self.write_legacy(
            {"player": {"gold": 6}},
            {"rlv2_seed": "old", "seed_list": [8], "other": 42},
        )
        repository = self.repository(enabled=False, mirror_legacy=True)

        imported = repository.load()
        self.assertEqual(imported.uid, SINGLE_USER_UID)
        self.assertEqual(imported.run["player"]["gold"], 6)
        self.assertEqual(imported.rlv2_seed, "old")

        repository.save(
            None,
            {"player": {"gold": 9}},
            {"rlv2_seed": "new", "seed_list": [10], "other": 42},
            expected_revision=imported.revision,
        )
        mirrored_run = json.loads(self.legacy_run.read_text(encoding="utf-8"))
        mirrored_server = json.loads(
            self.legacy_server.read_text(encoding="utf-8")
        )
        self.assertEqual(mirrored_run["player"]["gold"], 9)
        self.assertEqual(mirrored_server["rlv2_seed"], "new")
        self.assertEqual(mirrored_server["other"], 42)

    def test_multi_user_legacy_migration_requires_an_explicit_owner(self):
        self.write_legacy(
            {"player": {"gold": 6}},
            {"rlv2_seed": "legacy", "seed_list": [1]},
        )
        repository = self.repository(enabled=True)

        self.assertIsNone(repository.load("alice").run["player"])
        migrated = repository.migrate_legacy("alice")
        self.assertEqual(migrated.run["player"]["gold"], 6)
        self.assertEqual(migrated.rlv2_seed, "legacy")
        self.assertIsNone(repository.load("bob").run["player"])

        with self.assertRaises(LegacyRunAlreadyMigratedError):
            repository.migrate_legacy("alice")
        with self.assertRaises(LegacyRunAlreadyMigratedError):
            repository.migrate_legacy("bob")

    def test_single_user_sentinel_transfers_to_first_explicit_uid(self):
        self.write_legacy(
            {"player": {"gold": 6}},
            {"rlv2_seed": "old", "seed_list": [1]},
        )
        single_user_repository = self.repository(
            enabled=False, mirror_legacy=False
        )
        imported = single_user_repository.load()
        single_user_repository.save(
            None,
            {"player": {"gold": 99}},
            {"rlv2_seed": "sqlite-new", "seed_list": [7, 8]},
            expected_revision=imported.revision,
        )

        multi_user_repository = self.repository(enabled=True)
        migrated = multi_user_repository.migrate_legacy("alice")
        self.assertEqual(migrated.run["player"]["gold"], 99)
        self.assertEqual(migrated.rlv2_seed, "sqlite-new")
        self.assertEqual(migrated.seed_list, [7, 8])

        with sqlite3.connect(multi_user_repository.database_path) as connection:
            sentinel_count = connection.execute(
                "SELECT COUNT(*) FROM roguelike_runs WHERE uid = ?",
                (SINGLE_USER_UID,),
            ).fetchone()[0]
        self.assertEqual(sentinel_count, 0)
        with self.assertRaises(LegacyRunAlreadyMigratedError):
            multi_user_repository.migrate_legacy("bob")


if __name__ == "__main__":
    unittest.main()

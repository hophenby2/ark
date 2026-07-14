"""Transactional persistence for an active Integrated Strategies run.

The current HTTP API identifies a player with the ``Uid`` request header, but
does not authenticate that header.  Callers should pass an identity already
validated by the authentication layer.  ``uid_from_headers`` only exists as a
transition helper; it is not an authentication mechanism.

SQLite is the source of truth.  In single-user mode the old JSON sidecars are
imported once and kept as compatibility mirrors.  In multi-user mode legacy
data is never assigned implicitly because its owner cannot be inferred safely.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = 1
SINGLE_USER_UID = "__single_user__"
DEFAULT_UID_HEADER = "Uid"
_UID_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+\-]{0,127}\Z")


def empty_run() -> dict[str, None]:
    return {
        "player": None,
        "record": None,
        "map": None,
        "troop": None,
        "inventory": None,
        "game": None,
        "buff": None,
        "module": None,
    }


class RunRepositoryError(RuntimeError):
    pass


class RepositoryConfigurationError(RunRepositoryError):
    pass


class MissingUserIdError(RunRepositoryError):
    pass


class InvalidUserIdError(RunRepositoryError):
    pass


class ConcurrentWriteError(RunRepositoryError):
    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"stale roguelike revision: expected {expected}, found {actual}"
        )


class LegacyRunAlreadyMigratedError(RunRepositoryError):
    pass


class LegacyMirrorError(RunRepositoryError):
    """The SQLite commit succeeded, but a compatibility mirror failed."""

    def __init__(self, snapshot: "RunSnapshot", cause: OSError):
        self.snapshot = snapshot
        self.cause = cause
        super().__init__(f"legacy mirror failed after commit: {cause}")


@dataclass(frozen=True)
class RepositorySettings:
    enabled: bool = False
    uid_header: str = DEFAULT_UID_HEADER
    database_path: Path = Path("data/user/rlv2_runs.sqlite3")
    single_user_uid: str = SINGLE_USER_UID
    mirror_legacy: bool = True

    @classmethod
    def from_file(
        cls,
        path: str | os.PathLike[str],
        *,
        project_root: str | os.PathLike[str] | None = None,
    ) -> "RepositorySettings":
        config_path = Path(path)
        root = (
            Path(project_root)
            if project_root is not None
            else config_path.parent.parent
        )
        try:
            with config_path.open(encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryConfigurationError(
                f"cannot read multi-user config {config_path}: {exc}"
            ) from exc

        if not isinstance(raw, dict) or not isinstance(raw.get("enabled"), bool):
            raise RepositoryConfigurationError(
                "multi-user config must contain a boolean 'enabled'"
            )

        enabled = raw["enabled"]
        uid_header = raw.get("uidHeader", DEFAULT_UID_HEADER)
        single_user_uid = raw.get("singleUserUid", SINGLE_USER_UID)
        database_value = raw.get(
            "rlv2Database", "data/user/rlv2_runs.sqlite3"
        )
        mirror_legacy = raw.get("mirrorLegacy", not enabled)

        if not isinstance(uid_header, str) or not uid_header.strip():
            raise RepositoryConfigurationError("uidHeader must be a string")
        if not isinstance(mirror_legacy, bool):
            raise RepositoryConfigurationError("mirrorLegacy must be boolean")
        if not isinstance(database_value, str) or not database_value:
            raise RepositoryConfigurationError("rlv2Database must be a path")

        try:
            single_user_uid = canonicalize_uid(single_user_uid)
        except InvalidUserIdError as exc:
            raise RepositoryConfigurationError(str(exc)) from exc

        database_path = Path(database_value)
        if not database_path.is_absolute():
            database_path = root / database_path

        return cls(
            enabled=enabled,
            uid_header=uid_header.strip(),
            database_path=database_path,
            single_user_uid=single_user_uid,
            mirror_legacy=mirror_legacy,
        )


def canonicalize_uid(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, uuid.UUID)):
        raise InvalidUserIdError("UID must be a string, integer, or UUID")

    uid = str(value).strip()
    if not _UID_PATTERN.fullmatch(uid):
        raise InvalidUserIdError(
            "UID must be 1-128 ASCII letters, digits, or ._:@+-"
        )

    try:
        return str(uuid.UUID(uid))
    except ValueError:
        return uid


def uid_from_headers(
    headers: Mapping[str, object] | None,
    settings: RepositorySettings,
) -> str:
    """Resolve a storage key; this does not verify the asserted identity."""
    if not settings.enabled:
        return settings.single_user_uid
    if headers is None:
        raise MissingUserIdError(
            f"multi-user mode requires the {settings.uid_header} header"
        )

    raw_uid = headers.get(settings.uid_header)
    if raw_uid is None:
        target = settings.uid_header.casefold()
        raw_uid = next(
            (value for key, value in headers.items() if key.casefold() == target),
            None,
        )
    if raw_uid is None:
        raise MissingUserIdError(
            f"multi-user mode requires the {settings.uid_header} header"
        )
    uid = canonicalize_uid(raw_uid)
    if uid == settings.single_user_uid:
        raise InvalidUserIdError("the single-user UID is reserved")
    return uid


@dataclass(frozen=True)
class RunSnapshot:
    uid: str
    revision: int
    run: dict[str, Any]
    rlv2_seed: Any = None
    seed_list: list[Any] = field(default_factory=list)
    updated_at_ns: int = 0

    def merged_server_data(
        self, base: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        result = deepcopy(dict(base or {}))
        result["rlv2_seed"] = deepcopy(self.rlv2_seed)
        result["seed_list"] = deepcopy(self.seed_list)
        return result


@dataclass
class RunTransaction:
    uid: str
    revision: int
    run: dict[str, Any]
    server_data: dict[str, Any]
    committed_snapshot: RunSnapshot | None = field(default=None, init=False)
    _commit_requested: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def commit(self) -> None:
        """Request a commit when the surrounding context exits cleanly."""
        if self._closed:
            raise RunRepositoryError("transaction is already closed")
        self._commit_requested = True

    def rollback(self) -> None:
        if self._closed:
            raise RunRepositoryError("transaction is already closed")
        self._commit_requested = False


class RunRepository:
    def __init__(
        self,
        settings: RepositorySettings,
        *,
        legacy_run_path: str | os.PathLike[str] = "data/user/rlv2.json",
        legacy_server_data_path: str | os.PathLike[str] = (
            "data/user/serverData.json"
        ),
    ) -> None:
        self.settings = settings
        self.database_path = Path(settings.database_path)
        self.legacy_run_path = Path(legacy_run_path)
        self.legacy_server_data_path = Path(legacy_server_data_path)
        self._schema_lock = threading.RLock()
        self._mirror_lock = threading.RLock()
        self._initialize_schema()
        if not settings.enabled:
            self._bootstrap_single_user()

    @classmethod
    def from_project(
        cls, project_root: str | os.PathLike[str] = "."
    ) -> "RunRepository":
        root = Path(project_root)
        settings = RepositorySettings.from_file(
            root / "config/multiUserConfig.json", project_root=root
        )
        return cls(
            settings,
            legacy_run_path=root / "data/user/rlv2.json",
            legacy_server_data_path=root / "data/user/serverData.json",
        )

    def uid_from_headers(self, headers: Mapping[str, object] | None) -> str:
        return uid_from_headers(headers, self.settings)

    def load(self, uid: object | None = None) -> RunSnapshot:
        storage_uid = self._storage_uid(uid)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM roguelike_runs WHERE uid = ?", (storage_uid,)
            ).fetchone()
        finally:
            connection.close()
        return self._snapshot_from_row(storage_uid, row)

    def load_run(self, uid: object | None = None) -> dict[str, Any]:
        return self.load(uid).run

    def load_server_data(
        self,
        uid: object | None = None,
        *,
        base: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if base is None:
            base = self._read_json_if_present(self.legacy_server_data_path, {})
        return self.load(uid).merged_server_data(base)

    def save(
        self,
        uid: object | None,
        run: Mapping[str, Any],
        server_data: Mapping[str, Any] | None = None,
        *,
        expected_revision: int | None = None,
    ) -> RunSnapshot:
        storage_uid = self._storage_uid(uid)
        encoded_run, clean_run = self._encode_run(run)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM roguelike_runs WHERE uid = ?", (storage_uid,)
            ).fetchone()
            current = self._snapshot_from_row(storage_uid, row)
            if (
                expected_revision is not None
                and expected_revision != current.revision
            ):
                raise ConcurrentWriteError(
                    expected_revision, current.revision
                )

            if server_data is None:
                seed = current.rlv2_seed
                seed_list = current.seed_list
            else:
                if not isinstance(server_data, Mapping):
                    raise TypeError("server_data must be a mapping")
                seed = deepcopy(server_data.get("rlv2_seed"))
                seed_list = self._validate_seed_list(
                    server_data.get("seed_list", [])
                )

            snapshot = self._write_snapshot(
                connection,
                storage_uid,
                current.revision + 1,
                encoded_run,
                clean_run,
                seed,
                seed_list,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

        self._mirror_after_commit(snapshot)
        return snapshot

    @contextmanager
    def transaction(
        self, uid: object | None = None
    ) -> Iterator[RunTransaction]:
        """Open a write transaction; call ``tx.commit()`` to persist it."""
        storage_uid = self._storage_uid(uid)
        connection = self._connect()
        transaction: RunTransaction | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM roguelike_runs WHERE uid = ?", (storage_uid,)
            ).fetchone()
            snapshot = self._snapshot_from_row(storage_uid, row)
            base = self._read_json_if_present(
                self.legacy_server_data_path, {}
            )
            transaction = RunTransaction(
                uid=storage_uid,
                revision=snapshot.revision,
                run=snapshot.run,
                server_data=snapshot.merged_server_data(base),
            )
            yield transaction

            if transaction._commit_requested:
                encoded_run, clean_run = self._encode_run(transaction.run)
                seed_list = self._validate_seed_list(
                    transaction.server_data.get("seed_list", [])
                )
                new_snapshot = self._write_snapshot(
                    connection,
                    storage_uid,
                    snapshot.revision + 1,
                    encoded_run,
                    clean_run,
                    deepcopy(transaction.server_data.get("rlv2_seed")),
                    seed_list,
                )
                connection.commit()
                transaction.committed_snapshot = new_snapshot
            else:
                connection.rollback()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if transaction is not None:
                transaction._closed = True
            connection.close()

        if transaction is not None and transaction.committed_snapshot:
            self._mirror_after_commit(transaction.committed_snapshot)

    def migrate_legacy(
        self,
        uid: object | None,
        *,
        overwrite: bool = False,
    ) -> RunSnapshot:
        """Assign legacy JSON state to one explicitly selected user."""
        storage_uid = self._storage_uid(uid)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if self.settings.enabled:
                owner_row = connection.execute(
                    "SELECT value FROM repository_metadata WHERE key = ?",
                    ("legacy_owner_uid",),
                ).fetchone()
                if (
                    owner_row is not None
                    and owner_row["value"] != storage_uid
                ):
                    raise LegacyRunAlreadyMigratedError(
                        "legacy roguelike state is already owned by UID "
                        f"{owner_row['value']}"
                    )
            row = connection.execute(
                "SELECT revision FROM roguelike_runs WHERE uid = ?",
                (storage_uid,),
            ).fetchone()
            if row is not None and not overwrite:
                raise LegacyRunAlreadyMigratedError(
                    f"a run already exists for UID {storage_uid}"
                )

            sentinel_row = None
            if self.settings.enabled:
                sentinel_row = connection.execute(
                    "SELECT * FROM roguelike_runs WHERE uid = ?",
                    (self.settings.single_user_uid,),
                ).fetchone()
            if sentinel_row is not None:
                source = self._snapshot_from_row(
                    self.settings.single_user_uid, sentinel_row
                )
                encoded_run, clean_run = self._encode_run(source.run)
                seed = source.rlv2_seed
                seed_list = source.seed_list
            else:
                run = self._read_json_if_present(
                    self.legacy_run_path, empty_run()
                )
                server_data = self._read_json_if_present(
                    self.legacy_server_data_path, {}
                )
                encoded_run, clean_run = self._encode_run(run)
                seed = deepcopy(server_data.get("rlv2_seed"))
                seed_list = self._validate_seed_list(
                    server_data.get("seed_list", [])
                )

            revision = int(row["revision"]) + 1 if row is not None else 1
            snapshot = self._write_snapshot(
                connection,
                storage_uid,
                revision,
                encoded_run,
                clean_run,
                seed,
                seed_list,
            )
            if self.settings.enabled:
                if sentinel_row is not None:
                    connection.execute(
                        "DELETE FROM roguelike_runs WHERE uid = ?",
                        (self.settings.single_user_uid,),
                    )
                connection.execute(
                    """
                    INSERT INTO repository_metadata (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("legacy_owner_uid", storage_uid),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

        self._mirror_after_commit(snapshot)
        return snapshot

    def sync_legacy_mirror(self) -> None:
        """Repair compatibility sidecars from the single-user source."""
        if self.settings.enabled:
            raise RunRepositoryError(
                "legacy mirrors are not available in multi-user mode"
            )
        self._write_legacy_mirror(self.load())

    def _storage_uid(self, uid: object | None) -> str:
        if not self.settings.enabled:
            return self.settings.single_user_uid
        if uid is None:
            raise MissingUserIdError("multi-user repository requires a UID")
        storage_uid = canonicalize_uid(uid)
        if storage_uid == self.settings.single_user_uid:
            raise InvalidUserIdError("the single-user UID is reserved")
        return storage_uid

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        with self._schema_lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if version > SCHEMA_VERSION:
                    raise RepositoryConfigurationError(
                        f"database schema {version} is newer than supported "
                        f"schema {SCHEMA_VERSION}"
                    )
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS roguelike_runs (
                        uid TEXT PRIMARY KEY,
                        revision INTEGER NOT NULL CHECK (revision > 0),
                        run_json TEXT NOT NULL,
                        rlv2_seed_json TEXT NOT NULL,
                        seed_list_json TEXT NOT NULL,
                        updated_at_ns INTEGER NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS repository_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _bootstrap_single_user(self) -> None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM roguelike_runs WHERE uid = ?",
                (self.settings.single_user_uid,),
            ).fetchone()
        finally:
            connection.close()
        if row is not None:
            return

        if not self.legacy_run_path.exists() and not (
            self.legacy_server_data_path.exists()
        ):
            return
        try:
            self.migrate_legacy(self.settings.single_user_uid)
        except LegacyRunAlreadyMigratedError:
            # Another process won the one-time bootstrap transaction.
            pass

    def _snapshot_from_row(
        self, uid: str, row: sqlite3.Row | None
    ) -> RunSnapshot:
        if row is None:
            return RunSnapshot(uid=uid, revision=0, run=empty_run())
        try:
            run = json.loads(row["run_json"])
            seed = json.loads(row["rlv2_seed_json"])
            seed_list = json.loads(row["seed_list_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise RunRepositoryError(
                f"corrupt roguelike record for UID {uid}: {exc}"
            ) from exc
        if not isinstance(run, dict) or not isinstance(seed_list, list):
            raise RunRepositoryError(
                f"corrupt roguelike record types for UID {uid}"
            )
        return RunSnapshot(
            uid=uid,
            revision=int(row["revision"]),
            run=run,
            rlv2_seed=seed,
            seed_list=seed_list,
            updated_at_ns=int(row["updated_at_ns"]),
        )

    def _write_snapshot(
        self,
        connection: sqlite3.Connection,
        uid: str,
        revision: int,
        encoded_run: str,
        clean_run: dict[str, Any],
        seed: Any,
        seed_list: list[Any],
    ) -> RunSnapshot:
        encoded_seed = self._encode_json(seed)
        encoded_seed_list = self._encode_json(seed_list)
        updated_at_ns = time.time_ns()
        connection.execute(
            """
            INSERT INTO roguelike_runs (
                uid, revision, run_json, rlv2_seed_json,
                seed_list_json, updated_at_ns
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                revision = excluded.revision,
                run_json = excluded.run_json,
                rlv2_seed_json = excluded.rlv2_seed_json,
                seed_list_json = excluded.seed_list_json,
                updated_at_ns = excluded.updated_at_ns
            """,
            (
                uid,
                revision,
                encoded_run,
                encoded_seed,
                encoded_seed_list,
                updated_at_ns,
            ),
        )
        return RunSnapshot(
            uid=uid,
            revision=revision,
            run=clean_run,
            rlv2_seed=deepcopy(seed),
            seed_list=deepcopy(seed_list),
            updated_at_ns=updated_at_ns,
        )

    def _encode_run(
        self, run: Mapping[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(run, Mapping):
            raise TypeError("run must be a mapping")
        encoded = self._encode_json(dict(run))
        clean = json.loads(encoded)
        if not isinstance(clean, dict):
            raise TypeError("run must encode to an object")
        return encoded, clean

    @staticmethod
    def _encode_json(value: Any) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError(f"value is not JSON serializable: {exc}") from exc

    def _validate_seed_list(self, value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise TypeError("seed_list must be a list")
        return json.loads(self._encode_json(value))

    @staticmethod
    def _read_json_if_present(path: Path, default: Any) -> Any:
        if not path.exists():
            return deepcopy(default)
        with path.open(encoding="utf-8") as file:
            return json.load(file)

    def _mirror_after_commit(
        self,
        snapshot: RunSnapshot,
    ) -> None:
        if self.settings.enabled or not self.settings.mirror_legacy:
            return
        try:
            self._write_legacy_mirror(snapshot)
        except OSError as exc:
            raise LegacyMirrorError(snapshot, exc) from exc

    def _write_legacy_mirror(
        self,
        snapshot: RunSnapshot,
    ) -> None:
        with self._mirror_lock:
            # This repository owns only roguelike seed fields.  Re-read the
            # latest legacy file so unrelated modules are not overwritten by
            # a stale server_data copy from the start of the request.
            base = self._read_json_if_present(
                self.legacy_server_data_path, {}
            )
            merged_server_data = snapshot.merged_server_data(base)
            self._atomic_write_json(self.legacy_run_path, snapshot.run)
            self._atomic_write_json(
                self.legacy_server_data_path, merged_server_data
            )

    @staticmethod
    def _atomic_write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                json.dump(value, file, ensure_ascii=False, indent=4)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


_default_repository: RunRepository | None = None
_default_repository_root: Path | None = None
_default_repository_lock = threading.Lock()


def get_run_repository(
    project_root: str | os.PathLike[str] = ".",
) -> RunRepository:
    """Return the process-wide repository without import-time filesystem I/O."""
    global _default_repository, _default_repository_root
    root = Path(project_root).resolve()
    with _default_repository_lock:
        if _default_repository is None:
            _default_repository = RunRepository.from_project(root)
            _default_repository_root = root
        elif _default_repository_root != root:
            raise RepositoryConfigurationError(
                "the default run repository was initialized for "
                f"{_default_repository_root}, not {root}"
            )
        return _default_repository

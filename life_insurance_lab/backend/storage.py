"""Transactional local storage. Run snapshots never depend on mutable config rows."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from ..errors import ModelError
from ..jsonio import dumps, loads


class NotFound(ModelError):
    pass


class Conflict(ModelError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ModelError("Unsupported database schema version.")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS configs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                    revision INTEGER NOT NULL, document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(kind, name)
                );
                CREATE TABLE IF NOT EXISTS config_revisions (
                    config_id TEXT NOT NULL REFERENCES configs(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL, name TEXT NOT NULL,
                    document_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(config_id, revision)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                    request_json TEXT NOT NULL, result_json TEXT, error TEXT,
                    created_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _config(row):
        if row is None:
            raise NotFound("Configuration not found.")
        result = dict(row)
        result["document"] = loads(result.pop("document_json"))
        return result

    def create_config(self, kind: str, name: str, document: dict) -> dict:
        identifier, timestamp, encoded = "cfg_"+uuid.uuid4().hex, now(), dumps(document)
        try:
            with self.connection() as db, db:
                db.execute("INSERT INTO configs VALUES (?,?,?,?,?,?,?)",
                           (identifier, kind, name, 1, encoded, timestamp, timestamp))
                db.execute("INSERT INTO config_revisions VALUES (?,?,?,?,?)",
                           (identifier, 1, name, encoded, timestamp))
        except sqlite3.IntegrityError as exc:
            raise Conflict("A configuration with this name and kind already exists.") from exc
        return self.get_config(identifier)

    def get_config(self, identifier: str, revision: int | None = None) -> dict:
        with self.connection() as db:
            if revision is None:
                return self._config(db.execute("SELECT * FROM configs WHERE id=?", (identifier,)).fetchone())
            row = db.execute("SELECT r.config_id AS id,c.kind,r.name,r.revision,r.document_json,r.created_at "
                             "FROM config_revisions r JOIN configs c ON c.id=r.config_id "
                             "WHERE r.config_id=? AND r.revision=?", (identifier, revision)).fetchone()
            return self._config(row)

    def list_configs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,name,revision,created_at,updated_at FROM configs "
                "ORDER BY created_at DESC,id LIMIT ? OFFSET ?", (limit, offset))]

    def update_config(self, identifier: str, name: str, document: dict, expected_revision: int) -> dict:
        encoded, timestamp = dumps(document), now()
        try:
            with self.connection() as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT revision FROM configs WHERE id=?", (identifier,)).fetchone()
                if row is None:
                    raise NotFound("Configuration not found.")
                if row["revision"] != expected_revision:
                    raise Conflict("Configuration changed. Fetch its latest revision before updating.")
                new_revision = expected_revision+1
                db.execute("UPDATE configs SET name=?,revision=?,document_json=?,updated_at=? WHERE id=?",
                           (name, new_revision, encoded, timestamp, identifier))
                db.execute("INSERT INTO config_revisions VALUES (?,?,?,?,?)",
                           (identifier, new_revision, name, encoded, timestamp))
        except sqlite3.IntegrityError as exc:
            raise Conflict("A configuration with this name and kind already exists.") from exc
        return self.get_config(identifier)

    def delete_config(self, identifier: str, expected_revision: int) -> None:
        with self.connection() as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM configs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise NotFound("Configuration not found.")
            if row["revision"] != expected_revision:
                raise Conflict("Configuration changed. Fetch its latest revision before deleting.")
            db.execute("DELETE FROM configs WHERE id=?", (identifier,))

    def begin_run(self, kind: str, snapshot: dict) -> str:
        identifier = "run_"+uuid.uuid4().hex
        with self.connection() as db, db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                       (identifier, kind, "running", dumps(snapshot), None, None, now(), None))
        return identifier

    def finish_run(self, identifier: str, status: str, result: dict | None = None, error: str | None = None):
        encoded = None if result is None else dumps(result)
        with self.connection() as db, db:
            changed = db.execute("UPDATE runs SET status=?,result_json=?,error=?,finished_at=? "
                                 "WHERE id=? AND status='running'",
                                 (status, encoded, error, now(), identifier)).rowcount
            if changed != 1:
                raise Conflict("Run is absent or has already finished; its result is immutable.")

    def get_run(self, identifier: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise NotFound("Run not found.")
        result = dict(row)
        result["request"] = loads(result.pop("request_json"))
        encoded = result.pop("result_json")
        result["result"] = None if encoded is None else json.loads(encoded)
        return result

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,status,error,created_at,finished_at FROM runs "
                "ORDER BY created_at DESC,id LIMIT ? OFFSET ?", (limit, offset))]

    def recover_interrupted(self):
        """Call only on startup of the single server owning this database."""
        with self.connection() as db, db:
            return db.execute("UPDATE runs SET status='interrupted',error=?,finished_at=? WHERE status='running'",
                              ("Server stopped before this computation finished.", now())).rowcount

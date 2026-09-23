"""Small SQLite store with atomic progress updates and normalized source records."""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Document


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                    status TEXT NOT NULL, mode TEXT NOT NULL, stage INTEGER NOT NULL,
                    stage_label TEXT NOT NULL, error TEXT, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS documents (
                    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                    id TEXT NOT NULL, position INTEGER NOT NULL, filename TEXT NOT NULL,
                    document_type TEXT NOT NULL, side TEXT NOT NULL, warnings_json TEXT NOT NULL,
                    PRIMARY KEY(analysis_id, id)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    analysis_id TEXT NOT NULL, document_id TEXT NOT NULL, id TEXT NOT NULL,
                    position INTEGER NOT NULL, data_json TEXT NOT NULL,
                    PRIMARY KEY(analysis_id, id),
                    FOREIGN KEY(analysis_id, document_id) REFERENCES documents(analysis_id, id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS analyses_created ON analyses(created_at DESC);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _analysis(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        result = value.pop("result_json", None)
        value["result"] = json.loads(result) if result else None
        return value

    def create(self, title: str, mode: str, documents: list[Document]) -> dict[str, Any]:
        analysis_id = str(uuid.uuid4())
        created = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?,?,?)",
                       (analysis_id, title, created, "queued", mode, 0, "Documents read · analysis queued", None, None))
            for position, document in enumerate(documents):
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)", (
                    analysis_id, document.id, position, document.filename, document.document_type,
                    document.side, json.dumps(document.warnings, ensure_ascii=False),
                ))
                db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?)", [
                    (analysis_id, document.id, chunk.id, index, chunk.model_dump_json())
                    for index, chunk in enumerate(document.chunks)
                ])
        return self.get(analysis_id)  # type: ignore[return-value]

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
            if row is None:
                return None
            analysis = self._analysis(row)
            documents = []
            for source in db.execute("SELECT * FROM documents WHERE analysis_id=? ORDER BY position", (analysis_id,)):
                document = {key: source[key] for key in ("id", "filename", "document_type", "side")}
                document["warnings"] = json.loads(source["warnings_json"])
                document["chunks"] = [json.loads(chunk["data_json"]) for chunk in db.execute(
                    "SELECT data_json FROM chunks WHERE analysis_id=? AND document_id=? ORDER BY position",
                    (analysis_id, source["id"]),
                )]
                documents.append(document)
            analysis["documents"] = documents
            return analysis

    def list(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,title,created_at,status,mode,stage,stage_label,error FROM analyses ORDER BY created_at DESC"
            )]

    def progress(self, analysis_id: str, stage: int, label: str) -> None:
        if stage not in range(8):
            raise ValueError("Invalid pipeline stage")
        with self.connect() as db:
            db.execute("UPDATE analyses SET status='running',stage=?,stage_label=? WHERE id=?",
                       (stage, label, analysis_id))

    def complete(self, analysis_id: str, result: AnalysisResult) -> None:
        # Revalidate even if a future pipeline implementation returns a dict.
        checked = AnalysisResult.model_validate(result)
        with self.connect() as db:
            db.execute("UPDATE analyses SET status='completed',stage=7,stage_label='Analysis complete',result_json=?,error=NULL WHERE id=?",
                       (checked.model_dump_json(), analysis_id))

    def fail(self, analysis_id: str, message: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE analyses SET status='failed',stage_label='Analysis failed',error=? WHERE id=?",
                       (message, analysis_id))

    def interrupt_stale(self) -> None:
        with self.connect() as db:
            db.execute("UPDATE analyses SET status='failed',stage_label='Analysis interrupted',error=? WHERE status IN ('queued','running')",
                       ("The server stopped before this analysis finished. Create a new analysis to retry.",))

    def delete(self, analysis_id: str) -> bool:
        with self.connect() as db:
            return db.execute("DELETE FROM analyses WHERE id=? AND status IN ('completed','failed')", (analysis_id,)).rowcount > 0

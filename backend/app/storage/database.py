from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.config import DB_PATH, ensure_runtime_dirs


MOLECULE_COLUMNS = (
    "id",
    "upload_id",
    "name",
    "smiles",
    "source_filename",
    "properties_json",
    "mol_weight",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
    "cluster_id",
)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_runtime_dirs()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS molecules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id TEXT NOT NULL,
                name TEXT,
                smiles TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                mol_weight REAL,
                logp REAL,
                hbd INTEGER,
                hba INTEGER,
                tpsa REAL,
                rotatable_bonds INTEGER,
                cluster_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(upload_id) REFERENCES uploads(id)
            )
            """
        )


def create_upload(upload_id: str, filename: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO uploads (id, filename) VALUES (?, ?)",
            (upload_id, filename),
        )


def insert_molecules(records: Iterable[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    with get_connection() as conn:
        for record in records:
            cursor = conn.execute(
                """
                INSERT INTO molecules (
                    upload_id, name, smiles, source_filename, properties_json,
                    mol_weight, logp, hbd, hba, tpsa, rotatable_bonds, cluster_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["upload_id"],
                    record.get("name"),
                    record["smiles"],
                    record["source_filename"],
                    json.dumps(record.get("properties", {})),
                    record.get("mol_weight"),
                    record.get("logp"),
                    record.get("hbd"),
                    record.get("hba"),
                    record.get("tpsa"),
                    record.get("rotatable_bonds"),
                    record.get("cluster_id"),
                ),
            )
            ids.append(int(cursor.lastrowid))
    return ids


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    data["properties"] = json.loads(data.pop("properties_json") or "{}")
    return data


def list_molecules(upload_id: str | None = None) -> list[dict[str, Any]]:
    query = f"SELECT {', '.join(MOLECULE_COLUMNS)} FROM molecules"
    params: tuple[Any, ...] = ()
    if upload_id:
        query += " WHERE upload_id = ?"
        params = (upload_id,)
    query += " ORDER BY id DESC"

    with get_connection() as conn:
        return [_row_to_dict(row) for row in conn.execute(query, params).fetchall()]


def get_molecule(molecule_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {', '.join(MOLECULE_COLUMNS)} FROM molecules WHERE id = ?",
            (molecule_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_molecules_by_ids(molecule_ids: list[int]) -> list[dict[str, Any]]:
    if not molecule_ids:
        return []
    placeholders = ",".join("?" for _ in molecule_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {', '.join(MOLECULE_COLUMNS)}
            FROM molecules
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            tuple(molecule_ids),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_cluster_ids(cluster_assignments: dict[int, int]) -> None:
    with get_connection() as conn:
        conn.executemany(
            "UPDATE molecules SET cluster_id = ? WHERE id = ?",
            [(cluster_id, molecule_id) for molecule_id, cluster_id in cluster_assignments.items()],
        )

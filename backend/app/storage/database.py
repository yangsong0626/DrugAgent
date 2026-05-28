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

UPLOAD_COLUMNS = (
    "id",
    "project_id",
    "filename",
    "created_at",
)

PROJECT_COLUMNS = (
    "id",
    "name",
    "description",
    "created_at",
)

DECISION_LOG_COLUMNS = (
    "id",
    "project_id",
    "entry_type",
    "title",
    "body_json",
    "created_at",
)

DESIGN_FEEDBACK_COLUMNS = (
    "id",
    "project_id",
    "smiles",
    "feedback",
    "reason",
    "design_json",
    "created_at",
    "updated_at",
)

COMMERCIAL_CATALOG_COLUMNS = (
    "id",
    "filename",
    "source_type",
    "compound_count",
    "created_at",
)

COMMERCIAL_COMPOUND_COLUMNS = (
    "id",
    "catalog_id",
    "vendor",
    "catalog_number",
    "name",
    "smiles",
    "properties_json",
    "mol_weight",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
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
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        upload_columns = {row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()}
        if "project_id" not in upload_columns:
            conn.execute("ALTER TABLE uploads ADD COLUMN project_id TEXT REFERENCES projects(id)")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS design_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                smiles TEXT NOT NULL,
                feedback TEXT NOT NULL,
                reason TEXT,
                design_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, smiles),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commercial_catalogs (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'commercial',
                compound_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        commercial_catalog_columns = {row["name"] for row in conn.execute("PRAGMA table_info(commercial_catalogs)").fetchall()}
        if "source_type" not in commercial_catalog_columns:
            conn.execute("ALTER TABLE commercial_catalogs ADD COLUMN source_type TEXT NOT NULL DEFAULT 'commercial'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commercial_compounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_id TEXT NOT NULL,
                vendor TEXT,
                catalog_number TEXT,
                name TEXT,
                smiles TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                mol_weight REAL,
                logp REAL,
                hbd INTEGER,
                hba INTEGER,
                tpsa REAL,
                rotatable_bonds INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(catalog_id) REFERENCES commercial_catalogs(id)
            )
            """
        )


def create_project(project_id: str, name: str, description: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
            (project_id, name, description),
        )


def get_project(project_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {', '.join(PROJECT_COLUMNS)} FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(f"SELECT {', '.join(PROJECT_COLUMNS)} FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def create_upload(upload_id: str, filename: str, project_id: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO uploads (id, project_id, filename) VALUES (?, ?, ?)",
            (upload_id, project_id, filename),
        )


def get_upload(upload_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {', '.join(UPLOAD_COLUMNS)} FROM uploads WHERE id = ?",
            (upload_id,),
        ).fetchone()
    return dict(row) if row else None


def list_uploads(project_id: str | None = None) -> list[dict[str, Any]]:
    query = f"SELECT {', '.join(UPLOAD_COLUMNS)} FROM uploads"
    params: tuple[Any, ...] = ()
    if project_id:
        query += " WHERE project_id = ?"
        params = (project_id,)
    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


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


def list_molecules_for_project(project_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {', '.join(f'm.{column}' for column in MOLECULE_COLUMNS)}
            FROM molecules m
            JOIN uploads u ON u.id = m.upload_id
            WHERE u.project_id = ?
            ORDER BY m.id DESC
            """,
            (project_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def create_decision_log(project_id: str, entry_type: str, title: str, body: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO decision_logs (project_id, entry_type, title, body_json)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, entry_type, title, json.dumps(body)),
        )
        row = conn.execute(
            f"SELECT {', '.join(DECISION_LOG_COLUMNS)} FROM decision_logs WHERE id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
    return _decision_row_to_dict(row)


def list_decision_logs(project_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {', '.join(DECISION_LOG_COLUMNS)}
            FROM decision_logs
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
    return [_decision_row_to_dict(row) for row in rows]


def upsert_design_feedback(
    project_id: str,
    smiles: str,
    feedback: str,
    design: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO design_feedback (project_id, smiles, feedback, reason, design_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, smiles) DO UPDATE SET
                feedback = excluded.feedback,
                reason = excluded.reason,
                design_json = excluded.design_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (project_id, smiles, feedback, reason, json.dumps(design)),
        )
        row = conn.execute(
            f"""
            SELECT {', '.join(DESIGN_FEEDBACK_COLUMNS)}
            FROM design_feedback
            WHERE project_id = ? AND smiles = ?
            """,
            (project_id, smiles),
        ).fetchone()
    return _feedback_row_to_dict(row)


def list_design_feedback(project_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {', '.join(DESIGN_FEEDBACK_COLUMNS)}
            FROM design_feedback
            WHERE project_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
    return [_feedback_row_to_dict(row) for row in rows]


def _feedback_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    data["design"] = json.loads(data.pop("design_json") or "{}")
    return data


def _decision_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    data["body"] = json.loads(data.pop("body_json") or "{}")
    return data


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


def create_commercial_catalog(catalog_id: str, filename: str, records: Iterable[dict[str, Any]], source_type: str = "commercial") -> dict[str, Any]:
    records = list(records)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO commercial_catalogs (id, filename, source_type, compound_count) VALUES (?, ?, ?, ?)",
            (catalog_id, filename, source_type, len(records)),
        )
        for record in records:
            conn.execute(
                """
                INSERT INTO commercial_compounds (
                    catalog_id, vendor, catalog_number, name, smiles, properties_json,
                    mol_weight, logp, hbd, hba, tpsa, rotatable_bonds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    catalog_id,
                    record.get("vendor"),
                    record.get("catalog_number"),
                    record.get("name"),
                    record["smiles"],
                    json.dumps(record.get("properties", {})),
                    record.get("mol_weight"),
                    record.get("logp"),
                    record.get("hbd"),
                    record.get("hba"),
                    record.get("tpsa"),
                    record.get("rotatable_bonds"),
                ),
            )
        row = conn.execute(
            f"SELECT {', '.join(COMMERCIAL_CATALOG_COLUMNS)} FROM commercial_catalogs WHERE id = ?",
            (catalog_id,),
        ).fetchone()
    return dict(row)


def list_commercial_catalogs() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(COMMERCIAL_CATALOG_COLUMNS)} FROM commercial_catalogs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_commercial_catalog(catalog_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {', '.join(COMMERCIAL_CATALOG_COLUMNS)} FROM commercial_catalogs WHERE id = ?",
            (catalog_id,),
        ).fetchone()
    return dict(row) if row else None


def list_commercial_compounds(catalog_id: str | None = None) -> list[dict[str, Any]]:
    query = f"SELECT {', '.join(COMMERCIAL_COMPOUND_COLUMNS)} FROM commercial_compounds"
    params: tuple[Any, ...] = ()
    if catalog_id:
        query += " WHERE catalog_id = ?"
        params = (catalog_id,)
    query += " ORDER BY id DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_commercial_row_to_dict(row) for row in rows]


def _commercial_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    data["properties"] = json.loads(data.pop("properties_json") or "{}")
    return data

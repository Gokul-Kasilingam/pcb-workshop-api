from __future__ import annotations

import csv
import os
import threading
from pathlib import Path
from typing import Dict, Iterable, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
LOCK = threading.RLock()

SCHEMAS: Dict[str, List[str]] = {
    "admin_credentials": ["username", "password_hash", "salt", "role", "created_at"],
    "participants": ["participant_id", "name", "email", "phone", "college", "department", "year", "created_at"],
    "teams": ["team_id", "team_name", "created_at"],
    "team_members": ["team_id", "participant_id", "member_role"],
    "quiz_questions": ["question_id", "question", "option_a", "option_b", "option_c", "option_d", "correct_option", "points"],
    "quiz_results": ["result_id", "team_id", "total_score", "max_score", "answers_json", "created_at"],
    "game_scores": ["score_id", "team_id", "game_name", "score", "max_score", "notes", "created_at"],
    "leaderboard": ["team_id", "team_name", "quiz_score", "game_score", "total_score", "updated_at"],
}

ID_FIELDS = {
    "participants": "participant_id",
    "teams": "team_id",
    "quiz_questions": "question_id",
    "quiz_results": "result_id",
    "game_scores": "score_id",
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for table, headers in SCHEMAS.items():
        path = table_path(table)
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()


def table_path(table: str) -> Path:
    if table not in SCHEMAS:
        raise ValueError(f"Unknown table: {table}")
    return DATA_DIR / f"{table}.csv"


def read_rows(table: str) -> List[dict]:
    ensure_data_dir()
    path = table_path(table)
    with LOCK:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [{key: (row.get(key, "") or "") for key in SCHEMAS[table]} for row in reader]


def write_rows(table: str, rows: Iterable[dict]) -> None:
    ensure_data_dir()
    path = table_path(table)
    headers = SCHEMAS[table]
    clean_rows = []
    for row in rows:
        clean_rows.append({key: str(row.get(key, "") or "") for key in headers})
    with LOCK:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(clean_rows)


def append_row(table: str, row: dict) -> dict:
    rows = read_rows(table)
    clean = {key: str(row.get(key, "") or "") for key in SCHEMAS[table]}
    rows.append(clean)
    write_rows(table, rows)
    return clean


def next_id(table: str) -> str:
    id_field = ID_FIELDS[table]
    rows = read_rows(table)
    max_id = 0
    for row in rows:
        value = str(row.get(id_field, "")).strip()
        if value.isdigit():
            max_id = max(max_id, int(value))
    return str(max_id + 1)


def replace_by_id(table: str, id_value: str, new_row: dict) -> bool:
    id_field = ID_FIELDS[table]
    rows = read_rows(table)
    found = False
    next_rows = []
    for row in rows:
        if str(row.get(id_field)) == str(id_value):
            merged = {**row, **new_row, id_field: str(id_value)}
            next_rows.append(merged)
            found = True
        else:
            next_rows.append(row)
    if found:
        write_rows(table, next_rows)
    return found


def delete_by_id(table: str, id_value: str) -> bool:
    id_field = ID_FIELDS[table]
    rows = read_rows(table)
    next_rows = [row for row in rows if str(row.get(id_field)) != str(id_value)]
    if len(next_rows) != len(rows):
        write_rows(table, next_rows)
        return True
    return False


def import_csv_rows(table: str, rows: Iterable[dict]) -> int:
    headers = SCHEMAS[table]
    clean_rows = []
    for row in rows:
        clean_rows.append({key: str(row.get(key, "") or "") for key in headers})
    write_rows(table, clean_rows)
    return len(clean_rows)

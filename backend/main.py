from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import random
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .csv_db import DATA_DIR, SCHEMAS, append_row, delete_by_id, ensure_data_dir, import_csv_rows, next_id, read_rows, table_path, write_rows

APP_TITLE = "PCB Workshop API"
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "change-this-secret-before-public-deploy")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "28800"))  # 8 hours
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "PCB@123")

app = FastAPI(title=APP_TITLE, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def password_hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def seed_admin_and_questions() -> None:
    ensure_data_dir()
    admins = read_rows("admin_credentials")
    if not admins:
        salt = secrets.token_hex(16)
        append_row(
            "admin_credentials",
            {
                "username": DEFAULT_ADMIN_USERNAME,
                "password_hash": password_hash(DEFAULT_ADMIN_PASSWORD, salt),
                "salt": salt,
                "role": "admin",
                "created_at": now_iso(),
            },
        )

    questions = read_rows("quiz_questions")
    if not questions:
        sample_questions = [
            {
                "question": "What does PCB stand for?",
                "option_a": "Printed Circuit Board",
                "option_b": "Power Control Box",
                "option_c": "Plastic Circuit Base",
                "option_d": "Printed Cable Board",
                "correct_option": "A",
                "points": "5",
            },
            {
                "question": "Which PCB part carries current and signals?",
                "option_a": "Silkscreen",
                "option_b": "Copper trace",
                "option_c": "Solder mask only",
                "option_d": "Board outline",
                "correct_option": "B",
                "points": "5",
            },
            {
                "question": "Why is a resistor used with an LED?",
                "option_a": "To increase weight",
                "option_b": "To limit current",
                "option_c": "To make PCB green",
                "option_d": "To create mounting holes",
                "correct_option": "B",
                "points": "5",
            },
            {
                "question": "What does a schematic mainly show?",
                "option_a": "Physical board color",
                "option_b": "Manufacturing price",
                "option_c": "What connects to what",
                "option_d": "Gift winners",
                "correct_option": "C",
                "points": "5",
            },
            {
                "question": "What is DRC in PCB design?",
                "option_a": "Design Rule Check",
                "option_b": "Direct Routing Cable",
                "option_c": "Digital Repair Circuit",
                "option_d": "Design Review Cost",
                "correct_option": "A",
                "points": "5",
            },
        ]
        for q in sample_questions:
            q["question_id"] = next_id("quiz_questions")
            append_row("quiz_questions", q)


@app.on_event("startup")
def startup() -> None:
    seed_admin_and_questions()
    rebuild_leaderboard()


def sign_payload(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    signature = hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired token")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


class LoginIn(BaseModel):
    username: str
    password: str


class ParticipantIn(BaseModel):
    name: str = Field(min_length=1)
    email: str = ""
    phone: str = ""
    college: str = ""
    department: str = ""
    year: str = ""


class TeamGenerateIn(BaseModel):
    team_size: int = Field(default=6, ge=2, le=15)
    team_prefix: str = "Team"
    shuffle_members: bool = True


class QuizQuestionIn(BaseModel):
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str = Field(pattern="^[ABCDabcd]$")
    points: int = Field(default=5, ge=1, le=100)


class QuizSubmitIn(BaseModel):
    team_id: str
    answers: Dict[str, str]


class GameScoreIn(BaseModel):
    team_id: str
    game_name: str
    score: int = Field(ge=0)
    max_score: int = Field(default=100, ge=1)
    notes: str = ""


class ChangePasswordIn(BaseModel):
    username: str
    current_password: str
    new_password: str = Field(min_length=6)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "data_dir": str(DATA_DIR)}


@app.post("/api/auth/login")
def login(data: LoginIn) -> dict:
    admins = read_rows("admin_credentials")
    for admin in admins:
        if admin.get("username") == data.username:
            salt = admin.get("salt", "")
            if password_hash(data.password, salt) == admin.get("password_hash"):
                payload = {
                    "sub": data.username,
                    "role": admin.get("role", "admin"),
                    "iat": int(time.time()),
                    "exp": int(time.time()) + TOKEN_TTL_SECONDS,
                }
                return {"token": sign_payload(payload), "username": data.username, "role": payload["role"]}
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/api/auth/me")
def me(admin: dict = Depends(require_admin)) -> dict:
    return {"username": admin.get("sub"), "role": admin.get("role")}


@app.post("/api/admin/change-password")
def change_password(data: ChangePasswordIn, admin: dict = Depends(require_admin)) -> dict:
    rows = read_rows("admin_credentials")
    changed = False
    for row in rows:
        if row.get("username") == data.username:
            if password_hash(data.current_password, row.get("salt", "")) != row.get("password_hash"):
                raise HTTPException(status_code=401, detail="Current password is wrong")
            salt = secrets.token_hex(16)
            row["salt"] = salt
            row["password_hash"] = password_hash(data.new_password, salt)
            row["role"] = row.get("role") or "admin"
            changed = True
            break
    if not changed:
        raise HTTPException(status_code=404, detail="Admin username not found")
    write_rows("admin_credentials", rows)
    return {"message": "Password changed successfully"}


@app.get("/api/dashboard/stats")
def dashboard_stats(admin: dict = Depends(require_admin)) -> dict:
    return {
        "participants": len(read_rows("participants")),
        "teams": len(read_rows("teams")),
        "quiz_questions": len(read_rows("quiz_questions")),
        "quiz_results": len(read_rows("quiz_results")),
        "game_scores": len(read_rows("game_scores")),
    }


@app.get("/api/participants")
def list_participants(admin: dict = Depends(require_admin)) -> List[dict]:
    return read_rows("participants")


@app.post("/api/participants")
def create_participant(data: ParticipantIn, admin: dict = Depends(require_admin)) -> dict:
    row = data.dict()
    row["participant_id"] = next_id("participants")
    row["created_at"] = now_iso()
    return append_row("participants", row)


@app.delete("/api/participants/{participant_id}")
def remove_participant(participant_id: str, admin: dict = Depends(require_admin)) -> dict:
    deleted = delete_by_id("participants", participant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Participant not found")
    # Remove from team_members too.
    team_members = [row for row in read_rows("team_members") if row.get("participant_id") != str(participant_id)]
    write_rows("team_members", team_members)
    rebuild_leaderboard()
    return {"message": "Participant deleted"}


@app.get("/api/teams")
def list_teams(admin: dict = Depends(require_admin)) -> List[dict]:
    return read_rows("teams")


@app.get("/api/team-members")
def list_team_members(admin: dict = Depends(require_admin)) -> List[dict]:
    participants = {row["participant_id"]: row for row in read_rows("participants")}
    teams = {row["team_id"]: row for row in read_rows("teams")}
    members = []
    for row in read_rows("team_members"):
        participant = participants.get(row.get("participant_id"), {})
        team = teams.get(row.get("team_id"), {})
        members.append({**row, "team_name": team.get("team_name", ""), "participant_name": participant.get("name", ""), "department": participant.get("department", ""), "year": participant.get("year", "")})
    return members


@app.post("/api/teams/generate")
def generate_teams(data: TeamGenerateIn, admin: dict = Depends(require_admin)) -> dict:
    participants = read_rows("participants")
    if not participants:
        raise HTTPException(status_code=400, detail="Add participants before generating teams")

    pool = participants[:]
    if data.shuffle_members:
        random.shuffle(pool)

    team_count = max(1, (len(pool) + data.team_size - 1) // data.team_size)
    teams = []
    members = []
    roles = ["Team Lead", "Schematic Engineer", "Component Engineer", "Layout Engineer", "Routing Engineer", "Quality Engineer", "Presenter"]

    for i in range(team_count):
        teams.append({"team_id": str(i + 1), "team_name": f"{data.team_prefix} {i + 1}", "created_at": now_iso()})

    for index, participant in enumerate(pool):
        team_id = str((index % team_count) + 1)
        member_count_in_team = len([m for m in members if m["team_id"] == team_id])
        role = roles[member_count_in_team % len(roles)]
        members.append({"team_id": team_id, "participant_id": participant["participant_id"], "member_role": role})

    write_rows("teams", teams)
    write_rows("team_members", members)
    rebuild_leaderboard()
    return {"message": "Teams generated", "team_count": team_count, "participant_count": len(pool)}


@app.delete("/api/teams/reset")
def reset_teams(admin: dict = Depends(require_admin)) -> dict:
    write_rows("teams", [])
    write_rows("team_members", [])
    write_rows("leaderboard", [])
    return {"message": "Teams reset"}


@app.get("/api/quiz/questions")
def get_quiz_questions(admin: dict = Depends(require_admin)) -> List[dict]:
    return read_rows("quiz_questions")


@app.post("/api/quiz/questions")
def add_quiz_question(data: QuizQuestionIn, admin: dict = Depends(require_admin)) -> dict:
    row = data.dict()
    row["question_id"] = next_id("quiz_questions")
    row["correct_option"] = row["correct_option"].upper()
    row["points"] = str(row["points"])
    return append_row("quiz_questions", row)


@app.delete("/api/quiz/questions/{question_id}")
def delete_quiz_question(question_id: str, admin: dict = Depends(require_admin)) -> dict:
    if not delete_by_id("quiz_questions", question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question deleted"}


@app.post("/api/quiz/submit")
def submit_quiz(data: QuizSubmitIn, admin: dict = Depends(require_admin)) -> dict:
    questions = read_rows("quiz_questions")
    teams = {row["team_id"] for row in read_rows("teams")}
    if data.team_id not in teams:
        raise HTTPException(status_code=400, detail="Invalid team_id")

    total = 0
    max_score = 0
    normalized_answers = {str(k): str(v).upper() for k, v in data.answers.items()}

    for q in questions:
        points = int(q.get("points") or 0)
        max_score += points
        if normalized_answers.get(q["question_id"]) == q.get("correct_option", "").upper():
            total += points

    row = {
        "result_id": next_id("quiz_results"),
        "team_id": data.team_id,
        "total_score": str(total),
        "max_score": str(max_score),
        "answers_json": json.dumps(normalized_answers, ensure_ascii=False),
        "created_at": now_iso(),
    }
    append_row("quiz_results", row)
    rebuild_leaderboard()
    return {"message": "Quiz submitted", "team_id": data.team_id, "total_score": total, "max_score": max_score}


@app.get("/api/quiz/results")
def list_quiz_results(admin: dict = Depends(require_admin)) -> List[dict]:
    return read_rows("quiz_results")


@app.post("/api/games/scores")
def add_game_score(data: GameScoreIn, admin: dict = Depends(require_admin)) -> dict:
    teams = {row["team_id"] for row in read_rows("teams")}
    if data.team_id not in teams:
        raise HTTPException(status_code=400, detail="Invalid team_id")
    row = data.dict()
    row["score_id"] = next_id("game_scores")
    row["created_at"] = now_iso()
    saved = append_row("game_scores", row)
    rebuild_leaderboard()
    return saved


@app.get("/api/games/scores")
def list_game_scores(admin: dict = Depends(require_admin)) -> List[dict]:
    return read_rows("game_scores")


@app.delete("/api/games/scores/{score_id}")
def delete_game_score(score_id: str, admin: dict = Depends(require_admin)) -> dict:
    if not delete_by_id("game_scores", score_id):
        raise HTTPException(status_code=404, detail="Score not found")
    rebuild_leaderboard()
    return {"message": "Game score deleted"}


@app.get("/api/leaderboard")
def get_leaderboard(admin: dict = Depends(require_admin)) -> List[dict]:
    rebuild_leaderboard()
    rows = read_rows("leaderboard")
    return sorted(rows, key=lambda row: int(row.get("total_score") or 0), reverse=True)


def int_value(value: str) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def rebuild_leaderboard() -> None:
    ensure_data_dir()
    teams = read_rows("teams")
    quiz_results = read_rows("quiz_results")
    game_scores = read_rows("game_scores")

    best_quiz_by_team: Dict[str, int] = {}
    for result in quiz_results:
        team_id = result.get("team_id", "")
        best_quiz_by_team[team_id] = max(best_quiz_by_team.get(team_id, 0), int_value(result.get("total_score", "0")))

    best_game_by_team_and_game: Dict[str, Dict[str, int]] = {}
    for score in game_scores:
        team_id = score.get("team_id", "")
        game_name = score.get("game_name", "Game")
        best_game_by_team_and_game.setdefault(team_id, {})[game_name] = max(
            best_game_by_team_and_game.setdefault(team_id, {}).get(game_name, 0),
            int_value(score.get("score", "0")),
        )

    rows = []
    for team in teams:
        team_id = team.get("team_id", "")
        quiz_score = best_quiz_by_team.get(team_id, 0)
        game_score = sum(best_game_by_team_and_game.get(team_id, {}).values())
        total_score = quiz_score + game_score
        rows.append(
            {
                "team_id": team_id,
                "team_name": team.get("team_name", ""),
                "quiz_score": str(quiz_score),
                "game_score": str(game_score),
                "total_score": str(total_score),
                "updated_at": now_iso(),
            }
        )
    write_rows("leaderboard", rows)


@app.get("/api/csv/tables")
def csv_tables(admin: dict = Depends(require_admin)) -> dict:
    return {"tables": list(SCHEMAS.keys())}


@app.get("/api/csv/{table_name}")
def download_csv(table_name: str, admin: dict = Depends(require_admin)):
    if table_name not in SCHEMAS:
        raise HTTPException(status_code=404, detail="CSV table not found")
    path = table_path(table_name)
    return FileResponse(path, media_type="text/csv", filename=f"{table_name}.csv")


@app.post("/api/csv/{table_name}/import")
async def upload_csv(table_name: str, file: UploadFile = File(...), admin: dict = Depends(require_admin)) -> dict:
    if table_name not in SCHEMAS:
        raise HTTPException(status_code=404, detail="CSV table not found")
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    count = import_csv_rows(table_name, reader)
    if table_name in {"teams", "quiz_results", "game_scores"}:
        rebuild_leaderboard()
    return {"message": "CSV imported", "table": table_name, "rows": count}


@app.get("/api/csv/export/all")
def download_all_csv(admin: dict = Depends(require_admin)):
    ensure_data_dir()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for table in SCHEMAS:
            path = table_path(table)
            zf.write(path, arcname=f"data/{table}.csv")
    memory.seek(0)
    headers = {"Content-Disposition": "attachment; filename=pcb_workshop_csv_database.zip"}
    return StreamingResponse(memory, media_type="application/zip", headers=headers)


# Serve frontend after all API routes.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

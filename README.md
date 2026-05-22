# PCB Workshop Registration + Teams + Quiz + Games API

This is a deployable version of the PCB workshop website.

It includes:

- Admin login handled by backend API
- Registration API
- Auto team formation API
- Quiz question and quiz submission API
- Game score API
- Live leaderboard API
- CSV database storage
- CSV import/export
- Static frontend served by FastAPI

## Default Admin Login

Username: `admin`  
Password: `PCB@123`

Change this before public deployment.

## Folder Structure

```text
pcb_workshop_api/
├── backend/
│   ├── main.py
│   ├── csv_db.py
│   └── data/
│       ├── admin_credentials.csv
│       ├── participants.csv
│       ├── teams.csv
│       ├── team_members.csv
│       ├── quiz_questions.csv
│       ├── quiz_results.csv
│       ├── game_scores.csv
│       └── leaderboard.csv
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
├── Procfile
├── render.yaml
└── .env.example
```

## Run Locally

```bash
cd pcb_workshop_api
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Deploy on Render

### Option 1: Using render.yaml

1. Push this folder to GitHub.
2. Open Render.
3. Create New Blueprint.
4. Connect your GitHub repo.
5. Render will read `render.yaml`.
6. Deploy.

### Option 2: Manual Render Web Service

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=PCB@123
TOKEN_SECRET=use-a-long-random-secret
DATA_DIR=/var/data
```

Important: Add a Render Persistent Disk and mount it at:

```text
/var/data
```

Without a persistent disk, the CSV database can reset after redeployment.

## Main API Endpoints

### Auth

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/admin/change-password
```

### Participants

```text
GET    /api/participants
POST   /api/participants
DELETE /api/participants/{participant_id}
```

### Teams

```text
GET    /api/teams
GET    /api/team-members
POST   /api/teams/generate
DELETE /api/teams/reset
```

### Quiz

```text
GET    /api/quiz/questions
POST   /api/quiz/questions
DELETE /api/quiz/questions/{question_id}
POST   /api/quiz/submit
GET    /api/quiz/results
```

### Games

```text
POST   /api/games/scores
GET    /api/games/scores
DELETE /api/games/scores/{score_id}
```

### Leaderboard

```text
GET /api/leaderboard
```

### CSV Database

```text
GET  /api/csv/tables
GET  /api/csv/{table_name}
POST /api/csv/{table_name}/import
GET  /api/csv/export/all
```

## CSV Database Tables

- `admin_credentials.csv`
- `participants.csv`
- `teams.csv`
- `team_members.csv`
- `quiz_questions.csv`
- `quiz_results.csv`
- `game_scores.csv`
- `leaderboard.csv`

## Important Security Note

This version is better than HTML-only login because credentials are handled on the backend.

For public deployment:

- Change the default password.
- Set a strong `TOKEN_SECRET`.
- Use HTTPS.
- Use Render persistent disk or migrate CSV to a proper database later.

## Suggested Workshop Use

1. Login as admin.
2. Register students.
3. Generate teams.
4. Run quiz during PPT or after schematic lab.
5. Add scores for games:
   - Schematic Detective
   - Placement Challenge
   - Routing Race
   - PCB Rescue Mission
6. Show leaderboard.
7. Export all CSV files at the end.

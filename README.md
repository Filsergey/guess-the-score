# Guess The Score

Backend for the football score prediction application «Угадай счёт».

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy 2 (async)
- API-Football
- Railway

## Local start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open:

- `GET /health` — application health check
- `GET /docs` — Swagger UI
- `GET /api/football/leagues` — test request to API-Football

## Environment variables

Copy `.env.example` to `.env` locally. Never commit real secrets.

Required for API-Football requests:

```env
API_FOOTBALL_KEY=your_key_here
```

For Railway, add secrets in the service Variables section instead of committing `.env`.

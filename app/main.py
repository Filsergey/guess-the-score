from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.providers.api_football import APIFootballProvider

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@app.get("/api/football/leagues")
async def football_leagues() -> dict:
    try:
        return await APIFootballProvider().get_leagues()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="API-Football request failed") from exc

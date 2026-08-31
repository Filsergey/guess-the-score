import httpx

from app.config import get_settings


class SStatsProvider:
    BASE_URL = "https://api.sstats.net"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.sstats_api_key:
            return {}
        return {"Authorization": f"ApiKey {self.settings.sstats_api_key}"}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            payload = response.json()

        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success", "200"}:
            message = payload.get("message") or "SStats returned an error"
            raise RuntimeError(f"SStats error: {message}")
        return payload

    async def _post(self, path: str, json: dict) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=json)
            response.raise_for_status()
            payload = response.json()

        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success", "200"}:
            message = payload.get("message") or "SStats returned an error"
            raise RuntimeError(f"SStats error: {message}")
        return payload

    async def get_leagues(self) -> dict:
        return await self._get("leagues")

    async def get_games(self, league_id: int, year: int) -> dict:
        return await self._get("games/list", {"LeagueId": league_id, "Year": year})

    async def query_games(self, league_id: int, year: int) -> dict:
        return await self._post(
            "games/query",
            {
                "Condition": f"LeagueId = {league_id} AND Year = {year}",
                "Fields": [
                    "Id",
                    "Date",
                    "LeagueId",
                    "LeagueName",
                    "CountryName",
                    "Year",
                    "Status",
                    "HomeTeamId",
                    "HomeTeamName",
                    "AwayTeamId",
                    "AwayTeamName",
                    "ScoreHome",
                    "ScoreAway",
                    "ScoreHomeFT",
                    "ScoreAwayFT",
                ],
                "Order": "Date ASC",
                "Limit": 1000,
                "Format": "json",
                "Timezone": 0,
            },
        )

    async def get_game(self, game_id: int) -> dict:
        return await self._get(f"games/{game_id}")

    async def get_teams(self, **params) -> dict:
        return await self._get("teams/list", params or None)

    async def get_team(self, team_id: int) -> dict:
        return await self._get(f"teams/{team_id}")

import httpx


class SStatsProvider:
    BASE_URL = "https://api.sstats.net"

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params)
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
            response = await client.post(url, json=json)
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

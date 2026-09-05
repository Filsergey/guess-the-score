import httpx

from app.config import get_settings


class APIFootballProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _format_api_errors(errors: object) -> str:
        if isinstance(errors, dict):
            return "; ".join(f"{key}: {value}" for key, value in errors.items())
        if isinstance(errors, list):
            return "; ".join(str(item) for item in errors)
        return str(errors)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.settings.api_football_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")

        headers = {"x-apisports-key": self.settings.api_football_key}
        url = f"{self.settings.api_football_base_url.rstrip('/')}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"API-Football error: {self._format_api_errors(errors)}")

        return payload

    async def get_leagues(self) -> dict:
        return await self._get("leagues")

    async def get_fixtures(self, league: int, season: int) -> dict:
        return await self._get("fixtures", {"league": league, "season": season})

    async def get_live_fixtures(self) -> dict:
        return await self._get("fixtures", {"live": "all"})

    async def get_teams(self, league: int, season: int) -> dict:
        """Fetch a whole competition's team catalogue in one API request."""
        return await self._get("teams", {"league": league, "season": season})

    async def search_teams(self, name: str) -> dict:
        """Search team metadata without a season restriction.

        Kept only as a last-resort metadata fallback. Bulk catalogue lookup is
        preferred because the free API-Football plan has a small daily quota.
        """
        return await self._get("teams", {"search": name})

    async def search_players(self, name: str, season: int = 2024) -> dict:
        """Resolve player profile metadata, including photo, by name."""
        return await self._get("players", {"search": name, "season": season})

    async def get_squad(self, team_id: int) -> dict:
        """Return the team's current registered squad in one request.

        This endpoint is preferred for the tournament player picker because it
        provides current player ids, positions and photo URLs without a season
        lookup and avoids ambiguous same-name search results.
        """
        return await self._get("players/squads", {"team": team_id})

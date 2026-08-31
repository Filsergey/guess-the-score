import httpx

from app.config import get_settings


class APIFootballProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.settings.api_football_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")

        headers = {"x-apisports-key": self.settings.api_football_key}
        url = f"{self.settings.api_football_base_url.rstrip('/')}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_leagues(self) -> dict:
        return await self._get("leagues")

    async def get_fixtures(self, league: int, season: int) -> dict:
        return await self._get("fixtures", {"league": league, "season": season})

    async def get_live_fixtures(self) -> dict:
        return await self._get("fixtures", {"live": "all"})

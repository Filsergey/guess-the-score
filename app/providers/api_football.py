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

    async def search_teams(self, name: str) -> dict:
        return await self._get("teams", {"search": name})

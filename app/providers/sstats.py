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
                    "Id", "FlashId", "SeasonUid", "Date", "LeagueId", "LeagueName",
                    "CountryName", "Year", "Status", "HomeTeamId", "HomeTeamName",
                    "AwayTeamId", "AwayTeamName", "ScoreHome", "ScoreAway",
                    "ScoreHomeFT", "ScoreAwayFT", "ScoreHomeHT", "ScoreAwayHT",
                    "ScoreHomeET", "ScoreAwayET", "ScoreHomePT", "ScoreAwayPT",
                    "VenueId", "VenueName", "VenueCity",
                ],
                "Order": "Date ASC",
                "Limit": 1000,
                "Format": "json",
                "Timezone": 0,
            },
        )

    async def query_game_details(self, game_id: int) -> dict:
        fields = [
            "Id", "FlashId", "SeasonUid", "Date", "LeagueId", "LeagueName", "Year", "Status",
            "HomeTeamId", "HomeTeamName", "AwayTeamId", "AwayTeamName",
            "HomeTeamCoachName", "AwayTeamCoachName",
            "ScoreHome", "ScoreAway", "ScoreHomeFT", "ScoreAwayFT", "ScoreHomeHT", "ScoreAwayHT",
            "ScoreHomeET", "ScoreAwayET", "ScoreHomePT", "ScoreAwayPT",
            "VenueId", "VenueName", "VenueAddress", "VenueCity",
            "Winner1", "WinnerX", "Winner2", "OddsXgHome", "OddsXgAway",
            "GlickoRatingHome", "GlickoRatingAway", "GlickoWinProbHome", "GlickoWinProbAway",
            "GlickoXgHome", "GlickoXgAway",
            "ShotsOnGoalHome", "ShotsOnGoalAway", "ShotsOffGoalHome", "ShotsOffGoalAway",
            "TotalShotsHome", "TotalShotsAway", "BlockedShotsHome", "BlockedShotsAway",
            "ShotsInsideBoxHome", "ShotsInsideBoxAway", "ShotsOutsideBoxHome", "ShotsOutsideBoxAway",
            "FoulsHome", "FoulsAway", "CornerKicksHome", "CornerKicksAway",
            "BallPossessionHome", "BallPossessionAway", "YellowCardsHome", "YellowCardsAway",
            "RedCardsHome", "RedCardsAway", "GoalkeeperSavesHome", "GoalkeeperSavesAway",
            "TotalPassesHome", "TotalPassesAway", "PassesAccurateHome", "PassesAccurateAway",
            "OffsidesHome", "OffsidesAway", "ExpectedGoalsHome", "ExpectedGoalsAway",
            "CalculatedXgHome", "CalculatedXgAway",
            "CoverageSeasonPlayers", "CoverageSeasonEvents", "CoverageSeasonLineups",
            "CoverageSeasonStatisticsFixtures", "CoverageSeasonStatisticsPlayers",
            "CoverageSeasonStandings", "CoverageSeasonOdds",
        ]
        return await self._post(
            "games/query",
            {"Condition": f"Id = {game_id}", "Fields": fields, "Limit": 1, "Format": "json", "Timezone": 0},
        )

    async def get_game(self, game_id: int) -> dict:
        return await self._get(f"games/{game_id}")

    async def get_glicko(self, game_id: int) -> dict:
        return await self._get(f"games/glicko/{game_id}")

    async def get_flashscore_game(self, flash_id: str) -> dict:
        return await self._get("Ls/GameInfo", {"id": flash_id})

    async def get_teams(self, **params) -> dict:
        return await self._get("teams/list", params or None)

    async def get_team(self, team_id: int) -> dict:
        return await self._get(f"teams/{team_id}")

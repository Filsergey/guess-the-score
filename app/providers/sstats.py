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
            raise RuntimeError(f"SStats error: {payload.get('message') or 'unknown error'}")
        return payload

    async def _post(self, path: str, json: dict) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=json)
            response.raise_for_status()
            payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success", "200"}:
            raise RuntimeError(f"SStats error: {payload.get('message') or 'unknown error'}")
        return payload

    async def get_leagues(self) -> dict:
        return await self._get("Leagues")

    async def get_games(
        self,
        league_id: int | None = None,
        year: int | None = None,
        season_uid: str | None = None,
        offset: int = 0,
        limit: int = 1000,
        live: bool | None = None,
        upcoming: bool | None = None,
        ended: bool | None = None,
    ) -> dict:
        params: dict[str, object] = {"Offset": offset, "Limit": limit}
        if league_id is not None: params["LeagueId"] = league_id
        if year is not None: params["Year"] = year
        if season_uid: params["SeasonUid"] = season_uid
        if live is not None: params["Live"] = live
        if upcoming is not None: params["Upcoming"] = upcoming
        if ended is not None: params["Ended"] = ended
        return await self._get("Games/list", params)

    async def get_all_games(self, league_id: int | None = None, year: int | None = None, season_uid: str | None = None) -> dict:
        """Read every page from the documented Games/list endpoint."""
        offset = 0
        limit = 1000
        rows: list[dict] = []
        first_payload: dict = {}
        while True:
            payload = await self.get_games(league_id=league_id, year=year, season_uid=season_uid, offset=offset, limit=limit)
            if not first_payload: first_payload = payload
            page = payload.get("data") or payload.get("response") or []
            if not isinstance(page, list): page = []
            rows.extend(page)
            total = payload.get("TotalCount") or payload.get("totalCount") or payload.get("count")
            if not page or len(page) < limit or (total is not None and len(rows) >= int(total)): break
            offset += len(page)
        result = dict(first_payload)
        result["data"] = rows
        result["count"] = len(rows)
        result["offset"] = 0
        return result

    async def query_games(self, league_id: int, year: int) -> dict:
        """Compatibility alias. Normal match synchronization uses GET Games/list."""
        return await self.get_all_games(league_id=league_id, year=year)

    async def query_game_details(self, game_id: int) -> dict:
        # Keep Games/query only for analytics fields not guaranteed by Games/{id}.
        fields = ["Id","SeasonUid","Date","LeagueId","LeagueName","Year","Status","HomeTeamId","HomeTeamName","AwayTeamId","AwayTeamName","HomeTeamCoachName","AwayTeamCoachName","ScoreHome","ScoreAway","ScoreHomeFT","ScoreAwayFT","ScoreHomeHT","ScoreAwayHT","ScoreHomeET","ScoreAwayET","ScoreHomePT","ScoreAwayPT","VenueId","VenueName","VenueAddress","VenueCity","Winner1","WinnerX","Winner2","OddsXgHome","OddsXgAway","GlickoRatingHome","GlickoRatingAway","GlickoWinProbHome","GlickoWinProbAway","GlickoXgHome","GlickoXgAway","ShotsOnGoalHome","ShotsOnGoalAway","ShotsOffGoalHome","ShotsOffGoalAway","TotalShotsHome","TotalShotsAway","BlockedShotsHome","BlockedShotsAway","ShotsInsideBoxHome","ShotsInsideBoxAway","ShotsOutsideBoxHome","ShotsOutsideBoxAway","FoulsHome","FoulsAway","CornerKicksHome","CornerKicksAway","BallPossessionHome","BallPossessionAway","YellowCardsHome","YellowCardsAway","RedCardsHome","RedCardsAway","GoalkeeperSavesHome","GoalkeeperSavesAway","TotalPassesHome","TotalPassesAway","PassesAccurateHome","PassesAccurateAway","OffsidesHome","OffsidesAway","ExpectedGoalsHome","ExpectedGoalsAway","CalculatedXgHome","CalculatedXgAway","CoverageSeasonPlayers","CoverageSeasonEvents","CoverageSeasonLineups","CoverageSeasonStatisticsFixtures","CoverageSeasonStatisticsPlayers","CoverageSeasonStandings","CoverageSeasonOdds"]
        return await self._post("Games/query", {"Condition": f"Id = {game_id}", "Fields": fields, "Limit": 1, "Format": "json", "Timezone": 0})

    async def get_game(self, game_id: int) -> dict:
        return await self._get(f"Games/{game_id}")

    async def get_glicko(self, game_id: int) -> dict:
        return await self._get(f"Games/glicko/{game_id}")

    async def get_standings(self, league_id: int | None = None, year: int | None = None, season_uid: str | None = None) -> dict:
        params: dict[str, object] = {}
        if season_uid: params["uid"] = season_uid
        else:
            if league_id is not None: params["leagueId"] = league_id
            if year is not None: params["year"] = year
        return await self._get("Seasons/standings", params)

    async def get_teams(self, name: str | None = None, country: str | None = None, offset: int = 0, limit: int = 1000) -> dict:
        params = {"Offset": offset, "Limit": limit}
        if name: params["Name"] = name
        if country: params["Country"] = country
        return await self._get("Teams/list", params)

    async def get_team(self, team_id: int) -> dict:
        return await self._get(f"Teams/{team_id}")

    async def find_players(self, name: str) -> dict:
        return await self._get("Players/find", {"name": name})

    async def get_players(self, team_id: int | None = None, offset: int = 0, limit: int = 1000) -> dict:
        params = {"Offset": offset, "Limit": limit}
        if team_id is not None: params["teamId"] = team_id
        return await self._get("Players/list", params)

    async def get_player(self, player_id: int) -> dict:
        return await self._get(f"Players/{player_id}")

    async def get_player_events(self, player_id: int, include_assists: bool = True) -> dict:
        return await self._get(f"Players/{player_id}/events", {"includeAssists": include_assists})

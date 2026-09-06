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

    async def _get(self, path: str, params: dict | None = None, timeout: float = 20.0) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success", "200"}:
            raise RuntimeError(f"SStats error: {payload.get('message') or 'unknown error'}")
        return payload

    async def _post(self, path: str, json: dict, timeout: float = 30.0) -> dict:
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=self._headers(), json=json)
            response.raise_for_status()
            payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status and status not in {"ok", "success", "200"}:
            raise RuntimeError(f"SStats error: {payload.get('message') or 'unknown error'}")
        return payload

    @staticmethod
    def _value(row: dict, *names: str):
        for name in names:
            if name in row:
                return row[name]
        return None

    @classmethod
    def _deep_value(cls, obj, *names):
        wanted={str(name).casefold() for name in names}
        if isinstance(obj,dict):
            for key,value in obj.items():
                if str(key).casefold() in wanted and value not in (None,""):
                    return value
            for value in obj.values():
                found=cls._deep_value(value,*names)
                if found not in (None,""):
                    return found
        elif isinstance(obj,list):
            for value in obj:
                found=cls._deep_value(value,*names)
                if found not in (None,""):
                    return found
        return None

    @staticmethod
    def _details_payload(payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"data": []}
        if "data" in payload or "response" in payload:
            return payload
        return {"data": payload}

    @staticmethod
    def _payload_object(payload:dict):
        if not isinstance(payload,dict):return {}
        data=payload.get("data",payload.get("response",payload))
        if isinstance(data,list):return data[0] if data and isinstance(data[0],dict) else {}
        return data if isinstance(data,dict) else {}

    @classmethod
    def _season_from_league_row(cls, row: dict, year: int) -> dict | None:
        containers = []
        for key in ("seasons", "Seasons", "season", "Season"):
            value = row.get(key)
            if isinstance(value, list): containers.extend(x for x in value if isinstance(x, dict))
            elif isinstance(value, dict): containers.append(value)
        for season in containers:
            season_year = cls._value(season, "year", "Year", "seasonYear", "SeasonYear")
            if season_year is not None:
                try:
                    if int(season_year) != int(year): continue
                except (TypeError, ValueError): continue
            uid = cls._value(season, "uid", "Uid", "UID", "seasonUid", "SeasonUid", "id", "Id")
            if uid: return {"uid": str(uid), "year": int(year), "raw": season}
        return None

    @classmethod
    def _normalize_game(cls, row: dict) -> dict:
        if not isinstance(row, dict): return row
        out = dict(row)
        home = cls._value(row, "homeTeam", "HomeTeam") or {}
        away = cls._value(row, "awayTeam", "AwayTeam") or {}
        season = cls._value(row, "season", "Season") or {}
        league = cls._value(season, "league", "League") or {}
        if isinstance(home, dict):
            out.setdefault("homeTeamId", cls._value(home, "id", "Id"))
            out.setdefault("homeTeamName", cls._value(home, "name", "Name"))
        if isinstance(away, dict):
            out.setdefault("awayTeamId", cls._value(away, "id", "Id"))
            out.setdefault("awayTeamName", cls._value(away, "name", "Name"))
        if isinstance(season, dict):
            out.setdefault("seasonUid", cls._value(season, "uid", "Uid"))
            out.setdefault("year", cls._value(season, "year", "Year"))
        if isinstance(league, dict):
            out.setdefault("leagueId", cls._value(league, "id", "Id"))
            out.setdefault("leagueName", cls._value(league, "name", "Name"))
            country = cls._value(league, "country", "Country") or {}
            if isinstance(country, dict): out.setdefault("countryName", cls._value(country, "name", "Name"))
        out.setdefault("scoreHome", cls._value(row, "homeResult", "HomeResult"))
        out.setdefault("scoreAway", cls._value(row, "awayResult", "AwayResult"))
        out.setdefault("scoreHomeFT", cls._value(row, "homeFTResult", "HomeFTResult"))
        out.setdefault("scoreAwayFT", cls._value(row, "awayFTResult", "AwayFTResult"))
        out.setdefault("scoreHomeHT", cls._value(row, "homeHTResult", "HomeHTResult"))
        out.setdefault("scoreAwayHT", cls._value(row, "awayHTResult", "AwayHTResult"))
        return out

    async def get_leagues(self) -> dict:
        return await self._get("Leagues")

    async def resolve_season_uid(self, league_id: int, year: int) -> dict | None:
        payload = await self.get_leagues(); rows = payload.get("data") or payload.get("response") or []
        if isinstance(rows, dict): rows = [rows]
        if not isinstance(rows, list): return None
        for row in rows:
            if not isinstance(row, dict): continue
            raw_id = self._value(row, "id", "Id", "leagueId", "LeagueId")
            try: same_league = raw_id is not None and int(raw_id) == int(league_id)
            except (TypeError, ValueError): same_league = False
            if not same_league: continue
            season = self._season_from_league_row(row, year)
            if season:
                season["league_id"] = int(league_id); season["league_name"] = self._value(row, "name", "Name", "leagueName", "LeagueName")
                return season
        return None

    async def get_games(self, league_id:int|None=None, year:int|None=None, season_uid:str|None=None, offset:int=0, limit:int=1000, live:bool|None=None, upcoming:bool|None=None, ended:bool|None=None) -> dict:
        params:dict[str,object]={"Offset":offset,"Limit":limit}
        if league_id is not None:params["LeagueId"]=league_id
        if year is not None:params["Year"]=year
        if season_uid:params["SeasonUid"]=season_uid
        if live is not None:params["Live"]=live
        if upcoming is not None:params["Upcoming"]=upcoming
        if ended is not None:params["Ended"]=ended
        return await self._get("Games/list",params)

    async def get_all_games(self, league_id:int|None=None, year:int|None=None, season_uid:str|None=None)->dict:
        offset=0;limit=1000;rows=[];first_payload={}
        while True:
            payload=await self.get_games(league_id=league_id,year=year,season_uid=season_uid,offset=offset,limit=limit)
            if not first_payload:first_payload=payload
            page=payload.get("data") or payload.get("response") or []
            if not isinstance(page,list):page=[]
            rows.extend(self._normalize_game(x) for x in page)
            total=payload.get("TotalCount") or payload.get("totalCount") or payload.get("count")
            if not page or len(page)<limit or (total is not None and len(rows)>=int(total)):break
            offset+=len(page)
        result=dict(first_payload);result["data"]=rows;result["count"]=len(rows);result["offset"]=0
        return result

    async def competition_games(self,league_id:int,year:int)->tuple[dict,dict]:
        season=await self.resolve_season_uid(league_id,year)
        if season and season.get("uid"):
            payload=await self.get_all_games(season_uid=season["uid"]);return payload,{"mode":"season_uid",**season}
        payload=await self.get_all_games(league_id=league_id,year=year);return payload,{"mode":"league_year","league_id":league_id,"year":year,"uid":None}

    async def query_games(self,league_id:int,year:int)->dict:
        payload,_=await self.competition_games(league_id,year);return payload

    async def query_game_details(self,game_id:int)->dict:
        fields=["Id","FlashId","SeasonUid","Date","LeagueId","LeagueName","Year","Status","HomeTeamId","HomeTeamName","AwayTeamId","AwayTeamName","HomeTeamCoachName","AwayTeamCoachName","ScoreHome","ScoreAway","ScoreHomeFT","ScoreAwayFT","ScoreHomeHT","ScoreAwayHT","ScoreHomeET","ScoreAwayET","ScoreHomePT","ScoreAwayPT","VenueId","VenueName","VenueAddress","VenueCity","Winner1","WinnerX","Winner2","GlickoRatingHome","GlickoRatingAway","GlickoWinProbHome","GlickoWinProbAway","GlickoXgHome","GlickoXgAway","ShotsOnGoalHome","ShotsOnGoalAway","ShotsOffGoalHome","ShotsOffGoalAway","TotalShotsHome","TotalShotsAway","BlockedShotsHome","BlockedShotsAway","ShotsInsideBoxHome","ShotsInsideBoxAway","ShotsOutsideBoxHome","ShotsOutsideBoxAway","FoulsHome","FoulsAway","CornerKicksHome","CornerKicksAway","BallPossessionHome","BallPossessionAway","YellowCardsHome","YellowCardsAway","RedCardsHome","RedCardsAway","GoalkeeperSavesHome","GoalkeeperSavesAway","TotalPassesHome","TotalPassesAway","PassesAccurateHome","PassesAccurateAway","OffsidesHome","OffsidesAway","ExpectedGoalsHome","ExpectedGoalsAway","CalculatedXgHome","CalculatedXgAway","CoverageSeasonPlayers","CoverageSeasonEvents","CoverageSeasonLineups","CoverageSeasonStatisticsFixtures","CoverageSeasonStatisticsPlayers","CoverageSeasonStandings","CoverageSeasonOdds"]
        payload=await self._post("Games/query",{"Condition":f"Id = {game_id}","Fields":fields,"Limit":1,"Format":"json","Timezone":0},timeout=2.5)
        return self._details_payload(payload)

    async def get_ls_game_info(self,flash_id:str)->dict:
        return self._details_payload(await self._get("Ls/GameInfo",{"id":str(flash_id)},timeout=2.5))

    async def get_game(self,game_id:int)->dict:
        return self._details_payload(await self._get(f"Games/{game_id}",timeout=2.0))

    async def get_game_full(self,game_id:int)->dict:
        primary={"data":[]};obj={}
        try:
            primary=await self.get_game(game_id);obj=self._payload_object(primary)
        except Exception:
            primary={"data":[]};obj={}
        flash_id=self._deep_value(obj,"flashId","FlashId","flashscoreId","FlashscoreId")
        if not flash_id:
            try:
                lookup=await self._post("Games/query",{"Condition":f"Id = {game_id}","Fields":["Id","FlashId"],"Limit":1,"Format":"json","Timezone":0},timeout=1.4)
                flash_id=self._deep_value(lookup,"flashId","FlashId")
            except Exception:
                flash_id=None
        if flash_id:
            try:
                ls=await self.get_ls_game_info(str(flash_id));ls_obj=self._payload_object(ls)
                if ls_obj:
                    enriched=dict(obj) if isinstance(obj,dict) else {}
                    enriched["_lsGameInfo"]=ls_obj
                    result=dict(primary);result["data"]=enriched
                    return result
            except Exception:
                pass
        return primary

    async def get_glicko(self,game_id:int)->dict:
        return self._details_payload(await self._get(f"Games/glicko/{game_id}",timeout=2.0))

    async def get_standings(self,league_id:int|None=None,year:int|None=None,season_uid:str|None=None)->dict:
        params={}
        if season_uid:params["uid"]=season_uid
        else:
            if league_id is not None:params["leagueId"]=league_id
            if year is not None:params["year"]=year
        return await self._get("Seasons/standings",params)
    async def get_teams(self,name:str|None=None,country:str|None=None,offset:int=0,limit:int=1000)->dict:
        params={"Offset":offset,"Limit":limit}
        if name:params["Name"]=name
        if country:params["Country"]=country
        return await self._get("Teams/list",params)
    async def get_team(self,team_id:int)->dict:return await self._get(f"Teams/{team_id}")
    async def find_players(self,name:str)->dict:return await self._get("Players/find",{"name":name})
    async def get_players(self,team_id:int|None=None,offset:int=0,limit:int=1000)->dict:
        params={"Offset":offset,"Limit":limit}
        if team_id is not None:params["teamId"]=team_id
        return await self._get("Players/list",params)
    async def get_player(self,player_id:int)->dict:return await self._get(f"Players/{player_id}")
    async def get_player_events(self,player_id:int,include_assists:bool=True)->dict:return await self._get(f"Players/{player_id}/events",{"includeAssists":include_assists})
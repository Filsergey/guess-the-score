import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

UEFA_STANDINGS_URL = "https://standings.uefa.com/v1/standings"
UEFA_SITE_BASE = "https://ru.uefa.com"
UEFA_COMPETITION_PATH = "uefachampionsleague"

@dataclass(slots=True)
class UEFATeam:
    id: int
    name: str
    name_ru: str | None
    country_code: str | None
    logo_url: str | None
    code: str | None = None
    international_name: str | None = None
    logo_small_url: str | None = None
    logo_medium_url: str | None = None
    logo_big_url: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

@dataclass(slots=True)
class UEFAPlayer:
    id: int
    name: str
    number: int | None
    nationality: str | None
    position: str | None
    photo_url: str | None
    profile_url: str | None

class UEFAProvider:
    """UEFA is the metadata catalogue; SStats remains the match/live provider."""
    def __init__(self) -> None:
        self.headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36","Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7"}

    async def competition_teams(self,competition_id:int=1,season_year:int=2027)->list[UEFATeam]:
        async with httpx.AsyncClient(timeout=25.0,follow_redirects=True,headers=self.headers) as client:
            response=await client.get(UEFA_STANDINGS_URL,params={"competitionId":competition_id,"seasonYear":season_year});response.raise_for_status();payload=response.json()
        teams={}
        groups=payload if isinstance(payload,list) else payload.get("standings",[]) if isinstance(payload,dict) else []
        for group in groups:
            candidates=[]
            if isinstance(group,dict):
                candidates.extend(group.get("items") or [])
                round_data=group.get("round") or {}
                if isinstance(round_data,dict):candidates.extend({"team":x} for x in (round_data.get("teams") or []) if isinstance(x,dict))
            for item in candidates:
                team=item.get("team") if isinstance(item,dict) else None
                if not isinstance(team,dict) or not team.get("id"):continue
                translations=team.get("translations") or {}
                display=(translations.get("displayName") or {}) if isinstance(translations,dict) else {}
                official=(translations.get("displayOfficialName") or {}) if isinstance(translations,dict) else {}
                short=(translations.get("shortName") or {}) if isinstance(translations,dict) else {}
                tid=int(team["id"]);ru=display.get("RU") or display.get("ru");international=team.get("internationalName") or display.get("EN") or display.get("en")
                aliases=[]
                for value in (international,team.get("teamCode"),team.get("code")):
                    if value:aliases.append(str(value))
                for bucket in (display,official,short):
                    if isinstance(bucket,dict):
                        for value in bucket.values():
                            if value:aliases.append(str(value))
                for key in ("displayName","displayOfficialName","shortName"):
                    value=team.get(key)
                    if isinstance(value,str) and value:aliases.append(value)
                aliases=tuple(dict.fromkeys(aliases))
                small=team.get("smallLogoUrl") or team.get("logoUrl");medium=team.get("mediumLogoUrl");big=team.get("bigLogoUrl")
                teams[tid]=UEFATeam(id=tid,name=str(ru or international or tid),name_ru=ru,country_code=team.get("countryCode") or team.get("country"),logo_url=medium or big or small,code=team.get("teamCode") or team.get("code"),international_name=international,logo_small_url=small,logo_medium_url=medium,logo_big_url=big,aliases=aliases)
        return list(teams.values())

    @staticmethod
    def _position_from_heading(value):
        return {"goalkeepers":"Goalkeeper","goalkeeper":"Goalkeeper","defenders":"Defender","defender":"Defender","midfielders":"Midfielder","midfielder":"Midfielder","forwards":"Attacker","forward":"Attacker","attackers":"Attacker","attacker":"Attacker","вратари":"Goalkeeper","вратарь":"Goalkeeper","защитники":"Defender","защитник":"Defender","полузащитники":"Midfielder","полузащитник":"Midfielder","нападающие":"Attacker","нападающий":"Attacker"}.get((value or "").strip().casefold())

    @staticmethod
    def parse_squad_html(html:str)->list[UEFAPlayer]:
        soup=BeautifulSoup(html,"html.parser");players={}
        for anchor in soup.select('a[href*="/clubs/players/"]'):
            href=str(anchor.get("href") or "");match=re.search(r"/players/(\d+)(?:--[^/?#]+)?/?",href)
            if not match:continue
            pid=int(match.group(1));avatar=anchor.select_one("pk-avatar") or anchor.select_one("img");name=avatar.get("alt") if avatar else None;photo=(avatar.get("src") or avatar.get("data-src")) if avatar else None
            if not name:
                primary=anchor.select_one('[slot="primary"]');name=primary.get_text(" ",strip=True) if primary else anchor.get("title")
            if not name:continue
            row=anchor.find_parent(attrs={"role":"row"}) or anchor.parent;number=nationality=position=None
            if row is not None:
                num=row.select_one(".squad--player-num")
                if num:
                    m=re.search(r"\d+",num.get_text(" ",strip=True));number=int(m.group()) if m else None
                country=row.select_one('[itemprop="country"]');nationality=country.get_text(" ",strip=True) or None if country else None
                table=row.find_parent("table") or row.find_parent("pk-table")
                if table:
                    heading=table.find_previous(["h2","h3","h4"]);position=UEFAProvider._position_from_heading(heading.get_text(" ",strip=True)) if heading else None
            if isinstance(photo,str) and photo.startswith("//"):photo="https:"+photo
            if isinstance(photo,str) and photo.startswith("/"):photo=UEFA_SITE_BASE+photo
            if href.startswith("/"):href=UEFA_SITE_BASE+href
            players[pid]=UEFAPlayer(pid,str(name).strip(),number,nationality,position,photo if isinstance(photo,str) else None,href or None)
        return list(players.values())

    async def squad(self,team_id:int)->tuple[list[UEFAPlayer],dict]:
        url=f"{UEFA_SITE_BASE}/{UEFA_COMPETITION_PATH}/clubs/{team_id}/squad/"
        async with httpx.AsyncClient(timeout=30.0,follow_redirects=True,headers=self.headers) as client:
            response=await client.get(url);response.raise_for_status();html=response.text
        players=self.parse_squad_html(html)
        return players,{"url":str(response.url),"status_code":response.status_code,"html_bytes":len(response.content),"players_found":len(players),"contains_squad_unavailable":"Official squad list not available yet" in html or "Официальный список состава пока недоступен" in html}

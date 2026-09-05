import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


UEFA_STANDINGS_URL = "https://standings.uefa.com/v1/standings"
UEFA_SITE_BASE = "https://www.uefa.com"
UEFA_COMPETITION_PATH = "uefachampionsleague"


@dataclass(slots=True)
class UEFATeam:
    id: int
    name: str
    name_ru: str | None
    country_code: str | None
    logo_url: str | None


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
    """Small client for public UEFA web data used by the app.

    Team metadata comes from standings.uefa.com. Squad data is parsed from the
    public UEFA club squad page. We persist the result locally, so normal app
    requests never need to scrape UEFA.
    """

    def __init__(self) -> None:
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def competition_teams(self, competition_id: int = 1, season_year: int = 2027) -> list[UEFATeam]:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=self.headers) as client:
            response = await client.get(
                UEFA_STANDINGS_URL,
                params={"competitionId": competition_id, "seasonYear": season_year},
            )
            response.raise_for_status()
            payload = response.json()

        teams: dict[int, UEFATeam] = {}
        for group in payload if isinstance(payload, list) else []:
            for item in group.get("items") or []:
                team = item.get("team") if isinstance(item, dict) else None
                if not isinstance(team, dict) or not team.get("id"):
                    continue
                translations = team.get("translations") or {}
                display_names = (translations.get("displayName") or {}) if isinstance(translations, dict) else {}
                team_id = int(team["id"])
                teams[team_id] = UEFATeam(
                    id=team_id,
                    name=str(team.get("internationalName") or display_names.get("EN") or team_id),
                    name_ru=display_names.get("RU"),
                    country_code=team.get("countryCode"),
                    logo_url=team.get("mediumLogoUrl") or team.get("logoUrl") or team.get("bigLogoUrl"),
                )
        return list(teams.values())

    @staticmethod
    def _position_from_heading(value: str | None) -> str | None:
        text = (value or "").strip().casefold()
        mapping = {
            "goalkeepers": "Goalkeeper",
            "goalkeeper": "Goalkeeper",
            "defenders": "Defender",
            "defender": "Defender",
            "midfielders": "Midfielder",
            "midfielder": "Midfielder",
            "forwards": "Attacker",
            "forward": "Attacker",
            "attackers": "Attacker",
            "attacker": "Attacker",
        }
        return mapping.get(text)

    @staticmethod
    def parse_squad_html(html: str) -> list[UEFAPlayer]:
        soup = BeautifulSoup(html, "html.parser")
        players: dict[int, UEFAPlayer] = {}

        # UEFA currently renders one squad table per position group. The exact
        # custom-element classes can change, so anchors containing /players/
        # are the stable primary selector.
        anchors = soup.select('a[href*="/clubs/players/"]')
        for anchor in anchors:
            href = str(anchor.get("href") or "")
            match = re.search(r"/players/(\d+)(?:--[^/?#]+)?/?", href)
            if not match:
                continue
            player_id = int(match.group(1))

            avatar = anchor.select_one("pk-avatar") or anchor.select_one("img")
            name = None
            photo_url = None
            if avatar is not None:
                name = avatar.get("alt")
                photo_url = avatar.get("src") or avatar.get("data-src")

            if not name:
                primary = anchor.select_one('[slot="primary"]')
                if primary:
                    name = primary.get_text(" ", strip=True)
            if not name:
                name = anchor.get("title")
            if not name:
                continue

            row = anchor.find_parent(attrs={"role": "row"}) or anchor.parent
            number = None
            nationality = None
            position = None
            if row is not None:
                number_el = row.select_one(".squad--player-num")
                if number_el:
                    number_match = re.search(r"\d+", number_el.get_text(" ", strip=True))
                    if number_match:
                        number = int(number_match.group())
                country_el = row.select_one('[itemprop="country"]')
                if country_el:
                    nationality = country_el.get_text(" ", strip=True) or None

                table = row.find_parent("table") or row.find_parent("pk-table")
                if table is not None:
                    heading = table.find_previous(["h2", "h3", "h4"])
                    if heading:
                        position = UEFAProvider._position_from_heading(heading.get_text(" ", strip=True))

            if isinstance(photo_url, str) and photo_url.startswith("//"):
                photo_url = "https:" + photo_url
            if isinstance(photo_url, str) and photo_url.startswith("/"):
                photo_url = UEFA_SITE_BASE + photo_url
            if href.startswith("/"):
                href = UEFA_SITE_BASE + href

            players[player_id] = UEFAPlayer(
                id=player_id,
                name=str(name).strip(),
                number=number,
                nationality=nationality,
                position=position,
                photo_url=photo_url if isinstance(photo_url, str) else None,
                profile_url=href or None,
            )

        return list(players.values())

    async def squad(self, team_id: int) -> tuple[list[UEFAPlayer], dict]:
        url = f"{UEFA_SITE_BASE}/{UEFA_COMPETITION_PATH}/clubs/{team_id}/squad/"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=self.headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        players = self.parse_squad_html(html)
        return players, {
            "url": str(response.url),
            "status_code": response.status_code,
            "html_bytes": len(response.content),
            "players_found": len(players),
            "contains_squad_unavailable": "Official squad list not available yet" in html,
        }

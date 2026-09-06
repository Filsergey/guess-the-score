"""Stable tournament branding helpers.

SStats league ids for the popular competitions currently match API-Football v3
competition ids. API-Sports exposes league logos from its public media CDN, so
we can use those assets without spending API request quota.
"""

API_SPORTS_LEAGUE_LOGO = "https://media.api-sports.io/football/leagues/{league_id}.png"

POPULAR_TOURNAMENTS = {
    2: {"name": "UEFA Champions League", "country": "World"},
    39: {"name": "Premier League", "country": "England"},
    140: {"name": "La Liga", "country": "Spain"},
    135: {"name": "Serie A", "country": "Italy"},
    78: {"name": "Bundesliga", "country": "Germany"},
}


def tournament_logo_url(provider_id: int | None, name: str | None = None, country: str | None = None) -> str | None:
    """Return a trusted logo URL only for the five explicitly mapped competitions."""
    if provider_id is None:
        return None
    try:
        provider_id = int(provider_id)
    except (TypeError, ValueError):
        return None
    expected = POPULAR_TOURNAMENTS.get(provider_id)
    if not expected:
        return None
    if name and expected["name"].casefold() != str(name).strip().casefold():
        # Champions League names can arrive with the UEFA prefix; other ids are exact.
        if provider_id != 2 or "champions league" not in str(name).casefold():
            return None
    if country and provider_id != 2 and expected["country"].casefold() != str(country).strip().casefold():
        return None
    return API_SPORTS_LEAGUE_LOGO.format(league_id=provider_id)

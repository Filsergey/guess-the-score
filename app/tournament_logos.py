"""Local tournament branding shared by the Mini App and the PWA."""

from pathlib import Path


TOURNAMENT_LOGO_DIR = Path(__file__).resolve().parent / "static" / "tournament-logos"

POPULAR_TOURNAMENTS = {
    2: {"name": "UEFA Champions League", "country": "World"},
    39: {"name": "Premier League", "country": "England"},
    61: {"name": "Ligue 1", "country": "France"},
    71: {"name": "Serie A", "country": "Brazil"},
    78: {"name": "Bundesliga", "country": "Germany"},
    88: {"name": "Eredivisie", "country": "Netherlands"},
    94: {"name": "Primeira Liga", "country": "Portugal"},
    135: {"name": "Serie A", "country": "Italy"},
    140: {"name": "La Liga", "country": "Spain"},
    235: {"name": "Russian Premier League", "country": "Russia"},
    262: {"name": "Liga MX", "country": "Mexico"},
}


def _normalized_provider_id(provider_id: int | str | None) -> int | None:
    if provider_id is None:
        return None
    try:
        return int(provider_id)
    except (TypeError, ValueError):
        return None


def local_tournament_logo_path(provider_id: int | str | None) -> Path | None:
    """Return a bundled PNG path for a configured competition."""
    logo_id = _normalized_provider_id(provider_id)
    if logo_id not in POPULAR_TOURNAMENTS:
        return None
    path = TOURNAMENT_LOGO_DIR / f"{logo_id}.png"
    return path if path.is_file() else None


def tournament_logo_url(
    provider_id: int | str | None,
    name: str | None = None,
    country: str | None = None,
) -> str | None:
    """Return the same-origin URL of a bundled tournament emblem.

    ``name`` and ``country`` remain accepted for callers using the old helper
    signature. The provider id is the stable mapping key.
    """
    del name, country
    logo_id = _normalized_provider_id(provider_id)
    if local_tournament_logo_path(logo_id) is None:
        return None
    return f"/static/tournament-logos/{logo_id}.png?v=2"

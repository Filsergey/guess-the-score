from datetime import date, datetime


# Official UEFA 2026/27 calendar. Keep provider-independent competition
# knowledge here rather than teaching every provider its own date mapping.
# Source: UEFA competition calendar / league-phase fixture schedule.
_UCL_2026_27_WINDOWS: tuple[tuple[date, date, str, int | None], ...] = (
    (date(2026, 9, 8), date(2026, 9, 10), "league_phase", 1),
    (date(2026, 10, 13), date(2026, 10, 14), "league_phase", 2),
    (date(2026, 10, 20), date(2026, 10, 21), "league_phase", 3),
    (date(2026, 11, 3), date(2026, 11, 4), "league_phase", 4),
    (date(2026, 11, 24), date(2026, 11, 25), "league_phase", 5),
    (date(2026, 12, 8), date(2026, 12, 9), "league_phase", 6),
    (date(2027, 1, 19), date(2027, 1, 20), "league_phase", 7),
    (date(2027, 1, 27), date(2027, 1, 27), "league_phase", 8),
    (date(2027, 2, 16), date(2027, 2, 17), "knockout_playoff", 1),
    (date(2027, 2, 23), date(2027, 2, 24), "knockout_playoff", 2),
    (date(2027, 3, 9), date(2027, 3, 10), "round_of_16", 1),
    (date(2027, 3, 16), date(2027, 3, 17), "round_of_16", 2),
    (date(2027, 4, 6), date(2027, 4, 7), "quarter_final", 1),
    (date(2027, 4, 13), date(2027, 4, 14), "quarter_final", 2),
    (date(2027, 4, 27), date(2027, 4, 28), "semi_final", 1),
    (date(2027, 5, 4), date(2027, 5, 5), "semi_final", 2),
    (date(2027, 6, 5), date(2027, 6, 5), "final", None),
)

_STAGE_LABELS = {
    "league_phase": "League phase",
    "knockout_playoff": "Knockout phase play-offs",
    "round_of_16": "Round of 16",
    "quarter_final": "Quarter-finals",
    "semi_final": "Semi-finals",
    "final": "Final",
}


def classify_ucl_round(season: int, kickoff_at: datetime) -> dict | None:
    """Classify a UCL fixture using official competition dates.

    At the moment only the 2026/27 season is encoded because that is the live
    season used by the application. Qualifying rounds are intentionally left
    unclassified until their round data is sourced explicitly.
    """
    if season != 2026:
        return None

    fixture_date = kickoff_at.date()
    for start, end, stage, matchday in _UCL_2026_27_WINDOWS:
        if start <= fixture_date <= end:
            label = _STAGE_LABELS[stage]
            if stage == "league_phase":
                round_label = f"{label} - Matchday {matchday}"
            elif matchday is not None:
                round_label = f"{label} - Leg {matchday}"
            else:
                round_label = label
            return {
                "stage": stage,
                "stage_label": label,
                "matchday": matchday if stage == "league_phase" else None,
                "leg": matchday if stage != "league_phase" else None,
                "round_label": round_label,
            }
    return None

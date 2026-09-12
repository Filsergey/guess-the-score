from pathlib import Path

from app.nav_icon_assets import ensure_nav_icons

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Generate crisp vector navigation masks before app.main mounts /static.
ensure_nav_icons(STATIC_DIR)

# The iOS/PWA browser can retain an earlier 404 for generated icon URLs and an old
# copy of menu-view.css. Inject a cache-busted inline override into index.html at
# process start so the root no-cache response always points at fresh icon URLs.
index_path = STATIC_DIR / "index.html"
marker = "gts-nav-icons-inline-v6"
try:
    html = index_path.read_text(encoding="utf-8")
    if marker not in html:
        css = f'''<style id="{marker}">
.nav{{padding:5px 4px calc(5px + env(safe-area-inset-bottom))!important}}
.nav button{{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:1px!important;min-width:0!important;padding:3px 2px!important;line-height:1.05!important}}
.nav button::before{{content:""!important;display:block!important;width:23px!important;height:23px!important;flex:0 0 23px!important;background:var(--gts-accent,#268fff)!important;-webkit-mask-position:center!important;mask-position:center!important;-webkit-mask-repeat:no-repeat!important;mask-repeat:no-repeat!important;-webkit-mask-size:contain!important;mask-size:contain!important;opacity:.62!important;filter:none!important;transition:opacity .16s ease,filter .16s ease,transform .16s ease!important}}
.nav button.active{{color:var(--gts-accent,#58aaff)!important}}
.nav button.active::before{{opacity:1!important;filter:drop-shadow(0 0 1.5px rgba(var(--gts-accent-rgb,38,143,255),.62))!important;transform:translateY(-1px)!important}}
#navHome::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/home.svg?v=6')!important;mask-image:url('/static/nav-icons/home.svg?v=6')!important}}
#navMatches::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/matches.svg?v=6')!important;mask-image:url('/static/nav-icons/matches.svg?v=6')!important}}
#navLeagues::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/leagues.svg?v=6')!important;mask-image:url('/static/nav-icons/leagues.svg?v=6')!important}}
#navTable::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/table.svg?v=6')!important;mask-image:url('/static/nav-icons/table.svg?v=6')!important}}
#navMenu::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/settings.svg?v=6')!important;mask-image:url('/static/nav-icons/settings.svg?v=6')!important}}
#navMenu.active::after{{color:var(--gts-accent,#58aaff)!important}}
</style>'''
        index_path.write_text(html.replace("</head>", css + "</head>"), encoding="utf-8")
except Exception:
    pass

usage_script_marker = "gts-admin-openai-usage-v1"
try:
    html = index_path.read_text(encoding="utf-8")
    if usage_script_marker not in html:
        script = (
            f'<script id="{usage_script_marker}" '
            'src="/static/admin-openai-usage.js?v=1" '
            'data-gts-admin-openai-usage="1"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

usage_nav_fix_marker = "gts-admin-openai-nav-fix-v1"
try:
    html = index_path.read_text(encoding="utf-8")
    if usage_nav_fix_marker not in html:
        script = (
            f'<script id="{usage_nav_fix_marker}" '
            'src="/static/admin-openai-nav-fix.js?v=1"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

trace_script_marker = "gts-admin-openai-trace-v1"
try:
    html = index_path.read_text(encoding="utf-8")
    if trace_script_marker not in html:
        script = (
            f'<script id="{trace_script_marker}" '
            'src="/static/admin-openai-trace.js?v=1" '
            'data-gts-admin-openai-trace="1"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

# Rich Oracle presentation is injected from the no-cache root. It installs after
# DOMContentLoaded so it safely overrides the older bundled openOracle renderer.
explanation_view_marker = "gts-oracle-analysis-view-v3"
try:
    html = index_path.read_text(encoding="utf-8")
    if explanation_view_marker not in html:
        script = (
            f'<script id="{explanation_view_marker}" '
            'src="/static/oracle-analysis-view-v2.js?v=3" '
            'data-gts-oracle-analysis-view="3"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

# Fair tournament-prediction flow: the form stays open until the Round of 16,
# a prediction becomes immutable after its first save, and other users' picks are
# revealed only after the viewer has committed their own prediction.
tournament_prediction_policy_marker = "gts-tournament-prediction-policy-v2"
try:
    html = index_path.read_text(encoding="utf-8")
    if tournament_prediction_policy_marker not in html:
        script = (
            f'<script id="{tournament_prediction_policy_marker}" '
            'src="/static/tournament-prediction-policy-v2.js?v=1" '
            'data-gts-tournament-prediction-policy="2"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

match_detail_close_marker = "gts-match-detail-close-v6"
try:
    html = index_path.read_text(encoding="utf-8")
    if match_detail_close_marker not in html:
        script = (
            f'<script id="{match_detail_close_marker}" '
            'src="/static/match-detail-close.js?v=6" '
            'data-gts-match-detail-close="6"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

tournament_standings_refresh_marker = "gts-tournament-standings-live-refresh-v1"
try:
    html = index_path.read_text(encoding="utf-8")
    if tournament_standings_refresh_marker not in html:
        script = (
            f'<script id="{tournament_standings_refresh_marker}" '
            'src="/static/tournament-standings-live-refresh.js?v=1" '
            'data-gts-tournament-standings-live-refresh="1"></script>'
        )
        index_path.write_text(html.replace("</body>", script + "</body>"), encoding="utf-8")
except Exception:
    pass

from app.openai_usage import admin_router as _openai_admin_router
from app.openai_usage import install_openai_usage_tracking
from app.oracle import router as _oracle_router
from app.oracle_bookmaker_panel import install_bookmaker_panel
from app.oracle_enrichment import install_oracle_enrichment
from app.oracle_explanations import install_oracle_explanations
from app.oracle_h2h import install_oracle_h2h
from app.oracle_h2h_flashscore import install_oracle_h2h_flashscore
from app.oracle_h2h_flashscore_parser import install_flashscore_h2h_parser_patch
from app.oracle_h2h_verified import install_oracle_h2h_verified
from app.oracle_openai_structured import install_structured_oracle_openai
from app.oracle_recent_matches import install_oracle_recent_matches
from app.oracle_usage_trace import activity_router as _oracle_activity_router
from app.oracle_usage_trace import install_oracle_usage_trace
from app.services.oracle_events import install_oracle_event_hooks
from app.tournament_prediction_policy import install_tournament_prediction_policy
from app.notification_membership_scope import install_notification_membership_scope

_oracle_router.include_router(_openai_admin_router)
_oracle_router.include_router(_oracle_activity_router)
install_openai_usage_tracking()
install_oracle_enrichment()
# Fill concrete recent fixtures from SStats before the stable bookmaker wrapper
# computes the final analytical context hash.
install_oracle_recent_matches()
install_bookmaker_panel()
# Keep full H2H rows for the UI, but send only recency-weighted aggregates to OpenAI.
install_oracle_h2h()
# The main SStats game table can omit old meetings; use the documented Flashscore
# BothTeams endpoint only when the weighted H2H layer still has fewer than 5 rows.
install_oracle_h2h_flashscore()
# LS responses can wrap H2H events several levels deep; flatten only match-like
# objects and avoid the unreliable current-game FlashId heuristic.
install_flashscore_h2h_parser_patch()
# When upstream providers genuinely have no historical H2H, use a deliberately
# small registry of separately verified authoritative competition records.
install_oracle_h2h_verified()
install_structured_oracle_openai()
install_oracle_explanations()
install_oracle_usage_trace()
install_oracle_event_hooks()
install_tournament_prediction_policy()
install_notification_membership_scope()

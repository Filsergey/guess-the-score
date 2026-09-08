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
    # Navigation remains usable even if the visual hotfix cannot be injected.
    pass

# Load the admin-only OpenAI usage dashboard from the no-cache root document so
# PWA/browser caches cannot keep an older menu without the new tab.
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

# Add a separate trace overlay so admins can see WHY an OpenAI call happened,
# including cache hits that cost $0, without changing the existing cost dashboard.
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

# Register admin usage endpoints, richer prediction signals and real OpenAI
# token/cost accounting before event-driven Oracle initialization starts.
from app.openai_usage import admin_router as _openai_admin_router
from app.openai_usage import install_openai_usage_tracking
from app.oracle import router as _oracle_router
from app.oracle_enrichment import install_oracle_enrichment
from app.oracle_openai_structured import install_structured_oracle_openai
from app.oracle_usage_trace import activity_router as _oracle_activity_router
from app.oracle_usage_trace import install_oracle_usage_trace
from app.services.oracle_events import install_oracle_event_hooks

_oracle_router.include_router(_openai_admin_router)
_oracle_router.include_router(_oracle_activity_router)
install_openai_usage_tracking()
install_oracle_enrichment()
install_structured_oracle_openai()
install_oracle_usage_trace()
install_oracle_event_hooks()

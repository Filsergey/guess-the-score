from pathlib import Path

from app.nav_icon_assets import ensure_nav_icons

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Generate navigation WebP assets before app.main mounts /static.
ensure_nav_icons(STATIC_DIR)

# The iOS/PWA browser can retain an earlier 404 for generated icon URLs and an old
# copy of menu-view.css. Inject a tiny cache-busted inline override into index.html
# at process start so the root no-cache response always points at fresh icon URLs.
index_path = STATIC_DIR / "index.html"
marker = "gts-nav-icons-inline-v3"
try:
    html = index_path.read_text(encoding="utf-8")
    if marker not in html:
        css = f'''<style id="{marker}">
.nav button{{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:3px!important;min-width:0!important}}
.nav button::before{{content:""!important;display:block!important;width:30px!important;height:30px!important;flex:0 0 30px!important;background-position:center!important;background-repeat:no-repeat!important;background-size:contain!important;opacity:.50!important;filter:saturate(.55) brightness(.88)!important;transition:opacity .16s ease,filter .16s ease,transform .16s ease!important}}
.nav button.active::before{{opacity:1!important;filter:saturate(1.18) brightness(1.12) drop-shadow(0 0 6px rgba(80,224,255,.72))!important;transform:translateY(-1px) scale(1.05)!important}}
#navHome::before{{background-image:url('/static/nav-icons/home.webp?v=3')!important}}
#navMatches::before{{background-image:url('/static/nav-icons/matches.webp?v=3')!important}}
#navLeagues::before{{background-image:url('/static/nav-icons/leagues.webp?v=3')!important}}
#navTable::before{{background-image:url('/static/nav-icons/table.webp?v=3')!important}}
#navMenu::before{{background-image:url('/static/nav-icons/settings.webp?v=3')!important}}
</style>'''
        index_path.write_text(html.replace("</head>", css + "</head>"), encoding="utf-8")
except Exception:
    # Navigation remains usable even if the visual hotfix cannot be injected.
    pass

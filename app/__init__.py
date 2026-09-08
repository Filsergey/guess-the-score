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

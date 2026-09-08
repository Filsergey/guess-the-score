from pathlib import Path

from app.nav_icon_assets import ensure_nav_icons

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Generate navigation WebP assets before app.main mounts /static.
ensure_nav_icons(STATIC_DIR)

# The iOS/PWA browser can retain an earlier 404 for generated icon URLs and an old
# copy of menu-view.css. Inject a cache-busted inline override into index.html at
# process start so the root no-cache response always points at fresh icon URLs.
index_path = STATIC_DIR / "index.html"
marker = "gts-nav-icons-inline-v5"
try:
    html = index_path.read_text(encoding="utf-8")
    if marker not in html:
        css = f'''<style id="{marker}">
.nav{{padding:5px 4px calc(5px + env(safe-area-inset-bottom))!important}}
.nav button{{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:1px!important;min-width:0!important;padding:3px 2px!important;line-height:1.05!important}}
.nav button::before{{content:""!important;display:block!important;width:22px!important;height:22px!important;flex:0 0 22px!important;background:var(--gts-accent,#268fff)!important;-webkit-mask-position:center!important;mask-position:center!important;-webkit-mask-repeat:no-repeat!important;mask-repeat:no-repeat!important;-webkit-mask-size:contain!important;mask-size:contain!important;opacity:.38!important;filter:none!important;transition:opacity .16s ease,filter .16s ease,transform .16s ease!important}}
.nav button.active{{color:var(--gts-accent,#58aaff)!important}}
.nav button.active::before{{opacity:1!important;filter:drop-shadow(0 0 5px rgba(var(--gts-accent-rgb,38,143,255),.72))!important;transform:translateY(-1px) scale(1.04)!important}}
#navHome::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/home.webp?v=5')!important;mask-image:url('/static/nav-icons/home.webp?v=5')!important}}
#navMatches::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/matches.webp?v=5')!important;mask-image:url('/static/nav-icons/matches.webp?v=5')!important}}
#navLeagues::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/leagues.webp?v=5')!important;mask-image:url('/static/nav-icons/leagues.webp?v=5')!important}}
#navTable::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/table.webp?v=5')!important;mask-image:url('/static/nav-icons/table.webp?v=5')!important}}
#navMenu::before{{background-image:none!important;-webkit-mask-image:url('/static/nav-icons/settings.webp?v=5')!important;mask-image:url('/static/nav-icons/settings.webp?v=5')!important}}
#navMenu.active::after{{color:var(--gts-accent,#58aaff)!important}}
</style>'''
        index_path.write_text(html.replace("</head>", css + "</head>"), encoding="utf-8")
except Exception:
    # Navigation remains usable even if the visual hotfix cannot be injected.
    pass

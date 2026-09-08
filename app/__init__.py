from pathlib import Path

from app.nav_icon_assets import ensure_nav_icons

# Generate the navigation WebP files before app.main mounts /static.
ensure_nav_icons(Path(__file__).resolve().parent / "static")

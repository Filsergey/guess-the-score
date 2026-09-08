from __future__ import annotations

from pathlib import Path


def ensure_nav_icons(static_dir: Path) -> None:
    """Create crisp vector masks for the bottom navigation.

    The previous WebP assets had several Gaussian-blur layers baked into their
    alpha channel. Because the files are used as CSS masks, that blur also made
    the actual icon silhouette fuzzy at the 22px navigation size. SVG keeps the
    edges sharp on both Retina iPhones and desktop browsers.
    """

    target = static_dir / "nav-icons"
    target.mkdir(parents=True, exist_ok=True)

    def svg(body: str) -> str:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
            'fill="none" stroke="#fff" stroke-linecap="round" '
            'stroke-linejoin="round">'
            f"{body}</svg>"
        )

    icons = {
        "home": svg(
            '<path d="M24 62 64 27l40 35" stroke-width="10"/>'
            '<path d="M33 58v45h21V78h20v25h21V58" stroke-width="10"/>'
        ),
        "matches": svg(
            '<circle cx="64" cy="64" r="39" stroke-width="8"/>'
            '<path d="M64 47 80 58 74 77H54L48 58Z" stroke-width="6"/>'
            '<path d="M64 47V29M80 58l18-5M74 77l11 16M54 77 43 16M48 58l-18-5" '
            'stroke-width="5"/>'
        ),
        "leagues": svg(
            '<path d="M41 28h46v25c0 18-10 29-23 29S41 71 41 53Z" stroke-width="8"/>'
            '<path d="M41 36H24v10c0 14 8 23 22 23M87 36h17v10c0 14-8 23-22 23" '
            'stroke-width="8"/>'
            '<path d="M64 82v18M48 101h32M39 111h50" stroke-width="8"/>'
        ),
        "table": svg(
            '<rect x="22" y="75" width="16" height="28" rx="4" stroke-width="7"/>'
            '<rect x="45" y="58" width="16" height="45" rx="4" stroke-width="7"/>'
            '<rect x="68" y="34" width="16" height="69" rx="4" stroke-width="7"/>'
            '<rect x="91" y="62" width="16" height="41" rx="4" stroke-width="7"/>'
        ),
        "settings": svg(
            '<circle cx="64" cy="64" r="20" stroke-width="8"/>'
            '<circle cx="64" cy="64" r="7" stroke-width="6"/>'
            '<path d="M64 17v17M64 94v17M17 64h17M94 64h17M31 31l12 12M85 85l12 12'
            'M97 31 85 43M43 85 31 97" stroke-width="10"/>'
        ),
    }

    for name, content in icons.items():
        path = target / f"{name}.svg"
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")

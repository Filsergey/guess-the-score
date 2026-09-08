from __future__ import annotations

from pathlib import Path


def ensure_nav_icons(static_dir: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return

    target = static_dir / "nav-icons"
    target.mkdir(parents=True, exist_ok=True)

    size = 128
    cyan = (94, 245, 255, 255)
    blue = (27, 118, 255, 255)

    def render(name: str, draw_shape) -> None:
        path = target / f"{name}.webp"
        if path.exists() and path.stat().st_size > 1000:
            return
        core = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(core)
        draw_shape(d, cyan)
        glow1 = core.filter(ImageFilter.GaussianBlur(11))
        glow2 = core.filter(ImageFilter.GaussianBlur(5))
        halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        draw_shape(hd, blue)
        halo = halo.filter(ImageFilter.GaussianBlur(16))
        out = Image.alpha_composite(halo, glow1)
        out = Image.alpha_composite(out, glow2)
        out = Image.alpha_composite(out, core)
        out.save(path, "WEBP", lossless=True, method=6)

    def home(d, c):
        d.line([(24, 62), (64, 27), (104, 62)], fill=c, width=10, joint="curve")
        d.line([(33, 58), (33, 103), (54, 103), (54, 78), (74, 78), (74, 103), (95, 103), (95, 58)], fill=c, width=10, joint="curve")

    def ball(d, c):
        d.ellipse((25, 25, 103, 103), outline=c, width=8)
        d.regular_polygon((64, 64, 17), n_sides=5, rotation=-18, outline=c, width=6)
        pts = [(64, 47), (42, 42), (31, 61), (39, 84), (64, 91), (89, 84), (97, 61), (86, 42)]
        for p in pts:
            d.line([(64, 64), p], fill=c, width=5)

    def trophy(d, c):
        d.rounded_rectangle((40, 27, 88, 69), radius=10, outline=c, width=8)
        d.arc((17, 31, 51, 69), 80, 280, fill=c, width=8)
        d.arc((77, 31, 111, 69), -100, 100, fill=c, width=8)
        d.line([(64, 69), (64, 90)], fill=c, width=8)
        d.line([(49, 92), (79, 92)], fill=c, width=8)
        d.line([(40, 103), (88, 103)], fill=c, width=8)

    def table(d, c):
        bars = [(22, 75, 38, 103), (45, 58, 61, 103), (68, 34, 84, 103), (91, 62, 107, 103)]
        for box in bars:
            d.rounded_rectangle(box, radius=5, outline=c, width=7)

    def settings(d, c):
        d.ellipse((43, 43, 85, 85), outline=c, width=8)
        cx, cy = 64, 64
        import math
        for i in range(8):
            a = math.radians(i * 45)
            x1, y1 = cx + math.cos(a) * 30, cy + math.sin(a) * 30
            x2, y2 = cx + math.cos(a) * 47, cy + math.sin(a) * 47
            d.line([(x1, y1), (x2, y2)], fill=c, width=10)
        d.ellipse((55, 55, 73, 73), outline=c, width=6)

    for name, fn in {
        "home": home,
        "matches": ball,
        "leagues": trophy,
        "table": table,
        "settings": settings,
    }.items():
        render(name, fn)

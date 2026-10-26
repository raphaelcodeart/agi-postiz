#!/usr/bin/env python3
"""
Rende il marchio AGI Post in PNG per le email transazionali.

Perche' uno script e non un file binario committato e basta: il marchio esiste
gia' due volte come SVG (la landing, e BrandMark in
apps/dashboard/app/portal/_shared/brand.tsx) e i client email non sanno
renderizzare SVG. Un PNG "arrivato da qualche parte" diverge dal marchio alla
prima ritoccata senza che nessuno sappia piu' come rigenerarlo; qui le stesse
coordinate del BrandMark sono scritte una volta e il PNG si rifa' in un comando.

Niente Pillow di proposito: il server non ce l'ha, e aggiungere una dipendenza
di rendering all'immagine dell'API per un asset che cambia una volta l'anno
sarebbe un pessimo scambio. Il disegno e' geometria elementare (tre anelli e due
segmenti), il campionamento e' 4x4 per lato, e l'encoder PNG sono venti righe di
zlib: tutto stdlib.

    python3 scripts/render-email-logo.py

Scrive apps/api/app/services/email/assets/agipost-logo.png (RGBA, fondo
trasparente: nelle email sta su una scheda bianca).
"""
import math
import pathlib
import struct
import zlib

# --- Geometria, identica al viewBox 64x64 di BrandMark --------------------
RINGS = [(14.0, 32.0), (46.0, 16.0), (46.0, 48.0)]
RING_RADIUS = 6.4
RING_HALF_STROKE = 4.6 / 2
SEGMENTS = [
    ((19.6, 29.2), (40.4, 18.8)),
    ((19.6, 34.8), (40.4, 45.2)),
]
SEG_HALF_STROKE = 4.2 / 2

# Le quattro fermate del gradiente del marchio (--pa-g1..g4 in globals.css),
# lungo l'asse (6,58) -> (58,6).
GRADIENT_FROM = (6.0, 58.0)
GRADIENT_TO = (58.0, 6.0)
STOPS = [
    (0.00, (0x7C, 0x6B, 0xD8)),
    (0.38, (0x4F, 0xB3, 0xF5)),
    (0.72, (0xF2, 0x68, 0x5E)),
    (1.00, (0xF6, 0xB2, 0x5A)),
]

SIZE = 192       # lato in pixel: mostrato a 48px, 4x per gli schermi retina
SUPERSAMPLE = 4  # campioni per lato, 16 per pixel
PADDING = 1.0    # unita' del viewBox, perche' lo stroke non tocchi il bordo


def gradient_color(x: float, y: float) -> tuple:
    ax, ay = GRADIENT_FROM
    bx, by = GRADIENT_TO
    dx, dy = bx - ax, by - ay
    t = ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))
    for i in range(len(STOPS) - 1):
        t0, c0 = STOPS[i]
        t1, c1 = STOPS[i + 1]
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
    return STOPS[-1][1]


def point_to_segment(px: float, py: float, a: tuple, b: tuple) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = min(1.0, max(0.0, t))  # clamp = estremita' arrotondate, come strokeLinecap="round"
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def inside(x: float, y: float) -> bool:
    for cx, cy in RINGS:
        if abs(math.hypot(x - cx, y - cy) - RING_RADIUS) <= RING_HALF_STROKE:
            return True
    return any(point_to_segment(x, y, a, b) <= SEG_HALF_STROKE for a, b in SEGMENTS)


def render() -> bytes:
    """Righe RGBA grezze, gia' con il filtro PNG 0 in testa a ciascuna."""
    scale = (64.0 + PADDING * 2) / SIZE
    step = scale / SUPERSAMPLE
    rows = bytearray()
    for py in range(SIZE):
        rows.append(0)  # filtro "None"
        for px in range(SIZE):
            hits = 0
            for sy in range(SUPERSAMPLE):
                vy = (py * SUPERSAMPLE + sy + 0.5) * step - PADDING
                for sx in range(SUPERSAMPLE):
                    vx = (px * SUPERSAMPLE + sx + 0.5) * step - PADDING
                    if inside(vx, vy):
                        hits += 1
            if not hits:
                rows.extend((0, 0, 0, 0))
                continue
            cx = (px + 0.5) * scale - PADDING
            cy = (py + 0.5) * scale - PADDING
            r, g, b = gradient_color(cx, cy)
            rows.extend((r, g, b, round(255 * hits / (SUPERSAMPLE * SUPERSAMPLE))))
    return bytes(rows)


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def main() -> None:
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8 bit, RGBA
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(render(), 9))
        + png_chunk(b"IEND", b"")
    )
    out = (
        pathlib.Path(__file__).resolve().parent.parent
        / "apps/api/app/services/email/assets/agipost-logo.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"{out} - {len(png)} byte, {SIZE}x{SIZE}")


if __name__ == "__main__":
    main()

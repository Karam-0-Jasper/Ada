"""Kernel Fresh logo motion — renders horizontal (1920x1080) and vertical (1080x1920) MP4s.

Usage: python3 render.py <logo.jpg> <out_dir>
The logo is split into colour layers straight from the source artwork, so the
animated shapes match the original exactly.
"""
import heapq
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

FPS = 30
DURATION = 6.0
BG = (247, 247, 247)
ORANGE = (247, 141, 0)
GREEN = (139, 190, 40)
TEXT_Y = 308   # rows below this are the wordmark
DROP_Y = 243   # neck between the green tail and the droplet


# ---------- easing ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def prog(t, start, dur):
    return clamp((t - start) / dur)

def ease_in_out(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2

def ease_out(x):
    return 1 - (1 - x) ** 3

def ease_out_back(x, s=1.9):
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


# ---------- layer extraction ----------
def extract(path):
    im = np.array(Image.open(path).convert("RGB")).astype(float)
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    is_orange = (R - G) > 0
    a_or = np.clip((247 - B) / 247, 0, 1)
    a_gr = np.clip((247 - B) / 205, 0, 1)
    alpha = np.where(is_orange, a_or, a_gr)
    alpha = np.clip((alpha - 0.08) / 0.92, 0, 1)
    orange = np.where(is_orange, alpha, 0)
    green = np.where(~is_orange, alpha, 0)
    return orange, green


def geodesic(mask, start):
    """Dijkstra distance inside mask from start (8-connected)."""
    h, w = mask.shape
    dist = np.full((h, w), np.inf)
    dist[start] = 0
    pq = [(0.0, start)]
    nbr = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1),
           (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    while pq:
        d, (y, x) = heapq.heappop(pq)
        if d > dist[y, x]:
            continue
        for dy, dx, c in nbr:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]:
                nd = d + c
                if nd < dist[ny, nx]:
                    dist[ny, nx] = nd
                    heapq.heappush(pq, (nd, (ny, nx)))
    return dist


def farthest(dist):
    d = np.where(np.isfinite(dist), dist, -1)
    return np.unravel_index(np.argmax(d), d.shape)


def stroke_order(alpha, from_inner):
    """Normalised 0..1 'draw-on' order along a stroke, by geodesic distance."""
    mask = alpha > 0.35
    seed = tuple(np.argwhere(mask)[0])
    e1 = farthest(geodesic(mask, seed))
    d1 = geodesic(mask, e1)
    e2 = farthest(d1)
    ys, xs = np.nonzero(mask)
    cy, cx = ys.mean(), xs.mean()
    r1 = math.hypot(e1[0] - cy, e1[1] - cx)
    r2 = math.hypot(e2[0] - cy, e2[1] - cx)
    inner = e1 if r1 < r2 else e2
    outer = e2 if inner == e1 else e1
    d = geodesic(mask, inner if from_inner else outer)
    d[~np.isfinite(d)] = np.nan
    d = d / np.nanmax(d)
    # spread values to soft edge pixels outside the threshold mask
    for _ in range(6):
        filled = d.copy()
        for sh in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            r = np.roll(d, sh, axis=(0, 1))
            filled = np.where(np.isnan(filled) & ~np.isnan(r), r, filled)
        d = filled
    return np.nan_to_num(d, nan=1.0)


def letters(alpha):
    """Split a wordmark alpha into per-letter column ranges."""
    cols = alpha.max(0) > 0.15
    spans, x = [], 0
    w = len(cols)
    while x < w:
        if cols[x]:
            s = x
            while x < w and cols[x]:
                x += 1
            spans.append((s, x))
        x += 1
    return spans


# ---------- upscaling helpers ----------
def up_alpha(a, size):
    img = Image.fromarray((a * 255).astype(np.uint8)).resize(size, Image.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    arr = np.asarray(img).astype(float) / 255
    return np.clip((arr - 0.5) * 1.5 + 0.5, 0, 1)  # crisp edges after upscale

def up_field(f, size):
    return np.asarray(Image.fromarray(f.astype(np.float32), mode="F").resize(size, Image.BILINEAR))

def rgba(alpha, color, opacity=1.0):
    h, w = alpha.shape
    out = np.empty((h, w, 4), np.uint8)
    out[..., :3] = color
    out[..., 3] = np.clip(alpha * opacity * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# ---------- build ----------
def build(path):
    orange, green = extract(path)
    H, W = orange.shape
    ys, xs = np.nonzero((orange + green) > 0.1)
    box = (xs.min() - 4, ys.min() - 4, xs.max() + 5, ys.max() + 5)  # x0,y0,x1,y1

    g_or = orange.copy(); g_or[TEXT_Y:] = 0
    g_gr = green.copy(); g_gr[TEXT_Y:] = 0
    drop = g_gr.copy(); drop[:DROP_Y - 3] = 0
    g_gr[DROP_Y + 3:] = 0  # small overlap hides the seam

    o_or = stroke_order(g_or, from_inner=False)  # orange winds inward
    o_gr = stroke_order(g_gr, from_inner=True)   # green unwinds out to the tail

    t_or = orange.copy(); t_or[:TEXT_Y] = 0
    t_gr = green.copy(); t_gr[:TEXT_Y] = 0
    return dict(box=box, g_or=g_or, g_gr=g_gr, drop=drop, o_or=o_or, o_gr=o_gr,
                t_or=t_or, t_gr=t_gr)


def prepare(L, scale):
    """Crop to logo box and upscale everything for a given canvas scale."""
    x0, y0, x1, y1 = L["box"]
    def crop(a):
        return a[y0:y1, x0:x1]
    cw, ch = x1 - x0, y1 - y0
    size = (round(cw * scale), round(ch * scale))
    P = dict(size=size, scale=scale)
    for k in ["g_or", "g_gr", "drop"]:
        P[k] = up_alpha(crop(L[k]), size)
    for k in ["o_or", "o_gr"]:
        P[k] = up_field(crop(L[k]), size)
    # drop anchor: top-centre of droplet
    dy, dx = np.nonzero(P["drop"] > 0.3)
    P["drop_anchor"] = (dx.mean(), dy.min())
    # spiral pivot
    gy, gx = np.nonzero((P["g_or"] + P["g_gr"]) > 0.3)
    P["pivot"] = (gx.mean(), gy.mean())
    # per-letter text sprites
    P["letters"] = []
    for key, color in [("t_or", ORANGE), ("t_gr", GREEN)]:
        a = crop(L[key])
        for s, e in letters(a):
            sub = np.zeros_like(a); sub[:, s:e] = a[:, s:e]
            P["letters"].append((up_alpha(sub, size), color, (s + e) / 2 * scale))
    P["letters"].sort(key=lambda l: l[2])
    return P


def frame(P, t, W, H, logo_xy):
    canvas = Image.new("RGBA", (W, H), BG + (255,))
    lw, lh = P["size"]
    ox, oy = logo_xy
    sc = P["scale"]

    # --- spirals draw on, with a settle rotation/scale ---
    p_or = ease_in_out(prog(t, 0.25, 1.5))
    p_gr = ease_in_out(prog(t, 0.45, 1.4))
    soft = 0.035
    a_or = P["g_or"] * np.clip((p_or * (1 + soft) - P["o_or"]) / soft, 0, 1)
    a_gr = P["g_gr"] * np.clip((p_gr * (1 + soft) - P["o_gr"]) / soft, 0, 1)
    spin = ease_out(prog(t, 0.2, 2.0))
    g = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    g.alpha_composite(rgba(a_or, ORANGE))
    g.alpha_composite(rgba(a_gr, GREEN))
    angle = (1 - spin) * 70
    zoom = 0.82 + 0.18 * spin
    px, py = P["pivot"]
    g = g.rotate(angle, resample=Image.BICUBIC, center=(px, py))
    if zoom != 1:
        zw, zh = round(lw * zoom), round(lh * zoom)
        gz = g.resize((zw, zh), Image.BICUBIC)
        g = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        g.alpha_composite(gz, (round(px - px * zoom), round(py - py * zoom)))
    canvas.alpha_composite(g, (ox, oy))

    # --- droplet forms at the end of the green tail, with a jelly bounce ---
    pd = prog(t, 1.65, 0.75)
    if pd > 0:
        s = max(0.001, ease_out_back(pd))
        wob = math.sin(prog(t, 1.9, 0.9) * math.pi * 3) * 0.06 * (1 - prog(t, 1.9, 0.9))
        sx, sy = s * (1 + wob), s * (1 - wob)
        d = rgba(P["drop"], GREEN, min(1, pd * 3))
        ax, ay = P["drop_anchor"]
        dw, dh = max(1, round(lw * sx)), max(1, round(lh * sy))
        dz = d.resize((dw, dh), Image.BICUBIC)
        canvas.alpha_composite(dz, (round(ox + ax - ax * sx), round(oy + ay - ay * sy)))

    # --- wordmark: letters rise in, staggered ---
    n = len(P["letters"])
    for i, (a, color, _) in enumerate(P["letters"]):
        pl = prog(t, 2.05 + i * 0.07, 0.6)
        if pl <= 0:
            continue
        e = ease_out(pl)
        dy = round((1 - e) * 38 * sc)
        canvas.alpha_composite(rgba(a, color, e), (ox, oy + dy))

    # --- glossy shine sweep across the finished logo ---
    ps = prog(t, 3.6, 0.9)
    if 0 < ps < 1:
        logo = np.asarray(canvas.crop((ox, oy, ox + lw, oy + lh))).astype(float)
        yy, xx = np.mgrid[0:lh, 0:lw]
        band_x = -0.3 * lw + ps * 1.6 * lw
        dist = (xx + yy * 0.45) - band_x
        band = np.exp(-(dist / (0.06 * lw)) ** 2) * 0.55
        ink = 1 - np.clip(logo[..., :3].mean(-1) / 247, 0, 1)  # only on coloured pixels
        ink = np.clip(ink * 4, 0, 1)
        logo[..., :3] += (255 - logo[..., :3]) * (band * ink)[..., None]
        canvas.paste(Image.fromarray(logo.astype(np.uint8), "RGBA"), (ox, oy))

    # --- slow breathe during the hold so it never feels frozen ---
    pb = prog(t, 4.5, DURATION - 4.5)
    if pb > 0:
        z = 1 + 0.025 * ease_in_out(pb)
        cz = canvas.resize((round(W * z), round(H * z)), Image.BICUBIC)
        cx, cy = (cz.width - W) // 2, (cz.height - H) // 2
        canvas = cz.crop((cx, cy, cx + W, cy + H))

    return canvas.convert("RGB")


def render(L, W, H, logo_frac, out):
    x0, y0, x1, y1 = L["box"]
    cw, ch = x1 - x0, y1 - y0
    scale = min(W * logo_frac[0] / cw, H * logo_frac[1] / ch)
    P = prepare(L, scale)
    lw, lh = P["size"]
    logo_xy = ((W - lw) // 2, (H - lh) // 2)
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i in range(int(DURATION * FPS)):
        ff.stdin.write(frame(P, i / FPS, W, H, logo_xy).tobytes())
    ff.stdin.close()
    ff.wait()
    print("wrote", out)
    return P, logo_xy


if __name__ == "__main__":
    src, out_dir = sys.argv[1], sys.argv[2]
    L = build(src)
    render(L, 1920, 1080, (0.5, 0.62), f"{out_dir}/KernelFresh_Logo_Animation_horizontal.mp4")
    render(L, 1080, 1920, (0.78, 0.5), f"{out_dir}/KernelFresh_Logo_Animation_vertical.mp4")

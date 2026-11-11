"""Regional Youth Conference logo motion — 3s, with sound.

Usage: python3 render.py <logo.jpg> <out_dir>
Renders vertical (1080x1920) and horizontal (1920x1080) MP4s with a soft
synthesized soundtrack (whoosh, bounce pops, text ticks, closing chime).
"""
import math
import subprocess
import sys
import wave
from collections import deque

import numpy as np
from PIL import Image

FPS = 30
DUR = 3.0
SR = 44100
BG = (255, 255, 255)
RED = (158, 36, 57)
ARCH = (28, 32, 72)
TEXT = (10, 24, 72)

# timeline (seconds)
T_ARCH, T_U, T_HEAD, T_TEXT, T_HOP = 0.0, 0.15, 0.42, 0.9, 1.85
D_HEAD = 0.55


# ---------- easing ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def prog(t, s, d):
    return clamp((t - s) / d)

def ease_out(x):
    return 1 - (1 - x) ** 3

def ease_out_back(x, s=1.7):
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2

def ease_out_bounce(x):
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d; return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d; return n * x * x + 0.9375
    x -= 2.625 / d; return n * x * x + 0.984375

BOUNCE_HITS = [1 / 2.75, 2 / 2.75, 2.5 / 2.75]  # contact points of ease_out_bounce


# ---------- layers ----------
def components(mask):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in np.argwhere(mask):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    q.append((ny, nx))
    return lab, n


def build(path, scale):
    src = Image.open(path).convert("RGB")
    a = np.asarray(src).astype(int)
    ink = a.sum(-1) < 600
    ys, xs = np.nonzero(ink)
    pad = 40
    box = (xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad)
    crop = src.crop(box)
    size = (round(crop.width * scale), round(crop.height * scale))
    im = np.asarray(crop.resize(size, Image.LANCZOS)).astype(float)
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    is_red = (R - B) > 0
    alpha = np.where(is_red, (255 - G) / (255 - 36), (255 - R) / (255 - 12))
    alpha = np.clip((alpha - 0.04) / 0.96, 0, 1)

    # label red and navy separately: the arms and the arch touch
    lab_r, nr = components((alpha > 0.5) & is_red)
    lab_n, nn = components((alpha > 0.5) & ~is_red)
    lab = np.where(lab_n > 0, lab_n + nr, lab_r)
    n = nr + nn
    # grow labels into soft edge pixels
    for _ in range(3):
        for sh in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            r = np.roll(lab, sh, axis=(0, 1))
            lab = np.where((lab == 0) & (r > 0) & (alpha > 0) & (is_red == (r <= nr)), r, lab)

    info = []
    for i in range(1, n + 1):
        yy, xx = np.nonzero(lab == i)
        info.append(dict(id=i, x0=xx.min(), x1=xx.max(), y0=yy.min(), y1=yy.max(),
                         red=is_red[yy, xx].mean() > 0.5, area=len(yy)))
    big = [c for c in info if c["area"] > 30]
    w = size[0]
    mark_right = max(c["x1"] for c in big if c["red"]) + 5
    reds = sorted([c for c in big if c["red"]], key=lambda c: c["area"])
    head, u = reds[-2], reds[-1]
    arch = max([c for c in big if not c["red"] and c["x1"] <= mark_right + 20], key=lambda c: c["area"])
    text_ids = [c for c in big if not c["red"] and c is not arch]

    def layer(ids):
        m = np.isin(lab, [c["id"] for c in ids])
        return alpha * m

    L = dict(size=size, head=layer([head]), u=layer([u]), arch=layer([arch]))
    # group letters into lines by where each letter starts vertically
    text_ids.sort(key=lambda c: c["y0"])
    span = max(c["y1"] for c in text_ids) - min(c["y0"] for c in text_ids)
    groups = [[text_ids[0]]]
    for c in text_ids[1:]:
        if c["y0"] - groups[-1][-1]["y0"] > 0.12 * span:
            groups.append([])
        groups[-1].append(c)
    L["lines"] = [layer(g) for g in groups]
    L["head_box"] = head
    L["u_box"] = u
    L["arch_box"] = arch
    return L


def sprite(alpha, color, opacity=1.0):
    h, w = alpha.shape
    out = np.empty((h, w, 4), np.uint8)
    out[..., :3] = color
    out[..., 3] = np.clip(alpha * opacity * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def place(canvas, spr, ox, oy, sx=1.0, sy=1.0, anchor=(0, 0), angle=0.0, dx=0, dy=0):
    """Composite a full-logo-sized sprite, scaled/rotated about an anchor point."""
    ax, ay = anchor
    if angle:
        spr = spr.rotate(angle, resample=Image.BICUBIC, center=(ax, ay))
    if sx != 1 or sy != 1:
        w, h = max(1, round(spr.width * sx)), max(1, round(spr.height * sy))
        spr = spr.resize((w, h), Image.BICUBIC)
        ox += ax - ax * sx
        oy += ay - ay * sy
    canvas.alpha_composite(spr, (round(ox + dx), round(oy + dy)))


# ---------- frames ----------
def frame(L, S, t, W, H, ox, oy, k):
    """k = pixels per logo unit (motion distances scale with layout)."""
    c = Image.new("RGBA", (W, H), BG + (255,))

    # navy arch rises up from below
    p = prog(t, T_ARCH, 0.55)
    if p > 0:
        a = L["arch_box"]
        e = ease_out_back(p)
        hop = 0
        ph = prog(t, T_HOP, 0.5)
        sq = 1 - 0.06 * math.sin(ph * math.pi) if ph > 0 else 1  # squash as figure pushes off
        place(c, S["arch"].copy() if p >= 1 else sprite(L["arch"], ARCH, min(1, p * 2.5)),
              ox, oy, sx=1 / sq if sq != 1 else 1, sy=sq, anchor=((a["x0"] + a["x1"]) / 2, a["y1"]),
              dy=(1 - e) * 170 * k)

    # red "arms" pop open from the middle
    p = prog(t, T_U, 0.6)
    if p > 0:
        u = L["u_box"]
        e = ease_out_back(p, 2.2)
        s = 0.25 + 0.75 * e
        ph = prog(t, T_HOP, 0.5)
        lift = -math.sin(ph * math.pi) * 22 * k if ph > 0 else 0
        stretch = 1 + 0.08 * math.sin(ph * math.pi) if ph > 0 else 1
        place(c, sprite(L["u"], RED, min(1, p * 3)), ox, oy, sx=s / stretch ** 0.5, sy=s * stretch,
              anchor=((u["x0"] + u["x1"]) / 2, u["y1"]), angle=(1 - e) * -25, dy=lift)

    # head drops in and bounces, then jumps with joy
    p = prog(t, T_HEAD, D_HEAD)
    if p > 0:
        hb = L["head_box"]
        fall = (1 - ease_out_bounce(p)) * -330 * k
        # squash on each bounce contact
        sq = 1.0
        for i, hit in enumerate(BOUNCE_HITS):
            d = abs(p - hit)
            if d < 0.06:
                sq = min(sq, 1 - (0.22 / (i + 1)) * (1 - d / 0.06))
        ph = prog(t, T_HOP - 0.05, 0.6)
        jump = -math.sin(ph * math.pi) * 70 * k if ph > 0 else 0
        place(c, sprite(L["head"], RED, min(1, p * 5)), ox, oy, sx=1 / sq ** 0.5, sy=sq,
              anchor=((hb["x0"] + hb["x1"]) / 2, hb["y1"]), dy=fall + jump)

    # text lines slide in from the left, staggered
    for i, line in enumerate(L["lines"]):
        p = prog(t, T_TEXT + i * 0.13, 0.55)
        if p <= 0:
            continue
        e = ease_out(p)
        place(c, S["lines"][i] if p >= 1 else sprite(line, TEXT, e), ox, oy, dx=(1 - e) * 90 * k)

    return c.convert("RGB")


# ---------- sound ----------
def soundtrack():
    n = int(DUR * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(7)
    t = np.arange(n) / SR

    def add(start, sig, gain=1.0):
        i = int(start * SR)
        j = min(n, i + len(sig))
        out[i:j] += sig[: j - i] * gain

    def whoosh(dur, lo=300, hi=2500):
        m = int(dur * SR)
        x = rng.standard_normal(m)
        # sweeping one-pole low-pass for an airy rise-and-fall
        y = np.zeros(m); s = 0.0
        env = np.sin(np.linspace(0, math.pi, m)) ** 2
        for i in range(m):
            fc = lo + (hi - lo) * env[i]
            a = 1 - math.exp(-2 * math.pi * fc / SR)
            s += a * (x[i] - s); y[i] = s
        return y * env

    def pop(f0=700, f1=220, dur=0.09):
        m = int(dur * SR); tt = np.arange(m) / SR
        f = f1 + (f0 - f1) * np.exp(-tt * 45)
        ph = 2 * math.pi * np.cumsum(f) / SR
        return np.sin(ph) * np.exp(-tt * 38)

    def tick(f=1500, dur=0.05):
        m = int(dur * SR); tt = np.arange(m) / SR
        return np.sin(2 * math.pi * f * tt) * np.exp(-tt * 90)

    def bell(freqs, dur=1.3):
        m = int(dur * SR); tt = np.arange(m) / SR
        sig = np.zeros(m)
        for f in freqs:
            sig += np.sin(2 * math.pi * f * tt) * np.exp(-tt * 3.2)
            sig += 0.3 * np.sin(2 * math.pi * f * 2.01 * tt) * np.exp(-tt * 6)
        attack = np.clip(tt / 0.008, 0, 1)
        return sig * attack / len(freqs)

    add(T_ARCH, whoosh(0.5), 0.55)
    add(T_U + 0.05, whoosh(0.4, 500, 3500), 0.35)
    for i, hit in enumerate(BOUNCE_HITS):
        add(T_HEAD + hit * D_HEAD - 0.005, pop(), 0.55 / (i + 1) ** 1.3)
    for i in range(3):
        add(T_TEXT + i * 0.13 + 0.05, tick(1400 + i * 220), 0.18)
    add(T_HOP + 0.05, whoosh(0.3, 800, 4000), 0.2)
    add(T_HOP + 0.25, bell([523.25, 659.25, 783.99, 1046.5]), 0.6)  # C major landing chime

    fade = np.clip((DUR - t) / 0.2, 0, 1)
    out *= fade
    out /= max(1e-6, np.abs(out).max()) / 0.8
    st = np.stack([out, out], 1)
    return (st * 32767).astype(np.int16)


def write_wav(path):
    pcm = soundtrack()
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def render(path, W, H, frac, out, wav):
    probe = Image.open(path).convert("RGB")
    a = np.asarray(probe).astype(int)
    ys, xs = np.nonzero(a.sum(-1) < 600)
    lw, lh = xs.max() - xs.min() + 80, ys.max() - ys.min() + 80
    scale = min(W * frac / lw, H * 0.6 / lh)
    L = build(path, scale)
    S = dict(arch=sprite(L["arch"], ARCH), lines=[sprite(l, TEXT) for l in L["lines"]])
    w, h = L["size"]
    ox, oy = (W - w) // 2, (H - h) // 2
    k = w / 1000
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        ff.stdin.write(frame(L, S, i / FPS, W, H, ox, oy, k).tobytes())
    ff.stdin.close(); ff.wait()
    print("wrote", out, "lines:", len(L["lines"]))


if __name__ == "__main__":
    src, od = sys.argv[1], sys.argv[2]
    wav = f"{od}/RYC_sound.wav"
    write_wav(wav)
    render(src, 1080, 1920, 0.8, f"{od}/RYC_Logo_Animation_vertical.mp4", wav)
    render(src, 1920, 1080, 0.55, f"{od}/RYC_Logo_Animation_horizontal.mp4", wav)

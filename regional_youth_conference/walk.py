"""RYC logo — "walking" version (4s, new sound).

The icon walks in from the left on its two arch legs (body bob, arm swing,
head lag), stops on its spot, celebrates with a hop, then the wordmark wipes in.
Sound: soft footsteps, a marimba walking line, a ta-da and shimmer ticks.

Usage: python3 walk.py <logo.jpg> <out_dir>
"""
import math
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import render as R

FPS = 30
DUR = 4.0
SR = 44100
T_WALK = 2.1          # walking ends (decelerates to a stop)
STEPS = 6             # footfalls during the walk
T_HOP = 2.2
T_TEXT = 2.45


def walk_dist(t):
    """0..1 travelled; already moving at t=0, eases to a stop at T_WALK."""
    x = R.clamp(t / T_WALK)
    return 1 - (1 - x) ** 1.6

def walk_speed(t):
    x = R.clamp(t / T_WALK)
    return (1 - x) ** 0.6 if t < T_WALK else 0.0

def phase(t):
    # one footfall per pi of phase; contacts at pi/2 + n*pi
    return walk_dist(t) * STEPS * math.pi


def footfalls():
    ts, out = np.linspace(0, T_WALK, 4000), []
    prev = None
    for t in ts:
        n = math.floor((phase(t) - math.pi / 2) / math.pi)
        if prev is not None and n != prev and walk_speed(t) > 0.15:
            out.append(t)
        prev = n
    return out


def split_legs(L):
    a, box = L["arch"], L["arch_box"]
    cx = (box["x0"] + box["x1"]) / 2
    xx = np.arange(a.shape[1])[None, :]
    left = a * (xx <= cx + 3)
    right = a * (xx >= cx - 3)
    hip = (cx, box["y0"] + (box["y1"] - box["y0"]) * 0.18)
    # solid "pelvis" cap drawn over the joint so the split never shows
    yy = np.arange(a.shape[0])[:, None]
    r = (box["x1"] - box["x0"]) * 0.2
    cap = a * (np.hypot(xx - hip[0], yy - hip[1]) < r)
    return left, right, hip, cap


def frame(L, S, t, W, H, ox, oy, k):
    c = Image.new("RGBA", (W, H), R.BG + (255,))
    lw, lh = L["size"]
    ab, ub, hb = L["arch_box"], L["u_box"], L["head_box"]

    # walk position: start fully off-screen left
    icon_right = max(ab["x1"], ub["x1"])
    start = -(ox + icon_right) - 20
    dx = start * (1 - walk_dist(t))
    ph = phase(t)
    amp = walk_speed(t) ** 0.5
    swing = math.sin(ph) * amp
    bob = abs(math.sin(ph)) * amp          # 1 when legs are spread (contact)
    body_y = (bob * 14 - 7 * amp) * k      # low on contact, high when passing

    # celebration hop after arriving
    hp = R.prog(t, T_HOP, 0.55)
    hop = math.sin(hp * math.pi) if 0 < hp < 1 else 0.0

    # ground shadow while walking
    sh_a = 1 - R.prog(t, T_WALK - 0.2, 0.6)
    if sh_a > 0:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        cx = ox + dx + (ab["x0"] + ab["x1"]) / 2
        gy = oy + ab["y1"] + 6 * k
        rw = (ab["x1"] - ab["x0"]) * (0.55 - 0.06 * bob)
        d.ellipse([cx - rw, gy - 9 * k, cx + rw, gy + 9 * k], fill=(0, 0, 0, int(40 * sh_a)))
        c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8 * k)))

    # legs: two halves of the arch scissor around the hip
    hx, hy = S["hip"]
    leg_ang = 16 * swing
    if abs(leg_ang) < 0.05:
        R.place(c, S["arch"], ox, oy, dx=dx, dy=body_y * 0.3)
    else:
        R.place(c, S["leg_l"], ox, oy, anchor=(hx, hy), angle=leg_ang, dx=dx, dy=body_y * 0.3)
        R.place(c, S["leg_r"], ox, oy, anchor=(hx, hy), angle=-leg_ang, dx=dx, dy=body_y * 0.3)
        R.place(c, S["cap"], ox, oy, dx=dx, dy=body_y * 0.3)

    # arms: counter-swing + lift on the hop
    uax = (ub["x0"] + ub["x1"]) / 2
    stretch = 1 + 0.1 * hop
    R.place(c, S["arms"], ox, oy, sx=1 / stretch ** 0.5, sy=stretch, anchor=(uax, ub["y1"]),
            angle=-7 * swing, dx=dx, dy=body_y - 26 * k * hop)

    # head: bobs with a slight lag, nods, then jumps for joy
    lag = abs(math.sin(ph - 0.5)) * amp
    head_y = (lag * 16 - 8 * amp) * k - 80 * k * hop
    R.place(c, S["head"], ox, oy, anchor=((hb["x0"] + hb["x1"]) / 2, hb["y1"]),
            angle=4 * math.sin(ph - 0.5) * amp, dx=dx, dy=body_y + head_y)

    # wordmark wipes in left-to-right, line by line
    for i, line in enumerate(L["lines"]):
        p = R.prog(t, T_TEXT + i * 0.16, 0.5)
        if p <= 0:
            continue
        e = R.ease_out(p)
        if e >= 1:
            c.alpha_composite(S["lines"][i], (ox, oy))
            continue
        xs = np.nonzero(line.max(0) > 0.1)[0]
        x0, x1 = xs.min(), xs.max()
        edge = x0 + (x1 - x0 + 40 * k) * e
        xx = np.arange(lw)[None, :]
        ramp = np.clip((edge - xx) / (30 * k), 0, 1)
        c.alpha_composite(R.sprite(line * ramp, R.TEXT), (ox, oy + round((1 - e) * 10 * k)))

    return c.convert("RGB")


# ---------- sound ----------
def soundtrack():
    n = int(DUR * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(3)

    def add(start, sig, gain=1.0):
        i = int(start * SR); j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[: j - i] * gain

    def step(bright):
        m = int(0.12 * SR); tt = np.arange(m) / SR
        thump = np.sin(2 * math.pi * (95 + 25 * bright) * tt) * np.exp(-tt * 40)
        x = rng.standard_normal(m); y = np.zeros(m); s = 0.0
        a = 1 - math.exp(-2 * math.pi * 1800 / SR)
        for i in range(m):
            s += a * (x[i] - s); y[i] = s
        scuff = y * np.exp(-tt * 70)
        return thump * 0.9 + scuff * 0.5

    def marimba(f, dur=0.45):
        m = int(dur * SR); tt = np.arange(m) / SR
        sig = (np.sin(2 * math.pi * f * tt) * np.exp(-tt * 9)
               + 0.35 * np.sin(2 * math.pi * f * 3.98 * tt) * np.exp(-tt * 28)
               + 0.12 * np.sin(2 * math.pi * f * 9.2 * tt) * np.exp(-tt * 60))
        return sig * np.clip(tt / 0.003, 0, 1)

    def note(name):
        semis = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        return 261.63 * 2 ** ((semis[name[0]] + 12 * (int(name[1]) - 4)) / 12)

    # footsteps + a walking bass/melody, one note per step
    melody = ["C4", "E4", "G4", "E4", "F4", "A4", "G4", "B4"]
    for i, t in enumerate(footfalls()):
        add(t, step(i % 2), 0.55)
        add(t, marimba(note(melody[i % len(melody)])), 0.45)
        add(t + 0.0, marimba(note(melody[i % len(melody)]) / 2, 0.3), 0.25)

    # ta-da on the hop
    add(T_HOP + 0.02, marimba(note("G4"), 0.3), 0.55)
    for f in ["C5", "E5", "G5"]:
        add(T_HOP + 0.2, marimba(note(f), 1.2), 0.4)
    add(T_HOP + 0.2, marimba(note("C4"), 1.2), 0.35)

    # sparkly ticks as each text line wipes in
    for i in range(3):
        for j, f in enumerate([2093, 2637, 3136]):
            add(T_TEXT + i * 0.16 + j * 0.04, marimba(f * (1 + 0.06 * i), 0.25), 0.07)

    t = np.arange(n) / SR
    out *= np.clip((DUR - t) / 0.3, 0, 1)
    out /= np.abs(out).max() / 0.8
    return (np.stack([out, out], 1) * 32767).astype(np.int16)


def render(path, W, H, frac, out, wav):
    probe = np.asarray(Image.open(path).convert("RGB")).astype(int)
    ys, xs = np.nonzero(probe.sum(-1) < 600)
    lw, lh = xs.max() - xs.min() + 80, ys.max() - ys.min() + 80
    scale = min(W * frac / lw, H * 0.6 / lh)
    L = R.build(path, scale)
    arch = L["arch"]  # make the solid interior fully opaque so overlapping pieces don't darken
    L["arch"] = np.clip(arch / np.percentile(arch[arch > 0.5], 90), 0, 1)
    left, right, hip, cap = split_legs(L)
    S = dict(leg_l=R.sprite(left, R.ARCH), leg_r=R.sprite(right, R.ARCH), hip=hip,
             cap=R.sprite(cap, R.ARCH), arch=R.sprite(L["arch"], R.ARCH),
             arms=R.sprite(L["u"], R.RED), head=R.sprite(L["head"], R.RED),
             lines=[R.sprite(l, R.TEXT) for l in L["lines"]])
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
    print("wrote", out)


if __name__ == "__main__":
    src, od = sys.argv[1], sys.argv[2]
    wav = f"{od}/_walk_sound.wav"
    pcm = soundtrack()
    with wave.open(wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print("footfalls:", [round(x, 2) for x in footfalls()])
    render(src, 1080, 1920, 0.8, f"{od}/RYC_Walk_Animation_vertical.mp4", wav)
    render(src, 1920, 1080, 0.55, f"{od}/RYC_Walk_Animation_horizontal.mp4", wav)

"""Export an editable After Effects project kit for the RYC logo animation.

Usage: python3 export_ae.py <logo.jpg> <out_dir>
Writes <out_dir>/assets/*.png (one transparent layer per logo element, full
source resolution), assets/RYC_sound.wav, and RYC_Build_AE.jsx — an
ExtendScript that builds keyframed vertical + horizontal comps inside AE.
"""
import json
import os
import sys

import numpy as np

import render as R


def bbox(a):
    ys, xs = np.nonzero(a > 0.2)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main(src, out):
    os.makedirs(f"{out}/assets", exist_ok=True)
    L = R.build(src, 1.0)  # full source resolution
    pw, ph = L["size"]
    layers = []

    def save(name, alpha, color, pivot):
        R.sprite(alpha, color).save(f"{out}/assets/{name}.png")
        layers.append(dict(name=name, file=f"{name}.png", pivot=[float(pivot[0]), float(pivot[1])]))

    a = L["arch_box"]; save("Arch", L["arch"], R.ARCH, ((a["x0"] + a["x1"]) / 2, a["y1"]))
    u = L["u_box"]; save("Arms", L["u"], R.RED, ((u["x0"] + u["x1"]) / 2, u["y1"]))
    h = L["head_box"]; save("Head", L["head"], R.RED, ((h["x0"] + h["x1"]) / 2, h["y1"]))
    for i, (line, word) in enumerate(zip(L["lines"], ["Regional", "Youth", "Conference"])):
        x0, y0, x1, y1 = bbox(line)
        save(f"Text_{i + 1}_{word}", line, R.TEXT, (x0, (y0 + y1) / 2))
    R.write_wav(f"{out}/assets/RYC_sound.wav")

    data = dict(pw=pw, ph=ph, layers=layers, T=dict(
        arch=R.T_ARCH, u=R.T_U, head=R.T_HEAD, dhead=R.D_HEAD, text=R.T_TEXT, hop=R.T_HOP))
    jsx = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ae_template.jsx")).read()
    with open(f"{out}/RYC_Build_AE.jsx", "w") as f:
        f.write(jsx.replace("/*DATA*/", json.dumps(data)))
    print("exported", out, pw, ph)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

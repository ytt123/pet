#!/usr/bin/env python3
"""Process keyed frames -> normalized, feet-anchored animation frames.

Reads:  _key_a/*.png  (idle, beige-keyed)   _key_b/*.png (web, green-keyed)
Writes: assets/idle/###.png , assets/web/###.png  (all same canvas size,
        character normalized to same height, feet centered at canvas bottom)
Also writes assets/meta.json and _verify montages.
"""
import glob, os, json, subprocess, shutil
from PIL import Image, ImageFilter, ImageEnhance

# ---- 1) 从两段视频抽帧 + 色键抠背景 (需要 ffmpeg) --------------------------
# video.mp4      = 待机(米色背景),干净帧区间 4..80
# video (1).mp4  = 吐丝(绿幕背景 + 黄色地面阴影),干净帧区间 10..80
WORK_A, WORK_B = "_work_idle", "_work_web"

def extract():
    for d in (WORK_A, WORK_B):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    # idle: 米色抠除
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", "video.mp4",
        "-vf", "select='between(n,4,80)',colorkey=0xD1CFC2:0.20:0.08,format=rgba",
        "-vsync", "0", f"{WORK_A}/f_%03d.png"], check=True)
    # web: 绿幕 + 黄色地面阴影抠除
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", "video (1).mp4",
        "-vf", ("select='between(n,10,80)',"
                "colorkey=0x5EB558:0.32:0.14,"
                "colorkey=0xBFD033:0.30:0.12,format=rgba"),
        "-vsync", "0", f"{WORK_B}/f_%03d.png"], check=True)
    print(f"extracted idle={len(glob.glob(WORK_A+'/*.png'))} "
          f"web={len(glob.glob(WORK_B+'/*.png'))}")

TARGET_H = 150          # character height in px, consistent across states
PAD_X = 24              # transparent side padding on canvas
PAD_TOP = 40            # headroom (bob/rotation)
PAD_BOTTOM = 12         # a little under the feet

def alpha_bbox(im, erode=0, thresh=128):
    a = im.split()[-1].point(lambda v: 255 if v >= thresh else 0)
    if erode:
        a = a.filter(ImageFilter.MinFilter(erode))
    return a.getbbox()

def union(b1, b2):
    if b1 is None: return b2
    if b2 is None: return b1
    return (min(b1[0], b2[0]), min(b1[1], b2[1]),
            max(b1[2], b2[2]), max(b1[3], b2[3]))

def load(dirn):
    return [Image.open(f).convert("RGBA")
            for f in sorted(glob.glob(f"{dirn}/f_*.png"))]

def core_bbox(frames, erode):
    """Union bbox of the character core across all frames."""
    bb = None
    for im in frames:
        bb = union(bb, alpha_bbox(im, erode=erode))
    return bb

extract()
idle = load(WORK_A)
web  = load(WORK_B)
print(f"loaded idle={len(idle)} web={len(web)}")

# idle: light erode to drop stray specks; web: strong erode to drop thin strand
bb_idle = core_bbox(idle, erode=3)
bb_web  = core_bbox(web,  erode=25)
# pad web bbox back out to recover eroded character edges
pw = 30
W = web[0].width; H = web[0].height
bb_web = (max(0, bb_web[0]-pw), max(0, bb_web[1]-pw),
          min(W, bb_web[2]+pw), min(H, bb_web[3]+pw))
print("idle bbox", bb_idle, "->", bb_idle[3]-bb_idle[1], "tall")
print("web  bbox", bb_web,  "->", bb_web[3]-bb_web[1],  "tall")

def scale_for(bb):
    return TARGET_H / float(bb[3] - bb[1])

s_idle = scale_for(bb_idle)
s_web  = scale_for(bb_web)

def process(frames, bb, scale):
    out = []
    for im in frames:
        c = im.crop(bb)
        nw = max(1, round(c.width * scale))
        nh = max(1, round(c.height * scale))
        out.append(c.resize((nw, nh), Image.LANCZOS))
    return out

pi = process(idle, bb_idle, s_idle)
# web kept un-graded: the source video uses shaded (gradient) red vs the idle's
# flat red; a global color LUT can't reconcile the two styles cleanly.
pw_ = process(web, bb_web, s_web)

# unified canvas: wide enough for the widest frame of either set
maxw = max(max(i.width for i in pi), max(i.width for i in pw_))
CW = maxw + 2 * PAD_X
CH = TARGET_H + PAD_TOP + PAD_BOTTOM
print(f"canvas {CW}x{CH}")

def compose(frames, outdir):
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(f"{outdir}/*.png"):
        os.remove(old)
    for idx, im in enumerate(frames):
        canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        x = (CW - im.width) // 2
        y = CH - PAD_BOTTOM - im.height   # feet at (bottom - PAD_BOTTOM)
        canvas.alpha_composite(im, (x, y))
        canvas.save(f"{outdir}/{idx:03d}.png")

compose(pi, "assets/idle")
compose(pw_, "assets/web")

meta = {"canvas": [CW, CH], "target_h": TARGET_H,
        "feet_y": CH - PAD_BOTTOM,
        "idle_frames": len(pi), "web_frames": len(pw_)}
with open("assets/meta.json", "w") as f:
    json.dump(meta, f, indent=2)
print("meta", meta)

# verification montages (every ~8th frame)
def montage(frames, out, step=8):
    sel = frames[::step]
    w = sum(f.width for f in sel); h = max(f.height for f in sel)
    m = Image.new("RGBA", (w, h), (200, 200, 200, 255))
    x = 0
    for f in sel:
        m.alpha_composite(f, (x, 0)); x += f.width
    m.convert("RGB").save(out)

os.makedirs("_verify", exist_ok=True)
# reload composed frames for montage (on canvas)
def load_dir(d):
    return [Image.open(f).convert("RGBA") for f in sorted(glob.glob(f"{d}/*.png"))]
montage(load_dir("assets/idle"), "_verify/idle.png", step=8)
montage(load_dir("assets/web"),  "_verify/web.png",  step=8)
print("wrote _verify/idle.png _verify/web.png")

# cleanup intermediate extraction dirs
shutil.rmtree(WORK_A, ignore_errors=True)
shutil.rmtree(WORK_B, ignore_errors=True)
print("done.")

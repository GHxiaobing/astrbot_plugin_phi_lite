# 独立渲染进程：读 stdin 的 JSON，画 B30 图，输出图片路径。
# 之所以单独起进程，是因为在 AstrBot 主进程里 PIL 画日文假名会变方块，独立进程则正常。
import io, json, os, sys, time, hashlib, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONT_DIR = HERE / "resources" / "font"
FONTS = [FONT_DIR / "phi_cn.ttf", FONT_DIR / "NotoSansJP-Regular.otf"]
ILLUS_BASE = "https://somnia.xtower.site/illustration"
COLORS = {"EZ": (126, 217, 87), "HD": (255, 208, 60), "IN": (255, 92, 96), "AT": (70, 70, 78)}

def font(size, path=None):
    p = path or next((f for f in FONTS if f.exists()), None)
    return ImageFont.truetype(str(p), size)

_FACE, _CMAP = {}, {}

def _face(size, path):
    k = (str(path), size)
    if k not in _FACE:
        _FACE[k] = ImageFont.truetype(str(path), size)
    return _FACE[k]

def _cmap(path):
    if path not in _CMAP:
        from fontTools.ttLib import TTFont
        f = TTFont(str(path), fontNumber=0, lazy=True)
        s = set()
        for t in f["cmap"].tables:
            s |= set(t.cmap.keys())
        _CMAP[path] = s
    return _CMAP[path]

def txt(d, xy, text, font=None, fill=None):
    """画字：主字体缺字时逐字换另一套字体补，别留方块。"""
    text = str(text)
    prim = next((f for f in FONTS if f.exists()), None)
    size = getattr(font, "size", 20)
    if prim is None:
        d.text(xy, text, font=font, fill=fill)
        return
    cm = _cmap(prim)
    if all(ord(c) in cm for c in text):
        d.text(xy, text, font=_face(size, prim), fill=fill)
        return
    x, y = xy
    for c in text:
        path = prim
        if ord(c) not in cm:
            path = next((f for f in FONTS if f.exists() and ord(c) in _cmap(f)), prim)
        fa = _face(size, path)
        d.text((x, y), c, font=fa, fill=fill)
        x += d.textlength(c, font=fa)

def cover(key, cache):
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / (hashlib.md5(key.encode()).hexdigest() + ".png")
    if p.exists():
        try: return Image.open(p).convert("RGB")
        except Exception: pass
    try:
        req = urllib.request.Request(ILLUS_BASE + "/" + urllib.parse.quote(key) + ".png",
                                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://lilith.xtower.site/"})
        data = urllib.request.urlopen(req, timeout=12).read()
        p.write_bytes(data)
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None

def main():
    payload = json.load(sys.stdin)
    data, out_dir, cache_dir = payload["data"], Path(payload["out_dir"]), Path(payload["cache_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    save = data["save"]; rec = save["game_record"]
    nick = data.get("nickname") or "Phigros Player"
    total = data["rks"]["totalRks"]; b30 = data["rks"]["b30Charts"]
    norm = lambda s: "".join(str(s).split()).lower()
    idx = {}
    for song, charts in rec.items():
        for c in charts:
            idx[(norm(song), c.get("difficulty"))] = (song, c)

    rows = []
    for it in b30:
        hit = idx.get((norm(it["songId"]), it["difficulty"]))
        if not hit: continue
        song, c = hit
        rows.append({"song": song, "diff": it["difficulty"], "score": c.get("score", 0),
                     "acc": c.get("accuracy", 0), "const": c.get("chart_constant", 0), "rks": it["rks"],
                     "fc": c.get("is_full_combo"),
                     "ap": c.get("score", 0) >= 1000000 or float(c.get("accuracy", 0)) >= 100})
    if not rows:
        print(json.dumps({"ok": False, "error": "没有可渲染的成绩"})); return

    cols, cardW, cardH, gapx, gapy = 3, 480, 150, 16, 12
    rowsN = (len(rows) + cols - 1) // cols
    W, H = 1560, 200 + rowsN * (cardH + gapy) + 70
    img = Image.new("RGB", (W, H), (16, 17, 22))
    d = ImageDraw.Draw(img)
    f = font

    txt(d, (36, 30), f"{nick}({total:.6f})", font=f(42), fill=(255, 255, 255))
    txt(d, (36, 88), "Best30 · 存档 " + str(save.get("updatedAt", ""))[:10], font=f(22), fill=(150, 150, 165))

    x0, y0 = 36, 150
    for i, r in enumerate(rows):
        cx = x0 + (i % cols) * (cardW + gapx)
        cy = y0 + (i // cols) * (cardH + gapy)
        d.rounded_rectangle([cx, cy, cx + cardW, cy + cardH], radius=14, fill=(30, 32, 41))
        im = cover(r["song"], cache_dir)
        if im:
            w0, h0 = im.size; side = min(w0, h0)
            im = im.crop(((w0 - side) // 2, (h0 - side) // 2, (w0 - side) // 2 + side, (h0 - side) // 2 + side))
            thumb = im.resize((cardH, cardH), Image.LANCZOS)
            mask = Image.new("L", (cardH, cardH), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, cardH - 1, cardH - 1], radius=14, fill=255)
            img.paste(thumb, (cx, cy), mask)
            tx = cx + cardH + 14
        else:
            tx = cx + 16
        txt(d, (tx, cy + 10), f"#{i+1}", font=f(19), fill=(150, 152, 164))
        name = r["song"] if len(r["song"]) <= 18 else r["song"][:17] + "…"
        txt(d, (tx + 46, cy + 8), name, font=f(21), fill=(242, 242, 248))
        tag = r["diff"]; tw = d.textlength(tag, font=f(16))
        d.rounded_rectangle([tx, cy + 46, tx + tw + 16, cy + 72], radius=8, fill=COLORS.get(tag, (90, 90, 96)))
        txt(d, (tx + 8, cy + 49), tag, font=f(16), fill=(20, 20, 20) if tag != "AT" else (255, 255, 255))
        txt(d, (tx + tw + 24, cy + 48), f"{float(r['const']):.1f} → {r['rks']:.2f}", font=f(17), fill=(160, 200, 255))
        txt(d, (tx, cy + 84), f"{int(r['score']):,}", font=f(27), fill=(255, 214, 92))
        txt(d, (tx, cy + 118), f"Acc {float(r['acc']):.2f}%", font=f(17), fill=(190, 192, 202))
        if im:
            badge = "AP" if r["ap"] else ("FC" if r["fc"] else None)
            if badge:
                bw = d.textlength(badge, font=f(17)) + 20
                by = cy + cardH - 34
                d.rounded_rectangle([cx + 8, by, cx + 8 + bw, by + 26], radius=7,
                                    fill=(255, 205, 70) if badge == "AP" else (96, 165, 250))
                txt(d, (cx + 18, by + 3), badge, font=f(17), fill=(25, 25, 25) if badge == "AP" else (255, 255, 255))
        if r["ap"]:
            d.rounded_rectangle([cx, cy, cx + cardW, cy + cardH], radius=14, outline=(255, 205, 70), width=4)
        elif r["fc"]:
            d.rounded_rectangle([cx, cy, cx + cardW, cy + cardH], radius=14, outline=(96, 165, 250), width=3)

    txt(d, (36, H - 46), "数据 r0semi.xtower.site · 曲绘 somnia.xtower.site · phi_lite", font=f(18), fill=(110, 112, 122))
    out = out_dir / f"b30_{int(time.time())}.jpg"
    img.save(out, quality=92)
    print(json.dumps({"ok": True, "path": str(out)}))

if __name__ == "__main__":
    main()

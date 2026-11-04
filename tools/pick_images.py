# -*- coding: utf-8 -*-
"""
エラータ：肖像の代わりに使う写真を、Wikimedia Commons から候補として集めるスクリプト

使い方（Windows）
  1. このファイルを好きなフォルダに置く（find_portraits.py と同じフォルダでよい）
  2. python pick_images.py
  3. できた pick.html をブラウザで開いて、使いたい写真の番号を決める
  4. その番号の画像（pick_images フォルダの中）と pick.json をClaudeに渡す

※ requests と pillow を使います（find_portraits.py のときに入れたものです）
"""
import io, json, os, re, time
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "pick.json")
HTML = os.path.join(HERE, "pick.html")
DIR = os.path.join(HERE, "pick_images")
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "ErrataCreditCollector/1.1 (school quiz game; contact via GitHub raylekeiss)"}

# 必ず候補に入れるファイル
FILES = [
    "Forum Comitium.jpg",
    "Forum Romanum panorama 2.jpg",
    "RomanForum01ShiftN gobeirne.jpg",
    "Rome (IT), Forum Romanum -- 2013 -- 3398.jpg",
]
# 検索して候補に足す言葉
QUERIES = ["Comitium Rome", "Comitium Forum Romanum", "Curia Julia Comitium", "Rostra Forum Romanum", "Forum Romanum view"]
PER_QUERY = 12

S = requests.Session()
S.headers.update(UA)


def get(params):
    params = dict(params, format="json", maxlag=5)
    for attempt in range(6):
        try:
            r = S.get(API, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 503):
            time.sleep(max(int(r.headers.get("Retry-After", 0) or 0), 10 * (attempt + 1)))
            continue
        r.raise_for_status()
        d = r.json()
        err = d.get("error")
        if err:
            if "rate" in str(err.get("code", "")) or err.get("code") == "maxlag":
                time.sleep(max(int(r.headers.get("Retry-After", 0) or 0), 15 * (attempt + 1)))
                continue
            raise RuntimeError(f"Wikimedia のエラー：{err.get('code')} {err.get('info', '')}")
        return d
    raise RuntimeError("Wikimedia が混んでいて取得できませんでした")


def fetch(url):
    for attempt in range(6):
        try:
            r = S.get(url, timeout=60)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 503):
            time.sleep(max(int(r.headers.get("Retry-After", 0) or 0), 10 * (attempt + 1)))
            continue
        r.raise_for_status()
        return r.content
    raise RuntimeError("画像を取得できませんでした")


def main():
    os.makedirs(DIR, exist_ok=True)
    titles = ["File:" + f for f in FILES]
    for q in QUERIES:
        d = get({"action": "query", "list": "search", "srsearch": q, "srnamespace": 6, "srlimit": PER_QUERY})
        for h in d.get("query", {}).get("search", []):
            if h["title"] not in titles and re.search(r"\.(jpe?g|png)$", h["title"], re.I):
                titles.append(h["title"])
        time.sleep(0.5)
    print(f"候補 {len(titles)} 枚の情報を集めます")
    infos = []
    for i in range(0, len(titles), 40):
        d = get({"action": "query", "titles": "|".join(titles[i:i + 40]), "prop": "imageinfo",
                 "iiprop": "extmetadata|url|size|mime", "iiurlwidth": 900})
        for p in d.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("thumburl") or not str(ii.get("mime", "")).startswith("image/"):
                continue
            m = ii.get("extmetadata", {})
            val = lambda k: (m.get(k, {}).get("value") or "").strip()
            artist = re.sub(r"<[^>]+>", "", val("Artist")).strip() or "不明"
            fn = p["title"].split(":", 1)[1]
            infos.append({
                "file": fn,
                "license": val("LicenseShortName") or "不明",
                "author": " ".join(artist.split()),
                "url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/File:" + fn.replace(" ", "_"),
                "desc": " ".join(re.sub(r"<[^>]+>", "", val("ImageDescription")).split())[:200],
                "thumb": ii["thumburl"],
            })
    rows = []
    for n, c in enumerate(infos, 1):
        try:
            raw = fetch(c["thumb"])
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            c["no"] = n
            c["saved"] = f"{n:02d}.jpg"
            im.save(os.path.join(DIR, c["saved"]), quality=92)
            print(f"[{n}/{len(infos)}] {c['file']}（{c['license']}）")
            rows.append(f'<div class="c"><img src="pick_images/{c["saved"]}"><p><b>{n}</b>　{c["license"]}<br>'
                        f'{c["file"]}<br><small>{c["desc"]}</small></p></div>')
        except Exception as e:
            print(f"[{n}/{len(infos)}] {c['file']}：取得できず（{e}）")
        time.sleep(0.3)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump([c for c in infos if c.get("saved")], f, ensure_ascii=False, indent=1)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'><title>写真の候補</title><style>body{font-family:sans-serif}"
                ".c{display:inline-block;vertical-align:top;width:300px;margin:8px;font-size:12px}"
                ".c img{width:300px;height:220px;object-fit:cover}</style><h1>写真の候補</h1>" + "".join(rows))
    print("おわり。pick.html を開いて番号を決め、その画像（pick_images フォルダ）と pick.json をClaudeに渡してください。")


if __name__ == "__main__":
    main()

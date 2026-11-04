# -*- coding: utf-8 -*-
"""
エラータ：出典がわからない肖像を、Wikimedia Commons から探すスクリプト

ゲームに入っている肖像（GitHub Pages の画像）と、コモンズの検索で出てきた画像を
1枚ずつ見比べて、似ているものを探します。肖像は切り抜いて使っているので、
「コモンズの画像の一部と一致するか」で比べます。

使い方（Windows）
  1. このファイルを好きなフォルダに置く
  2. そのフォルダで  pip install requests pillow numpy  を一度だけ実行
  3. python find_portraits.py
  4. できた found.json をClaudeに渡す
     （found.html をブラウザで開くと、見比べた結果を目で確かめられます）

途中で止まっても、もう一度実行すれば、終わった人は飛ばして続きから探します。
"""
import io, json, os, re, time
import requests
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "found.json")
HTML = os.path.join(HERE, "found.html")
THUMBS = os.path.join(HERE, "found_thumbs")
BASE = "https://raylekeiss.github.io/errata/"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "ErrataCreditCollector/1.1 (school quiz game; contact via GitHub raylekeiss)"}

# 人物名 : (ゲームの肖像, [コモンズで検索する言葉])
PEOPLE = {
    "ホルテンシウス": ("img/722fe983de18.webp", ["Quintus Hortensius", "Hortensius bust", "Hortensius Hortalus"]),
    "冒頓単于": ("img/442aedf24fd4.webp", ["Modu Chanyu", "冒顿单于", "冒頓單于", "Modun statue"]),
    "張儀": ("img/bb1772ceb92c.webp", ["張儀", "张仪", "Zhang Yi Warring States"]),
    "李元昊": ("img/9b85d2715098.webp", ["李元昊", "Western Xia tombs", "西夏王陵", "Western Xia Imperial Tombs"]),
    "荀子": ("img/d81d9197002f.webp", ["荀子", "Xunzi"]),
    "荘子": ("img/4f82e77aeabb.webp", ["莊子", "庄子", "Zhuangzi", "Zhuang Zhou"]),
    "陳勝": ("img/2585a35543f1.webp", ["陳勝", "陈胜", "Chen Sheng", "陈胜吴广"]),
    "カーリダーサ": ("img/b81cbf6e27bd.webp", ["Kalidasa statue", "Kalidas statue", "Kalidasa"]),
    "モンテ＝コルヴィノ": ("img/e05730724f42.webp", ["Montecorvino", "Giovanni da Montecorvino", "John of Montecorvino"]),
}

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


def fetch_image(url):
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
        return Image.open(io.BytesIO(r.content)).convert("RGB"), r.content
    raise RuntimeError("画像を取得できませんでした")


def search_files(q, limit=25):
    d = get({"action": "query", "list": "search", "srsearch": q, "srnamespace": 6, "srlimit": limit})
    return [h["title"] for h in d.get("query", {}).get("search", [])]


def file_infos(titles):
    out = {}
    for i in range(0, len(titles), 40):
        d = get({"action": "query", "titles": "|".join(titles[i:i + 40]), "prop": "imageinfo",
                 "iiprop": "extmetadata|url|mime", "iiurlwidth": 240})
        for p in d.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("thumburl") or not str(ii.get("mime", "")).startswith("image/"):
                continue
            m = ii.get("extmetadata", {})
            val = lambda k: (m.get(k, {}).get("value") or "").strip()
            artist = re.sub(r"<[^>]+>", "", val("Artist")).strip() or "不明"
            fn = p["title"].split(":", 1)[1]
            out[fn] = {
                "file": fn,
                "license": val("LicenseShortName") or "不明",
                "author": " ".join(artist.split()),
                "url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/File:" + fn.replace(" ", "_"),
                "thumb": ii["thumburl"],
            }
    return out


def gray(im, w):
    h = max(1, round(im.height * w / im.width))
    return np.asarray(im.convert("L").resize((w, h), Image.LANCZOS), dtype=np.float32)


def match(game, cand):
    """ゲームの肖像が、候補の画像のどこかを切り抜いたものかどうか（1に近いほど一致）"""
    C = gray(cand, 120)
    best = -1.0
    for f in (1.0, .92, .85, .78, .7, .62, .55, .48, .4, .33):
        gw = round(120 * f)
        G = gray(game, gw)
        gh, cw = G.shape[0], C.shape[1]
        if gh > C.shape[0] or gh < 8:
            continue
        g = G - G.mean()
        gn = np.sqrt((g * g).sum()) + 1e-6
        step = 2
        for y in range(0, C.shape[0] - gh + 1, step):
            for x in range(0, cw - gw + 1, step):
                c = C[y:y + gh, x:x + gw]
                c = c - c.mean()
                v = float((c * g).sum() / (np.sqrt((c * c).sum()) * gn + 1e-6))
                if v > best:
                    best = v
    return best


def save_html(results):
    rows = []
    for name, r in results.items():
        cells = [f'<td><b>{name}</b><br><img src="{BASE}{PEOPLE[name][0]}"><br>ゲームの肖像</td>']
        for i, c in enumerate(r.get("top", [])):
            mark = "★いちばん近い" if i == 0 else ""
            cells.append(f'<td><img src="found_thumbs/{c["thumbfile"]}"><br>{i + 1}. 一致度 {c["score"]:.2f} {mark}'
                         f'<br><small>{c["file"]}</small></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    html = ("<!doctype html><meta charset='utf-8'><title>肖像の候補</title><style>body{font-family:sans-serif}"
            "td{vertical-align:top;width:170px;font-size:12px;padding:6px;border-bottom:1px solid #ccc}"
            "img{max-width:160px;max-height:200px}</style><h1>肖像の候補</h1>"
            "<p>一致度は0.9以上ならほぼ同じ画像、0.6以下なら別の画像です。</p><table>" + "".join(rows) + "</table>")
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    os.makedirs(THUMBS, exist_ok=True)
    results = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            results = json.load(f)
    todo = [n for n in PEOPLE if n not in results or not results[n].get("top")]
    print(f"探す人数：{len(todo)}人")
    for i, name in enumerate(todo, 1):
        path, queries = PEOPLE[name]
        try:
            game, _ = fetch_image(BASE + path)
            titles = []
            for q in queries:
                for t in search_files(q):
                    if t not in titles:
                        titles.append(t)
                time.sleep(0.5)
            infos = file_infos(titles)
            print(f"[{i}/{len(todo)}] {name}：候補 {len(infos)} 枚を見比べます")
            scored = []
            for j, (fn, meta) in enumerate(infos.items()):
                try:
                    im, raw = fetch_image(meta["thumb"])
                except Exception as e:
                    print(f"    {fn}：取得できず（{e}）")
                    continue
                sc = match(game, im)
                tf = f"{abs(hash((name, fn))) % 10**10}.jpg"
                im.save(os.path.join(THUMBS, tf), quality=85)
                scored.append(dict(meta, score=round(sc, 3), thumbfile=tf))
                time.sleep(0.3)
            scored.sort(key=lambda c: -c["score"])
            results[name] = {"top": scored[:6]}
            if scored:
                b = scored[0]
                print(f"    いちばん近い：{b['file']}（一致度 {b['score']:.2f}）")
            else:
                print("    候補が見つかりませんでした")
        except Exception as e:
            print(f"[{i}/{len(todo)}] {name}：エラー {e}")
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        save_html(results)
    print("おわり。found.json をClaudeに渡してください（found.html で結果を目で確かめられます）。")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
エラータ：肖像画の出典情報だけを集め直すスクリプト（画像はダウンロードしません）

使い方（Windows）
  1. このファイルと person_list.csv と credits.json を同じフォルダに置く
  2. そのフォルダで  pip install requests  を一度だけ実行
  3. python get_credits.py
  4. credits.json が更新されるので、それをClaudeに渡す

すでに出典がわかっている人物（credits.json にある人物）は飛ばします。
途中で止まっても、もう一度実行すれば続きから集めます。
"""
import csv, json, os, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "person_list.csv")
OUT = os.path.join(HERE, "credits.json")
UA = {"User-Agent": "ErrataCreditCollector/1.0 (school quiz game; contact via GitHub raylekeiss)"}

# person_list.csv に入っていない人物（中世の巻で出典が取れなかった人）
EXTRA = {
    "カール＝マルテル": "Charles Martel",
    "ウマル": "Umar",
    "フワーリズミー": "Muhammad ibn Musa al-Khwarizmi",
    "ジョン": "John, King of England",
    "トマス＝アクィナス": "Thomas Aquinas",
    "エラスムス": "Erasmus",
}

S = requests.Session()
S.headers.update(UA)


def get(url, params):
    params = dict(params, format="json", maxlag=5)
    for attempt in range(6):
        try:
            r = S.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 503) or "maxlag" in r.text[:200]:
            wait = int(r.headers.get("Retry-After", 0) or 0)
            time.sleep(max(wait, 10 * (attempt + 1)))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Wikimedia が混んでいて取得できませんでした")


def p18_file(enwiki_title):
    """英語版Wikipediaの記事名 → Wikidataの代表画像(P18)のファイル名"""
    d = get("https://www.wikidata.org/w/api.php",
            {"action": "wbgetentities", "sites": "enwiki", "titles": enwiki_title,
             "props": "claims", "redirects": "yes"})
    for qid, ent in d.get("entities", {}).items():
        if qid.startswith("Q"):
            for c in ent.get("claims", {}).get("P18", []):
                v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if v:
                    return v, qid
            return None, qid
    return None, None


def pageimage_file(enwiki_title):
    """P18がないとき：英語版Wikipediaの記事の代表画像"""
    d = get("https://en.wikipedia.org/w/api.php",
            {"action": "query", "titles": enwiki_title, "prop": "pageimages",
             "piprop": "name", "redirects": 1})
    for p in d.get("query", {}).get("pages", {}).values():
        if p.get("pageimage"):
            return p["pageimage"]
    return None


def file_meta(filename):
    d = get("https://commons.wikimedia.org/w/api.php",
            {"action": "query", "titles": "File:" + filename, "prop": "imageinfo",
             "iiprop": "extmetadata|url"})
    for p in d.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        m = ii.get("extmetadata", {})
        val = lambda k: (m.get(k, {}).get("value") or "").strip()
        import re
        artist = re.sub(r"<[^>]+>", "", val("Artist")).strip() or "不明"
        return {
            "file": filename,
            "license": val("LicenseShortName") or "不明",
            "author": " ".join(artist.split()),
            "url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/File:" + filename.replace(" ", "_"),
        }
    return None


def main():
    credits = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            credits = json.load(f)
    people = []
    with open(CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            people.append((row["人物名"], row["英語版Wikipedia名"]))
    people += list(EXTRA.items())

    todo = [(n, t) for n, t in people if n not in credits]
    print(f"出典を集める人数：{len(todo)}人（すでにわかっている人：{len(credits)}人）")
    for i, (name, title) in enumerate(todo, 1):
        try:
            fn, qid = p18_file(title)
            how = "Wikidata"
            if not fn:
                fn = pageimage_file(title)
                how = "Wikipedia記事の画像"
            if not fn:
                print(f"[{i}/{len(todo)}] {name}：画像が見つからない（手で確認してください）")
                continue
            meta = file_meta(fn)
            if not meta:
                print(f"[{i}/{len(todo)}] {name}：ファイル情報が取れない")
                continue
            meta["check"] = how != "Wikidata"
            credits[name] = meta
            print(f"[{i}/{len(todo)}] {name}：{meta['license']}（{how}）")
        except Exception as e:
            print(f"[{i}/{len(todo)}] {name}：エラー {e}")
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(credits, f, ensure_ascii=False, indent=1)
        time.sleep(0.5)
    print("おわり。credits.json をClaudeに渡してください。")


if __name__ == "__main__":
    main()

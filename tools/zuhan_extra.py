# -*- coding: utf-8 -*-
"""
エラータ：図版の残り10枠（絵画・彫刻など）の写真を集めて、webp まで作る

使い方（リポジトリのいちばん上のフォルダで。Windows でも可。requests と Pillow が必要）
  python tools/zuhan_extra.py
    → 枠ごとに Wikimedia Commons を検索して候補を最大6枚、900px の webp にする
       tools/zuhan_out/キー.webp            … 1番目の候補（とりあえずの採用）
       tools/zuhan_out/zuhan_credits.json   … 採用した写真の出典
       tools/zuhan_out/候補/キー/01.webp …   … 候補すべて
       tools/zuhan_out/候補/一覧.html       … 候補をブラウザで見比べる用

  候補の2番目などに替えたいとき
  python tools/zuhan_extra.py --use monalisa 03
    → 候補/monalisa/03.webp を採用に差し替える（出典も書きかわる）

  特定の枠だけ集め直すとき
  python tools/zuhan_extra.py monalisa milo

  できた zuhan_out フォルダを zip にして Claude に渡す（または python3 tools/apply_zuhan.py tools/zuhan_out）
"""
import html, io, json, os, re, sys, time, urllib.parse

import requests
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "zuhan_out")
CAND = os.path.join(OUT, "候補")
CPATH = os.path.join(OUT, "zuhan_credits.json")
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "ErrataCreditCollector/1.1 (school quiz game; contact via GitHub raylekeiss)"}
OUT_SIZE = 900
PER_SLOT = 6

# 枠のキー: (名前, 検索する言葉。上から順に候補に入る)
SLOTS = {
    'akbarnama': ('ムガル絵画（『アクバル＝ナーマ』の挿絵）', ['Akbarnama painting', 'Akbarnama miniature Akbar']),
    'primavera': ('ボッティチェリ「春（プリマヴェーラ）」', ['Botticelli Primavera Uffizi', 'Botticelli Primavera']),
    'monalisa': ('レオナルド＝ダ＝ヴィンチ「モナ＝リザ」', ['Mona Lisa by Leonardo da Vinci C2RMF', 'Mona Lisa Leonardo']),
    'lastjudgment': ('ミケランジェロ「最後の審判」', ['Michelangelo Last Judgment Sistine Chapel', 'Last Judgement Michelangelo']),
    'ghent': ('ファン＝アイク兄弟「ヘント（ガン）の祭壇画」', ['Ghent Altarpiece open', 'Ghent Altarpiece van Eyck']),
    'fourapostles': ('デューラー「四人の使徒」', ['Dürer Four Apostles', 'Albrecht Dürer Vier Apostel']),
    'erasmus': ('ホルバイン「エラスムス像」', ['Holbein Erasmus portrait', 'Hans Holbein Erasmus Rotterdam']),
    'rubens': ('ルーベンス「キリスト降架」', ['Rubens Descent from the Cross Antwerp', 'Rubens Kruisafneming']),
    'tutankhamun': ('ツタンカーメン王の黄金のマスク', ['Tutankhamun mask', 'mask of Tutankhamun Cairo']),
    'milo': ('「ミロのヴィーナス」', ['Venus de Milo Louvre', 'Aphrodite of Milos']),
}

S = requests.Session()
S.headers.update(UA)


def _get(url, **kw):
    """混んでいるときは待って、6回まで取り直す"""
    for a in range(6):
        try:
            r = S.get(url, timeout=60, **kw)
        except requests.RequestException as e:
            print(f"   通信エラー（{e.__class__.__name__}）。{5 * (a + 1)}秒待って再試行")
            time.sleep(5 * (a + 1))
            continue
        if r.status_code in (429, 503) or (r.status_code == 200 and "params" in kw and not r.text.lstrip().startswith("{")):
            w = max(int(r.headers.get("Retry-After", 0) or 0), 15 * (a + 1))
            print(f"   混んでいるので {w} 秒待ちます")
            time.sleep(w)
            continue
        return r
    return None


def api(params):
    r = _get(API, params=dict(params, format="json", maxlag=5))
    if r is None or r.status_code != 200:
        raise RuntimeError("Wikimedia の検索に失敗しました。しばらく待ってからもう一度実行してください")
    return r.json()


def search(queries):
    titles = []
    for q in queries:
        d = api({"action": "query", "list": "search", "srsearch": q + " filetype:bitmap", "srnamespace": 6, "srlimit": 12})
        for h in d.get("query", {}).get("search", []):
            t = h["title"]
            if t not in titles and re.search(r"\.(jpe?g|png|webp|tiff?)$", t, re.I):
                titles.append(t)
        time.sleep(0.5)
    return titles


def info(titles):
    d = api({"action": "query", "titles": "|".join(titles), "prop": "imageinfo",
             "iiprop": "extmetadata|url|mime|size", "iiurlwidth": 960})
    norm = {n["to"]: n["from"] for n in d.get("query", {}).get("normalized", [])}
    out = {}
    for p in d.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime", "")).startswith("image/"):
            continue
        m = ii.get("extmetadata", {})
        val = lambda k: (m.get(k, {}).get("value") or "").strip()
        fn = norm.get(p["title"], p["title"]).split(":", 1)[1]
        out[fn] = {
            "f": fn,
            "a": " ".join(html.unescape(re.sub(r"<[^>]+>", " ", val("Artist"))).split()) or "不明",
            "lic": val("LicenseShortName") or "不明",
            "url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(fn.replace(" ", "_")),
            "_thumb": ii.get("thumburl"), "_orig": ii.get("url"), "_size": f"{ii.get('width')}×{ii.get('height')}",
        }
    return out


def to_webp(c, path):
    for u in (c.get("_thumb"), c.get("_orig")):
        if not u:
            continue
        r = _get(u)
        if r is None or r.status_code != 200:
            continue
        try:
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            continue
        im.thumbnail((OUT_SIZE, OUT_SIZE))
        im.save(path, "WEBP", quality=74)
        return True
    return False


def load_credits():
    if os.path.exists(CPATH):
        with open(CPATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_credits(cr):
    with open(CPATH, "w", encoding="utf-8") as f:
        json.dump(cr, f, ensure_ascii=False, indent=1)


def write_html():
    rows = []
    for k, (name, _) in SLOTS.items():
        p = os.path.join(CAND, k, "candidates.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            cs = json.load(f)
        e = html.escape
        cards = "".join(f'<figure><img src="{e(k)}/{e(c["no"])}.webp" loading="lazy"><figcaption><b>{e(c["no"])}</b>　{e(c["lic"])}　{e(c["_size"])}<br>{e(c["f"])}</figcaption></figure>' for c in cs)
        rows.append(f'<section><h2>{e(name)} <small>{e(k)}</small></h2><div class="g">{cards}</div>'
                    f'<p class="cmd">差し替え：python tools/zuhan_extra.py --use {e(k)} 番号</p></section>')
    page = ("<!doctype html><meta charset='utf-8'><title>図版の候補</title><style>body{font-family:sans-serif;margin:16px;background:#f4f1e8}"
            "section{background:#fff;padding:10px 12px;margin:0 0 16px;border:1px solid #ccc}h2{font-size:16px;margin:0 0 8px}h2 small{color:#888;font-weight:normal}"
            ".g{display:flex;flex-wrap:wrap;gap:8px}figure{margin:0;width:230px}img{width:100%;height:170px;object-fit:contain;background:#222}"
            "figcaption{font-size:11px;word-break:break-all}.cmd{font-size:12px;color:#555;margin:6px 0 0}</style>"
            "<h1>図版の候補（01 が採用中）</h1><p>説明板や文字が写っている写真は、答えのヒントになるので避けてください。</p>" + "".join(rows))
    with open(os.path.join(CAND, "一覧.html"), "w", encoding="utf-8") as f:
        f.write(page)


def collect(keys):
    os.makedirs(CAND, exist_ok=True)
    cr = load_credits()
    for n, k in enumerate(keys, 1):
        name, queries = SLOTS[k]
        print(f"[{n}/{len(keys)}] {k}（{name}）")
        titles = search(queries)[:PER_SLOT * 2]
        if not titles:
            print("   候補が見つかりませんでした")
            continue
        inf = info(titles)
        d = os.path.join(CAND, k)
        os.makedirs(d, exist_ok=True)
        keep = []
        for t in titles:
            c = inf.get(t.split(":", 1)[1])
            if not c:
                continue
            no = f"{len(keep) + 1:02d}"
            if to_webp(c, os.path.join(d, no + ".webp")):
                c["no"] = no
                keep.append(c)
                print(f"   {no}  {c['lic']}  {c['f']}")
            if len(keep) >= PER_SLOT:
                break
            time.sleep(1)
        with open(os.path.join(d, "candidates.json"), "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=1)
        if keep:
            use(k, "01", cr, quiet=True)
        save_credits(cr)
    write_html()
    print(f"\nおわり。tools/zuhan_out/候補/一覧.html で候補を確かめてください（01 を採用中）。")


def use(k, no, cr=None, quiet=False):
    own = cr is None
    if own:
        cr = load_credits()
    d = os.path.join(CAND, k)
    with open(os.path.join(d, "candidates.json"), encoding="utf-8") as f:
        cs = {c["no"]: c for c in json.load(f)}
    no = f"{int(no):02d}"
    if no not in cs:
        print(f"{k} に候補 {no} はありません（{', '.join(cs)}）")
        return
    c = cs[no]
    with open(os.path.join(d, no + ".webp"), "rb") as s, open(os.path.join(OUT, k + ".webp"), "wb") as t:
        t.write(s.read())
    cr[k] = {"f": c["f"], "a": c["a"], "lic": c["lic"], "url": c["url"]}
    if own:
        save_credits(cr)
    if not quiet:
        print(f"{k}：候補 {no}（{c['f']}）を採用しました")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--use":
        if len(args) < 3:
            print("使い方：python tools/zuhan_extra.py --use キー 番号")
            return
        use(args[1], args[2])
        return
    keys = args or list(SLOTS)
    bad = [k for k in keys if k not in SLOTS]
    if bad:
        print("知らない枠：", ", ".join(bad), "\n使える枠：", ", ".join(SLOTS))
        return
    collect(keys)


if __name__ == "__main__":
    main()

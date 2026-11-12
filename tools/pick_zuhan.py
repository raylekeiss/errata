# -*- coding: utf-8 -*-
"""
エラータ：問題演習「図版・地図」の写真を、Wikimedia Commons から選んで書き出すスクリプト

使い方（Windows）
  【1】候補を集める
      python pick_zuhan.py              … すべての枠
      python pick_zuhan.py giza lascaux … 枠を指定（キーは下の SLOTS の左側）
     → pick_zuhan.html ができるので、ブラウザで開く
  【2】ブラウザで、枠ごとに使いたい写真をクリックして選ぶ（もう一度クリックで取り消し）
     → いちばん下の「選んだ結果を保存」で zuhan_choice.json がダウンロードされる
       （ダウンロードフォルダに入るので、このスクリプトと同じフォルダに移す）
  【3】選んだ写真を書き出す
      python pick_zuhan.py --make zuhan_choice.json
     → zuhan_out フォルダに「キー.webp」と zuhan_credits.json ができる
  【4】zuhan_out の中身をまとめて Claude に渡す
     （GitHub に直接入れる場合は、webp を img/zuhan/ に置き、zuhan_credits.json を Claude に渡す）

※ requests と pillow を使います（find_portraits.py のときに入れたものです）
※ 説明板・文字・ファイル名が写っている写真は答えのヒントになるので避ける。有名すぎる角度より、特徴が見える写真がおすすめ
"""
import html, io, json, os, re, sys, time
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "pick_zuhan.html")
META = os.path.join(HERE, "pick_zuhan.json")
DIR = os.path.join(HERE, "pick_zuhan")
OUT = os.path.join(HERE, "zuhan_out")
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "ErrataCreditCollector/1.1 (school quiz game; contact via GitHub raylekeiss)"}
PER_QUERY = 8      # 1つの検索語から取る候補の数
MAX_PER_SLOT = 14  # 1つの枠の候補の上限
OUT_SIZE = 900     # 書き出す写真の長い辺（px）

# 枠のキー: (名前, 検索する言葉)。名前は答えたあとにだけ表示される
SLOTS = {
    'sarnath': ('サールナートの仏坐像', ['Seated Buddha Sarnath Museum Gupta', 'Sarnath Buddha preaching first sermon statue']),
    'gandhara': ('ガンダーラの仏立像', ['Gandhara standing Buddha', 'Gandhara Buddha Tokyo National Museum']),
    'yungang': ('雲崗石窟の大仏', ['Yungang Grottoes cave 20 Buddha', 'Yungang Grottoes Buddha']),
    'longmen': ('竜門石窟の盧舎那仏', ['Longmen Fengxian Vairocana', 'Longmen Grottoes Vairocana']),
    'gothic': ('ケルン大聖堂（ゴシック）', ['Kölner Dom Westfassade', 'Cologne Cathedral facade']),
    'pisa': ('ピサ大聖堂（ロマネスク）', ['Pisa Cathedral facade', 'Duomo di Pisa facade']),
    'hagia': ('ハギア＝ソフィア聖堂（ビザンツ）', ['Hagia Sophia exterior', 'Hagia Sophia Istanbul']),
    'stpeter': ('サン＝ピエトロ大聖堂（ルネサンス）', ["St. Peter's Basilica facade dome", 'Petersdom Rom']),
    'angkor': ('アンコール＝ワット', ['Angkor Wat', 'Angkor Wat sunrise west']),
    'borobudur': ('ボロブドゥール', ['Borobudur temple', 'Borobudur aerial']),
    'watteau': ('ヴァトー「シテール島への巡礼」（ロココ）', ['Watteau Embarkation for Cythera']),
    'venus': ('ボッティチェリ「ヴィーナスの誕生」', ['Botticelli Birth of Venus']),
    'nightwatch': ('レンブラント「夜警」', ['Rembrandt Night Watch']),
    'david': ('ダヴィド「ナポレオンの戴冠式」（新古典主義）', ['David Coronation of Napoleon']),
    'lascaux': ('ラスコーの洞窟壁画', ['Lascaux painting', 'Lascaux cave horse']),
    'giza': ('ギザの三大ピラミッド', ['Giza pyramids', 'Pyramids of Giza']),
    'hammurabi': ('ハンムラビ法典碑', ['Code of Hammurabi stele Louvre', 'Hammurabi stele']),
    'cuneiform': ('楔形文字の粘土板', ['cuneiform tablet', 'cuneiform clay tablet']),
    'hieroglyph': ('神聖文字（ヒエログリフ）', ['Egyptian hieroglyphs relief', 'hieroglyphs wall']),
    'oracle': ('甲骨文字', ['oracle bone Shang', 'oracle bone inscription']),
    'indusseal': ('インダス文字の印章', ['Indus seal unicorn', 'Indus valley seal']),
    'rosetta': ('ロゼッタ＝ストーン', ['Rosetta Stone British Museum']),
    'nefertiti': ('ネフェルトイティの胸像（アマルナ美術）', ['Nefertiti bust Berlin', 'Nefertiti bust Neues Museum']),
    'persepolis': ('ペルセポリスの宮殿跡', ['Persepolis Apadana', 'Persepolis ruins']),
    'caitao': ('彩文土器（仰韶文化）', ['Yangshao painted pottery', 'Yangshao culture pottery']),
    'heitao': ('黒陶（竜山文化）', ['Longshan black pottery', 'Longshan culture eggshell pottery']),
    'ding': ('殷の青銅器', ['Shang dynasty bronze ding', 'Shang bronze vessel']),
    'sancai': ('唐三彩', ['Tang sancai', 'sancai horse Tang']),
    'teotihuacan': ('テオティワカンの「太陽のピラミッド」', ['Teotihuacan Pyramid of the Sun']),
    'machupicchu': ('マチュ＝ピチュ', ['Machu Picchu']),
    'chichen': ('チチェン＝イツァのピラミッド（マヤ）', ['Chichen Itza El Castillo']),
    'olmec': ('オルメカの巨石人頭像', ['Olmec colossal head']),
    'scythian': ('スキタイの金製品', ['Scythian gold', 'Scythian gold pectoral']),
    'terracotta': ('兵馬俑', ['Terracotta Army', 'Terracotta Warriors pit 1']),
    'banliang': ('半両銭', ['Ban Liang coin', 'Banliang Qin coin']),
    'sanchi': ('サーンチーのストゥーパ', ['Sanchi Stupa']),
    'lion': ('アショーカ王の石柱の獅子柱頭', ['Lion Capital of Ashoka Sarnath']),
    'ajanta': ('アジャンター石窟の壁画', ['Ajanta cave painting Padmapani', 'Ajanta murals']),
    'dongson': ('ドンソン文化の銅鼓', ['Dong Son drum', 'Ngoc Lu drum']),
    'naqsh': ('ナクシェ＝ロスタムの戦勝浮き彫り', ['Naqsh-e Rustam Shapur Valerian relief']),
    'parthenon': ('パルテノン神殿', ['Parthenon Athens', 'Parthenon east']),
    'doric': ('ドーリア式の柱頭', ['Doric capital', 'Doric column capital']),
    'ionic': ('イオニア式の柱頭', ['Ionic capital', 'Ionic order capital']),
    'corinthian': ('コリント式の柱頭', ['Corinthian capital', 'Corinthian order capital']),
    'papyrus': ('エジプトのパピルス柱（カルナック）', ['Karnak hypostyle hall columns', 'papyrus column Karnak']),
    'laocoon': ('ラオコーン群像', ['Laocoön and His Sons Vatican']),
    'colosseum': ('コロッセウム', ['Colosseum Rome exterior', 'Colosseo']),
    'pontdugard': ('ポン＝デュ＝ガール（水道橋）', ['Pont du Gard']),
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


def info(titles, width):
    """ファイル名の一覧 → 作者・ライセンス・縮小画像のURL"""
    out = []
    for i in range(0, len(titles), 40):
        d = get({"action": "query", "titles": "|".join(titles[i:i + 40]), "prop": "imageinfo",
                 "iiprop": "extmetadata|url|size|mime", "iiurlwidth": width})
        for p in d.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("thumburl") or not str(ii.get("mime", "")).startswith("image/"):
                continue
            m = ii.get("extmetadata", {})
            val = lambda k: (m.get(k, {}).get("value") or "").strip()
            artist = html.unescape(re.sub(r"<[^>]+>", " ", val("Artist")))
            fn = p["title"].split(":", 1)[1]
            out.append({
                "file": fn,
                "license": val("LicenseShortName") or "不明",
                "author": " ".join(artist.split()) or "不明",
                "url": ii.get("descriptionurl") or "https://commons.wikimedia.org/wiki/File:" + fn.replace(" ", "_"),
                "desc": " ".join(html.unescape(re.sub(r"<[^>]+>", " ", val("ImageDescription"))).split())[:160],
                "size": f"{ii.get('width')}×{ii.get('height')}",
                "thumb": ii["thumburl"],
            })
        time.sleep(0.5)
    order = {t.split(":", 1)[1]: n for n, t in enumerate(titles)}
    return sorted(out, key=lambda c: order.get(c["file"], 999))


def collect(keys):
    os.makedirs(DIR, exist_ok=True)
    meta = {}
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            meta = json.load(f)
    for k in keys:
        name, queries = SLOTS[k]
        titles = []
        for q in queries:
            d = get({"action": "query", "list": "search", "srsearch": q + " filetype:bitmap", "srnamespace": 6, "srlimit": PER_QUERY})
            for h in d.get("query", {}).get("search", []):
                if h["title"] not in titles and re.search(r"\.(jpe?g|png|webp|tiff?)$", h["title"], re.I):
                    titles.append(h["title"])
            time.sleep(0.5)
        cands = info(titles[:MAX_PER_SLOT], 400)
        os.makedirs(os.path.join(DIR, k), exist_ok=True)
        keep = []
        for n, c in enumerate(cands, 1):
            try:
                im = Image.open(io.BytesIO(fetch(c["thumb"]))).convert("RGB")
                c["saved"] = f"{k}/{n:02d}.jpg"
                im.save(os.path.join(DIR, c["saved"]), quality=88)
                keep.append(c)
            except Exception as e:
                print(f"   {c['file']}：取得できず（{e}）")
            time.sleep(0.3)
        meta[k] = keep
        print(f"[{keys.index(k) + 1}/{len(keys)}] {k}（{name}）：候補 {len(keep)} 枚")
        with open(META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    write_html(meta)
    print("おわり。pick_zuhan.html を開いて写真を選んでください。")


def write_html(meta):
    e = lambda s: html.escape(str(s))
    secs = []
    for k in SLOTS:
        if k not in meta:
            continue
        name = SLOTS[k][0]
        cards = "".join(
            f'<button class="c" data-k="{e(k)}" data-f="{e(c["file"])}"><img src="pick_zuhan/{e(c["saved"])}" loading="lazy">'
            f'<span class="l">{e(c["license"])}　{e(c["size"])}</span><span class="f">{e(c["file"])}</span><span class="d">{e(c["desc"])}</span></button>'
            for c in meta[k])
        secs.append(f'<section id="s-{e(k)}"><h2>{e(name)}<small>{e(k)}</small><span class="pick" id="p-{e(k)}">未選択</span></h2><div class="g">{cards or "候補が見つかりませんでした"}</div></section>')
    page = """<!doctype html><meta charset="utf-8"><title>図版の写真を選ぶ</title>
<style>body{font-family:sans-serif;margin:16px;background:#f4f1e8;color:#222}h1{font-size:20px}
section{background:#fff;margin:0 0 18px;padding:10px 12px;border:1px solid #ccc}h2{font-size:16px;margin:0 0 8px;display:flex;gap:10px;align-items:baseline}
h2 small{color:#888;font-weight:normal}.pick{margin-left:auto;font-size:13px;color:#b5302a}.pick.on{color:#2f6b46}
.g{display:flex;flex-wrap:wrap;gap:8px}.c{width:220px;text-align:left;border:3px solid transparent;background:#f8f8f6;padding:4px;cursor:pointer;font:inherit}
.c img{width:100%;height:160px;object-fit:contain;background:#222;display:block}.c span{display:block;font-size:11px;line-height:1.35;word-break:break-all}
.c .l{font-weight:bold;margin-top:3px}.c .d{color:#777;max-height:4em;overflow:hidden}.c.on{border-color:#2f6b46;background:#e3f0e6}
#bar{position:sticky;bottom:0;background:#1c2540;color:#fff;padding:10px;display:flex;gap:12px;align-items:center}#bar button{font-size:15px;padding:8px 16px}</style>
<h1>図版の写真を選ぶ</h1><p>枠ごとに1枚クリックして選びます（もう一度クリックで取り消し）。選ばなかった枠は今の写真のまま変わりません。<br>説明板や文字が写っている写真は、答えのヒントになるので避けてください。</p>
""" + "".join(secs) + """<div id="bar"><span id="n"></span><button id="save">選んだ結果を保存（zuhan_choice.json）</button></div>
<script>
const KEY='errata_zuhan_choice';let C={};try{C=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function draw(){document.querySelectorAll('.c').forEach(b=>b.classList.toggle('on',C[b.dataset.k]===b.dataset.f));
 document.querySelectorAll('.pick').forEach(p=>{const k=p.id.slice(2);p.textContent=C[k]?'選択済み':'未選択';p.classList.toggle('on',!!C[k])});
 document.getElementById('n').textContent=Object.keys(C).length+' 枠を選択中';try{localStorage.setItem(KEY,JSON.stringify(C))}catch(e){}}
document.querySelectorAll('.c').forEach(b=>b.onclick=()=>{const k=b.dataset.k,f=b.dataset.f;if(C[k]===f)delete C[k];else C[k]=f;draw()});
document.getElementById('save').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(C,null,1)],{type:'application/json'}));a.download='zuhan_choice.json';a.click()};
draw();
</script>"""
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(page)


def make(path):
    with open(path, encoding="utf-8") as f:
        choice = json.load(f)
    bad = [k for k in choice if k not in SLOTS]
    if bad:
        print("知らない枠のキーがあります（無視します）：", ", ".join(bad))
    choice = {k: v for k, v in choice.items() if k in SLOTS}
    os.makedirs(OUT, exist_ok=True)
    cands = info(["File:" + f for f in choice.values()], 960)  # Wikimedia は決まった幅（500・960・1280など）の縮小画像しか作らない
    by = {c["file"]: c for c in cands}
    cpath = os.path.join(OUT, "zuhan_credits.json")
    credits = {}
    if os.path.exists(cpath):  # 途中で止まったときは、書き出し済みの枠を飛ばして続きから
        with open(cpath, encoding="utf-8") as f:
            credits = json.load(f)
    failed = []
    for k, fn in choice.items():
        if credits.get(k, {}).get("f") == fn and os.path.exists(os.path.join(OUT, k + ".webp")):
            continue
        c = by.get(fn)
        if not c:
            print(f"{k}：{fn} の情報が取れませんでした")
            failed.append(k)
            continue
        try:
            im = Image.open(io.BytesIO(fetch(c["thumb"]))).convert("RGB")
        except Exception as e:
            print(f"{k}：画像を取得できませんでした（{e}）")
            failed.append(k)
            continue
        im.thumbnail((OUT_SIZE, OUT_SIZE))
        im.save(os.path.join(OUT, k + ".webp"), "WEBP", quality=74)
        credits[k] = {"f": c["file"], "a": c["author"], "lic": c["license"], "url": c["url"]}
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(credits, f, ensure_ascii=False, indent=1)
        print(f"{k}：{fn}（{c['license']}）")
        time.sleep(1.5)
    if failed:
        print("取得できなかった枠：", " ".join(failed), "（しばらく待ってから同じコマンドをもう一度実行すると、続きから書き出します）")
    print(f"おわり。zuhan_out フォルダの中身（{len(credits)} 枚の webp と zuhan_credits.json）を Claude に渡してください。")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--make":
        make(args[1] if len(args) > 1 else os.path.join(HERE, "zuhan_choice.json"))
        return
    keys = args or list(SLOTS)
    bad = [k for k in keys if k not in SLOTS]
    if bad:
        print("知らない枠のキー：", ", ".join(bad))
        print("使えるキー：", " ".join(SLOTS))
        return
    collect(keys)


if __name__ == "__main__":
    main()

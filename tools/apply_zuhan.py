# -*- coding: utf-8 -*-
"""
エラータ：pick_zuhan.py で書き出した写真を本体に取り込む

使い方（リポジトリのいちばん上のフォルダで）
  python3 tools/apply_zuhan.py zuhan_out
    → zuhan_out の「キー.webp」を img/zuhan/ にコピーし、
      index.html の "ZI"（写真の枠）と credits.json・tools/credits.json の出典を書きかえる
"""
import json, os, shutil, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "zuhan_out"
    with open(os.path.join(src, "zuhan_credits.json"), encoding="utf-8") as f:
        cr = json.load(f)
    path = os.path.join(ROOT, "index.html")
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    i = lines.index('"ZI": {')
    zi, pos = {}, {}
    j = i + 1
    while not lines[j].startswith("}"):
        k, v = lines[j].rstrip(",").split(":", 1)
        k = json.loads(k)
        zi[k], pos[k] = json.loads(v), j
        j += 1
    os.makedirs(os.path.join(ROOT, "img", "zuhan"), exist_ok=True)
    done = []
    for k, c in cr.items():
        if k not in zi:
            print(f"{k}：index.html の \"ZI\" にない枠なので飛ばします")
            continue
        shutil.copyfile(os.path.join(src, k + ".webp"), os.path.join(ROOT, "img", "zuhan", k + ".webp"))
        zi[k].update(f=c["f"], a=c["a"], lic=c["lic"])
        end = "," if lines[pos[k]].endswith(",") else ""
        lines[pos[k]] = json.dumps(k, ensure_ascii=False) + ":" + json.dumps(zi[k], ensure_ascii=False, separators=(",", ":")) + end
        done.append(k)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    for cf in ["credits.json", os.path.join("tools", "credits.json")]:
        p = os.path.join(ROOT, cf)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for k in done:
            z = zi[k]
            d["図版：" + z["l"]] = {"file": z["f"], "license": z["lic"], "author": z["a"],
                                  "url": cr[k].get("url") or "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(z["f"].replace(" ", "_"))}
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(done)} 枚を取り込みました：", " ".join(done))
    print("ブラウザのキャッシュで古い写真が出るときは、再読み込みしてください。")


if __name__ == "__main__":
    main()

"""主人公のSDの完成絵を書き出す。
tools/hero_parts/ に置いたパーツ（すべて同じ2048px四方のキャンバス・透明背景）を重ねて、
img/sd_hero_s{肌}_{後ろ髪}_{色}.webp を作る。

  skin1.png〜skin3.png      … 素体（1褐色・2薄橙・3クリーム）
  front_{色}.png            … 前髪（必ず重ねる）
  back_{長さ}_{色}.png      … 後ろ髪（素体の下に重ねる。なければ前髪だけ）
  side_{長さ}_{色}.png      … 後ろ髪のうち、素体の上に来る部分（任意）

使い方：python3 tools/compose_hero.py
書き出したら、表示されたIMGの行を index.html の IMG に貼る（すでにあれば不要）。
"""
import os, re
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); P=os.path.join(HERE,'hero_parts'); OUT=os.path.join(HERE,'..','img')
H=420  # 書き出す高さ（px）
def load(n):
  f=os.path.join(P,n); return Image.open(f).convert('RGBA') if os.path.exists(f) else None
files=os.listdir(P)
colors=sorted({m.group(1) for f in files if (m:=re.match(r'front_(.+)\.png$',f))})
lengths=sorted({m.group(1) for f in files if (m:=re.match(r'back_(.+?)_.+\.png$',f))})
rows=[]
for s in (1,2,3):
  for ln in [None]+lengths:
    for c in colors:
      back=load(f'back_{ln}_{c}.png') if ln else None
      if ln and back is None: continue
      im=Image.new('RGBA',(2048,2048),(0,0,0,0))
      if back: im.alpha_composite(back)
      im.alpha_composite(load(f'skin{s}.png'))
      side=load(f'side_{ln}_{c}.png') if ln else None
      if side: im.alpha_composite(side)
      im.alpha_composite(load(f'front_{c}.png'))
      im=im.crop(im.getchannel('A').getbbox())
      im=im.resize((round(im.width*H/im.height),H),Image.LANCZOS)
      name=f'sd_hero_s{s}'+(f'_{ln}' if ln else '')+f'_{c}.webp'
      im.save(os.path.join(OUT,name),'WEBP',quality=90,method=6)
      key=f'SD_主人公_肌{s}'+(f'_{ln}' if ln else '')+f'_{c}'
      rows.append(f'"{key}": "img/{name}",')
for r in rows: print(r)

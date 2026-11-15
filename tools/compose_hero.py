"""主人公のSDの完成絵を書き出す。
tools/hero_parts/ に置いたパーツ（すべて同じ2048px四方のキャンバス・透明背景）を重ねて、
img/sd_hero_s{肌}_{後ろ髪}_{色}.webp を作る。

  skin1.png〜skin3.png      … 素体（1褐色・2薄橙・3クリーム）
  front_{色}.png            … 前髪（必ず重ねる）
  back_{長さ}_{色}.png      … 後ろ髪（素体の下に重ねる。なければ前髪だけ）
  mid_{長さ}_{色}.png       … 頭の後ろ・体の手前に来る部分（任意。三つ編みなど）。素体の頭（あごより上）がこの上に重なる
  side_{長さ}_{色}.png      … 後ろ髪のうち、素体の上に来る部分（任意）
  back・mid・side のどれか1つだけの髪型でもよい

使い方：python3 tools/compose_hero.py            … すべて書き出す
        python3 tools/compose_hero.py 三つ編み   … 指定した後ろ髪だけ書き出す
あわせて、選択画面で使う髪型のアイコン img/look_hair_{後ろ髪}.webp も書き出す
書き出したら、表示されたIMGの行を index.html の IMG に貼る（すでにあれば不要）。
"""
import os, re, sys
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); P=os.path.join(HERE,'hero_parts'); OUT=os.path.join(HERE,'..','img')
H=420  # 書き出す高さ（px）
def load(n):
  f=os.path.join(P,n); return Image.open(f).convert('RGBA') if os.path.exists(f) else None
files=os.listdir(P)
colors=sorted({m.group(1) for f in files if (m:=re.match(r'front_(.+)\.png$',f))})
lengths=sorted({m.group(1) for f in files if (m:=re.match(r'(?:back|mid|side)_(.+?)_.+\.png$',f))})
only=set(sys.argv[1:])
CHIN=1100  # mid の髪より手前に重ねる、素体の頭の範囲（この高さより上）
def headof(sk):
  h=Image.new('RGBA',sk.size,(0,0,0,0)); h.paste(sk.crop((0,0,sk.width,CHIN)),(0,0)); return h
rows=[]
for s in (1,2,3):
  for ln in [None]+lengths:
    for c in colors:
      if only and ln not in only: continue
      back=load(f'back_{ln}_{c}.png') if ln else None
      mid=load(f'mid_{ln}_{c}.png') if ln else None
      side=load(f'side_{ln}_{c}.png') if ln else None
      if ln and back is None and mid is None and side is None: continue
      im=Image.new('RGBA',(2048,2048),(0,0,0,0))
      if back: im.alpha_composite(back)
      sk=load(f'skin{s}.png'); im.alpha_composite(sk)
      if mid: im.alpha_composite(mid); im.alpha_composite(headof(sk))
      if side: im.alpha_composite(side)
      im.alpha_composite(load(f'front_{c}.png'))
      im=im.crop(im.getchannel('A').getbbox())
      im=im.resize((round(im.width*H/im.height),H),Image.LANCZOS)
      name=f'sd_hero_s{s}'+(f'_{ln}' if ln else '')+f'_{c}.webp'
      im.save(os.path.join(OUT,name),'WEBP',quality=90,method=6)
      key=f'SD_主人公_肌{s}'+(f'_{ln}' if ln else '')+f'_{c}'
      rows.append(f'"{key}": "img/{name}",')
for r in rows: print(r)
# 髪型のアイコン（頭部のシルエット）。髪＝濃い色、顔＝明るい色の2色。黒髪のパーツを型に使う
NECK=1180  # 素体のうち、この高さより上を頭とみなす
INK=(58,48,44,255); FACE=(244,232,214,255)
def fill(layer,col):
  m=layer.getchannel('A').point(lambda v:255 if v>96 else 0); out=Image.new('RGBA',layer.size,(0,0,0,0)); out.paste(Image.new('RGBA',layer.size,col),(0,0),m); return out
head=load('skin2.png'); head=head.crop((0,0,2048,NECK)); h2=Image.new('RGBA',(2048,2048),(0,0,0,0)); h2.paste(head,(0,0))
for ln in [None]+lengths:
  if only and ln not in only: continue
  c='黒'; back=load(f'back_{ln}_{c}.png') if ln else None; side=load(f'side_{ln}_{c}.png') if ln else None; mid=load(f'mid_{ln}_{c}.png') if ln else None
  im=Image.new('RGBA',(2048,2048),(0,0,0,0))
  if back: im.alpha_composite(fill(back,INK))
  im.alpha_composite(fill(h2,FACE))
  if mid: im.alpha_composite(fill(mid,INK)); im.alpha_composite(fill(headof(load('skin2.png')),FACE))
  if side: im.alpha_composite(fill(side,INK))
  im.alpha_composite(fill(load(f'front_{c}.png'),INK))
  im=im.crop((180,0,1868,1720)); im=im.resize((round(im.width*128/im.height),128),Image.LANCZOS)
  name=f'look_hair_{ln or "なし"}.webp'; im.save(os.path.join(OUT,name),'WEBP',quality=90,method=6)
  print('icon',name)

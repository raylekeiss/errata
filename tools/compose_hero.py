"""主人公のSDの完成絵を書き出す。
tools/hero_parts/ に置いたパーツ（すべて同じ2048px四方のキャンバス・透明背景）を重ねて、
img/sd_hero_s{肌}_{後ろ髪}_{色}_e{目}b{眉}.webp を作る。

  body1.png〜body3.png      … 首から下の素体（1褐色・2薄橙・3クリーム）
  head1.png〜head3.png      … 頭（顔の輪郭・耳・口。肌の番号は素体と同じ）
  eyes_{番号}.png           … 目（選べる）
  brows_{番号}.png          … 眉（選べる。前髪より手前に重ねる）
  front_{色}.png            … 前髪（必ず重ねる）
  back_{長さ}_{色}.png      … 後ろ髪（いちばん奥）
  mid_{長さ}_{色}.png       … 体の手前・頭の後ろに来る髪（任意。三つ編みなど）
  side_{長さ}_{色}.png      … 頭の手前・前髪の奥に来る髪（任意）
  back・mid・side のどれか1つだけの髪型でもよい

重ねる順：後ろ髪 → 素体 → mid → 頭 → 目 → side → 前髪 → 眉

使い方：python3 tools/compose_hero.py            … すべて書き出す
        python3 tools/compose_hero.py 三つ編み   … 指定した後ろ髪だけ書き出す
あわせて、選択画面で使うアイコンも書き出す：
  img/look_hair_{後ろ髪}.webp（頭部のシルエット）・img/look_eyes_{番号}.webp・img/look_brows_{番号}.webp
書き出したら、表示されたIMGの行を index.html の IMG に貼る（すでにあれば不要）。
"""
import os, re, sys
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); P=os.path.join(HERE,'hero_parts'); OUT=os.path.join(HERE,'..','img')
H=420  # 書き出す高さ（px）
_cache={}
def load(n):
  if n not in _cache:
    f=os.path.join(P,n); _cache[n]=Image.open(f).convert('RGBA') if os.path.exists(f) else None
  return _cache[n]
files=os.listdir(P)
colors=sorted({m.group(1) for f in files if (m:=re.match(r'front_(.+)\.png$',f))})
lengths=sorted({m.group(1) for f in files if (m:=re.match(r'(?:back|mid|side)_(.+?)_.+\.png$',f))})
eyes=sorted({int(m.group(1)) for f in files if (m:=re.match(r'eyes_(\d+)\.png$',f))})
brows=sorted({int(m.group(1)) for f in files if (m:=re.match(r'brows_(\d+)\.png$',f))})
skins=sorted({int(m.group(1)) for f in files if (m:=re.match(r'body(\d+)\.png$',f))})
only=set(sys.argv[1:])

def compose(s,ln,c,e,b):
  im=Image.new('RGBA',(2048,2048),(0,0,0,0))
  for layer in (f'back_{ln}_{c}.png',f'body{s}.png',f'mid_{ln}_{c}.png',f'head{s}.png',f'eyes_{e}.png',
                f'side_{ln}_{c}.png',f'front_{c}.png',f'brows_{b}.png'):
    l=load(layer)
    if l: im.alpha_composite(l)
  return im

rows=[]
for s in skins:
  for ln in lengths:
    if only and ln not in only: continue
    for c in colors:
      if not any(load(f'{p}_{ln}_{c}.png') for p in ('back','mid','side')): continue
      for e in eyes:
        for b in brows:
          im=compose(s,ln,c,e,b)
          im=im.crop(im.getchannel('A').getbbox())
          im=im.resize((round(im.width*H/im.height),H),Image.LANCZOS)
          name=f'sd_hero_s{s}_{ln}_{c}_e{e}b{b}.webp'
          im.save(os.path.join(OUT,name),'WEBP',quality=88,method=6)
          rows.append(f'"SD_主人公_肌{s}_{ln}_{c}_目{e}_眉{b}": "img/{name}"')
print(', '.join(rows))

# ---- 選択画面のアイコン ----
INK=(58,48,44,255); FACE=(244,232,214,255)
def fill(layer,col):
  m=layer.getchannel('A').point(lambda v:255 if v>96 else 0); out=Image.new('RGBA',layer.size,(0,0,0,0)); out.paste(Image.new('RGBA',layer.size,col),(0,0),m); return out
def save_icon(im,box,name,h=128):
  im=im.crop(box); im=im.resize((round(im.width*h/im.height),h),Image.LANCZOS)
  im.save(os.path.join(OUT,name),'WEBP',quality=90,method=6); print('icon',name)
# 髪型：頭部のシルエット（髪＝濃い色、顔＝明るい色）。黒髪のパーツを型に使う
for ln in lengths:
  if only and ln not in only: continue
  c='黒'; im=Image.new('RGBA',(2048,2048),(0,0,0,0))
  for layer,col in ((f'back_{ln}_{c}.png',INK),(f'mid_{ln}_{c}.png',INK),('head2.png',FACE),(f'side_{ln}_{c}.png',INK),(f'front_{c}.png',INK)):
    l=load(layer)
    if l: im.alpha_composite(fill(l,col))
  save_icon(im,(180,0,1868,1720),f'look_hair_{ln}.webp')
# 目・眉：髪のない頭に乗せて、顔のあたりを切り出す（眉は目1と組み合わせて見せる）
FACEBOX=(480,520,1400,1100)
for e in eyes:
  im=Image.new('RGBA',(2048,2048),(0,0,0,0)); im.alpha_composite(load('head2.png')); im.alpha_composite(load(f'eyes_{e}.png'))
  save_icon(im,FACEBOX,f'look_eyes_{e}.webp',96)
for b in brows:
  im=Image.new('RGBA',(2048,2048),(0,0,0,0)); im.alpha_composite(load('head2.png')); im.alpha_composite(load(f'eyes_{eyes[0]}.png')); im.alpha_composite(load(f'brows_{b}.png'))
  save_icon(im,FACEBOX,f'look_brows_{b}.webp',96)

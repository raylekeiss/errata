"""主人公のSDのパーツを、ゲームで使う大きさに書き出す（重ねるのはゲームがその場で行う）。
tools/hero_parts/ に置いたパーツ（すべて同じ2048px四方のキャンバス・透明背景）を、
全パーツが収まる範囲で切り出して縮め、img/hero/{パーツ名}.webp に書き出す。

  body1.png〜body3.png      … 首から下の素体・スカート（1褐色・2薄橙・3クリーム）
  body1_ズボン.png〜        … 首から下の素体・ズボン（肌の番号は同じ）
  head1.png〜head3.png      … 頭（顔の輪郭・耳・口。肌の番号は素体と同じ）
  eyes_{番号}.png           … 目（選べる）
  brows_{番号}.png          … 眉（選べる。前髪より手前に「乗算」で重ねる）
  front_{番号}_{色}.png     … 前髪（選べる）
  back_{長さ}_{色}.png      … 後ろ髪（いちばん奥）
  mid_{長さ}_{色}.png       … 体の手前・頭の後ろに来る髪（任意。三つ編みなど）
  side_{長さ}_{色}.png      … 頭の手前・前髪の奥に来る髪（任意）
  back・mid・side のどれか1つだけの髪型でもよい

重ねる順（index.html の heroBuild）：後ろ髪 → 素体（服） → mid → 頭 → 目 → side → 前髪 → 眉（乗算）

使い方：python3 tools/compose_hero.py
  書き出したあと、表示された IMG の行（"HERO_パーツ名"）を index.html の IMG に入れる。
  パーツを足しただけなら、足したものの行だけ追加すればよい。
  選択画面のアイコン（髪型 img/look_hair_長さ.webp・前髪 img/look_bang_番号.webp（どちらも頭部のシルエット）、目 img/look_eyes_番号.webp、眉 img/look_brows_番号.webp、服 img/look_wear_服.webp）も書き出す。
目・眉・髪型・前髪・服を足したら、index.html の LOOK_EYES・LOOK_BROWS・LOOK_HAIRS・LOOK_BANGS・LOOK_WEARS にも1行足す。
"""
import os, re
from PIL import Image, ImageChops
HERE=os.path.dirname(os.path.abspath(__file__)); P=os.path.join(HERE,'hero_parts'); IMGD=os.path.join(HERE,'..','img'); OUT=os.path.join(IMGD,'hero')
HP=520  # 全パーツが収まる範囲を、この高さ（px）に縮める
os.makedirs(OUT,exist_ok=True)
files=sorted(f for f in os.listdir(P) if f.endswith('.png'))
def load(n):
  f=os.path.join(P,n); return Image.open(f).convert('RGBA') if os.path.exists(f) else None
# すべてのパーツが収まる範囲（どの組み合わせでも同じ位置に重なるよう、全パーツ共通で切り出す）
box=None
for f in files:
  b=load(f).getchannel('A').getbbox()
  if b: box=b if box is None else (min(box[0],b[0]),min(box[1],b[1]),max(box[2],b[2]),max(box[3],b[3]))
W=round((box[2]-box[0])*HP/(box[3]-box[1]))
rows=[]
for f in files:
  name=f[:-4]
  im=load(f).crop(box).resize((W,HP),Image.LANCZOS)
  im.save(os.path.join(OUT,name+'.webp'),'WEBP',quality=92,method=6)
  rows.append(f'"HERO_{name}": "img/hero/{name}.webp"')
print(', '.join(rows))
print(f'# 範囲 {box} → {W}×{HP}px')

# ---- 選択画面のアイコン ----
INK=(58,48,44,255); FACE=(244,232,214,255)
def fill(layer,col):
  m=layer.getchannel('A').point(lambda v:255 if v>96 else 0); out=Image.new('RGBA',layer.size,(0,0,0,0)); out.paste(Image.new('RGBA',layer.size,col),(0,0),m); return out
def multiply(base,layer):
  """layer を base に乗算で重ねる（base が不透明な部分）"""
  mul=ImageChops.multiply(base.convert('RGB'),layer.convert('RGB'))
  a=layer.getchannel('A'); out=base.copy(); out.paste(Image.merge('RGBA',(*mul.split(),base.getchannel('A'))),(0,0),a); return out
def save_icon(im,b,name,h=128):
  im=im.crop(b); im=im.resize((round(im.width*h/im.height),h),Image.LANCZOS)
  im.save(os.path.join(IMGD,name),'WEBP',quality=90,method=6); print('icon',name)
lengths=sorted({m.group(1) for f in files if (m:=re.match(r'(?:back|mid|side)_(.+?)_.+\.png$',f))})
eyes=sorted({int(m.group(1)) for f in files if (m:=re.match(r'eyes_(\d+)\.png$',f))})
brows=sorted({int(m.group(1)) for f in files if (m:=re.match(r'brows_(\d+)\.png$',f))})
# 髪型：頭部のシルエット（髪＝濃い色、顔＝明るい色）。黒髪のパーツを型に使う
for ln in lengths:
  c='黒'; im=Image.new('RGBA',(2048,2048),(0,0,0,0))
  for layer,col in ((f'back_{ln}_{c}.png',INK),(f'mid_{ln}_{c}.png',INK),('head2.png',FACE),(f'side_{ln}_{c}.png',INK),(f'front_1_{c}.png',INK)):
    l=load(layer)
    if l: im.alpha_composite(fill(l,col))
  save_icon(im,(180,0,1868,1720),f'look_hair_{ln}.webp')
# 目・眉：髪のない頭に乗せて、顔のあたりを切り出す（眉は目1と組み合わせて見せる）
FACEBOX=(480,520,1400,1100)
for e in eyes:
  im=load('head2.png'); im.alpha_composite(load(f'eyes_{e}.png'))
  save_icon(im,FACEBOX,f'look_eyes_{e}.webp',96)
for b in brows:
  im=load('head2.png'); im.alpha_composite(load(f'eyes_{eyes[0]}.png')); im=multiply(im,load(f'brows_{b}.png'))
  save_icon(im,FACEBOX,f'look_brows_{b}.webp',96)
# 前髪：髪のない頭に前髪だけを重ねたシルエット
bangs=sorted({int(m.group(1)) for f in files if (m:=re.match(r'front_(\d+)_.+\.png$',f))})
for n in bangs:
  im=Image.new('RGBA',(2048,2048),(0,0,0,0)); im.alpha_composite(fill(load('head2.png'),FACE)); im.alpha_composite(fill(load(f'front_{n}_黒.png'),INK))
  save_icon(im,(250,120,1620,1260),f'look_bang_{n}.webp')
# 服：素体（肌2）の首から下
wears=[('スカート','body2.png')]+[(m.group(1),f) for f in files if (m:=re.match(r'body2_(.+)\.png$',f))]
for k,f in wears:
  save_icon(load(f),(600,1080,1460,1960),f'look_wear_{k}.webp',160)
# 小物（acc_〇〇.png）：顔（頭・目1）に重ねて、顔のあたりを切り出す。index.html の LOOK_ACCS にも1行足し、
# IMG に "UI_小物_〇〇": "img/look_acc_〇〇.webp" を入れる。
for f in files:
  m=re.match(r'acc_(.+)\.png$',f)
  if not m: continue
  im=load('head2.png'); im.alpha_composite(load(f'eyes_{eyes[0]}.png')); im.alpha_composite(load(f))
  b=im.getchannel('A').point(lambda v:255 if v>40 else 0).getbbox()  # 頭全体と小物が入る範囲（帽子・冠は顔の外に出るため）
  save_icon(im,b,f'look_acc_{m.group(1)}.webp',128)
  print(f'"UI_小物_{m.group(1)}": "img/look_acc_{m.group(1)}.webp"')

#!/usr/bin/env python3
"""tools/drill-edit.html で「書き出す」したファイルを index.html のドリルデータ（Q・JQ）に取り込む。

使い方: python3 tools/apply_drill_edits.py drill-edits_20261106.json
1問1行の形はそのまま保つ。紙魚の一言（n）を空にした問題は n を消す。
削除（del）にした問題はデータから取り除く。
"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
KEYS = ('q', 'a', 'd', 'x', 'n', 'lv', 'ok')


def main(path):
    edits = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    lines = HTML.read_text(encoding='utf-8').split('\n')
    done = set()
    removed = []
    for head in ('"Q": [', '"JQ": ['):
        if head not in lines:
            continue
        i = lines.index(head) + 1
        while lines[i].strip() != '],':
            t = lines[i].strip()
            comma = t.endswith(',')
            q = json.loads(t.rstrip(','))
            e = edits.get(q['id'])
            if e and e.get('del'):
                removed.append(q['id'])
                done.add(q['id'])
                del lines[i]
                continue
            if e:
                for k in KEYS:
                    if k in e:
                        q[k] = e[k]
                if not q.get('n'):
                    q.pop('n', None)
                # n は x の直後に置く（読みやすさのため）
                order = [k for k in q if k != 'n']
                pos = order.index('x') + 1 if 'x' in order else len(order)
                if 'n' in q:
                    order.insert(pos, 'n')
                q = {k: q[k] for k in order}
                lines[i] = '  ' + json.dumps(q, ensure_ascii=False, separators=(',', ':')) + (',' if comma else '')
                done.add(q['id'])
            i += 1
        # 配列の最後の要素のあとにカンマが残らないようにする
        j = i - 1
        if lines[j].rstrip().endswith(','):
            lines[j] = lines[j].rstrip()[:-1]
    HTML.write_text('\n'.join(lines), encoding='utf-8')
    miss = [k for k in edits if k not in done]
    if removed:
        print(f'削除: {len(removed)}問（{", ".join(removed)}）')
    print(f'{len(done)}問を取り込みました' + (f'（見つからないID: {", ".join(miss)}）' if miss else ''))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

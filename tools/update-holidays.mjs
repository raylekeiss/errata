// 内閣府の「国民の祝日」CSVを取得し、data/holidays.json に変換して保存する
// 内容が変わっていなければファイルは書き換えない
//
// 使い方: node tools/update-holidays.mjs [CSVのパスまたはURL]
//   引数なし → 内閣府のURLから取得

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';

const SOURCE_URL = 'https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv';
const OUTPUT = 'data/holidays.json';

// 取得に失敗したり形式が変わったりしたとき、既存のデータを壊さないための下限
// （1955年以降の祝日は1000件以上あるので、大きく下回ったら異常とみなす）
const MIN_ENTRIES = 500;

async function loadCsv(source) {
  if (/^https?:\/\//.test(source)) {
    const res = await fetch(source);
    if (!res.ok) throw new Error(`取得に失敗しました: HTTP ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
  return readFile(source);
}

function parse(buf) {
  // 内閣府のCSVはShift_JIS
  const text = new TextDecoder('shift_jis').decode(buf);
  const holidays = {};
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2}),(.+)$/);
    if (!m) continue; // 見出し行・空行は飛ばす
    const [, y, mo, d, name] = m;
    const date = `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
    holidays[date] = name.trim();
  }
  return holidays;
}

const source = process.argv[2] || SOURCE_URL;
const holidays = parse(await loadCsv(source));
const count = Object.keys(holidays).length;
if (count < MIN_ENTRIES) {
  throw new Error(`祝日が${count}件しか読めませんでした。CSVの形式が変わった可能性があるため、保存しません。`);
}

// 日付順に並べて保存
const sorted = Object.fromEntries(Object.entries(holidays).sort(([a], [b]) => a.localeCompare(b)));
const json = JSON.stringify(sorted, null, 1) + '\n';

let current = null;
try { current = await readFile(OUTPUT, 'utf8'); } catch { /* 初回はファイルなし */ }

const years = Object.keys(sorted).map(d => d.slice(0, 4));
const range = `${years[0]}〜${years[years.length - 1]}年`;

if (current === json) {
  console.log(`変更なし（${count}件、${range}）`);
} else {
  await mkdir(dirname(OUTPUT), { recursive: true });
  await writeFile(OUTPUT, json);
  console.log(`更新しました（${count}件、${range}）`);
}

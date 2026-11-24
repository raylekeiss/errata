/** @OnlyCurrentDoc */
/**
 * エラータ　学校アカウント保存係
 * スプレッドシートの「拡張機能 → Apps Script」に貼り付けて使います。
 * 生徒ごとに「セーブ」シートへ1行ずつ記録します。
 */
const SHEET = 'セーブ';
const HEAD = ['メール', '名前', '最終保存', '修復した章', 'ドリル回数', '正解済みの問題', '間違えたままの問題', '栞', '持っている頁', 'セーブデータ'];
const COL_DATA = HEAD.length; // セーブデータの列（J列）
// 本名（フルネーム）はセーブデータの右（K列）に入れる。列の並びを変えるとずれるので、列は動かさないこと
const COL_REAL = COL_DATA + 1;

function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('エラータ')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover');
}

function sheet_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(SHEET);
  if (!sh) {
    sh = ss.insertSheet(SHEET);
    sh.appendRow(HEAD);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, HEAD.length).setFontWeight('bold');
  }
  if (sh.getRange(1, COL_REAL).getValue() !== '本名') sh.getRange(1, COL_REAL).setValue('本名').setFontWeight('bold');
  return sh;
}

function me_() {
  const email = Session.getActiveUser().getEmail();
  if (!email) throw new Error('ログインしているアカウントを確認できません');
  return email;
}

function findRow_(sh, email) {
  const hit = sh.getRange('A:A').createTextFinder(email).matchEntireCell(true).findNext();
  return hit ? hit.getRow() : 0;
}

/** ゲームを開いた生徒の記録を返す */
function getSave() {
  const email = me_();
  const sh = sheet_();
  const row = findRow_(sh, email);
  return { email: email, data: row ? String(sh.getRange(row, COL_DATA).getValue() || '') : null };
}

/** ゲームから送られてきた記録を保存する */
function putSave(json) {
  const email = me_();
  if (typeof json !== 'string' || json.length > 49000) throw new Error('記録が大きすぎます');
  const S = JSON.parse(json);
  const qs = S.qs || {};
  const vals = Object.keys(qs).map(k => qs[k]);
  const record = [
    email,
    String(S.name || ''),
    new Date(),
    (S.cleared || []).filter(Boolean).length,
    Number(S.drills || 0),
    vals.filter(v => v === 1).length,
    vals.filter(v => v === 2).length,
    Number(S.shiori || 0),
    Object.keys(S.cards || {}).length,
    json,
  ];
  const real = S.real && S.real.sei ? String(S.real.sei) + ' ' + String(S.real.mei || '') : '';
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = sheet_();
    const row = findRow_(sh, email);
    if (row) {
      // 古い記録で新しい記録を上書きしないように、保存時刻を比べる
      try {
        const old = JSON.parse(String(sh.getRange(row, COL_DATA).getValue() || '{}'));
        if ((old.t || 0) > (S.t || 0)) return { ok: true, skipped: true };
      } catch (e) {}
      sh.getRange(row, 1, 1, record.length).setValues([record]);
      if (real) sh.getRange(row, COL_REAL).setValue(real);
    } else {
      sh.appendRow(record.concat([real]));
    }
  } finally {
    lock.releaseLock();
  }
  return { ok: true };
}

/**
 * カードゲームのランキング（ハイスコア順）を返す。50階モード（hi）と無限回廊（hiE）の2つ。
 * 全員のセーブデータからハイスコアを読み出し、5分間キャッシュする。
 * 返すのはゲーム内の名前・スコア・到達階・キャラだけ（メールアドレスは返さない）。
 */
function getRanking() {
  const email = me_();
  const cache = CacheService.getScriptCache();
  let rows = null;
  const hit = cache.get('lxRank2');
  if (hit) { try { rows = JSON.parse(hit); } catch (e) { rows = null; } }
  if (!rows) {
    const sh = sheet_();
    const n = sh.getLastRow();
    rows = [];
    if (n >= 2) {
      const vals = sh.getRange(2, 1, n - 1, COL_DATA).getValues();
      vals.forEach(function (v) {
        try {
          const S = JSON.parse(String(v[COL_DATA - 1] || '{}'));
          const L = S.lib || {};
          if (Number(L.hi) > 0 || Number(L.hiE) > 0) rows.push({
            m: String(v[0]), name: String(S.name || '名無し').slice(0, 12),
            a: Number(L.hi || 0), af: Number(L.hiFl || 0), ac: String(L.hiCh0 || ''),
            b: Number(L.hiE || 0), bf: Number(L.hiEFl || 0), bc: String(L.hiECh0 || ''),
          });
        } catch (e) {}
      });
    }
    try { cache.put('lxRank2', JSON.stringify(rows), 300); } catch (e) {}
  }
  function board(key, fk, ck) {
    const list = rows.filter(function (x) { return x[key] > 0; }).sort(function (p, q) { return q[key] - p[key]; });
    let mine = -1;
    for (let i = 0; i < list.length; i++) if (list[i].m === email) { mine = i; break; }
    return {
      top: list.slice(0, 30).map(function (x) { return { name: x.name, score: x[key], fl: x[fk], ch: x[ck] === 'カコ' ? '' : x[ck], me: x.m === email }; }),
      me: mine >= 0 ? { rank: mine + 1, score: list[mine][key] } : null,
      n: list.length,
    };
  }
  const A = board('a', 'af', 'ac'), B = board('b', 'bf', 'bc');
  return { top: A.top, me: A.me, n: A.n, topE: B.top, meE: B.me, nE: B.n };
}

/* ===================================================================
 * 先生用：取り組み状況シート
 * スプレッドシートを開くと、メニューに「エラータ」→「取り組み状況を更新」が出る。
 * 押すと「取り組み状況」シートを作り直す（生徒の操作では動かない）。
 * 問題の数と章は、GitHub Pages のゲーム本体（index.html）から読み込むので、問題を足してもここは直さなくてよい。
 * 1行＝生徒1人。章ごとに「回数」（その章を解いた問題演習の回数）と「正解率」（その章の問題のうち、正解済みの割合）。
 * 正解率のセルにカーソルを合わせると、正解・間違えたまま・全問の数が出る（メモ）。
 * 章ごとの回数は、この仕組みを入れた日（2026年11月25日）より前の分は数えていない。
 * =================================================================== */
const PROG_SHEET = '取り組み状況';
const GAME_URL = 'https://raylekeiss.github.io/errata/index.html';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('エラータ')
    .addItem('取り組み状況を更新', 'updateProgress')
    .addToUi();
}

/** ゲーム本体から、問題ID→章 と 章ごとの問題数・章の名前を読む */
function gameData_() {
  const html = UrlFetchApp.fetch(GAME_URL + '?v=' + Date.now(), { muteHttpExceptions: true }).getContentText('UTF-8');
  const m = html.match(/<script[^>]*id="errata-data"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('ゲーム本体から問題を読み込めませんでした');
  const D = JSON.parse(m[1]);
  const chOf = {}, total = {};
  (D.Q || []).forEach(function (q) { chOf[q.id] = q.ch; total[q.ch] = (total[q.ch] || 0) + 1; });
  const n = Object.keys(D.chapters || {}).length || 15;
  const names = [];
  for (let c = 1; c <= n; c++) names.push((D.chapters || {})[c] || ('第' + c + '章'));
  return { chOf: chOf, total: total, names: names };
}

function updateProgress() {
  const G = gameData_();
  const N = G.names.length;
  const src = sheet_();
  const last = src.getLastRow();
  const rows = last >= 2 ? src.getRange(2, 1, last - 1, COL_REAL).getValues() : [];

  const head = ['本名', 'ゲーム内の名前', 'メール', '最終保存', '問題演習の回数（全体）', '受験対策の正解数', '記述対策（実戦を書いた数）'];
  const FIX = head.length;
  G.names.forEach(function (nm, i) {
    head.push('第' + (i + 1) + '章 回数');
    head.push('第' + (i + 1) + '章 ' + nm + '（' + (G.total[i + 1] || 0) + '問）正解率');
  });

  const out = [], notes = [];
  rows.forEach(function (v) {
    let S = {};
    try { S = JSON.parse(String(v[COL_DATA - 1] || '{}')); } catch (e) { return; }
    const ok = {}, ng = {};
    const qs = S.qs || {};
    Object.keys(qs).forEach(function (id) {
      const c = G.chOf[id];
      if (!c) return;
      if (qs[id] === 1) ok[c] = (ok[c] || 0) + 1;
      else if (qs[id] === 2) ng[c] = (ng[c] || 0) + 1;
    });
    let jk = 0;
    Object.keys(S.jq || {}).forEach(function (u) { jk += String(S.jq[u]).split('1').length - 1; });
    let kjW = 0;
    Object.keys(S.kj || {}).forEach(function (id) { const r = S.kj[id]; if (Array.isArray(r) && Number(r[2]) >= 0) kjW++; });
    const dch = Array.isArray(S.dch) ? S.dch : [];
    const row = [String(v[COL_REAL - 1] || ''), String(S.name || ''), String(v[0] || ''), v[2] || '', Number(S.drills || 0), jk, kjW];
    const note = ['', '', '', '', '', '', ''];
    for (let c = 1; c <= N; c++) {
      const t = G.total[c] || 0, a = ok[c] || 0, b = ng[c] || 0;
      row.push(Number(dch[c - 1] || 0));
      row.push(t ? a / t : 0);
      note.push('');
      note.push('正解 ' + a + '問／間違えたまま ' + b + '問／まだ解いていない ' + Math.max(0, t - a - b) + '問（全' + t + '問）');
    }
    out.push(row); notes.push(note);
  });
  // メールアドレス順（出席番号順になることが多い）
  const order = out.map(function (r, i) { return i; }).sort(function (i, j) { return String(out[i][2]).localeCompare(String(out[j][2])); });
  const body = order.map(function (i) { return out[i]; });
  const bodyNotes = order.map(function (i) { return notes[i]; });

  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(PROG_SHEET);
  if (sh) sh.clear(); else sh = ss.insertSheet(PROG_SHEET);
  sh.clearConditionalFormatRules();
  sh.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight('bold').setWrap(true).setVerticalAlignment('top');
  sh.setFrozenRows(1);
  sh.setFrozenColumns(2);
  if (body.length) {
    sh.getRange(2, 1, body.length, head.length).setValues(body);
    sh.getRange(2, 1, body.length, head.length).setNotes(bodyNotes);
    sh.getRange(2, 4, body.length, 1).setNumberFormat('yyyy/mm/dd hh:mm');
    const rules = [];
    for (let c = 1; c <= N; c++) {
      const col = FIX + c * 2;
      const r = sh.getRange(2, col, body.length, 1);
      r.setNumberFormat('0%');
      rules.push(SpreadsheetApp.newConditionalFormatRule()
        .setGradientMinpointWithValue('#f4c7c3', SpreadsheetApp.InterpolationType.NUMBER, '0')
        .setGradientMidpointWithValue('#fce8b2', SpreadsheetApp.InterpolationType.NUMBER, '0.5')
        .setGradientMaxpointWithValue('#b7e1cd', SpreadsheetApp.InterpolationType.NUMBER, '1')
        .setRanges([r]).build());
      sh.getRange(1, col - 1, body.length + 1, 1).setBackground('#f3f3f3');
    }
    sh.setConditionalFormatRules(rules);
  }
  sh.setColumnWidth(3, 200);
  for (let c = FIX + 1; c <= head.length; c++) sh.setColumnWidth(c, (c - FIX) % 2 ? 56 : 110);
  sh.setRowHeight(1, 60);
  sh.getRange(1, head.length + 2).setValue('更新：' + Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm'));
  SpreadsheetApp.getActive().toast(body.length + '人分の取り組み状況を更新しました', 'エラータ', 5);
}

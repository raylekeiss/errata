/** @OnlyCurrentDoc */
/**
 * エラータ　学校アカウント保存係
 * スプレッドシートの「拡張機能 → Apps Script」に貼り付けて使います。
 * 生徒ごとに「セーブ」シートへ1行ずつ記録します。
 */
const SHEET = 'セーブ';
const HEAD = ['メール', '名前', '最終保存', '修復した章', 'ドリル回数', '正解済みの問題', '間違えたままの問題', '栞', '持っている頁', 'セーブデータ'];
const COL_DATA = HEAD.length; // セーブデータの列（J列）

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
    } else {
      sh.appendRow(record);
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

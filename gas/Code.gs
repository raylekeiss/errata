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
  // now：この保存係の時計（デイリーミッションの日付に使う。iPadの時計を進めても受け取り直せないように）
  // admin：先生のアカウント（スクリプトプロパティ ADMIN_EMAILS）なら true。ゲームは学校の時間の利用制限をかけない
  return { email: email, data: row ? String(sh.getRange(row, COL_DATA).getValue() || '') : null, now: Date.now(), admin: isAdmin_(email) };
}

/** ゲームから送られてきた記録を保存する */
/**
 * base＝送ってきた画面が知っている、学校アカウント側の記録の時刻。
 * 保存されている記録がそれより新しい（ほかの端末で遊んだ）ときは上書きせず、新しい記録を返す。
 * 開きっぱなしの古いタブが、ほかの端末で進めた記録を上書きしないため。
 */
function putSave(json, base) {
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
        const oldJson = String(sh.getRange(row, COL_DATA).getValue() || '{}');
        const old = JSON.parse(oldJson);
        if (typeof base === 'number' && (old.t || 0) > base && (old.t || 0) !== (S.t || 0)) return { ok: false, conflict: true, data: oldJson, now: Date.now() };
        if ((old.t || 0) > (S.t || 0)) return { ok: true, skipped: true, now: Date.now() };
        // 一気に書き換えた記録の見張り（保存は止めない。アラームのシートに残し、管理者にメールする）
        const jump = checkJump_(old, S, sh.getRange(row, 3).getValue());
        if (jump.length) alarm_(email, S, real, jump);
      } catch (e) {}
      sh.getRange(row, 1, 1, record.length).setValues([record]);
      if (real) sh.getRange(row, COL_REAL).setValue(real);
    } else {
      sh.appendRow(record.concat([real]));
    }
  } finally {
    lock.releaseLock();
  }
  return { ok: true, now: Date.now() };
}

/* ===================================================================
 * アラーム（一気に書き換えた記録の見張り）
 * 前回の保存から増えた量が、その間の時間でふつうに遊んで増やせる量を大きく超えたら、
 * 「アラーム」シートに1行残し、管理者にメールする（同じ生徒へのメールは6時間に1回まで）。
 * 保存そのものは止めない（見張るだけ）。
 * 管理者のメールアドレスは、Apps Script の「プロジェクトの設定」→「スクリプト プロパティ」に
 * キー ADMIN_EMAILS、値にアドレス（複数ならカンマ区切り）で登録する。コードには書かない。
 * =================================================================== */
const ALARM_SHEET = 'アラーム';
const ALARM_HEAD = ['日時', 'メール', 'ゲーム内の名前', '本名', '増え方', '前回の保存からの時間（分）'];
// 許す増え方＝ base ＋ perMin ×（前回の保存からの分）
const JUMP_RULE = {
  drills: { label: '問題演習の回数', base: 3, perMin: 1.5 },
  okQ: { label: '正解済みの問題', base: 60, perMin: 30 },
  shiori: { label: '栞', base: 800, perMin: 100 },
  cards: { label: '頁の種類', base: 15, perMin: 1 },
  g: { label: 'もらったGの合計', base: 3000, perMin: 400 },
};

function jumpVals_(o) {
  const qs = o.qs || {};
  return {
    drills: Number(o.drills || 0),
    okQ: Object.keys(qs).filter(function (k) { return qs[k] === 1; }).length,
    shiori: Array.isArray(o.sh) ? o.sh.reduce(function (a, b) { return a + (Number(b) || 0); }, 0) : Number(o.shiori || 0),
    cards: Object.keys(o.cards || {}).length,
    g: Number(o.gt || 0),
  };
}

function checkJump_(old, S, lastSaved) {
  const last = lastSaved instanceof Date ? lastSaved.getTime() : 0;
  if (!last) return [];
  const min = Math.max(1, (Date.now() - last) / 60000);
  const a = jumpVals_(old), b = jumpVals_(S), out = [];
  Object.keys(JUMP_RULE).forEach(function (k) {
    const R = JUMP_RULE[k], d = b[k] - a[k];
    if (d > R.base + R.perMin * min) out.push(R.label + ' ' + a[k] + '→' + b[k] + '（＋' + d + '）');
  });
  if (out.length) out.push('_min:' + Math.round(min));
  return out;
}

function alarm_(email, S, real, jump, force) {
  const min = jump.filter(function (x) { return x.indexOf('_min:') === 0; }).map(function (x) { return Number(x.slice(5)); })[0] || '';
  const items = jump.filter(function (x) { return x.indexOf('_min:') !== 0; });
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(ALARM_SHEET);
  if (!sh) {
    sh = ss.insertSheet(ALARM_SHEET);
    sh.appendRow(ALARM_HEAD);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, ALARM_HEAD.length).setFontWeight('bold');
  }
  sh.appendRow([new Date(), email, String(S.name || ''), real, items.join('／'), min]);
  try {
    const to = String(PropertiesService.getScriptProperties().getProperty('ADMIN_EMAILS') || '').trim();
    const cache = CacheService.getScriptCache();
    if (to && (force || !cache.get('al:' + email))) {
      cache.put('al:' + email, '1', 21600);
      MailApp.sendEmail(to, (force ? '【エラータ】問題演習を止めました：' : '【エラータ】記録の急な増え方：') + (real || email),
        (force ? (real || '') + '（' + email + '）の問題演習を、自動操作の疑いで止めました。\n\n' : (real || '') + '（' + email + '）の記録が、前回の保存から' + min + '分で次のように増えました。\n\n') + items.join('\n') +
        '\n\nスプレッドシートの「アラーム」シートに記録しています。保存は止めていません。');
    }
  } catch (e) {}
}

/* ===================================================================
 * 問題演習ログ（成績用の取り組み回数）
 * 端末の記録は書き換えられるので、成績に使う回数はこのログから数える。
 * ・drillStart：問題演習を始めたときに呼ばれる。受付番号を作り、この保存係の時計で開始時刻を覚えておく（6時間）
 * ・drillLog：終わったとき（途中で中断したときも）に呼ばれる。受付番号を確かめて、「問題演習ログ」シートに1行足す
 *   状態：確認済み（受付番号が本物）／受付切れ（6時間を過ぎた・別のアカウントの番号）／未確認（受付番号なし＝始めたときに通信できなかった）
 * 数えるかどうかは、updateProgress（取り組み状況を更新）のときに決める（下の LOG_RULE）。
 * =================================================================== */
const LOG_SHEET = '問題演習ログ';
const LOG_HEAD = ['日時', 'メール', '状態', '秒数（保存係の時計）', '答えた数', '正解数', '問題ID', '正誤', '秒数（端末）', 'ハード', '中断', '棚', '答えるまでの秒数', '自動操作の判定', '端末'];
const LOG_RULE = {
  minQ: 5,         // 1回と数える最低の問題数（途中で中断した回も、これだけ答えていれば数える）
  minSecPerQ: 2.5, // 1問あたりの平均秒数がこれより短いと数えない
};

function logSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(LOG_SHEET);
  if (!sh) {
    sh = ss.insertSheet(LOG_SHEET);
    sh.appendRow(LOG_HEAD);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, LOG_HEAD.length).setFontWeight('bold');
  }
  return sh;
}

function drillStart(label) {
  const email = me_();
  const tok = Utilities.getUuid().replace(/-/g, '').slice(0, 20);
  const lock = lockUntil_(email);
  if (lock > Date.now()) return { lock: lock };
  CacheService.getScriptCache().put('dk:' + tok, JSON.stringify({ m: email, t: Date.now() }), 21600);
  return { tok: tok };
}

function drillLog(p) {
  const email = me_();
  if (!p || typeof p !== 'object') throw new Error('記録の形がちがいます');
  const ids = Array.isArray(p.ids) ? p.ids.slice(0, 60).map(function (x) { return String(x).slice(0, 40); }) : [];
  const r = String(p.r || '').replace(/[^01]/g, '').slice(0, ids.length);
  if (!ids.length || r.length !== ids.length) throw new Error('記録の形がちがいます');
  const cid = String(p.cid || '').slice(0, 30);
  const cache = CacheService.getScriptCache();
  // 同じ記録を2回送ってきたとき（通信が切れて送り直したときなど）は、1回分だけにする
  if (cid && cache.get('dc:' + email + ':' + cid)) return { ok: true, dup: true };
  let state = '未確認', sec = '';
  const tok = String(p.tok || '').slice(0, 40);
  if (tok) {
    if (cache.get('du:' + tok)) return { ok: true, dup: true };
    let rec = null;
    try { rec = JSON.parse(cache.get('dk:' + tok) || 'null'); } catch (e) { rec = null; }
    if (rec && rec.m === email) {
      state = '確認済み';
      sec = Math.round((Date.now() - rec.t) / 1000);
      cache.remove('dk:' + tok);
      cache.put('du:' + tok, '1', 21600);
    } else {
      state = '受付切れ';
    }
  }
  const okN = r.split('').filter(function (c) { return c === '1'; }).length;
  const dt = (Array.isArray(p.dt) ? p.dt : []).slice(0, ids.length).map(function (x) { return Number(x); });
  const env = p.env && typeof p.env === 'object' ? p.env : {};
  // 自動操作の判定：端末が止めた理由（p.b）か、保存係でも同じ基準で判定する
  const why = String(p.b || '').slice(0, 60) || botVerdict_(dt, r, env);
  if (why) state = '自動操作の疑い';
  const tooFast = state === '確認済み' && sec < ids.length * LOG_RULE.minSecPerQ;
  const envTxt = (env.wd ? '自動操作ブラウザ／' : '') + (Number(env.tp) > 0 ? 'タッチ端末' : 'タッチなし') + '／' + String(env.ua || '').slice(0, 120);
  const row = [new Date(), email, state, sec, ids.length, okN, ids.join(','), r, Number(p.cs) || '', p.h ? 'ハード' : '', p.s ? '中断' : '', String(p.k || '').slice(0, 40),
    dt.map(function (x) { return x >= 0 ? (x / 10).toFixed(1) : '時間切れ'; }).join(','), why, envTxt];
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  let until = 0;
  try {
    logSheet_().appendRow(row);
    // 正解率に使う「問題ごとの最後の答え」。自動操作の疑いの回・速すぎる回は入れない
    if (!why && !tooFast) putResults_(email, ids, r);
    if (why) until = setLock_(email);
  } finally {
    lock.releaseLock();
  }
  if (why) {
    let real = '', name = '';
    try { const sv = sheet_(); const rw = findRow_(sv, email); if (rw) { real = String(sv.getRange(rw, COL_REAL).getValue() || ''); name = JSON.parse(String(sv.getRange(rw, COL_DATA).getValue() || '{}')).name || ''; } } catch (e) {}
    alarm_(email, { name: name }, real, ['自動操作の疑いで問題演習を止めた：' + why + '（' + Utilities.formatDate(new Date(until), 'Asia/Tokyo', 'M/d H:mm') + 'まで）', '端末：' + envTxt], true);
  }
  if (cid) cache.put('dc:' + email + ':' + cid, '1', 21600);
  return { ok: true, lock: until || 0 };
}

/* ===================================================================
 * 自動操作の判定と、問題演習の一時停止（ロック）
 * 判定の基準はゲーム側（index.html の botVerdict）と同じ。
 *  ・ブラウザの自動操作（navigator.webdriver）
 *  ・タッチなしのLinuxの端末（生徒はiPadで遊ぶ前提。遠隔のAIが動かすブラウザはこれになる）。Windows・Macは止めない
 *  ・管理者（先生）のアカウントも判定する（試すため）。isAdmin_ は時間の制限を外すときに使う
 *  ・12問以上で、答えるまでの時間の中央値が0.9秒未満
 *  ・15問以上で、答える間隔のばらつき（標準偏差÷平均）が0.12未満、かつ9割以上正解
 * 止める時間：1回目は1時間。7日以内に2回目以降は24時間。
 * 解除はスプレッドシートのメニュー「エラータ」→「問題演習の停止をすべて解除」。
 * =================================================================== */
const BOT_LOCK = { firstMs: 3600000, againMs: 86400000, windowMs: 7 * 86400000 };

function botVerdict_(dt, r, env) {
  const d = [], ok = [];
  dt.forEach(function (x, i) { if (x >= 0) { d.push(x / 10); ok.push(r.charAt(i) === '1'); } });
  const n = d.length;
  if (env && env.wd && n >= 3) return 'ブラウザの自動操作';
  const ua = String(env && env.ua || '');
  if (n >= 1 && env && !Number(env.tp) && /Linux/.test(ua) && !/Android/.test(ua)) return 'iPad以外の端末（タッチなし・Linux）';
  if (!n) return '';
  const so = d.slice().sort(function (a, b) { return a - b; });
  const med = so[Math.floor(n / 2)];
  const mean = d.reduce(function (a, b) { return a + b; }, 0) / n;
  const sd = Math.sqrt(d.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n);
  const cv = mean ? sd / mean : 0;
  const acc = ok.filter(Boolean).length / n;
  if (n >= 12 && med < 0.9) return '答えるのが速すぎる（中央値' + med.toFixed(1) + '秒）';
  if (n >= 15 && cv < 0.12 && acc >= 0.9) return '答える間隔が一定すぎる（ばらつき' + cv.toFixed(2) + '）';
  return '';
}

function isAdmin_(email) {
  const list = String(PropertiesService.getScriptProperties().getProperty('ADMIN_EMAILS') || '').toLowerCase().split(/[,\s]+/).filter(Boolean);
  return list.indexOf(String(email).toLowerCase()) >= 0;
}

function lockUntil_(email) {
  try { const o = JSON.parse(PropertiesService.getScriptProperties().getProperty('lock:' + email) || 'null'); return o ? Number(o.until) || 0 : 0; } catch (e) { return 0; }
}

function setLock_(email) {
  const P = PropertiesService.getScriptProperties();
  let o = null;
  try { o = JSON.parse(P.getProperty('lock:' + email) || 'null'); } catch (e) { o = null; }
  const now = Date.now();
  const again = o && o.last && now - Number(o.last) < BOT_LOCK.windowMs;
  const until = now + (again ? BOT_LOCK.againMs : BOT_LOCK.firstMs);
  P.setProperty('lock:' + email, JSON.stringify({ until: until, last: now, n: (o && o.n || 0) + 1 }));
  return until;
}

function unlockAll() {
  const P = PropertiesService.getScriptProperties();
  // 止めた回数の記録（7日以内の2回目は24時間にするため）は残し、止めている時間だけ消す
  let n = 0;
  P.getKeys().filter(function (k) { return k.indexOf('lock:') === 0; }).forEach(function (k) {
    try { const o = JSON.parse(P.getProperty(k) || '{}'); if (Number(o.until) > Date.now()) n++; o.until = 0; P.setProperty(k, JSON.stringify(o)); } catch (e) { P.deleteProperty(k); }
  });
  SpreadsheetApp.getActive().toast(n + '人分の停止を解除しました', 'エラータ', 5);
}

/* ===================================================================
 * 正誤記録（正解率の元）
 * 生徒ごとに1行、「問題ID→最後の答え（1＝正解／0＝不正解）」をJSONで持つ。
 * 問題演習ログを送ってきたときに更新する（自動操作の疑いの回・速すぎる回は入れない）。
 * 取り組み状況シートの正解率と、ゲームの「自分の正解率」はここから計算する。
 * =================================================================== */
const RES_SHEET = '正誤記録';

function resSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(RES_SHEET);
  if (!sh) {
    sh = ss.insertSheet(RES_SHEET);
    sh.appendRow(['メール', '更新', '正誤（問題ID→最後の答え）']);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, 3).setFontWeight('bold');
  }
  return sh;
}

function putResults_(email, ids, r) {
  const sh = resSheet_();
  const row = findRow_(sh, email);
  let m = {};
  if (row) { try { m = JSON.parse(String(sh.getRange(row, 3).getValue() || '{}')); } catch (e) { m = {}; } }
  ids.forEach(function (id, i) { m[id] = r.charAt(i) === '1' ? 1 : 0; });
  const json = JSON.stringify(m);
  if (row) sh.getRange(row, 2, 1, 2).setValues([[new Date(), json]]);
  else sh.appendRow([email, new Date(), json]);
}

function getResults_(email) {
  const sh = SpreadsheetApp.getActive().getSheetByName(RES_SHEET);
  if (!sh) return {};
  const row = findRow_(sh, email);
  if (!row) return {};
  try { return JSON.parse(String(sh.getRange(row, 3).getValue() || '{}')); } catch (e) { return {}; }
}

/** ゲームの「自分の正解率」用。自分の正誤記録だけを返す */
function getMyRates() {
  return { data: JSON.stringify(getResults_(me_())) };
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
 * 1行＝生徒1人。章ごとに「回数」（その章を解いた問題演習の回数）と「正解率」（その章の問題のうち、最後に答えたときに正解だった割合。「正誤記録」シートから計算）。
 * 正解率のセルにカーソルを合わせると、正解・間違えたまま・全問の数が出る（メモ）。
 * 回数は「問題演習ログ」シートから数える（端末の記録は書き換えられるため）。ログを入れる前に遊んだ分は数えていない。
 * 「端末の記録の回数」は参考。ログより10回以上多いと「要確認」に印が出る。
 * =================================================================== */
const PROG_SHEET = '取り組み状況';
const GAME_URL = 'https://raylekeiss.github.io/errata/index.html';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('エラータ')
    .addItem('取り組み状況を更新', 'updateProgress')
    .addItem('問題演習の停止をすべて解除', 'unlockAll')
    .addToUi();
}

/** ゲーム本体から、問題ID→章 と 章ごとの問題数・章の名前を読む */
function gameData_() {
  const html = UrlFetchApp.fetch(GAME_URL + '?v=' + Date.now(), { muteHttpExceptions: true }).getContentText('UTF-8');
  const m = html.match(/<script[^>]*id="errata-data"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('ゲーム本体から問題を読み込めませんでした');
  const D = JSON.parse(m[1]);
  const chOf = {}, total = {};
  const regOf = {};
  // ゲームと同じく、削除した問題（del）は数えない。正解率の分母は通常の問題演習の問題（ch があり、u・z でない）
  (D.Q || []).forEach(function (q) { if (q.del || !q.ch || q.u || q.z) return; chOf[q.id] = q.ch; regOf[q.id] = q.ch; total[q.ch] = (total[q.ch] || 0) + 1; });
  const n = Object.keys(D.chapters || {}).length || 15;
  const names = [];
  for (let c = 1; c <= n; c++) names.push((D.chapters || {})[c] || ('第' + c + '章'));
  return { chOf: chOf, regOf: regOf, total: total, names: names };
}

/**
 * 問題演習ログを数える。メールごとに
 *  n：数えた回／un：未確認の回（受付番号なし・受付切れ）／ng：数えなかった回／ch：章ごとの数えた回
 * 1回と数える条件（LOG_RULE）：確認済み・答えた数が minQ 問以上・1問あたり平均 minSecPerQ 秒以上。
 * 途中で中断した回も、この条件を満たせば数える。回数の上限はない（試験前に詰め込んでもよい）。
 * 章ごとの回数は、その回に答えた章（通常の問題演習の問題）を1回ずつ数える。
 */
function countLog_(G) {
  const out = {};
  const sh = SpreadsheetApp.getActive().getSheetByName(LOG_SHEET);
  if (!sh || sh.getLastRow() < 2) return out;
  const vals = sh.getRange(2, 1, sh.getLastRow() - 1, LOG_HEAD.length).getValues();
  vals.forEach(function (v) {
    const em = String(v[1] || ''); if (!em) return;
    const o = out[em] || (out[em] = { n: 0, un: 0, ng: 0, ch: {} });
    const state = String(v[2]), sec = Number(v[3]) || 0, n = Number(v[4]) || 0;
    if (state === '自動操作の疑い') { o.ng++; return; }
    if (state !== '確認済み') { o.un++; return; }
    if (n < LOG_RULE.minQ || sec < n * LOG_RULE.minSecPerQ) { o.ng++; return; }
    const chs = {};
    String(v[6] || '').split(',').forEach(function (id) { const c = G.regOf[id]; if (c) chs[c] = true; });
    const keys = Object.keys(chs);
    if (!keys.length) { o.ng++; return; }
    keys.forEach(function (c) { o.ch[c] = (o.ch[c] || 0) + 1; });
    o.n++;
  });
  return out;
}

function updateProgress() {
  const G = gameData_();
  const N = G.names.length;
  const src = sheet_();
  const last = src.getLastRow();
  const rows = last >= 2 ? src.getRange(2, 1, last - 1, COL_REAL).getValues() : [];

  const L = countLog_(G);
  // 正解率は「正誤記録」から（端末の記録は書き換えられるため）
  const RES = {};
  const rsh = SpreadsheetApp.getActive().getSheetByName(RES_SHEET);
  if (rsh && rsh.getLastRow() >= 2) rsh.getRange(2, 1, rsh.getLastRow() - 1, 3).getValues().forEach(function (v) { try { RES[String(v[0])] = JSON.parse(String(v[2] || '{}')); } catch (e) {} });
  const head = ['本名', 'ゲーム内の名前', 'メール', '最終保存', '問題演習の回数（ログで数えた回）', '未確認の回（通信できなかった回）', '数えなかった回（速すぎ・5問未満・自動操作の疑い）', '端末の記録の回数（参考）', '要確認', '受験対策の正解数', '記述対策（実戦を書いた数）'];
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
    const RS = RES[String(v[0] || '')] || {};
    Object.keys(RS).forEach(function (id) {
      const c = G.chOf[id];
      if (!c) return;
      if (RS[id] === 1) ok[c] = (ok[c] || 0) + 1;
      else ng[c] = (ng[c] || 0) + 1;
    });
    let jk = 0;
    Object.keys(S.jq || {}).forEach(function (u) { jk += String(S.jq[u]).split('1').length - 1; });
    let kjW = 0;
    Object.keys(S.kj || {}).forEach(function (id) { const r = S.kj[id]; if (Array.isArray(r) && Number(r[2]) >= 0) kjW++; });
    const em = String(v[0] || '');
    const lg = L[em] || { n: 0, un: 0, ng: 0, ch: {} };
    const dev = Number(S.drills || 0);
    // 端末の記録がログより大きくずれている（記録を書き換えた可能性）。ログを入れる前に遊んだ分もずれになるので、導入後しばらくは目安
    const warn = dev - lg.n - lg.un - lg.ng >= 10 ? 'ずれ ' + (dev - lg.n - lg.un - lg.ng) + '回' : '';
    const row = [String(v[COL_REAL - 1] || ''), String(S.name || ''), em, v[2] || '', lg.n, lg.un, lg.ng, dev, warn, jk, kjW];
    const note = ['', '', '', '', '', '', '', '', '', '', ''];
    for (let c = 1; c <= N; c++) {
      const t = G.total[c] || 0, a = ok[c] || 0, b = ng[c] || 0;
      row.push(Number(lg.ch[c] || 0));
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

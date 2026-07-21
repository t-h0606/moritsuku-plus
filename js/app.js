/* =====================================================================
   もりつく＋ アプリ本体
   ---------------------------------------------------------------------
   このファイルは「動き」だけを持ちます。中身（記事・動画・天気・スタッフ）は
   すべて data/ フォルダの JSON にあります。文言や記事を直すときは data/ を編集し、
   このファイルは触らないでください。
   ===================================================================== */

const CITY_NAMES = { moriya: "守谷", tsukuba: "つくば", tsukubamirai: "つくばみらい" };
const CAT_NAMES = { news: "ニュース", event: "イベント", gourmet: "グルメ", kids: "キッズ", ibaraki: "県内全域" };

// 読み込んだデータの置き場
let ARTICLES = [], VIDEOS = {}, WEATHER = {}, STAFF = [];
let WX_CASTERS = [], WX_COMMENTS = {}, NEWS_REPORTERS = [], ONAIR_STAFF = [], NEXT_AVATAR_IDX = 2;

let state = { city: "all", cat: "all", weekOpen: false };

/* ========== データ読み込み ========== */
async function loadJSON(path) {
  // preview-local.html から開いたときは、埋め込み済みのデータをそのまま使う
  if (window.__PRELOAD && window.__PRELOAD[path]) return window.__PRELOAD[path];
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(path + " が読めませんでした（" + res.status + "）");
  return res.json();
}

async function boot() {
  try {
    const [staff, articles, videos, weather] = await Promise.all([
      loadJSON("data/staff.json"),
      loadJSON("data/articles.json"),
      loadJSON("data/videos.json"),
      loadJSON("data/weather.json")
    ]);

    STAFF = staff.staff;
    WX_CASTERS = staff.wxCasters;
    WX_COMMENTS = staff.wxComments;
    NEWS_REPORTERS = staff.newsReporters;
    ONAIR_STAFF = staff.onairStaff;
    NEXT_AVATAR_IDX = staff.nextAvatarIdx;
    ARTICLES = articles.items;
    VIDEOS = videos;
    WEATHER = weather;

    renderFeed();
    renderVideo();
    renderNext();
    renderShelf();
    renderStaff();
    renderWeather();
    renderNewsCaster();
    renderOnairCaster();
    bindControls();

    // ページを開きっぱなしでも午前5時をまたいだら自動で交代する
    setInterval(() => { renderNewsCaster(); renderOnairCaster(); renderWeather(); }, 60 * 1000);
  } catch (e) {
    console.error(e);
    document.getElementById("feed").innerHTML =
      '<div class="empty">データの読み込みに失敗しました。ページを再読み込みしてください。</div>';
  }
}

/* ========== もりつく気象台 ========== */

// 天気の種類を判定。キャスターのセリフはこの4分類で選ばれる。
// 気象庁の天気コードは update_weather.py で絵文字に変換済みなので、ここは絵文字を見れば足りる。
function wxType(w) {
  if (/🌧|⛈|🌦|❄|🌨/.test(w.icon)) return "rain";
  if (typeof w.high === "number" && w.high >= 31) return "hot";
  if (/⛅|☁|🌫/.test(w.icon)) return "cloud";
  return "sun";
}

// 気温などが取れなかったときは「―」を出す（数字が消えて崩れるのを防ぐ）
function num(v) { return (v === null || v === undefined || v === "") ? "―" : v; }

function renderWeather() {
  // 気象庁の予報単位は「茨城県南部」で、3市に分かれない。
  // よって天気は常に1本。駅セレクタを押しても変わらない（記事だけが絞り込まれる）
  const w = WEATHER.forecast;
  const c = pickOfDay(WX_CASTERS);   // キャスターは午前5時交代の日替わり
  const type = wxType(w);
  const sky = type === "rain" ? "sky-rain" : type === "cloud" ? "sky-cloud" : "sky-sun";
  // 表示する日付。17時の発表以降は今日の気温が予報の対象外になるため、
  // update_weather.py が対象日を明日に切り替えて targetLabel に入れてくる。
  const now = new Date();
  const dateStr = WEATHER.targetLabel
    || `${now.getMonth() + 1}月${now.getDate()}日（${"日月火水木金土"[now.getDay()]}）`;
  document.getElementById("weatherCard").innerHTML = `
    <div class="wx-stage ${sky}" style="--cc:${c.cc}">
      <div class="wx-caster">
        <img src="${STAFF[c.idx].img}" alt="${c.name}">
        <span class="wx-caster-tag">${c.name} ${c.label}</span>
      </div>
      <div class="wx-main">
        <div class="wx-bubble">${WX_COMMENTS[c.comments][type]}</div>
        <div class="wx-city">${dateStr}｜${w.city}</div>
        <div class="wx-now">
          <div class="wx-icon">${w.icon}</div>
          <div class="wx-temp-block">
            <div class="wx-temp">${num(w.high)}°<span class="low">/ ${num(w.low)}°</span></div>
            <div class="wx-cond">${w.cond}</div>
            <div class="wx-hourly-note">％＝降水確率</div>
          </div>
          <div class="wx-hourly" aria-label="時間帯ごとの降水確率">
            ${w.hourly.map(h => `
              <div class="h-slot">
                <div class="h-time">${h.day ? `<span class="h-day">${h.day}</span>` : ""}${h.t}</div>
                <div class="h-icon">${h.icon}</div>
                <div class="h-temp">${h.pop === null || h.pop === undefined ? "―" : h.pop + "%"}</div>
              </div>`).join("")}
          </div>
        </div>
      </div>
      <div class="wx-week-side">
        <div class="ws-title">週間予報</div>
        ${w.week.map((d, i) => `
          <div class="ws-row${i === 0 ? " today" : ""}">
            <span class="ws-d">${d.d}</span>
            <span class="ws-i">${d.icon}</span>
            <span class="ws-t">
              ${num(d.hi)}°<span class="lo">/${num(d.lo)}°</span>
              <span class="ws-pop">${d.pop === null || d.pop === undefined ? "" : d.pop + "%"}</span>
            </span>
          </div>`).join("")}
      </div>
    </div>
    <div class="wx-foot">
      <button class="wx-week-toggle${state.weekOpen ? " open" : ""}" onclick="toggleWeek()" aria-expanded="${!!state.weekOpen}">週間予報</button>
      <span class="wx-note-inline">気象データ提供：気象庁</span>
    </div>
    <div class="wx-week${state.weekOpen ? " open" : ""}" style="--cc:${c.cc}">
      ${w.week.map((d, i) => `
        <div class="w-day${i === 0 ? " today" : ""}">
          <div class="d-label">${d.d}</div>
          <div class="d-icon">${d.icon}</div>
          <div class="d-temp">${num(d.hi)}°<span class="lo">/${num(d.lo)}°</span></div>
          <div class="d-pop">${d.pop === null || d.pop === undefined ? "" : d.pop + "%"}</div>
        </div>`).join("")}
    </div>`;
}

// 週間予報の開閉（スマホ用。PCでは常時表示のためボタン自体が非表示）
function toggleWeek() {
  state.weekOpen = !state.weekOpen;
  renderWeather();
}

/* ========== 記事カード ========== */

// 記事サムネイル：先頭記事（フィーチャー型）のみ使用。
// 記事データに thumb:"images/xxx.webp" を入れれば任意の画像に、無ければジャンル色グラデ＋絵文字
const CAT_TINTS = {
  news:    ["#2E3F63", "#5A76AC"],
  event:   ["#7A4FD0", "#B48CFF"],
  gourmet: ["#E8603C", "#FFB870"],
  kids:    ["#E85D9C", "#FFA8CF"],
  ibaraki: ["#0E7C87", "#5FC9D4"]
};
function thumbHTML(a, cls) {
  if (a.thumb) return `<span class="thumb ${cls}"><img src="${a.thumb}" alt=""></span>`;
  const [c1, c2] = CAT_TINTS[a.category] || ["#9DA9C0", "#C9D2E4"];
  return `<span class="thumb ${cls}" style="background:linear-gradient(135deg,${c1},${c2})">${a.emoji || "📰"}</span>`;
}

// 記事の日付から「2時間前」「昨日」などの表示を自動で作る。
// data 側は date:"2026-07-17"（同日中なら "2026-07-17T14:30"）と書けばよく、
// 手で「2時間前」と書き換える必要がありません。ago が直接書いてあればそちらを優先。
function agoLabel(a) {
  if (a.ago) return a.ago;
  if (!a.date) return "";
  const d = new Date(String(a.date).replace(" ", "T"));
  if (isNaN(d)) return "";
  const hasTime = /T\d/.test(String(a.date));
  const now = new Date();
  const hours = (now - d) / 3600000;
  if (hasTime && hours < 24) {
    const h = Math.max(1, Math.floor(hours));
    return h + "時間前";
  }
  const day0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day1 = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((day0 - day1) / 86400000);
  if (days <= 0) return "今日";
  if (days === 1) return "昨日";
  if (days < 7) return days + "日前";
  return (d.getMonth() + 1) + "月" + d.getDate() + "日";
}

function linkAttrs(url) {
  return url ? `href="${url}" target="_blank" rel="noopener"` : `href="#"`;
}

function renderFeed() {
  // 「県内全域」は3市に属さない記事。専用タブの中だけに出し、他のタブには一切混ざらない
  const list = ARTICLES.filter(a => {
    if (state.cat === "ibaraki") return a.category === "ibaraki";
    if (a.category === "ibaraki") return false;
    const cityOk = state.city === "all" || (a.city || []).includes(state.city);
    const catOk = state.cat === "all" || state.cat === "video" || a.category === state.cat;
    return cityOk && catOk;
  });
  document.getElementById("emptyNote").hidden = list.length > 0;
  document.getElementById("feed").innerHTML = list.map((a, i) => {
    const badges = `
      <div class="badges">
        <span class="cat ${a.category}">${CAT_NAMES[a.category]}</span>
        ${a.city.map(c => `<span class="city-badge ${c}">${CITY_NAMES[c]}</span>`).join("")}
      </div>`;
    const meta = `<div class="meta"><span class="src">${a.source}</span><span>${agoLabel(a)}</span><span class="arrow">→</span></div>`;
    if (i === 0) {
      // 先頭記事：サムネイル大型・上部配置のフィーチャー型
      return `
    <a class="card featured" ${linkAttrs(a.url)}>
      ${thumbHTML(a, "thumb-lg")}
      <div class="card-main">
        ${badges}
        <div class="title">${a.title}</div>
        ${meta}
      </div>
    </a>`;
    }
    return `
    <a class="card" ${linkAttrs(a.url)}>
      <div class="card-main">
        ${badges}
        <div class="title">${a.title}</div>
        ${meta}
      </div>
    </a>`;
  }).join("");
}

/* ========== 動画 ========== */

// YouTubeのURLから動画IDだけを取り出す（https://youtu.be/xxxx でも
// https://www.youtube.com/watch?v=xxxx でも、IDそのままでも受け付ける）
function youtubeId(v) {
  if (!v) return "";
  const m = String(v).match(/(?:youtu\.be\/|v=|embed\/|shorts\/)([A-Za-z0-9_-]{6,})/);
  return m ? m[1] : String(v).trim();
}
function youtubeWatch(v) {
  const id = youtubeId(v);
  return id ? "https://www.youtube.com/watch?v=" + id : "";
}
function youtubeThumb(v) {
  const id = youtubeId(v);
  return id ? `https://img.youtube.com/vi/${id}/maxresdefault.jpg` : "";
}

// YouTubeが未設定のときに出す仮サムネイル（番組ごとの絵柄）
function artSVG(art, uid) {
  const a = art || {};
  const t = a.title || "", s = a.sub || "";
  if (a.style === "news") {
    return `<svg viewBox="0 0 640 360" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#16203A"/><stop offset="1" stop-color="#3D7BFF"/>
      </linearGradient></defs>
      <rect width="640" height="360" fill="url(#${uid})"/>
      <rect x="0" y="268" width="640" height="92" fill="#101830" opacity="0.85"/>
      <rect x="30" y="288" width="220" height="18" rx="9" fill="#3D7BFF"/>
      <rect x="30" y="316" width="330" height="12" rx="6" fill="#55688C"/>
      <text x="34" y="120" font-family="sans-serif" font-size="52" font-weight="900" fill="#fff">${t}</text>
      <text x="36" y="160" font-family="sans-serif" font-size="26" font-weight="700" fill="#9DB8FF">${s}</text>
    </svg>`;
  }
  if (a.style === "gourmet") {
    return `<svg viewBox="0 0 640 360" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#E8603C"/><stop offset="1" stop-color="#FF9A6B"/>
      </linearGradient></defs>
      <rect width="640" height="360" fill="url(#${uid})"/>
      <circle cx="320" cy="200" r="120" fill="#fff" opacity="0.16"/>
      <circle cx="320" cy="200" r="86" fill="#fff" opacity="0.2"/>
      <text x="36" y="98" font-family="sans-serif" font-size="36" font-weight="900" fill="#fff">${t}</text>
      <text x="36" y="140" font-family="sans-serif" font-size="36" font-weight="900" fill="#fff">${s}</text>
    </svg>`;
  }
  // 既定＝TXさんぽ調
  return `<svg viewBox="0 0 640 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
    <defs><linearGradient id="${uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F59E2D"/><stop offset="1" stop-color="#FFD34D"/>
    </linearGradient></defs>
    <rect width="640" height="360" fill="url(#${uid})"/>
    <circle cx="520" cy="80" r="90" fill="#ffffff" opacity="0.18"/>
    <path d="M0 300 Q160 240 320 290 T640 280 V360 H0 Z" fill="#D97F12" opacity="0.55"/>
    <text x="42" y="205" font-family="sans-serif" font-size="44" font-weight="900" fill="#fff">${t}</text>
    <text x="44" y="248" font-family="sans-serif" font-size="24" font-weight="700" fill="#fff" opacity="0.9">${s}</text>
  </svg>`;
}

function screenHTML(v, uid) {
  const thumb = youtubeThumb(v.youtube);
  const inner = thumb
    ? `<img src="${thumb}" alt="" style="width:100%;height:100%;object-fit:cover;display:block">`
    : artSVG(v.art, uid);
  return `
    <a class="screen" ${linkAttrs(youtubeWatch(v.youtube))} aria-label="動画：${v.title}">
      ${inner}
      ${v.rec ? '<span class="rec"><i></i>REC</span>' : ""}
      <span class="play" aria-hidden="true"></span>
      ${v.duration ? `<span class="dur">${v.duration}</span>` : ""}
    </a>`;
}

function renderVideo() {
  const lead = VIDEOS.lead, subs = VIDEOS.subs || [];
  document.getElementById("videoLead").innerHTML = `
      <div class="main">
        ${screenHTML(lead, "vg-lead")}
        <div class="v-caption">
          <div class="t">${lead.title}</div>
          <div class="m">${lead.meta}</div>
        </div>
      </div>
      <div class="v-sub">
        ${subs.map((v, i) => `
        <div>
          ${screenHTML(v, "vg-sub" + i)}
          <div class="v-caption"><div class="t">${v.title}</div><div class="m">${v.meta}</div></div>
        </div>`).join("")}
      </div>`;
}

function renderNext() {
  const n = VIDEOS.next || {};
  document.getElementById("nextStrip").innerHTML = `
      <div class="next-thumb">
        <svg viewBox="0 0 320 180" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <rect width="320" height="180" fill="#101830"/>
          <text x="24" y="76" font-family="sans-serif" font-size="30" font-weight="900" fill="#2FA36B">COMING</text>
          <text x="24" y="112" font-family="sans-serif" font-size="30" font-weight="900" fill="#fff">SOON…</text>
          <rect x="24" y="132" width="130" height="10" rx="5" fill="#3A4763"/>
        </svg>
      </div>
      <img class="next-avatar" src="${STAFF[NEXT_AVATAR_IDX].img}" alt="制作プロデューサー ポン田P">
      <div class="next-body">
        <span class="next-label">次回予告</span>
        <div class="t">${n.title || ""}</div>
        <div class="d">${n.desc || ""}</div>
      </div>`;
}

function renderShelf() {
  const list = VIDEOS.library || [];
  document.getElementById("shelf").innerHTML = list.map((e, i) => {
    const thumb = youtubeThumb(e.youtube);
    const inner = thumb
      ? `<img src="${thumb}" alt="" style="width:100%;height:100%;object-fit:cover;display:block">`
      : `<svg viewBox="0 0 320 180" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs><linearGradient id="ep${i}" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="${e.c1}"/><stop offset="1" stop-color="${e.c2}"/>
          </linearGradient></defs>
          <rect width="320" height="180" fill="url(#ep${i})"/>
          <circle cx="268" cy="36" r="46" fill="#fff" opacity="0.15"/>
          <text x="20" y="104" font-family="sans-serif" font-size="26" font-weight="900" fill="#fff">${e.label}</text>
        </svg>`;
    return `
    <div class="item">
      <a class="screen" ${linkAttrs(youtubeWatch(e.youtube))} aria-label="過去放送：${e.t}">
        ${inner}
        <span class="play" aria-hidden="true"></span>
        <span class="dur">${e.dur}</span>
      </a>
      <div class="v-caption"><span class="ep-no">${e.no}</span><div class="t" style="font-size:0.85rem">${e.t}</div></div>
    </div>`;
  }).join("");
}

/* ========== スタッフ紹介 ========== */
function renderStaff() {
  document.getElementById("staff").innerHTML = STAFF.map(s => `
    <a class="staff-card" href="#">
      <span class="avatar" style="background:${s.bg}"><img src="${s.img}" alt="${s.name}" loading="lazy"></span>
      <span class="body">
        <div class="role">${s.role}</div>
        <div class="name">${s.name}</div>
        <div class="blog">${s.blog}</div>
      </span>
    </a>`).join("");
}

/* ========== 絞り込み操作 ========== */
function setPressed(sel, attr, val) {
  document.querySelectorAll(sel).forEach(b =>
    b.setAttribute("aria-pressed", b.dataset[attr] === val ? "true" : "false"));
}

function bindControls() {
  document.querySelectorAll(".station").forEach(b => b.addEventListener("click", () => {
    state.city = b.dataset.city; setPressed(".station", "city", state.city); renderFeed();
  }));
  document.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {
    state.cat = b.dataset.cat; setPressed(".chip", "cat", state.cat);
    applyVideoMode(state.cat === "video");
    renderFeed();
  }));
}

// ジャンル「動画」選択時：ヘッダー〜気象台〜「まちの新着ニュース」見出し〜ジャンルは固定のまま、
// ジャンルより下を「今週のオンエア（次回予告含む）→放送ライブラリー→記事カード→スタッフ紹介」の順にする。
// 実装：記事カード（#feed）だけを放送ライブラリー下の受け皿セクションへ移動する
function applyVideoMode(on) {
  const slot = document.getElementById("sec-feed-slot");
  const feed = document.getElementById("feed");
  const empty = document.getElementById("emptyNote");
  if (on) {
    document.getElementById("feedSlot").append(feed, empty);
    slot.hidden = false;
  } else {
    document.querySelector("#sec-articles .wrap").append(feed, empty);
    slot.hidden = true;
  }
}

/* ========== 日替わりキャラ（毎日 午前5時に交代） ========== */

// 「今日」を午前5時起点で数えた通し日数（当番決めの共通の物差し）
function broadcastDayNo(now) {
  const d = new Date(now || Date.now());
  if (d.getHours() < 5) d.setDate(d.getDate() - 1);   // 午前5時前はまだ「前日」扱い
  return Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86400000);
}
function pickOfDay(list, now) {
  const n = list.length;
  return list[((broadcastDayNo(now) % n) + n) % n];
}
function newsReporterOfDay(now) { return pickOfDay(NEWS_REPORTERS, now); }

// 当番のキャラ画像。useFlip が立っていれば反転版（見出しで右を向く用）を使う
function casterImage(r) {
  const s = STAFF[r.idx];
  return (r.useFlip && s.imgFlip) ? s.imgFlip : s.img;
}

let currentNewsReporter = null;
function renderNewsCaster() {
  const r = newsReporterOfDay();
  if (r === currentNewsReporter) return;   // 変わっていなければ何もしない
  currentNewsReporter = r;
  const s = STAFF[r.idx];
  const el = document.getElementById("newsCaster");
  const img = document.getElementById("newsCasterImg");
  img.src = casterImage(r);
  img.alt = s.name + "（" + r.label + "リポーター）";
  el.title = s.name + "／" + r.label + "リポーター";
  el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
}

let currentOnairStaff = null;
function renderOnairCaster() {
  const r = pickOfDay(ONAIR_STAFF);
  if (r === currentOnairStaff) return;
  currentOnairStaff = r;
  const s = STAFF[r.idx];
  const el = document.getElementById("onairCaster");
  const img = document.getElementById("onairCasterImg");
  img.src = casterImage(r);
  img.alt = s.name + "（" + r.label + "）";
  el.title = s.name + "／" + r.label;
  el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
}

/* ========== アプリ化（PWA）の下ごしらえ ========== */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(e => console.log("SW未登録", e));
  });
}

boot();

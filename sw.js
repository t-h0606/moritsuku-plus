/* もりつく＋ サービスワーカー
   役割：一度読んだ「入れ物」（HTML/CSS/JS/画像）を端末に保存し、2回目以降を高速化する。
   データ（data/*.json）は常に新しいものを取りに行き、通信できないときだけ保存分を使う。
   ※ サイトを更新したら下の CACHE の数字を1つ上げてください（古い保存分が捨てられます）。 */
const CACHE = "moritsuku-v47";
const SHELL = [
  "./", "./index.html", "./css/style.css", "./js/app.js", "./manifest.json",
  "./images/fukuro-kyokucho.webp", "./images/shiroku-gamako.webp", "./images/ponda-p.webp",
  "./images/uri-d.webp", "./images/fukuro-hamuta.webp", "./images/kawase-midori.webp",
  "./images/kawase-midori-flip.webp", "./images/shirasagi-non.webp", "./images/hayabusa-sora.webp",
  "./images/logo-moritsuku.webp"
];
self.addEventListener("install", e => {
  // 【v39で修正】caches.addAll(SHELL) だとブラウザのHTTPキャッシュが返す「古いapp.js」を
  // そのままキャッシュしてしまうことがあった（CACHE番号を上げても中身が更新されない事故の原因）。
  // fetch(url, {cache:"reload"}) で毎回ネットワークから新規に取得することで、
  // CACHE番号を上げたときに必ず最新の中身に入れ替わるようにする。
  e.waitUntil(
    caches.open(CACHE).then(cache =>
      Promise.all(SHELL.map(url =>
        fetch(url, { cache: "reload" }).then(res => cache.put(url, res))
      ))
    ).then(() => self.skipWaiting())
  );
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // データは「新しいもの優先」。取れなければ保存分（＝圏外でも直近の内容が読める）
  // データと、局内ツールの3ページ（記事投稿ページ・イベント投稿ページ・編成会議室）は「新しいもの優先」。
  // これらは更新頻度が高く、古いキャッシュが残ると投稿処理が古い版で動いてしまうため。
  if (url.pathname.includes("/data/") ||
      url.pathname.endsWith("/add-article.html") ||
      url.pathname.endsWith("/add-event.html") ||
      url.pathname.endsWith("/desk.html")) {
    e.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // 入れ物は「保存分優先」。無ければ取りに行く
  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(res => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match("./index.html")))
  );
});

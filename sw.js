/* もりつく＋ サービスワーカー
   役割：一度読んだ「入れ物」（HTML/CSS/JS/画像）を端末に保存し、2回目以降を高速化する。
   データ（data/*.json）は常に新しいものを取りに行き、通信できないときだけ保存分を使う。
   ※ サイトを更新したら下の CACHE の数字を1つ上げてください（古い保存分が捨てられます）。 */
const CACHE = "moritsuku-v4";
const SHELL = [
  "./", "./index.html", "./css/style.css", "./js/app.js", "./manifest.json",
  "./images/fukuro-kyokucho.webp", "./images/shiroku-gamako.webp", "./images/ponda-p.webp",
  "./images/uri-d.webp", "./images/fukuro-hamuta.webp", "./images/kawase-midori.webp",
  "./images/kawase-midori-flip.webp", "./images/shirasagi-non.webp", "./images/hayabusa-sora.webp"
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
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
  if (url.pathname.includes("/data/")) {
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

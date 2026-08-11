# -*- coding: utf-8 -*-
"""
もりつく＋ 報道部デスク（候補収集スクリプト）

GoogleニュースRSSから「過去7日以内」の記事だけを収集し、
data/candidates.json に候補リストとして保存する。
サイトに載せる記事は、編成会議室（desk.html）で人間が選ぶ（B案方式）。

仕組み：
1. when:7d 付きのRSSを見に行く（＝今週の分だけくださいという注文書）
2. 発行日をチェックして古い記事を捨てる（消印チェック）
3. すでにサイト掲載済みの記事を除外する（貼り済みチェック）
4. 前回までの候補と合流させ、重複を取り除いて保存する

実行方法（リポジトリの一番上の階層で）:
    pip install feedparser
    python scripts/collect.py
"""

import json
import re
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_FILE = ROOT / "data" / "candidates.json"
ARTICLES_FILE = ROOT / "data" / "articles.json"

MAX_AGE_DAYS = 7          # これより古い候補は消える
MAX_PER_FEED = 40         # 1つのRSSから読む最大件数
MAX_CANDIDATES = 150      # 候補リストの最大件数（3市と県内全域で別枠）

# 県全域のRSS（茨城新聞・LuckyFM）から拾うときの地名フィルタ。
# タイトルにこのどれかが入っている記事だけを候補にする。
# 水戸・日立など、もりつく＋の対象外の記事で候補リストが埋もれるのを防ぐため。
# 「筑波」は筑波山・筑波大学を拾える一方、筑波銀行など対象外の記事も混ざる。
# 余計なものが多いと感じたら、この行から "筑波" を消すだけでよい。
NEWS_AREA_WORDS = ["守谷", "つくばみらい", "つくば", "みらい平", "筑波",
                   "土浦", "石岡", "牛久", "取手", "常総"]

# ---- 収集する注文書（クエリ）一覧 -------------------------------------
# (デフォルト都市, デフォルトカテゴリ, 検索クエリ)
QUERIES = [
    # 時事ニュース（事件・行政・経済など全般）
    ("moriya",       "news",    "守谷市 when:7d"),
    ("tsukuba",      "news",    "つくば市 when:7d"),
    ("tsukubamirai", "news",    "つくばみらい市 when:7d"),
    # イベント
    ("moriya",       "event",   "守谷 (イベント OR 祭り OR フェス OR 開催 OR マルシェ) when:7d"),
    ("tsukuba",      "event",   "つくば (イベント OR 祭り OR フェス OR 開催 OR マルシェ) when:7d"),
    ("tsukubamirai", "event",   "つくばみらい (イベント OR 祭り OR 開催) when:7d"),
    # グルメ
    ("moriya",       "gourmet", "守谷 (オープン OR 開店 OR 新店 OR グルメ OR 新メニュー) when:7d"),
    ("tsukuba",      "gourmet", "つくば (オープン OR 開店 OR 新店 OR グルメ OR 新メニュー) when:7d"),
    ("tsukubamirai", "gourmet", "つくばみらい (オープン OR 開店 OR 新店) when:7d"),
    # キッズ（子育て）
    ("moriya",       "kids",    "守谷 (子育て OR 児童館 OR 親子 OR キッズ) when:7d"),
    ("tsukuba",      "kids",    "つくば (子育て OR 児童館 OR 親子 OR キッズ) when:7d"),
    ("tsukubamirai", "kids",    "つくばみらい (子育て OR 親子) when:7d"),
    # 3市周辺（土浦・常総・取手・牛久・石岡）— v追加。ジャンルは最新記事/イベント/グルメのみ収集
    ("kinko",         "news",    "(土浦市 OR 常総市 OR 取手市 OR 牛久市 OR 石岡市) when:7d"),
    ("kinko",         "event",   "(土浦 OR 常総 OR 取手 OR 牛久 OR 石岡) (イベント OR 祭り OR フェス OR 開催 OR マルシェ) when:7d"),
    ("kinko",         "gourmet", "(土浦 OR 常総 OR 取手 OR 牛久 OR 石岡) (オープン OR 開店 OR 新店 OR グルメ OR 新メニュー) when:7d"),
    # 県内全域（直近2日だけ・件数も絞る）
    ("ibaraki",      "news",    "茨城県 when:7d"),
]

# ---- 配信元のRSSを直接読む（Googleニュース経由とは別枠） ----------------
# Googleニュース経由だと記事URLが「news.google.com/rss/articles/...」という
# 転送用リンクになり、元記事のURLが分からない。Xに貼ってもカードが出ず、
# 読者も転送ページを1枚踏むことになる。
# ここに配信元のRSSを直接登録すると、元記事のURLがそのまま手に入る。
# ※ QUERIES（Googleニュース経由）は今までどおり全部生きている。これは上乗せ。
#
# (デフォルト都市, デフォルトカテゴリ, RSSのURL, 絞り込みキーワード or None)
#   絞り込みキーワードを入れると、タイトルにそのどれかが含まれる記事だけを拾う。
#   None なら全記事を拾う。
EXTRA_FEEDS = [
    # 号外NET（地元3市）。タイトルが必ず「【○○市】」で始まるので地域判定が正確。全記事を拾う
    ("moriya", "news", "https://toride-moriya-tsukubamirai.goguynet.jp/feed/", None),
    # 号外NET つくば市。全記事を拾う
    ("tsukuba", "news", "https://tsukuba.goguynet.jp/feed/", None),
    # 号外NET 土浦・かすみがうら・石岡市 → 3市周辺あつかい。全記事を拾う
    ("kinko", "news", "https://tsuchiura-kasumigaura-ishioka.goguynet.jp/feed/", None),
    # NEWSつくば（つくば・土浦の地域メディア）。全記事を拾う
    ("tsukuba", "news", "https://newstsukuba.jp/feed/", None),
    # LuckyFM 茨城放送。県全域なので地名で絞る
    ("kinko", "news", "https://lucky-ibaraki.com/feed/", NEWS_AREA_WORDS),
    # 茨城新聞クロスアイ。県全域が流れてくるので地名で絞る
    ("kinko", "news", "https://ibarakinews.jp/news/hphead.rss", NEWS_AREA_WORDS),
]

# ---- 仕分け用のキーワード ---------------------------------------------
GOURMET_WORDS = ["オープン", "開店", "閉店", "新店", "ランチ", "カフェ", "ラーメン",
                 "パン", "スイーツ", "グルメ", "新メニュー", "レストラン", "テイクアウト"]
EVENT_WORDS = ["イベント", "祭り", "まつり", "フェス", "開催", "マルシェ", "花火",
               "コンサート", "ワークショップ", "展示", "体験会"]
KIDS_WORDS = ["子育て", "児童館", "親子", "キッズ", "子ども", "こども", "保育", "幼稚園"]
# 3市周辺の判定用地名（タイトルにこれらが入っていれば city:kinko を付ける）
KINKO_WORDS = ["土浦", "常総", "取手", "牛久", "石岡"]

EMOJI = {"news": "📰", "event": "🎪", "gourmet": "🍜", "kids": "🧒", "ibaraki": "🗾"}


def gnews_url(query: str) -> str:
    return ("https://news.google.com/rss/search?q="
            + urllib.parse.quote(query) + "&hl=ja&gl=JP&ceid=JP:ja")


MEDIA_HINTS = ("新聞", "ニュース", "NEWS", "テレビ", "放送", "TIMES", "タイムス",
               "プレス", "デジタル", "クロスアイ", "オンライン", "Web", "web")


def strip_media_suffix(title: str) -> str:
    """タイトル末尾の「 - 媒体名」と「(媒体名)」を取り除く"""
    # GoogleニュースRSSは末尾に必ず「 - 媒体名」を付ける
    if " - " in title:
        head, _tail = title.rsplit(" - ", 1)
        if head.strip():
            title = head
    # さらに末尾に「(茨城新聞クロスアイ)」等が残っていれば除去
    m = re.search(r"[（(]([^（）()]{2,25})[）)]\s*$", title)
    if m and any(h in m.group(1) for h in MEDIA_HINTS):
        title = title[:m.start()]
    return title.strip()


def normalize_title(title: str) -> str:
    """重複判定用。末尾の「 - 媒体名」と空白を除去"""
    t = re.sub(r"\s*[-|｜–]\s*[^-|｜–]+$", "", title)
    return re.sub(r"\s+", "", t)


def make_id(title: str) -> str:
    return hashlib.md5(normalize_title(title).encode()).hexdigest()[:12]


def detect_cities(title: str, default_city: str) -> list:
    """タイトルの地名から担当市を判定（つくばみらい≠つくばに注意）"""
    t = title.replace("つくばみらい", "\u0000")  # 一時的に伏せ字にして誤判定防止
    hits = []
    if "守谷" in title:
        hits.append("moriya")
    if "\u0000" in t or "みらい平" in title:
        hits.append("tsukubamirai")
    if "つくば" in t:
        hits.append("tsukuba")
    if any(w in title for w in KINKO_WORDS):
        hits.append("kinko")
    return hits or [default_city]


def detect_category(title: str, default_cat: str) -> str:
    if any(w in title for w in KIDS_WORDS):
        return "kids"
    if any(w in title for w in GOURMET_WORDS):
        return "gourmet"
    if any(w in title for w in EVENT_WORDS):
        return "event"
    return default_cat


def clean_url(url: str) -> str:
    """記事URLから広告・解析用の飾りを落とす。
    LuckyFMのRSSは ?utm_source=rss&utm_medium=rss&... という長い追跡パラメータを
    付けてくる。そのまま保存すると、同じ記事が別物として重複判定されてしまう。"""
    url = (url or "").strip()
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    keep = [kv for kv in query.split("&")
            if kv and not kv.split("=")[0].lower().startswith(("utm_", "fbclid", "gclid"))]
    return base + ("?" + "&".join(keep) if keep else "")


def looks_garbled(entries) -> bool:
    """タイトルが文字化けしていないか見る。
    文字コードの解釈に失敗すると、読めなかった文字が「\ufffd（黒ひし形の?）」に
    置き換わる。これが混じっていたら化けていると判断する。"""
    for e in entries[:5]:
        if "\ufffd" in (e.get("title") or ""):
            return True
    return False


def fetch_feed(url: str):
    """RSSを1本読む。1本が落ちても全体を止めないよう、失敗しても空を返す。
    茨城新聞のRSSは宣言が UTF-8 なのに中身が別の文字コードで、そのままだと
    文字化けする。feedparser に文字コードを推測させたうえで、駄目なら
    バイト列から読み直す。"""
    try:
        parsed = feedparser.parse(url)
        if parsed.entries and not looks_garbled(parsed.entries):
            return parsed.entries
    except Exception as e:
        print(f"  [警告] 読み込み失敗: {url} ({e})")
        return []

    # 記事が取れなかった、または文字化けしていた場合はバイト列から読み直す
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "moritsuku-plus/1.0"})
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read()
        for enc in ("utf-8", "cp932", "euc-jp", "shift_jis"):
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue
            # 宣言と実体が食い違っているので、宣言のほうを実体に合わせる
            text = re.sub(r'encoding="[^"]*"', f'encoding="{enc}"', text, count=1)
            entries = feedparser.parse(text.encode(enc)).entries
            if entries:
                print(f"  [復旧] {url} を {enc} として読み直しました")
                return entries
    except Exception as e:
        print(f"  [警告] 読み直しも失敗: {url} ({e})")
    return []


def parse_published(entry):
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(JST)
    return datetime.now(JST)


# 配信元のRSSを直接読むときの媒体名（記事URLのドメインから引く）
SOURCE_BY_DOMAIN = {
    "toride-moriya-tsukubamirai.goguynet.jp": "号外NET",
    "tsukuba.goguynet.jp": "号外NET",
    "tsuchiura-kasumigaura-ishioka.goguynet.jp": "号外NET",
    "newstsukuba.jp": "NEWSつくば",
    "lucky-ibaraki.com": "LuckyFM 茨城放送",
    "ibarakinews.jp": "茨城新聞クロスアイ",
}


def source_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return SOURCE_BY_DOMAIN.get(host, "")


def clean_source(entry) -> str:
    if entry.get("source") and entry.source.get("title"):
        return entry.source.title
    return ""


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def collect():
    now = datetime.now(JST)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)

    # --- 掲載済みリスト（articles.json）を読み込む：貼り済みチェック用 ---
    posted_urls, posted_titles = set(), set()
    articles = load_json(ARTICLES_FILE, {})
    for item in articles.get("items", []):
        if item.get("url"):
            posted_urls.add(item["url"])
        if item.get("title"):
            posted_titles.add(normalize_title(item["title"]))

    # --- 前回までの候補を読み込む（消えないように合流させる） ---
    prev = load_json(CANDIDATES_FILE, {})
    pool = {}
    for c in prev.get("candidates", []):
        # 旧バージョンで収集した候補のタイトルから媒体名を除去
        c["title"] = strip_media_suffix(c.get("title", ""))
        # 旧バージョンの県内全域（city方式）をサイトの流儀（ジャンル方式）に変換
        if "ibaraki" in c.get("city", []):
            c["city"] = []
            c["category"] = "ibaraki"
            c["emoji"] = EMOJI["ibaraki"]
        # 「地名あり/なし」の印を付け直す
        if "sure" not in c:
            c["sure"] = (c.get("category") == "ibaraki") or any(
                k in c.get("title", "") for k in ("守谷", "つくば", "みらい平", "茨城", *KINKO_WORDS))
        pool[c["id"]] = c

    # --- RSSを巡回して新しい候補を追加 ---
    # (デフォルト都市, デフォルトカテゴリ, URL, 絞り込み語, 直接RSSか)
    feeds = [(city, cat, gnews_url(q), None, False) for city, cat, q in QUERIES]
    feeds += [(city, cat, url, words, True) for city, cat, url, words in EXTRA_FEEDS]

    for default_city, default_cat, url, filter_words, is_direct in feeds:
        entries = fetch_feed(url)
        for entry in entries[:MAX_PER_FEED]:
            title = strip_media_suffix(entry.get("title", "").strip())
            link = clean_url(entry.get("link", ""))
            if not title or not link:
                continue
            # 県全域のRSSは、対象エリアの地名が入っている記事だけ拾う
            if filter_words and not any(w in title for w in filter_words):
                continue

            published = parse_published(entry)
            if published < cutoff:            # 消印チェック
                continue

            # 配信元名。Googleニュース経由は entry.source に入っているが、
            # 配信元のRSSを直接読む場合は入っていないので、URLから引く。
            src = clean_source(entry) or source_from_url(link)

            cid = make_id(title)
            if default_city == "ibaraki":
                # サイトの流儀：県内全域はジャンル扱い（city は空）
                cat = "ibaraki"
                cities = []
            else:
                cat = detect_category(title, default_cat)
                cities = detect_cities(title, default_city)

            if cid in pool:
                # 既知の候補：カテゴリはそのまま、都市だけマージ
                for c in cities:
                    if c not in pool[cid]["city"]:
                        pool[cid]["city"].append(c)
                # 同じ記事がGoogleニュース経由でも入っていたら、元記事のURLで上書きする。
                # Googleの転送リンクはXでカードが出ず、読者も余計な1ページを踏むため。
                if is_direct and "news.google.com" in pool[cid].get("url", ""):
                    pool[cid]["url"] = link
                    if src:
                        pool[cid]["source"] = src
                    pool[cid]["sure"] = True
            else:
                # タイトルに地名が入っているか（入っていない=本文マッチの可能性）
                sure = (default_city == "ibaraki") or any(
                    k in title for k in ("守谷", "つくば", "みらい平", "茨城", *KINKO_WORDS))
                pool[cid] = {
                    "id": cid,
                    "title": title,
                    "source": src,
                    "date": published.strftime("%Y-%m-%dT%H:%M"),
                    "city": cities,
                    "category": cat,
                    "emoji": EMOJI.get(cat, "📰"),
                    "url": link,
                    "sure": sure,
                }

    # --- 古いもの・掲載済みのものを除外 ---
    result = []
    for c in pool.values():
        published = datetime.strptime(c["date"], "%Y-%m-%dT%H:%M").replace(tzinfo=JST)
        if published < cutoff:
            continue
        if c["url"] in posted_urls or normalize_title(c["title"]) in posted_titles:
            continue
        result.append(c)

    result.sort(key=lambda c: c["date"], reverse=True)

    # 3市と県内全域は別枠でそれぞれ最大件数まで保持（互いに枠を奪わない）
    local = [c for c in result if c["category"] != "ibaraki"][:MAX_CANDIDATES]
    pref = [c for c in result if c["category"] == "ibaraki"][:MAX_CANDIDATES]
    result = sorted(local + pref, key=lambda c: c["date"], reverse=True)

    payload = {
        "updated": now.strftime("%Y-%m-%dT%H:%M"),
        "count": len(result),
        "candidates": result,
    }
    CANDIDATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"候補 {len(result)} 件を保存しました（掲載済み除外: {len(posted_urls)}件参照）")


if __name__ == "__main__":
    collect()

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
    # 県内全域（直近2日だけ・件数も絞る）
    ("ibaraki",      "news",    "茨城県 when:7d"),
]

# ここに普通のRSS（市公式サイトなど）を足すと収集対象を増やせる
# (デフォルト都市, デフォルトカテゴリ, RSSのURL)
EXTRA_FEEDS = [
    # 例: ("tsukubamirai", "event", "https://www.city.tsukubamirai.lg.jp/????.xml"),
]

# ---- 仕分け用のキーワード ---------------------------------------------
GOURMET_WORDS = ["オープン", "開店", "閉店", "新店", "ランチ", "カフェ", "ラーメン",
                 "パン", "スイーツ", "グルメ", "新メニュー", "レストラン", "テイクアウト"]
EVENT_WORDS = ["イベント", "祭り", "まつり", "フェス", "開催", "マルシェ", "花火",
               "コンサート", "ワークショップ", "展示", "体験会"]
KIDS_WORDS = ["子育て", "児童館", "親子", "キッズ", "子ども", "こども", "保育", "幼稚園"]

EMOJI = {"news": "📰", "event": "🎪", "gourmet": "🍜", "kids": "🧒"}


def gnews_url(query: str) -> str:
    return ("https://news.google.com/rss/search?q="
            + urllib.parse.quote(query) + "&hl=ja&gl=JP&ceid=JP:ja")


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
    return hits or [default_city]


def detect_category(title: str, default_cat: str) -> str:
    if any(w in title for w in KIDS_WORDS):
        return "kids"
    if any(w in title for w in GOURMET_WORDS):
        return "gourmet"
    if any(w in title for w in EVENT_WORDS):
        return "event"
    return default_cat


def parse_published(entry):
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(JST)
    return datetime.now(JST)


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
        pool[c["id"]] = c

    # --- RSSを巡回して新しい候補を追加 ---
    feeds = [(city, cat, gnews_url(q)) for city, cat, q in QUERIES]
    feeds += EXTRA_FEEDS

    for default_city, default_cat, url in feeds:
        parsed = feedparser.parse(url)
        for entry in parsed.entries[:MAX_PER_FEED]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            if not title or not link:
                continue

            published = parse_published(entry)
            if published < cutoff:            # 消印チェック
                continue

            cid = make_id(title)
            cat = detect_category(title, default_cat)
            cities = (["ibaraki"] if default_city == "ibaraki"
                      else detect_cities(title, default_city))

            if cid in pool:
                # 既知の候補：カテゴリはそのまま、都市だけマージ
                for c in cities:
                    if c not in pool[cid]["city"]:
                        pool[cid]["city"].append(c)
            else:
                # タイトルに地名が入っているか（入っていない=本文マッチの可能性）
                sure = (default_city == "ibaraki") or any(
                    k in title for k in ("守谷", "つくば", "みらい平", "茨城"))
                pool[cid] = {
                    "id": cid,
                    "title": title,
                    "source": clean_source(entry),
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
    local = [c for c in result if "ibaraki" not in c["city"]][:MAX_CANDIDATES]
    pref = [c for c in result if "ibaraki" in c["city"]][:MAX_CANDIDATES]
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

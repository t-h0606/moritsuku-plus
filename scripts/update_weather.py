#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
もりつく気象台：気象庁の天気予報を data/weather.json に変換する

このファイルはGitHub Actionsが1時間ごとに実行します。手で動かす必要はありません。

【設計の考え方】
  ブラウザから気象庁を直接呼ばず、ここで取得して weather.json に書き出します。
  そうしておくと、将来ほかのサービスに乗り換えるときもサイト側（js/app.js）を
  触らずに済みます。気象庁が形式を変えた場合も、サイトが壊れるのではなく
  「更新が止まって直前の内容が出続ける」だけで済みます。

【気象庁のデータ構造】（2026-07 時点。公式仕様は非公開のため実データから確認）
  配列[0] = 3日予報   timeSeries[0] 天気（北部/南部）
                      timeSeries[1] 降水確率（北部/南部・6区分）
                      timeSeries[2] 気温（水戸/土浦）
  配列[1] = 週間予報   timeSeries[0] 天気と降水確率（茨城県）
                      timeSeries[1] 気温（水戸）
  ※守谷・つくばみらい・つくばは「南部」。気温は県南の「土浦」を採用
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

AREA_CODE   = "080000"   # 茨城県
SUBAREA     = "080020"   # 茨城県南部（守谷・つくばみらい・つくば）
TEMP_POINT  = "40341"    # 土浦（県南の気温観測点）
WEEK_TEMP   = "40201"    # 水戸（週間予報の気温はここしか無い）

URL = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{AREA_CODE}.json"

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "weather.json")

# 気象庁の天気コード → 絵文字と短い天気名。
# コード表はAPIから取得できないため、気象庁サイトの定義をもとに手で持つ。
# 3桁の先頭が 1=晴 2=くもり 3=雨 4=雪。細かい変化は下の辞書で個別に拾う。
CODE_TABLE = {
    "100": ("☀️", "晴れ"),      "101": ("🌤️", "晴れ時々くもり"), "102": ("🌦️", "晴れ一時雨"),
    "103": ("🌦️", "晴れ時々雨"), "104": ("🌨️", "晴れ一時雪"),    "105": ("🌨️", "晴れ時々雪"),
    "106": ("🌦️", "晴れ一時雨"), "107": ("🌦️", "晴れ時々雨"),    "108": ("🌦️", "晴れ一時雨"),
    "110": ("🌤️", "晴れのちくもり"), "111": ("🌤️", "晴れのちくもり"),
    "112": ("🌦️", "晴れのち雨"), "113": ("🌦️", "晴れのち雨"),    "114": ("🌦️", "晴れのち雨"),
    "115": ("🌨️", "晴れのち雪"), "116": ("🌨️", "晴れのち雪"),    "117": ("🌨️", "晴れのち雪"),
    "118": ("🌨️", "晴れのち雨か雪"), "119": ("⛈️", "晴れのち雨か雷雨"),
    "120": ("🌦️", "晴れ一時雨"), "121": ("🌦️", "晴れ一時雨"),    "122": ("🌦️", "晴れ時々雨"),
    "123": ("☀️", "晴れ"),      "124": ("☀️", "晴れ"),          "125": ("⛈️", "晴れのち雷雨"),
    "126": ("🌦️", "晴れ昼頃から雨"), "127": ("🌦️", "晴れ夕方から雨"),
    "128": ("🌦️", "晴れ夜は雨"), "130": ("☀️", "朝の内霧のち晴れ"), "131": ("☀️", "晴れ"),
    "132": ("🌤️", "晴れ時々くもり"), "140": ("⛈️", "晴れ時々雨で雷"),
    "160": ("🌨️", "晴れ一時雪"), "170": ("🌨️", "晴れ時々雪"),    "181": ("🌨️", "晴れのち雪"),

    "200": ("☁️", "くもり"),     "201": ("⛅", "くもり時々晴れ"), "202": ("🌧️", "くもり一時雨"),
    "203": ("🌧️", "くもり時々雨"), "204": ("🌨️", "くもり一時雪"), "205": ("🌨️", "くもり時々雪"),
    "206": ("🌧️", "くもり一時雨"), "207": ("🌧️", "くもり時々雨"), "208": ("🌧️", "くもり一時雨"),
    "209": ("🌫️", "霧"),         "210": ("⛅", "くもりのち晴れ"), "211": ("⛅", "くもりのち晴れ"),
    "212": ("🌧️", "くもりのち雨"), "213": ("🌧️", "くもりのち雨"), "214": ("🌧️", "くもりのち雨"),
    "215": ("🌨️", "くもりのち雪"), "216": ("🌨️", "くもりのち雪"), "217": ("🌨️", "くもりのち雪"),
    "218": ("🌨️", "くもりのち雨か雪"), "219": ("⛈️", "くもりのち雨か雷雨"),
    "220": ("🌧️", "くもり一時雨"), "221": ("🌧️", "くもり一時雨"), "222": ("🌧️", "くもり時々雨"),
    "223": ("⛅", "くもり時々晴れ"), "224": ("🌧️", "くもり昼頃から雨"),
    "225": ("🌧️", "くもり夕方から雨"), "226": ("🌧️", "くもり夜は雨"),
    "228": ("🌨️", "くもり昼頃から雪"), "229": ("🌨️", "くもり夕方から雪"),
    "230": ("🌨️", "くもり夜は雪"), "231": ("🌫️", "くもり海上は霧"),
    "240": ("⛈️", "くもり時々雨で雷"), "250": ("🌨️", "くもり時々雪で雷"),
    "260": ("🌨️", "くもり一時雪"), "270": ("🌨️", "くもり時々雪"), "281": ("🌨️", "くもりのち雪"),

    "300": ("🌧️", "雨"),        "301": ("🌦️", "雨時々晴れ"),    "302": ("🌧️", "雨時々止む"),
    "303": ("🌨️", "雨時々雪"),  "304": ("🌧️", "雨か雪"),        "306": ("🌧️", "大雨"),
    "308": ("🌧️", "雨で暴風雨"), "309": ("🌨️", "雨一時雪"),     "311": ("🌦️", "雨のち晴れ"),
    "313": ("🌧️", "雨のちくもり"), "314": ("🌨️", "雨のち雪"),   "315": ("🌨️", "雨のち雪"),
    "316": ("🌦️", "雨か雪のち晴れ"), "317": ("🌧️", "雨か雪のちくもり"),
    "320": ("🌦️", "朝の内雨のち晴れ"), "321": ("🌧️", "朝の内雨のちくもり"),
    "322": ("🌨️", "雨昼頃から雪"), "323": ("🌦️", "雨夕方から晴れ"),
    "324": ("🌦️", "雨夜は晴れ"), "325": ("🌦️", "雨夜は晴れ"),
    "326": ("🌨️", "雨夕方から雪"), "327": ("🌨️", "雨夜は雪"),
    "328": ("🌧️", "雨で激しく降る"), "329": ("🌨️", "雨一時雪"),
    "340": ("🌨️", "雪か雨"),    "350": ("⛈️", "雨で雷"),        "361": ("🌨️", "雪か雨のち晴れ"),
    "371": ("🌨️", "雪か雨のちくもり"),

    "400": ("❄️", "雪"),        "401": ("🌨️", "雪時々晴れ"),    "402": ("❄️", "雪時々止む"),
    "403": ("🌨️", "雪時々雨"),  "405": ("❄️", "大雪"),          "406": ("❄️", "風雪強い"),
    "407": ("❄️", "暴風雪"),    "409": ("🌨️", "雪一時雨"),      "411": ("🌨️", "雪のち晴れ"),
    "413": ("🌨️", "雪のちくもり"), "414": ("🌨️", "雪のち雨"),
    "420": ("🌨️", "朝の内雪のち晴れ"), "421": ("🌨️", "朝の内雪のちくもり"),
    "422": ("🌨️", "雪昼頃から雨"), "423": ("🌨️", "雪夕方から雨"),
    "425": ("❄️", "雪で大雪"),  "426": ("🌨️", "雪のちみぞれ"),  "427": ("🌨️", "雪一時みぞれ"),
    "450": ("⛈️", "雪で雷"),
}


def code_info(code):
    """天気コードから（絵文字, 天気名）を返す。未知のコードは先頭1桁で代用する。"""
    code = str(code or "").strip()
    if code in CODE_TABLE:
        return CODE_TABLE[code]
    head = code[:1]
    return {"1": ("☀️", "晴れ"), "2": ("☁️", "くもり"),
            "3": ("🌧️", "雨"),  "4": ("❄️", "雪")}.get(head, ("🌤️", "―"))


def pick_area(series, code):
    """timeSeries の areas から、指定コードのエリアを取り出す。"""
    for a in series.get("areas", []):
        if a.get("area", {}).get("code") == code:
            return a
    return series.get("areas", [{}])[0] if series.get("areas") else {}


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def hour_icon(base_emoji, pop, hour):
    """時間帯ごとの簡易アイコン。夜は月、降水確率が高ければ雨に寄せる。"""
    if pop is not None and pop >= 50:
        return "🌧️"
    if hour >= 21 or hour < 5:
        return "🌙"
    if pop is not None and pop >= 30:
        return "🌦️"
    return base_emoji


def build(raw, now=None):
    """気象庁のJSONを、サイトが読む形（weather.json）に組み替える。"""
    now = now or datetime.now(JST)
    today = now.date()

    daily, weekly = raw[0], raw[1]
    ds = daily["timeSeries"]

    # --- 天気（南部） ---
    wx = pick_area(ds[0], SUBAREA)
    wx_times = [datetime.fromisoformat(t) for t in ds[0]["timeDefines"]]
    codes = wx.get("weatherCodes", [])
    emoji, cond = code_info(codes[0] if codes else "")

    # --- 降水確率（南部・6区分） ---
    pop_area = pick_area(ds[1], SUBAREA)
    pop_times = [datetime.fromisoformat(t) for t in ds[1]["timeDefines"]]
    pops = [to_int(p) for p in pop_area.get("pops", [])]

    # --- 気温（土浦） ---
    tp = pick_area(ds[2], TEMP_POINT)
    tp_times = [datetime.fromisoformat(t) for t in ds[2]["timeDefines"]]
    temps = [to_int(v) for v in tp.get("temps", [])]

    # 指定した日の最高・最低を拾う。気象庁は
    # [今日09時(=最高), 今日00時(=最低), 明日00時(=最低), 明日09時(=最高)] の並びで返す。
    def temps_of(day):
        hi = lo = None
        for t, v in zip(tp_times, temps):
            if v is None or t.date() != day:
                continue
            if t.hour >= 6:
                hi = v if hi is None else max(hi, v)
            else:
                lo = v if lo is None else min(lo, v)
        # 時刻を過ぎた枠には、気象庁が最高と同じ値を入れて無効化してくることがある
        if lo is not None and hi is not None and lo >= hi:
            lo = None
        return hi, lo

    # 17時発表以降、今日の気温は予報の対象外になり気象庁は「-」を返す。
    # その場合は今日の枠に明日の数字を入れず、表示そのものを明日へ切り替える
    # （日付・天気・気温・週間予報の先頭をすべて明日に揃える）。
    tomorrow = today + timedelta(days=1)
    high, low = temps_of(today)
    target_day = today
    if high is None:
        t_hi, t_lo = temps_of(tomorrow)
        if t_hi is not None:
            target_day = tomorrow
            high, low = t_hi, t_lo
    elif low is None:
        # 昼の発表では今日の最低だけが過ぎている。
        # この「最低」は今晩から明朝にかけての冷え込みなので、明日00時の値が実質同じ意味になる
        for t, v in zip(tp_times, temps):
            if v is not None and t.date() == tomorrow and t.hour < 6:
                low = v
                break

    # 対象日が明日なら、天気も明日のものに差し替える
    if target_day != today:
        for t, c in zip(wx_times, codes):
            if t.date() == target_day:
                emoji, cond = code_info(c)
                break

    # --- 時間帯ごとの降水確率 ---
    # 気象庁が6時間単位で出している「実際の値」だけを並べる。
    # 時間ごとの気温は気象庁が公表していないため、推測値は載せない
    # （掲載情報はすべて実在、が本サイトの原則）。
    #
    # 気象庁の時刻は「その6時間の始まり」を指す：
    #   00:00→夜中〜朝  06:00→朝〜昼  12:00→昼〜夕  18:00→夕〜夜
    LABELS = {0: "00-06", 6: "06-12", 12: "12-18", 18: "18-24"}
    DAY_LABELS = {today: "今日", today + timedelta(days=1): "明日",
                  today + timedelta(days=2): "明後日"}
    hourly = []
    seen = set()
    for t_, p in zip(pop_times, pops):
        if t_ < now - timedelta(hours=6):
            continue                      # すでに終わった時間帯は出さない
        key = (t_.date(), t_.hour)
        if key in seen:
            continue
        seen.add(key)
        hourly.append({
            "t": LABELS.get(t_.hour, str(t_.hour)),
            "day": DAY_LABELS.get(t_.date(), f"{t_.month}/{t_.day}"),
            "icon": hour_icon(emoji, p, t_.hour),
            "pop": p,
        })
        if len(hourly) >= 4:
            break

    # --- 週間予報 ---
    ws = weekly["timeSeries"]
    wcodes = ws[0]["areas"][0].get("weatherCodes", [])
    wpops = ws[0]["areas"][0].get("pops", [])
    wtimes = [datetime.fromisoformat(t) for t in ws[0]["timeDefines"]]
    wt = pick_area(ws[1], WEEK_TEMP)
    tmax = [to_int(v) for v in wt.get("tempsMax", [])]
    tmin = [to_int(v) for v in wt.get("tempsMin", [])]

    # 気象庁は週間予報の「明日」の欄に降水確率を載せない（3日間予報の6時間ごとの値で
    # まかなえるため空文字が入る）。そこで、その日の6時間ごとの値の最大を代わりに使う。
    # 1日のどこかで降る確からしさなので、6時間ごとの最大が最も近い値になる。
    def pop_of_day(day):
        vals = [p for t_, p in zip(pop_times, pops) if p is not None and t_.date() == day]
        return max(vals) if vals else None

    # 先頭は表示対象の日（通常は今日、17時発表以降は明日）
    week = [{"d": DAY_LABELS.get(target_day, "今日"), "icon": emoji,
             "hi": high, "lo": low, "pop": pop_of_day(target_day)}]

    t_high, t_low = temps_of(tomorrow)

    for i, t in enumerate(wtimes):
        if t.date() <= target_day:
            continue                      # 先頭に出した日より前は重複するので飛ばす
        e, _ = code_info(wcodes[i] if i < len(wcodes) else "")
        hi = tmax[i] if i < len(tmax) else None
        lo = tmin[i] if i < len(tmin) else None
        if t.date() == tomorrow:
            hi = hi if hi is not None else t_high
            lo = lo if lo is not None else t_low
        pop = to_int(wpops[i]) if i < len(wpops) else None
        if pop is None:
            pop = pop_of_day(t.date())     # 明日ぶんは6時間予報から補う
        week.append({"d": DAY_LABELS.get(t.date(), f"{t.month}/{t.day}"),
                     "icon": e, "hi": hi, "lo": lo, "pop": pop})

    week = week[:8]

    WD = "月火水木金土日"
    return {
        "updated": now.isoformat(timespec="seconds"),
        "targetDate": target_day.isoformat(),
        "targetLabel": f"{target_day.month}月{target_day.day}日（{WD[target_day.weekday()]}）",
        "source": "気象庁（水戸地方気象台）",
        "reportDatetime": daily.get("reportDatetime"),
        "areaCode": AREA_CODE,
        "areaName": "茨城県南部",
        "forecast": {
            "city": "守谷市〜つくば市（茨城県南部）",
            "icon": emoji,
            "cond": cond,
            "high": high,
            "low": low,
            "hourly": hourly,
            "week": week,
        },
    }


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "moritsuku-plus/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = json.load(res)

    data = build(raw)

    # 最低限の妥当性チェック。おかしければ書き換えず、前回の内容を残す
    f = data["forecast"]
    if f["high"] is None or not f["hourly"] or len(f["week"]) < 2:
        print("取得できた内容が不十分です。weather.json は更新しません。", file=sys.stderr)
        return 1

    path = os.path.abspath(OUT)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")

    print(f"更新しました： {f['cond']} {f['high']}°/{f['low']}°  週間{len(f['week'])}日分")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# もりつく＋ v27

v24までは1枚10MBのHTMLでしたが、中身を種類ごとに分けました。**見た目と動作はv24と同一**です（PC・スマホとも全要素の位置が1pxも変わっていないことを確認済み）。

## フォルダの中身

```
index.html          サイトの骨組み（めったに触りません）
manifest.json       アプリとして名乗るための名札
sw.js               2回目以降を速くする係
css/style.css       見た目の指定
js/app.js           動きの指定
icons/              ホーム画面に置いたときのアイコン
images/             キャラクター画像（8体＋ミドリ反転版）
images/thumbs/      ★記事のサムネイル置き場
data/articles.json  ★記事
data/videos.json    ★動画
data/weather.json   天気（将来ロボットが自動更新）
data/staff.json     キャラ設定・気象台のセリフ
```

**★の3つだけが日常的に触るファイル**です。

## 記事を追加する

`data/articles.json` の `items` の **いちばん上** に1件足します。上にあるものほど新しい扱いで、**先頭の1件だけが大きなカード**になります。

```json
{
  "title": "記事の見出しをそのまま",
  "source": "配信元の名前",
  "ago": "2時間前",
  "city": ["moriya"],
  "category": "news",
  "emoji": "🏗️",
  "url": "https://配信元の記事URL",
  "thumb": ""
}
```

| 項目 | 入れるもの |
|---|---|
| city | `moriya` `tsukubamirai` `tsukuba` から選ぶ。複数可（3市共通の話題なら3つ並べる） |
| category | `news` `event` `gourmet` `kids` `ibaraki` のどれか。`ibaraki`（県内全域）は3市以外の県内ニュース用で、`city` は空 `[]` にします |
| emoji | サムネイルが無いときに出る絵文字 |
| url | 配信元の記事URL。空だとリンクしません |
| thumb | 先頭記事だけ使います。`images/thumbs/2026-07-19-cafe.webp` のように書く |

`,` の付け忘れに注意してください。項目と項目の間には必ずカンマが要ります。

## 動画を追加する

`data/videos.json` の `youtube` にURLを貼るだけです。IDだけでも、`https://youtu.be/xxxx` の形でも、`https://www.youtube.com/watch?v=xxxx` の形でも受け付けます。

```json
"lead": {
  "youtube": "https://youtu.be/xxxxxxxxxxx",
  "title": "TXさんぽ #04「守谷、ビール工場のまちの夕暮れ」",
  "meta": "散策バラエティ｜守谷",
  "duration": "12:34"
}
```

URLを入れると**YouTube側のサムネイルが自動で表示され**、クリックでYouTubeが開きます。空のままなら今の仮サムネイル（グラデーション）が出ます。

| 場所 | 何が出るか |
|---|---|
| `lead` | 今週のオンエアの大きい枠 |
| `subs` | その下の小さい2枠 |
| `next` | 次回予告（ポン田Pのコメント欄） |
| `library` | 放送ライブラリー（横スクロール） |

## キャスターのセリフを変える

`data/staff.json` の `wxComments` です。地域4種 × 天気4種（`sun` 晴／`hot` 猛暑／`cloud` くもり／`rain` 雨）の表になっています。

## サイトを更新したあとの注意

`sw.js` の1行目あたりにある `moritsuku-v1` の数字を1つ増やしてください。増やさないと、以前に見た人の端末に古い見た目が残り続けます。**中身（data/）の更新だけなら、この操作は不要**です。

## まだ入っていないもの

- 「あとで読む」機能
- プッシュ通知

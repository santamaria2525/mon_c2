# gazo フォルダ構造説明

## 概要
NOX Monster Strike自動化ツールで使用する画像テンプレートを機能別に整理したフォルダです。

## フォルダ構造

### 📁 ui/ (83ファイル)
**汎用UI要素**
- `ok.png`, `close.png`, `yes.png`, `no.png` - 基本ボタン
- `back.png`, `retry.png`, `modoru.png` - ナビゲーション
- `settei.png`, `option.png` - 設定関連
- `search.png`, `kensaku.png` - 検索機能
- `friends*.png` - フレンド関連UI
- `doors*.png` - ドア・入室関連UI

### 📁 login/ (36ファイル)
**ログイン・認証関連**
- `zz_home.png`, `zz_home2.png` - ホーム画面検出（重要）
- `room.png` - ルーム画面検出（重要）
- `ID.png`, `XFLAGID.png` - ID入力画面
- `doui.png`, `kyoka.png` - 同意・許可画面
- `title.png`, `login.png` - タイトル・ログイン画面

### 📁 gacha/ (16ファイル)
**ガチャ機能**
- `gacharu.png` - ガチャ実行ボタン（重要）
- `gacha.png`, `gacha_black.png` - ガチャ画面検出
- `10ren.png` - 10連ガチャ
- `01_hoshi_sentaku.png` - 星選択画面
- `hoshi_*.png` - 星・オーブ関連
- `shinshun_*.png` - キャラ獲得判定

### 📁 quest/ (53ファイル)
**クエスト機能**
- `quest.png`, `quest_c.png` - クエスト画面
- `start.png` - スタートボタン
- `battle.png` - バトル画面
- `event_*.png` - イベントクエスト
- `shugo_*.png` - 守護獣クエスト
- `counter.png` - カウンター系

### 📁 mission/ (30ファイル)
**ミッション機能**
- `m_mission.png`, `m_mission_b.png` - ミッション画面
- `m_uke0.png` ~ `m_uke5.png` - ミッション受取
- `m_kakunin.png` - 確認画面
- `m_tassei.png` - 達成画面
- `m_*.png` - 各種ミッション関連

### 📁 medal/ (8ファイル)
**メダル交換機能**
- `hikikae_p.png` - プレミアムメダル交換（重要）
- `hikikae_g.png` - ガチャメダル交換
- `medal1.png`, `medal2.png` - メダル画面
- `medal_fusoku.png` - メダル不足画面

### 📁 event/ (25ファイル)
**イベント機能**
- `sel1.png` ~ `sel22.png` - イベント選択画面
- `check.png` - イベント確認
- `el.png`, `geki.png` - イベント種類別
- `vani.png` - バニシングイベント

### 📁 macro/ (21ファイル)
**マクロ機能**
- `macro.png` - マクロ画面
- `macro_fin.png` - マクロ終了
- `hasya_fin.png` - 覇者終了
- `load*.png` - ロード画面
- `saikai*.png` - 再開画面
- `restart.png` - リスタート

### 📁 icons/ (24ファイル)
**アイコン類**
- `shugo1.png` ~ `shugo8.png` - 守護獣アイコン
- `m1.png` ~ `m16.png` - モンスターアイコン

### 📁 sell/ (21ファイル)
**売却機能**
- `sentaku.png` - 選択画面
- `ikkatsu.png` - 一括選択
- `kakunin.png` - 確認画面
- `l4check.png`, `l5check.png` - レベル確認
- `yes.png`, `yes2.png`, `yes3.png` - 確認ボタン
- `ok.png`, `ok2.png` - OKボタン

### 📁 deprecated/ (41ファイル)
**非推奨・未使用ファイル**
- `del/` - 旧売却機能画像
- `end/` - 旧終了画面画像
- `old/` - 過去イベント画像
- その他使用されていない画像

## 使用頻度ランキング

### 最重要（削除不可）
1. `ui/ok.png` - 確認ボタン（全機能で使用）
2. `login/zz_home.png` - ホーム画面検出
3. `login/room.png` - ルーム画面検出
4. `gacha/gacharu.png` - ガチャ実行
5. `medal/hikikae_p.png` - メダル交換

### 重要（機能別必須）
- `ui/close.png` - 画面クローズ
- `ui/yes.png` - 確認操作
- `quest/quest.png` - クエスト画面
- `mission/m_mission.png` - ミッション画面

## メンテナンス指針

### 追加時
- 新機能の画像は対応するフォルダに配置
- 汎用的なUI要素は `ui/` フォルダへ
- 機能特有の画像は専用フォルダへ

### 削除時
- 使用されていない画像は `deprecated/` へ移動
- 完全に不要と判断された場合のみ削除
- 削除前に必ずバックアップを作成

### 命名規則
- 機能名_操作名.png (例: quest_start.png)
- 連番がある場合は数字を使用 (例: sel1.png, sel2.png)
- 汎用UI要素は簡潔な名前 (例: ok.png, yes.png)

## 統計情報
- 総ファイル数: 337ファイル
- 使用中: 296ファイル (88%)
- 非推奨: 41ファイル (12%)
- 最終整理日: 2025-07-03
- 最終修正日: 2025-07-04 (売却機能完全修正)
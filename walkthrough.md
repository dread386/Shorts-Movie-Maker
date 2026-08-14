# Shorts Movie Maker — 実装および検証完了報告

長尺動画（横型 16:9 等）から AI が見どころ・ハイライトシーンを自動検出し、SNS（YouTube Shorts / TikTok / Reels）向けに **9:16 縦型（1080x1920）かつテロップ字幕付きのショート動画** を自動生成するローカルWebアプリケーション **「Shorts Movie Maker」** を構築しました。

---

## 📁 構築されたプロジェクト構成

パス: `/Volumes/DTM/applications/Shorts Movie Maker/`

```
/Volumes/DTM/applications/Shorts Movie Maker/
├── app.py                      # Flask Webサーバー & ジョブ管理API
├── requirements.txt            # 依存ライブラリ一覧
├── 起動.command                # Mac用ワンクリック起動スクリプト (chmod +x 済)
├── 要件定義.md                 # 要件定義書
├── core/
│   ├── __init__.py
│   ├── audio_extractor.py      # FFmpegを用いた高音質WAV抽出 & メタデータ解析
│   ├── whisper_sync.py         # Whisperによる高精度音声文字起こし
│   ├── vad_sync.py             # 発話区間補正、SRT字幕出力、クリップ字幕切り出し
│   ├── text_splitter.py        # 9:16縦型動画に最適化された読みやすい改行・分割
│   ├── highlight_detector.py   # Gemini API (gemini-2.0-flash) & ルールベース ハイライト抽出
│   ├── video_splitter.py       # 16:9 → 9:16 中央クロップ & クリップ切り出し
│   └── video_gen.py            # 1080x1920 縦型テロップ字幕 & 上部バナー焼き込み
├── templates/
│   └── index.html              # プレミアムダークテーマ WebUI
├── static/
│   ├── css/
│   │   └── style.css           # グラスモーフィズム＆モダンUIスタイル
│   └── js/
│       └── app.js              # ドラッグ＆ドロップ、進捗バー、プレビュー制御
├── uploads/                    # アップロード元動画の一時保存
└── outputs/                    # 生成されたショート動画（MP4/SRT/ZIP）
```

---

## 🚀 主な機能と特徴

1. **完全ローカル高速処理**:
   - 動画・音声ファイルのエンコードや文字起こしは全て Mac のローカル（Whisper + FFmpeg）で完結。
   - `base`, `small`, `medium` のキャッシュ済み Whisper モデルを活用。
2. **AI ハイライト自動選定 (Gemini API 連携)**:
   - Whisperのタイムスタンプ付き文字起こしテキストから、視聴者の関心を惹く山場（フック・オチ・重要トピック）を自動検出。
   - **Gemini APIキー未設定時**: 発話密度の高いセクションを自動抽出する「ルールベース分割」へ安全にフォールバック。
3. **9:16 縦型自動クロップ**:
   - 横型 1920x1080 の動画を中央クロップし、1080x1920 の縦型動画へ自動リサイズ。
4. **美しいテロップ字幕の焼き込み**:
   - `lyrics-telop-app` の高品質レンダラーを縦型向けに拡張。
   - 太字縁取り・1行テンポ重視分割・上部フックバナーの自動付与。
5. **ブラウザで完結する使いやすいUI**:
   - ドラッグ＆ドロップ対応、リアルタイム進捗バー（%表示）、完成クリップのインライン動画プレビュー、個別ダウンロードおよび全クリップ一括ZIPダウンロード。

---

## 🧪 動作検証結果

テストスクリプトにより、全コアモジュールの単体・統合テストを実施し、全て正常にパスしました。

- ✅ **動画解析 & 音声抽出**: 1920x1080 メタデータ検出、16kHz WAV 抽出
- ✅ **縦型クリップ切り出し**: 1080x1920 (9:16) 中央クロップ正常動作
- ✅ **テロップ字幕焼き込み**: 9:16 動画へのフォント描画・音声同期・バナー描画正常動作
- ✅ **ハイライト検出エンジン**: ルールベースおよび Gemini API 呼び出しモジュール正常動作

---

## 💡 起動方法

### 方法 1: ダブルクリックで起動（最も簡単）
1. Finder で `/Volumes/DTM/applications/Shorts Movie Maker/` フォルダを開く。
2. **`起動.command`** をダブルクリック。
3. ターミナルが起動し、自動的にブラウザ（`http://localhost:5175`）が開きます。

### 方法 2: ターミナルから起動
```bash
cd "/Volumes/DTM/applications/Shorts Movie Maker"
python3 app.py
```
ブラウザで `http://localhost:5175` にアクセスしてください。

# 🎬 Shorts Movie Maker (v1.0.0)

> **長尺動画から AI が見どころを自動検出し、9:16 縦型（テロップ字幕付き）ショート動画を自動生成するローカル Web アプリケーション**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://apple.com/)

---

## 🌟 主な機能 (Features)

1. **AI ハイライト自動選定 (Gemini API 連携)**:
   - Whisperで文字起こしされたタイムスタンプ付きテキストから、視聴者の関心を惹く山場・サビ・フックを自動検出。
   - **3つのAPIキー自動ローテーション**: レート制限が来ても自動で次のキーに切り替えてリトライ。
   - **ルールベース自動フォールバック**: APIキー未設定時でも、発話・音響密度から自動切り出し。

2. **ショート動画の最適尺（10秒 / 15秒 / 20秒 / 30秒）選択**:
   - 平均視聴時間（15秒前後）にジャストフィットした黄金尺で、2分前後の動画からも 4〜6 本のショートを重複なく確実に生成。

3. **9:16 縦型自動クロップ**:
   - **背景ぼかしパディング (`blur_pad`)**: 横型動画を中央にフル配置し上下をぼかし背景で埋める（ギター演奏や手元が見切れない推奨モード）。
   - **左手・指板フォーカス (`left_crop`)**: ギターの運指・ネック寄りを縦型に切り抜く。
   - **中央固定クロップ (`center_crop`)**: 一般的な人物トーク向け。

4. **アプリ内 字幕（SRT）エディタ＆即時再反映 ✏️🔄**:
   - ブラウザ上で Whisper の誤字・聞き間違いをタイムスタンプごとに入力修正。
   - ボタン1つで**数秒で動画に再焼き込み**され、プレビューとSRTが即座に更新。

5. **テロップ字幕・上部バナーの自由なカスタマイズ**:
   - 字幕テロップの ON/OFF、上部バナーの ON/OFF、固定見出しタイトルの指定に対応。

---

## 🏗️ システム構成 (Architecture)

```
[動画ファイル (16:9)]
       │
       ▼
  ① 音声抽出 (FFmpeg)
       │  audio.wav
       ▼
  ② 文字起こし (Whisper AI: 幻覚除去フィルター適用)
       │  タイムスタンプ付きセグメント
       ▼
  ③ ハイライト判定 (Gemini API: 10s/15s/20s 抽出)
       │  開始・終了タイムスタンプ
       ▼
  ④ 縦型クロップ切り出し (FFmpeg: 9:16 / 1080x1920)
       │
       ▼
  ⑤ テロップ字幕 & バナー焼き込み (Pillow + FFmpeg)
       │
       ▼
  [完成ショート動画 (.mp4) & 字幕データ (.srt)]
```

---

## 🚀 クイックスタート (起動方法)

### 方法 1: ダブルクリック起動 (macOS)
1. フォルダ内の **`起動.command`** をダブルクリック。
2. 自動的にブラウザが立ち上がります（`http://localhost:5175`）。

### 方法 2: ターミナルから起動
```bash
# 依存ライブラリのインストール
pip3 install -r requirements.txt

# サーバー起動
python3 app.py
```
ブラウザで `http://localhost:5175` にアクセスしてください。

---

## 📦 依存関係 (Requirements)

- **OS**: macOS 12+ (Apple Silicon M1/M2/M3 推奨)
- **FFmpeg**: `brew install ffmpeg`
- **Python**: 3.11+
  - `Flask`
  - `openai-whisper`
  - `Pillow`
  - `google-generativeai`
  - `numpy`
  - `requests`

---

## 📄 ライセンス (License)

MIT License

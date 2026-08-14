#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Shorts Movie Maker — 起動スクリプト
# このファイルをダブルクリックするとサーバーが起動してブラウザが開きます
# ─────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"
PORT=5175

echo "======================================"
echo " 🎬 Shorts Movie Maker"
echo "======================================"
echo ""

# ポートを使っている古いプロセスを確実にクリーンアップ
OLD_PIDS=$(lsof -ti tcp:$PORT 2>/dev/null)
if [ -n "$OLD_PIDS" ]; then
  echo "⚠️  ポート $PORT の旧プロセスをクリーンアップ中..."
  kill -9 $OLD_PIDS 2>/dev/null
  sleep 1
fi

echo "▶ サーバーを起動中… (http://localhost:$PORT)"
echo "   終了するにはこのターミナルで Ctrl+C を押してください。"
echo ""

# 1.2秒後にブラウザを自動オープン
(sleep 1.2 && open "http://localhost:$PORT") &

# サーバーを直接フォアグラウンド実行
python3 app.py

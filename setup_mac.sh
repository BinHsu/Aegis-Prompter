#!/bin/bash

# Staff Officer - Cross-Mac Deployment Script
# 讓專案不污染主機，跨機隨插即用

set -e

echo "🚀 [Staff Officer] 開始全自動跨機環境部署..."
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "檢查 Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "❌ 尚未安裝 Homebrew。請先安裝 Homebrew 後再試。"
    exit 1
fi

echo "檢查並安裝系統依賴 (portaudio)..."
brew list portaudio &> /dev/null || brew install portaudio

echo "檢查 BlackHole 系統音訊驅動..."
if ! ls -d /Library/Audio/Plug-Ins/HAL/BlackHole*.driver >/dev/null 2>&1; then
    echo "⚠️ 尚未偵測到 BlackHole 音效卡驅動檔案 (或安裝不完整)。準備修復..."
    echo "👉 [即將求密碼] 以下需要系統權限以寫入底層驅動，請輸入 Mac 登入密碼："
    brew reinstall --cask blackhole-2ch
    echo "🔄 重啟 Mac 音訊核心服務 (coreaudiod) 以即時載入新驅動..."
    sudo killall coreaudiod
else
    echo "✅ BlackHole 系統音效驅動已妥善安裝。"
fi

echo "檢查 Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 尚未安裝 Python 3。"
    exit 1
fi

echo "檢查虛擬環境 (.venv) 狀態..."
if [ -d ".venv" ]; then
    # 測試 .venv 內的 python 是否在當前 Mac 上可正常運作（跨機可能導致路徑無效）
    if .venv/bin/python -c "import sys" >/dev/null 2>&1; then
        echo "✅ 既有的 .venv 虛擬環境與當前 Mac 相容，保留使用。"
    else
        echo "⚠️ 既有 .venv 已失效 (可能因切換 Mac 導致 Python 絕對路徑變更)，正在重新建立..."
        rm -rf .venv
        python3 -m venv .venv
    fi
else
    echo "建立全新隔離虛擬環境 (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "確保快取目錄存在 (模型 & 套件)..."
mkdir -p .hf_cache
mkdir -p .pip_cache

echo "載入環境變數設定..."
export HF_HOME="$PROJECT_DIR/.hf_cache"
export PIP_CACHE_DIR="$PROJECT_DIR/.pip_cache"

echo "升級 pip 並安裝專案套件..."
python3 -m pip install --upgrade pip
pip install -r requirements.txt

echo "=========================================="
echo "✅ [Staff Officer] 部署完成！"
echo "👉 環境準備就緒。若要開發，請輸入 'source .venv/bin/activate' 啟動環境。"
echo "👉 主機不留痕跡，幾 GB 模型權重都會存放在 T7 硬碟的快取內！"
echo "=========================================="

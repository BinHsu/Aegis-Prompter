#!/bin/bash
# 🛡️ Staff Officer 自動化測試發動機 (Testing Engine)

# 1. 取得專案絕對路徑
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "🚀 [Staff Officer] 正在專案目錄啟動測試防線: $PROJECT_ROOT"

# 2. 定位 Python 引擎
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "⚠️ 錯誤：找不到 .venv 中的 Python。請確認您的外接硬碟已掛載且 .venv 完整。"
    exit 1
fi

# 3. 確保測試工具已就位 (pytest & pytest-mock)
echo "📦 [1/2] 正在檢查並安裝測試組件..."
"$PYTHON_BIN" -m pip install pytest pytest-mock -q

# 4. 啟動綠燈發動機 (過濾外部環境雜訊：EOL, SSL, Deprecation)
echo "🏗️ [2/2] 正在發動單元測試與 Mock 驗證..."
export PYTHONPATH="$PROJECT_ROOT"
"$PYTHON_BIN" -m pytest "$PROJECT_ROOT/tests/unit" -v \
    -W ignore::DeprecationWarning \
    -W ignore::FutureWarning \
    -W ignore:"urllib3 v2 only supports OpenSSL"

echo "✅ [完成] 測試發動完畢！目前環境警告已過濾，請專注於邏輯綠燈。"

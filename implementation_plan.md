# AI 參謀 (Staff Officer) 實作計畫

本計畫針對 A（中斷衝突）、B（專有名詞校正）、C（精簡輸出）優化，並新增了 **D（外接硬碟隔離）** 與 **E（跨 Mac 隨插即用）** 原則。

## 📍 Phase 1: 跨機部署腳本與基礎環境建設
**目標：** 建立不污染主機、模型快取完全留存在硬碟中的獨立生態，並寫出跨機能一鍵修復環境的腳本。
1. **開發 `setup_mac.sh`:** 
   - 檢測主機是否具備 Homebrew、PortAudio 與 BlackHole，並安裝缺失元件。
   - 重建符合當前 Mac 絕對路徑的 Python `.venv`。
2. **開發 `.env` 與 `requirements.txt`:**
   - 透過 `.env` 鎖定 `HF_HOME=.hf_cache` 與 `PIP_CACHE_DIR=.pip_cache`。
   - 定義必要套件：`numpy sounddevice mlx-whisper webrtcvad python-dotenv google-genai streamlit`.
3. **開發 `src/health_check.py`:**
   - 驗證雙音軌是否順利隔離 (BlackHole 2ch vs MacBook Microphone)。

## 📍 Phase 2: Whisper 轉譯與 Message Buffer 系統
**目標：** 解決打斷與 API 被塞爆的問題。
1. **開發 `src/transcriber.py`:** 準備使用 `large-v3-turbo` 的 mlx 版本，利用 M4 NPU 運算。
2. **實作 Sliding Window Buffer (`src/dialogue_buffer.py`):**
   - 建立共享 List 並使用 Thread Lock `threading.Lock()` 解決雙方同時講話觸發的 Race Condition。

## 📍 Phase 3: Gemini Prompt Engineering 與 API 呼叫
**目標：** 避開長篇大論與術語拼字錯誤。
1. **開發 `src/gemini_advisor.py`:**
   - System Prompt 強制帶入術語表：ASP ERP, ACC, TPC, Blue Card, DIN Standard。
   - 強制回覆格式：不可超過 3 點 Bullet points、包含一行 Red Flag 防禦口訣。
2. **定時打 API:**
   - 當從緩衝區取得完整段落後，才非同步呼叫 API 更新畫面。

## 📍 Phase 4: Streamlit 無干擾提詞介面
**目標：** 打造極簡 Dashboard。
1. **開發 `src/app.py`:** 
   - 啟動本地端 Dashboard，黑底白字自動顯示：面試官提問，以及三點 Bullet points。
   - 新增：將 Polling 冷卻時間下調至 `3 秒`。

## 📍 Phase 5: [新增] 實戰戰術防禦矩陣 (Tactical Defense Matrix)
**目標：** 在不重啟系統的前提下，讓使用者隨時能「熱更新」AI 的標準答案與個人戰績。
1. **建立 `context/profile.md`:** 完整注入使用者的 Edge-to-Cloud, IaC, ProxySQL 等真實戰績。
2. **建立 `context/qa.md`:** 部署 11 道「一招斃命」的面試陷阱題標準講稿，並透過 System Override 強制 AI 100% 照抄宣讀。
3. **建立 `context/fillers.md`:** 在 UI 右側提供靜態的破冰/爭取時間金句，填補大腦處理與 API 延遲的 3 秒鐘真空期。
4. **引擎升級:** 全面綁定 Pay-As-You-Go 信用卡，解除 `gemini-2.5-pro` 限制，全速改採 `gemini-2.5-flash` 保證最低延遲。

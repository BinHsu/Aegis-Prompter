# AI 會議參謀 (Staff Officer) - 專案導航與交接文件

> **🤖 [給未來 AI 的指引]**
> 您好！當您看到這份文件時，意味著新的開發 Session 已經啟動。這是專門部署在外部磁碟上的隔離專案。
> **您的首要任務是：詳細閱讀本 README 的「核心設計守則」，並依據 `implementation_plan.md` 的步驟著手進入開發環節（從建立 venv 與撰寫 health_check.py 開始）。**

---

## 🎯 專案緣起與目標 (Project Vision)
本專案為德國 TPC/IT 支援職位面試打造一個「本地端 AI 會議參謀」。利用 MacBook M4 算力與 BlackHole 虛擬音效卡，完全自動**分離面試官與面試者的語音軌道**。並即時傳送給 Gemini API，動態生成防禦重點與面試武器。

---

## ⚠️ 絕對守則 (Architecture Constraints)

### A. 語音重疊 (The Interruption Problem)
雙方講話經常重疊，一定會造成 API 被瘋狂頻繁呼叫。
👉 **實作規定：** 禁止「觸發 VAD 就打 API」。必須實作 **Message Buffer (滑動窗口)** 保留最近 10 句話。在 Thread 之間加鎖，集滿或判斷有完整概念後，再整包送給 Gemini。

### B. 德國工業術語 (Glossary Correction)
Whisper 遇到冷門工業單字會有幻覺問題。
👉 **實作規定：** 在 Gemini 的 System Prompt 中強制帶入「術語表校正 (Glossary)」。告訴 Gemini：「若 STT 出現音近字，請內部校正為：ASP ERP, ACC, TPC, Blue Card, DIN 標準 等。」

### C. 嚴格限制 LLM 廢話與即時熱更新防禦矩陣 (Tactical Defense Matrix)
面試時沒時間看長文，且必須確保 AI 提供的答案完全貼合您的履歷與歐洲 SRE 行情。
👉 **實作規定：**
1. 建立 `context/` 資料夾，動態載入 `profile.md` (履歷)、`qa.md` (面試魔王題防禦腳本)、`fillers.md` (買時間金句)。
2. 若命中 `qa.md` 的題目，Gemini 必須 **100% 照抄** 您預先寫好的最高級別 30 字英文講稿，完全禁止 AI 自己改寫發揮。
3. 為適應高強度實戰，API 打頻需縮短至 **3 秒**，並全面採用速度最快的 `gemini-2.5-flash` 模型。

### D. 環境與外部硬碟隔離 (Deployment Isolation)
👉 **實作規定：**
1. 將所有開發限制在此 `/Volumes/Samsung PSSD T7 Media/Staff Officer` 目錄下。
2. **必須建立 `.venv`**，且 pip cache 定向到外接碟內，不污染開發主機。
3. NPU 最佳化：務必安裝支援 Apple Silicon Metal 加速的 `mlx-whisper`。
4. 在任何實作前，先寫一隻測試腳本 `health_check.py` 確保 `BlackHole` 和 `Microphone` 的雙音軌完全隔離成功。

### E. 跨機隨插即用 (Cross-Mac Portability)
為了讓 T7 外接硬碟在不同的 Mac 之間無縫切換，不必重新下載數 GB 的模型與重新設定系統，必須：
1. **模型與套件快取留在硬碟內**：透過 `.env` 檔設定 `HF_HOME=.hf_cache` 與 `PIP_CACHE_DIR=.pip_cache`。
2. **系統相依性由腳本搞定**：建立 `setup_mac.sh` 腳本。它能一鍵自動檢測並透過 Homebrew 安裝新 Mac 缺乏的 `portaudio` 與 `blackhole-2ch`，並重新綁定失效的 `.venv` 的 Python 解譯器絕對路徑。

---

## 📁 資料夾與檔案架構設計
為了嚴格管理專案與便於跨機操作，本專案必須採用以下目錄結構：

```text
/Volumes/Samsung PSSD T7 Media/Staff Officer/
├── .venv/                   # Python 虛擬環境 (由 setup_mac.sh 自動產生/修復)
├── .pip_cache/              # pip 下載快取 (供所有主機共用)
├── .hf_cache/               # HuggingFace 模型快取 (儲存數 GB 的 Whisper 權重)
├── .env                     # 環境變數設定 (HF_HOME, PIP_CACHE_DIR, API_KEY 等)
├── README.md                # 專案導航與核心守則
├── implementation_plan.md   # 開發的逐步實踐指南
├── setup_mac.sh             # [重要] 跨 Mac 部署與環境重置腳本
├── requirements.txt         # 套件依賴清單
├── architecture_review.html # 雙聲道架構梳理報告
└── src/                     # 所有 Python 程式原始碼目錄
    ├── health_check.py      # 取代舊機測試：雙軌錄音環境與 BlackHole 健檢
    ├── transcriber.py       # mlx-whisper 語音轉文字與多執行緒邏輯
    ├── dialogue_buffer.py   # 滑動窗口緩衝區與 Thread Lock 鎖定機制
    ├── gemini_advisor.py    # 面試戰術 API 串接與術語校正
    └── app.py               # Streamlit 本地端極簡 UI 介面
├── context/                 # [面試防禦矩陣] 動態熱更新設定檔
    ├── profile.md           # 您的個人跨界 C++ / DevOps 履歷與戰績
    ├── qa.md                # 面試 11 大魔王題防禦題庫 (支援最高覆寫指令)
    └── fillers.md           # UI 右上角的「買時間英文金句」
```

---

## 💰 營運成本估算 (Cost Estimation - 2026 March)

本專案建議使用 Pay-as-you-go 模式以獲得最高限制額度。

| 模型 | Input (per 1M) | Output (per 1M) | 特性 |
|------|----------------|-----------------|------|
| **Gemini 2.5 Flash** | $0.30 | $2.50 | 穩定、高 CP 值 |
| **Gemini 3 Flash** | $0.50 | $3.00 | 最強邏輯、支援原生音訊 (未來擴展) |
| **Gemini 3.1 Flash-Lite** | $0.25 | $1.50 | 極致低廉 |

> **實戰試算：** 一場 60 分鐘的高強度面試（每 3 秒更新一次），Gemini 3 Flash 的成本約為 **$1.80 USD**。這是一筆極小且高效的投資。


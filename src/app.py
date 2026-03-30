import streamlit as st
import time
import os
import sys
import sounddevice as sd

# 確保能從 src 載入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dialogue_buffer import DialogueBuffer
from transcriber import Transcriber
from gemini_advisor import GeminiAdvisor

# ===== UI 樣式設定 (黑底白字純淨面具風) =====
st.set_page_config(page_title="Staff Officer", page_icon="🕵️‍♂️", layout="wide")

st.markdown("""
    <style>
    /* 強制整體背景極致黑，減少面試眼部疲勞 */
    .stApp { background-color: #0d1117; color: #FAFAFA; }
    h1, h2, h3 { color: #FFFFFF !important; font-family: 'Inter', sans-serif; }
    
    /* 戰術小抄的醒目大字體方塊 */
    .advisor-box {
        background-color: #161b22;
        padding: 30px;
        border-radius: 12px;
        border-left: 8px solid #238636;
        font-size: 24px !important;
        font-weight: 500;
        min-height: 500px;
        white-space: pre-wrap;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    }
    
    /* 歷史對話列表的暗沉小字體 */
    .transcript-box {
        background-color: #010409;
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #30363d;
        font-size: 15px;
        color: #8b949e;
        height: 500px;
        overflow-y: auto;
        white-space: pre-wrap;
    }
    </style>
""", unsafe_allow_html=True)

# ===== 系統狀態初始化 =====
if "buffer" not in st.session_state:
    st.session_state.buffer = DialogueBuffer(max_history=8)
    st.session_state.advisor = GeminiAdvisor()
    st.session_state.is_running = False
    st.session_state.transcriber_mic = None
    st.session_state.transcriber_bh = None
    st.session_state.advice = "等待對話..."
    st.session_state.last_dialogue = ""
    st.session_state.last_api_call = 0 # API 冷卻計時器

st.title("🕵️‍♂️ 本地端 AI 參謀 (Staff Officer)")

def toggle_recording():
    if not st.session_state.is_running:
        st.session_state.is_running = True
        st.session_state.buffer.clear()
        st.session_state.advice = "監聽中...等待對方發言。"
        
        def find_device(keyword):
            for i, dev in enumerate(sd.query_devices()):
                if keyword.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
                    return i
            return sd.default.device[0]
            
        # 啟動 M4 雙軌並發轉錄大腦
        t_mic = Transcriber(device_idx=find_device("MacBook"), role="您 (Bin)", buffer_instance=st.session_state.buffer)
        t_bh = Transcriber(device_idx=find_device("BlackHole"), role="與會者 (對方)", buffer_instance=st.session_state.buffer)
        
        t_mic.start()
        t_bh.start()
        
        st.session_state.transcriber_mic = t_mic
        st.session_state.transcriber_bh = t_bh
    else:
        st.session_state.is_running = False
        if st.session_state.transcriber_mic: st.session_state.transcriber_mic.stop()
        if st.session_state.transcriber_bh: st.session_state.transcriber_bh.stop()

# ===== 雙欄位排版 =====
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("🎤 即時聽譯 (Transcript)")
    btn_text = "⏹️ 結束會議 (停止背景資源)" if st.session_state.is_running else "🚀 啟動會議參謀模式"
    
    # 決定按鈕顏色樣式
    btn_type = "secondary" if st.session_state.is_running else "primary"
    
    if st.button(btn_text, type=btn_type, use_container_width=True):
        toggle_recording()
        st.rerun()
        
    dialogue_text = st.session_state.buffer.get_formatted_dialogue()
    st.markdown(f'<div class="transcript-box">{dialogue_text if dialogue_text else "對話記錄將會出現在這裡..."}</div>', unsafe_allow_html=True)
    
with col_right:
    st.subheader("💡 戰術情報 (Staff Officer)")
    
    # 從 context 資料夾動態讀取「買時間專用垃圾話 (Filler words)」
    fillers_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "fillers.md")
    if os.path.exists(fillers_path):
        with open(fillers_path, "r", encoding="utf-8") as f:
            fillers_content = f.read().strip()
    else:
        fillers_content = (
            "⏱️ **[買時間專用金句 (直接照唸)]**\n\n"
            "1️⃣ *\"That's a really great question, let me structure my thoughts for a second.\"*\n"
            "2️⃣ *\"To be perfectly honest, there are a few different ways to approach this.\"*\n"
            "3️⃣ *\"Just to make sure we're on the same page, you are basically asking about...\"*"
        )
    st.info(fillers_content)
    
    st.markdown(f'<div class="advisor-box">{st.session_state.advice}</div>', unsafe_allow_html=True)

# ===== 背景自動更新與 API 輪詢 =====
if st.session_state.is_running:
    current_dialogue = st.session_state.buffer.get_formatted_dialogue()
    
    # 只要有任何來自 Whisper 的雙軌新轉錄字句
    if current_dialogue != st.session_state.last_dialogue and len(current_dialogue.strip()) > 0:
        # 既然已經綁定了付費帳號解除了所有的請求上限封印！
        # 我們把戰術冷卻時間大幅從 15 秒縮短到只剩 3 秒，獲得最極致的即時戰鬥體驗！
        now = time.time()
        if now - st.session_state.last_api_call >= 3:
            st.session_state.last_api_call = now
            st.session_state.last_dialogue = current_dialogue
            
            # 同步向 Gemini API 索取最新的戰術小抄與講稿 (大約花費 1~1.5 秒)
            new_advice = st.session_state.advisor.analyze_dialogue_sync(current_dialogue)
            if new_advice:
                st.session_state.advice = new_advice
                st.rerun() # 立刻彈出最新情報給與會者
    
    # 為了讓前端 UI 持續接收最新的變數，以 2 秒幀率重跑畫面
    time.sleep(2)
    st.rerun()

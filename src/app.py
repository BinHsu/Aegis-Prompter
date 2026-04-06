import streamlit as st
import time
import os
import sys
import atexit
import threading

# 🤫 隱藏 Streamlit 關閉時不可避免的 "Event loop is closed" 噪音
orig_excepthook = threading.excepthook
def mute_event_loop_closed(args):
    if args.exc_type == RuntimeError and "Event loop is closed" in str(args.exc_value):
        return
    orig_excepthook(args)
threading.excepthook = mute_event_loop_closed

# 確保能從 src 載入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from global_state import get_global_state

# ===== 核心狀態初始化 (取得全域資源) =====
g_state = get_global_state()

# 💡 自動啟動：當有人連入 (或開發者重載) 時，直接幫忙按下開始錄音
if not g_state.is_running:
    g_state.start_recording()

def cleanup_resources():
    """程式結束時的清道夫：強制釋放音訊硬體與雲端資源"""
    g_state.stop_recording()
    if hasattr(g_state, 'advisor') and hasattr(g_state.advisor, 'cached_content_name') and g_state.advisor.cached_content_name:
        try:
            g_state.advisor.client.caches.delete(name=g_state.advisor.cached_content_name)
            print("🧹 已清除雲端快取空間。")
        except:
            pass

# 註冊退出掛鉤
atexit.register(cleanup_resources)

# ===== 全域安全驗證碼 (防止每連線重複產生) =====
import random
import string

@st.cache_resource
def get_global_access_code():
    code = ''.join(random.choices(string.digits, k=4))
    # 視覺強化：先推開舊資料，再用大框框包裹
    print("\n" * 20)
    print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("┃                                                    ┃")
    print(f"┃   🛡️  STAFF OFFICER ACCESS CODE:  [ {code} ]      ┃")
    print("┃                                                    ┃")
    print("┃   請在手機端輸入上方 4 位數代碼解鎖介面              ┃")
    print("┃                                                    ┃")
    print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print("\n")
    return code

# 取得 (或從快取抓取) 唯一的 Access Code
global_access_code = get_global_access_code()
if "access_code" not in st.session_state:
    st.session_state.access_code = global_access_code
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0

# 檢測是否為本地連線 (127.0.0.1 / localhost)
is_local = False
try:
    if hasattr(st, "context"):
        host = st.context.headers.get("host", "")
    else:
        from streamlit.web.server.websocket_headers import _get_websocket_headers
        headers = _get_websocket_headers()
        host = headers.get("Host", "")
    
    if "localhost" in host or "127.0.0.1" in host or not host:
        is_local = True
except:
    is_local = True # 保守估計，報錯就當成是 local

# [視覺強化]: 只要是本地端存取，就確保驗證碼刷新在終端機最後一行
if is_local:
    print(f"\r🛡️  STAFF OFFICER ACCESS CODE: [ {global_access_code} ]", end="", flush=True)

# 安全門禁
if not is_local and not st.session_state.authenticated:
    if st.session_state.login_attempts >= 3:
        st.error("❌ Access Revoked: Too many failed attempts.")
        st.stop()
    st.title("🔒 Staff Officer Security")
    st.write(f"偵測到遠端連線，請輸入認證碼 (剩餘次數: {3 - st.session_state.login_attempts})")
    user_input = st.text_input("Access Code", type="password", key="sec_login")
    if user_input:
        if user_input == st.session_state.access_code:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.session_state.login_attempts += 1
            st.error(f"驗證失敗 ({st.session_state.login_attempts}/3)")
            st.stop()
    else:
        st.stop()



# ===== 專業深色架構師 UI 樣式 =====
st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .transcript-box {
        background-color: #1e2130; border-radius: 10px; padding: 20px;
        height: 550px; overflow-y: auto; color: #e0e0e0; font-family: 'Inter', sans-serif;
        border: 1px solid #30363d; line-height: 1.6;
    }
    .advisor-box {
        background-color: #0d1117; border-radius: 10px; padding: 25px;
        height: 550px; border: 2px solid #238636; position: relative;
    }
    .cheatsheet-section { color: #58a6ff; font-size: 1.1rem; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    .script-section { color: #f0f6fc; font-size: 1.25rem; font-weight: 500; }
    .filler-text { color: #8b949e; font-style: italic; font-size: 0.9rem; margin-top: 20px; }
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #238636, #2ea043); }
</style>
""", unsafe_allow_html=True)

# ===== 極簡頂部列 =====
st.title("🕵️‍♂️ Staff Officer")

# ===== 音訊雷達 (Audio Heartbeat) =====
if g_state.is_running:
    st.markdown("---")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        rms_me = g_state.transcriber_me.get_rms() if g_state.transcriber_me else 0
        st.caption(f"🎤 您的聲音: {g_state.me_name}")
        st.progress(min(rms_me * 15, 1.0)) # 放大 15 倍感應
    with col_v2:
        rms_other = g_state.transcriber_other.get_rms() if g_state.transcriber_other else 0
        st.caption(f"🎧 對方聲音: {g_state.other_name}")
        st.progress(min(rms_other * 15, 1.0))
else:
    # ===== 狀態列 (偵測到的設備回饋) =====
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🎤 預定麥克風: {g_state.me_name}")
    with col_b:
        st.caption(f"🎧 預定對方設備: {g_state.other_name}")

# ===== 雙欄位排版 =====
col_left, col_right = st.columns([1, 2])

with col_left:
    dialogue_text = g_state.buffer.get_formatted_dialogue()
    st.markdown(f'<div class="transcript-box">{dialogue_text if dialogue_text else "對話紀錄..."}</div>', unsafe_allow_html=True)
    
with col_right:
    # 取得目前背景計算出的戰術情報與狀態
    advice, is_thinking = g_state.buffer.get_advice()
    
    # 邏輯優化：為避免「洗掉」正在唸的講稿，我們只在分析完成後才更新 UI
    if is_thinking and "last_stable_advice" in st.session_state:
        current_display_advice = st.session_state.last_stable_advice
    else:
        current_display_advice = advice
        st.session_state.last_stable_advice = advice

    cheatsheet = ""
    script = ""
    
    if "[動態會議小抄]" in current_display_advice and "[Suggested Script]" in current_display_advice:
        parts = current_display_advice.split("[Suggested Script]")
        cheatsheet = parts[0].replace("[動態會議小抄]", "").strip().replace("\n", "<br>")
        script = parts[1].strip().replace("\n", "<br>")
    else:
        script = current_display_advice.replace("\n", "<br>")
    
    # 穩定金句顯示邏輯
    filler_html = ""
    if is_thinking:
        if "stable_filler" not in st.session_state:
            # 從 context/fillers.md 動態讀取最新的金句
            try:
                f_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "fillers.md")
                with open(f_path, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f if '"' in ln]
                import random
                st.session_state.stable_filler = random.choice(lines) if lines else "Thinking..."
            except Exception:
                st.session_state.stable_filler = "That's a really great question..."
        
        filler_html = f'<div class="filler-text">🌀 AI 正在計算新戰術... <br> (若需買時間可說：<b>{st.session_state.stable_filler}</b>)</div>'
    else:
        if "stable_filler" in st.session_state:
            del st.session_state.stable_filler

    cheatsheet_html = f'<div class="cheatsheet-section">🎯 {cheatsheet}</div>' if cheatsheet else ""
    script_html = f'<div class="script-section"><b>💬 Suggested Script:</b><br>{script}</div>'
    advisor_html = f'<div class="advisor-box">{cheatsheet_html}{script_html}{filler_html}</div>'
    
    st.markdown(advisor_html, unsafe_allow_html=True)

# ===== 用戶端畫面重刷輪詢 (Polling) =====
try:
    if g_state.is_running:
        time.sleep(0.5) # 錄音中：每半秒高頻更新
    else:
        time.sleep(1.5) # 待機中：每 1.5 秒低頻巡邏，等待其他裝置按下開始
        
    # 只有在 ScriptRunner 依然活躍時才重刷
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx() is not None:
        st.rerun()
except (RuntimeError, Exception):
    pass

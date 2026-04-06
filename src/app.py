import streamlit as st
import time
import os
import sys
import sounddevice as sd
import atexit
import signal

# 確保能從 src 載入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dialogue_buffer import DialogueBuffer
from transcriber import Transcriber
from gemini_advisor import GeminiAdvisor

# 全域列表用於追蹤活動中的錄音器，實作「優雅停機」
ACTIVE_TRANSCRIBERS = []

def cleanup_resources():
    """程式結束時的清道夫：強制釋放音訊硬體"""
    for t in ACTIVE_TRANSCRIBERS:
        try:
            if hasattr(t, 'stop'):
                t.stop()
        except:
            pass
    # 針對一些頑固的 PortAudio 殘留進行強行釋放
    try:
        sd.stop()
    except:
        pass

# 註冊退出掛鉤
atexit.register(cleanup_resources)

# ===== 核心狀態初始化 (最高優先權) =====
if "init_v2" not in st.session_state:
    st.session_state.buffer = DialogueBuffer(max_history=8)
    st.session_state.advisor = GeminiAdvisor()
    st.session_state.is_running = False
    st.session_state.authenticated = False
    st.session_state.login_attempts = 0
    st.session_state.advice = "等待對話..."
    st.session_state.last_dialogue = ""
    st.session_state.last_api_call = 0
    st.session_state.last_stable_advice = ""
    
    # 動態音訊偵測
    me_idx, me_name = Transcriber.find_device_index(["MacBook Air Microphone", "Built-in Microphone"], fallback_to_default=True)
    other_idx, other_name = Transcriber.find_device_index(["BlackHole 2ch", "BlackHole"], fallback_to_default=False)
    
    st.session_state.me_name = me_name
    st.session_state.other_name = other_name
    
    # 初始化底層實體
    t_me = Transcriber(role="您 (Bin)", device_idx=me_idx, buffer_instance=st.session_state.buffer)
    st.session_state.transcriber_me = t_me
    ACTIVE_TRANSCRIBERS.append(t_me)
    
    if other_idx is not None:
        t_other = Transcriber(role="與會者 (對方)", device_idx=other_idx, buffer_instance=st.session_state.buffer)
        st.session_state.transcriber_other = t_other
        ACTIVE_TRANSCRIBERS.append(t_other)
    else:
        st.session_state.transcriber_other = None
        
    st.session_state.init_v2 = True

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
st.session_state.access_code = global_access_code

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

def toggle_recording():
    """切換錄製狀態與初始化存檔 Session"""
    if st.session_state.is_running:
        # 停止運行
        st.session_state.is_running = False
        if st.session_state.transcriber_me:
            st.session_state.transcriber_me.stop()
        if st.session_state.transcriber_other:
            st.session_state.transcriber_other.stop()
    else:
        # 開始對話：掃描設備
        me_idx, me_name = Transcriber.find_device_index(["MacBook Air Microphone", "Built-in Microphone"], fallback_to_default=True)
        other_idx, other_name = Transcriber.find_device_index(["BlackHole 2ch", "BlackHole"], fallback_to_default=False)
        
        st.session_state.me_name = me_name
        st.session_state.other_name = other_name
        
        # 💡 生成存檔 Session ID
        session_id = time.strftime("%Y-%m-%d_%H%M%S")
        st.session_state.buffer.start_session(session_id)
        
        # 初始化實體
        st.session_state.transcriber_me = Transcriber(role="您 (Bin)", device_idx=me_idx, buffer_instance=st.session_state.buffer)
        if other_idx is not None:
            st.session_state.transcriber_other = Transcriber(role="與會者 (對方)", device_idx=other_idx, buffer_instance=st.session_state.buffer)
        
        # 啟動錄製
        if st.session_state.transcriber_me:
            st.session_state.transcriber_me.start()
        if st.session_state.transcriber_other:
            st.session_state.transcriber_other.start()
            
        st.session_state.is_running = True

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

# ===== 極簡頂部列 (標題 + 按鈕) =====
col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title("🕵️‍♂️ Staff Officer")
with col_btn:
    btn_label = "⏹️ 結束對話" if st.session_state.is_running else "🚀 開始對話"
    st.button(btn_label, on_click=toggle_recording, use_container_width=True)

# ===== 音訊雷達 (Audio Heartbeat) =====
if st.session_state.is_running:
    st.markdown("---")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        rms_me = st.session_state.transcriber_me.get_rms() if st.session_state.transcriber_me else 0
        st.caption(f"🎤 您的聲音: {st.session_state.me_name}")
        st.progress(min(rms_me * 15, 1.0)) # 放大 15 倍感應
    with col_v2:
        rms_other = st.session_state.transcriber_other.get_rms() if st.session_state.transcriber_other else 0
        st.caption(f"🎧 對方聲音: {st.session_state.other_name}")
        st.progress(min(rms_other * 15, 1.0))
else:
    # ===== 狀態列 (偵測到的設備回饋) =====
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🎤 預定麥克風: {st.session_state.get('me_name', '未偵測')}")
    with col_b:
        st.caption(f"🎧 預定對方設備: {st.session_state.get('other_name', '未偵測')}")

# ===== 雙欄位排版 =====
col_left, col_right = st.columns([1, 2])

with col_left:
    dialogue_text = st.session_state.buffer.get_formatted_dialogue()
    st.markdown(f'<div class="transcript-box">{dialogue_text if dialogue_text else "對話紀錄..."}</div>', unsafe_allow_html=True)
    
with col_right:
    # 取得目前背景計算出的戰術情報與狀態
    advice, is_thinking = st.session_state.buffer.get_advice()
    
    # 邏輯優化：為避免「洗掉」正在唸的講稿，我們只在分析完成後才更新 UI
    # 如果正在分析中，我們依然顯示上一輪的 advice
    if is_thinking and "last_stable_advice" in st.session_state:
        current_display_advice = st.session_state.last_stable_advice
    else:
        current_display_advice = advice
        st.session_state.last_stable_advice = advice

    # 解析目前要顯示的內容 (可能是上一輪的，也可能是剛跑完的)
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
                    # 篩選出含有引號的英文對話句子
                    lines = [ln.strip() for ln in f if '"' in ln]
                import random
                st.session_state.stable_filler = random.choice(lines) if lines else "Thinking..."
            except Exception:
                st.session_state.stable_filler = "That's a really great question..."
        
        filler_html = f'<div class="filler-text">🌀 AI 正在計算新戰術... <br> (若需買時間可說：<b>{st.session_state.stable_filler}</b>)</div>'
    else:
        if "stable_filler" in st.session_state:
            del st.session_state.stable_filler

    # 分段構建 HTML 避免 Python 3.9 f-string 語法錯誤
    cheatsheet_html = f'<div class="cheatsheet-section">🎯 {cheatsheet}</div>' if cheatsheet else ""
    script_html = f'<div class="script-section"><b>💬 Suggested Script:</b><br>{script}</div>'
    advisor_html = f'<div class="advisor-box">{cheatsheet_html}{script_html}{filler_html}</div>'
    
    st.markdown(advisor_html, unsafe_allow_html=True)

# ===== 背景效能優化：非同步 API 處理與高頻 UI 更新 =====
if st.session_state.is_running:
    current_dialogue = st.session_state.buffer.get_formatted_dialogue()
    advice, is_thinking = st.session_state.buffer.get_advice()
    
    # 判斷是否需要呼叫 Gemini (針對付費版優化：冷卻縮短至 1s，且「與會者」提問時優先觸發)
    now = time.time()
    last_role = st.session_state.buffer.get_last_role()
    
    # ⚡️ [產品級優化]：實時偵測「救命小抄」 (零延遲本地匹配)
    full_dialogue = st.session_state.buffer.get_full_dialogue()
    if full_dialogue:
        last_entry = full_dialogue[-1]
        # 如果是對方剛說完話，立即嘗試本地匹配
        if last_entry['role'] == "與會者 (對方)":
            hint = st.session_state.advisor.get_local_hint(last_entry['text'])
            if hint:
                header, answer = hint
                st.session_state.buffer.set_advice(f"⚡️ [救命小抄命中：{header}]\n\n{answer}", is_thinking=False)

    # 邏輯：
    # 1. 目前沒在思考
    # 2. 對話內容有更新
    # 3. 滿足冷卻門檻：如果是對方剛講完話，門檻降至 0.8s；否則為建議的 1.0s
    threshold = 0.8 if last_role == "與會者 (對方)" else 1.0
    
    if not is_thinking and current_dialogue != st.session_state.last_dialogue and len(current_dialogue.strip()) > 0:
        if now - st.session_state.last_api_call >= threshold:
            st.session_state.last_api_call = now
            st.session_state.last_dialogue = current_dialogue
            
            # 設定思考狀態為 True，並啟動背景 Thread 呼叫 API
            st.session_state.buffer.set_advice(advice, is_thinking=True)
            
            def background_advice_task(diag_text, buffer_ref, advisor_ref):
                try:
                    new_advice = advisor_ref.analyze_dialogue_sync(diag_text)
                    buffer_ref.set_advice(new_advice, is_thinking=False)
                except Exception as e:
                    buffer_ref.set_advice(f"⚠️ API 錯誤: {e}", is_thinking=False)
            
            import threading
            threading.Thread(
                target=background_advice_task,
                args=(current_dialogue, st.session_state.buffer, st.session_state.advisor),
                daemon=True
            ).start()

    # 為了讓前端 UI 極速反應（特別是手機網頁），將重刷頻率提升到 0.5 秒
    # 改進：增加更嚴格的環境感應與異常捕獲，確保關機時不會亂噴 RuntimeError
    try:
        if st.session_state.is_running:
            time.sleep(0.5)
            # 只有在 ScriptRunner 依然活躍時才重刷，避免在關機瞬間噴出 Event loop is closed
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            if get_script_run_ctx() is not None:
                st.rerun()
    except (RuntimeError, Exception):
        # 捕捉一切關機時的殘留報錯，直接靜默退出
        pass
    finally:
        # 強制清理殘留資源的最後防線
        pass

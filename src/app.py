import streamlit as st
import time
import os
import sys
import atexit
import threading
import random
import string

# Mute the noisy "Event loop is closed" exception caused by Streamlit thread death
orig_excepthook = threading.excepthook
def mute_event_loop_closed(args):
    if args.exc_type == RuntimeError and "Event loop is closed" in str(args.exc_value):
        return
    orig_excepthook(args)
threading.excepthook = mute_event_loop_closed

# Ensure module pathing
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from global_state import get_global_state

# ===== Initialize Global State =====
g_state = get_global_state()

# Auto-start hardware recording when the first user connects
if not g_state.is_running:
    g_state.start_recording()

def cleanup_resources():
    """Teardown audio pipeline on exit."""
    g_state.stop_recording()

atexit.register(cleanup_resources)

# ===== Global Access Code & Auth (Basic Zero-Trust) =====
@st.cache_resource
def get_global_access_code():
    code = ''.join(random.choices(string.digits, k=4))
    print("\n" * 20)
    print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("┃                                                    ┃")
    print(f"┃   🛡️  STAFF OFFICER ACCESS CODE:  [ {code} ]      ┃")
    print("┃                                                    ┃")
    print("┃   Input this code on remote browsers to unlock.    ┃")
    print("┃                                                    ┃")
    print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print("\n")
    return code

global_access_code = get_global_access_code()

if "access_code" not in st.session_state:
    st.session_state.access_code = global_access_code
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0

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
    is_local = True

if is_local:
    print(f"\r🛡️  STAFF OFFICER ACCESS CODE: [ {global_access_code} ]", end="", flush=True)

if not is_local and not st.session_state.authenticated:
    if st.session_state.login_attempts >= 3:
        st.error("❌ Access Revoked: Too many failed attempts.")
        st.stop()
    st.title("🔒 Staff Officer Security")
    st.write(f"Remote connection detected. Enter PIN (Attempts left: {3 - st.session_state.login_attempts})")
    user_input = st.text_input("Access Code", type="password", key="sec_login")
    if user_input:
        if user_input == st.session_state.access_code:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.session_state.login_attempts += 1
            st.error(f"Authentication Failed ({st.session_state.login_attempts}/3)")
            st.stop()
    else:
        st.stop()

# ===== Role Selection UI =====
if "selected_role" not in st.session_state:
    query_role = st.query_params.get("role", "").lower()
    if query_role in ["speaker", "staff"]:
        st.session_state.selected_role = query_role
    else:
        st.title("🛡️ Aegis Prompter Initialization")
        st.write("Please select your operational role for this session:")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🎤 Speaker Mode (Teleprompter)", use_container_width=True):
                st.session_state.selected_role = "speaker"
                st.rerun()
        with col2:
            if st.button("💻 Staff Mode (Tactical Override)", use_container_width=True):
                st.session_state.selected_role = "staff"
                st.rerun()
        st.stop()

current_role = st.session_state.selected_role

# ===== UI Theme & Styling =====
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
    .staff-box {
        background-color: #1f2937; border-radius: 10px; padding: 15px; margin-top: 15px;
        border: 2px dashed #f59e0b;
    }
    .cheatsheet-section { color: #58a6ff; font-size: 1.1rem; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    .script-section { color: #f0f6fc; font-size: 1.25rem; font-weight: 500; }
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #238636, #2ea043); }
</style>
""", unsafe_allow_html=True)

st.title(f"🕵️‍♂️ Staff Officer ({'Staff Mode' if current_role == 'staff' else 'Speaker Mode'})")

# ===== Dashboard Top Indicators =====
if g_state.is_running:
    st.markdown("---")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        rms_me = g_state.transcriber_me.get_rms() if g_state.transcriber_me else 0
        st.caption(f"🎤 {g_state.me_name}")
        st.progress(min(rms_me * 15, 1.0))
    with col_v2:
        rms_other = g_state.transcriber_other.get_rms() if g_state.transcriber_other else 0
        st.caption(f"🎧 {g_state.other_name}")
        st.progress(min(rms_other * 15, 1.0))
else:
    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🎤 Target Mic: {g_state.me_name}")
    with col_b:
        st.caption(f"🎧 Target Speaker: {g_state.other_name}")

# ===== Main Container Layout =====
col_left, col_right = st.columns([1, 2])

with col_left:
    # Get last 5 lines for Auto-Scroll UX
    dialogue_text = g_state.buffer.get_formatted_dialogue(max_lines=5)
    st.markdown(f'<div class="transcript-box">{dialogue_text if dialogue_text else "Awaiting stream..."}</div>', unsafe_allow_html=True)
    
with col_right:
    # Retrieve active tactical hints
    advice, is_thinking = g_state.buffer.get_advice()
    script = advice.replace("\n", "<br>")
    script_html = f'<div class="script-section"><b>💬 Active Prompter:</b><br>{script}</div>'
    advisor_html = f'<div class="advisor-box">{script_html}</div>'
    
    st.markdown(advisor_html, unsafe_allow_html=True)

    # ===== Staff Manual Injection UI =====
    if current_role == "staff":
        st.markdown('<div class="staff-box">', unsafe_allow_html=True)
        st.caption("⚡ Manual Override (Pushes instantly to Speaker)")
        
        # Use a form to prevent live re-renders from stealing focus while typing
        with st.form("staff_injection_form", clear_on_submit=True):
            manual_hint = st.text_input("Enter tactical cue...")
            submitted = st.form_submit_button("Launch Cue")
            
            if submitted and manual_hint.strip():
                # Push directly to the shared singleton buffer
                g_state.buffer.set_advice(f"⚡ [STAFF OVERRIDE]\n\n{manual_hint}")
        st.markdown('</div>', unsafe_allow_html=True)

# ===== Polling Mechanism =====
try:
    if g_state.is_running:
        # Staff role might need a slightly slower poll to avoid forms glitching, 
        # but st.form() handles focus stealing pretty well. We stick to 0.5s.
        time.sleep(0.5) 
    else:
        time.sleep(1.5)
        
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx() is not None:
        st.rerun()
except (RuntimeError, Exception):
    pass

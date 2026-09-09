import streamlit as st
import html
import time
import os
import sys
import atexit
import threading
import random
import string
from datetime import timedelta

# Mute the noisy "Event loop is closed" exception caused by Streamlit thread death
orig_excepthook = threading.excepthook
def mute_event_loop_closed(args):
    if args.exc_type == RuntimeError and "Event loop is closed" in str(args.exc_value):
        return
    orig_excepthook(args)
threading.excepthook = mute_event_loop_closed

# Ensure module pathing
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# `bootstrap` is the ONLY module imported at this scope. It is stdlib + dotenv, so importing it
# costs nothing and -- critically -- does not drag in `huggingface_hub`, whose HF_HOME is frozen
# at its own import time (V19). Everything heavy hangs off `global_state`, which is imported
# inside functions that run only once a storage root exists (V20, R48).
import bootstrap

# Stdlib-only, in the same class as `bootstrap`: it holds the advisor labels and the retrieval
# threshold the pre-flight and running views render, and it imports no retrieval or ASR
# machinery. The module that does -- `local_advisor` -- is imported lazily by
# `advisors.build_advisor` (V19, V20).
import advisors
import model_search
import postmeeting

# ===== Configuration snapshot =====
settings = bootstrap.read_settings()
is_configured = bootstrap.is_configured(settings)


# ===== Local versus remote, decided once and failing closed (R34, V37) =====
def read_host_header():
    """Return (host, failure_reason). An unreadable header yields an empty host."""
    try:
        if hasattr(st, "context"):
            return st.context.headers.get("host", ""), ""
        from streamlit.web.server.websocket_headers import _get_websocket_headers
        headers = _get_websocket_headers() or {}
        return headers.get("Host", ""), ""
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


host_header, host_failure = read_host_header()
is_local = bootstrap.is_local_host(host_header)

# A silent fail-closed is a bricked app: the operator would face a control panel with no Start
# button and no explanation. The verdict has to be stated (R39).
undetermined_origin = (not is_local) and (not host_header or bool(host_failure))


# ===== Nothing is loaded until Start is pressed =====
#
# **Inverted 2026-08-14 at the operator's direction, and it reverses R24.** Until then, merely
# opening a configured page ran the whole boot sequence: check the cache, download whatever was
# missing, and warm 1794 MB of weights into the NPU. Three things were wrong with that, and the
# third has no fix inside the old shape:
#
# 1. **Opening the app is not asking for anything.** Reading the settings on a metered connection
#    pulled gigabytes. Every other expensive thing in this product now waits to be asked (R25 for
#    capture, the model fetch button, the post-meeting prompt that runs nothing at all); the boot
#    sequence was the last one that did not.
# 2. **Warm-up was believed to cost minutes.** V33 says "minutes, possibly preceded by a
#    download" and R24 was written from it. Measured later, warm-up from a warm weight cache is
#    **2.3 s** (V61) — the minutes are the *download*, which is a separate step.
# 3. **An early download can only ever fetch a guess.** You do not know which model to fetch until
#    the operator has finished configuring, so "early" is a bet. Today it loses badly: save with
#    the default, change `ASR_MODEL`, and the app demands a restart while the multi-gigabyte
#    download of the model you just replaced **runs to completion anyway** — `set_readiness`
#    revokes a stale boot only *between* repositories, and a `snapshot_download` in flight cannot
#    be interrupted.
#
# So the page applies the environment and stops. `apply_environment` stays because it is stdlib
# and it exports `HF_HOME` from the storage root (R48) — the paths must be right before anything
# is fetched, which is V19's ordering and the reason the configuration work came first.
def prepare_environment():
    """Export the derived paths and settle into `idle`. Costs nothing, fetches nothing."""
    current = bootstrap.read_settings()
    bootstrap.apply_environment(current)
    if bootstrap.get_readiness()["state"] == bootstrap.NO_CONFIG:
        bootstrap.set_readiness(bootstrap.IDLE, "nothing loaded")
    return True


def begin_capture(**arming):
    """Download, warm, and open the streams — everything the operator just asked for.

    Runs on a background thread so the polling views keep painting, and reports through the same
    process-global readiness state every browser session already reads. That is what makes the
    wait identical from every tab: one flag, one truth, no session-local progress (R23, R39).
    """
    current = bootstrap.read_settings()
    boot_id = bootstrap.begin_boot()

    def _run():
        try:
            def _after_download():
                if not bootstrap.set_readiness(
                    bootstrap.WARMING, (current.get("ASR_MODEL") or "").strip(), boot_id=boot_id
                ):
                    return
                try:
                    # Nothing else may reach the network from here on. Set before the ASR stack
                    # imports: huggingface_hub 1.27 otherwise pings huggingface.co during warm-up
                    # even with every file already cached.
                    bootstrap.enforce_offline()
                    from global_state import GlobalState
                    state = GlobalState()
                    import voice_gate
                    state.warm_up(asr_model=(current.get("ASR_MODEL") or "").strip() or None,
                                  mic_device=(current.get("MIC_DEVICE") or "").strip(),
                                  gate=voice_gate.settings_from(current))
                    if not bootstrap.set_readiness(bootstrap.READY, boot_id=boot_id):
                        return
                    state.start_recording(**arming)
                except Exception as exc:
                    bootstrap.set_readiness(bootstrap.FAILED, f"{type(exc).__name__}: {exc}",
                                            boot_id=boot_id)

            bootstrap.set_readiness(bootstrap.DOWNLOADING, "checking the model cache",
                                    boot_id=boot_id)
            bootstrap.download_models(current, on_complete=_after_download, boot_id=boot_id)
        except Exception as exc:
            bootstrap.set_readiness(bootstrap.FAILED, f"{type(exc).__name__}: {exc}",
                                    boot_id=boot_id)

    threading.Thread(target=_run, name="aegis-start", daemon=True).start()


def clear_failure():
    """Return to `idle` after a failed Start, releasing anything that half-loaded.

    `idle` has to mean *nothing loaded*, or the archive lock and the memory promise both become
    lies. A Start that died between warming and opening the streams leaves models resident, so
    the retry path drops them rather than trusting the next attempt to reuse a partial state.
    """
    if "global_state" in sys.modules:
        try:
            state = sys.modules["global_state"].GlobalState()
            if not state.is_running:
                state.release_engine()
        except Exception:
            pass
    bootstrap.set_readiness(bootstrap.IDLE, "nothing loaded")


def end_capture():
    """Stop, then 退駕 — the models go with the session that needed them."""
    from global_state import GlobalState
    state = GlobalState()
    state.stop_recording()
    freed = state.release_engine()
    bootstrap.set_readiness(bootstrap.IDLE, "nothing loaded")
    return freed


def engine():
    """The heavy singleton. Never call before readiness has left `no-config`."""
    from global_state import get_global_state
    return get_global_state()


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

# Do not print the access code on every local rerun. The one-time box from
# get_global_access_code() is enough; a `\r` banner corrupts log lines under multi-session
# polling and was a V52 measurement artefact.

# ===== State 1: Access =====
if not is_local and not st.session_state.authenticated:
    if st.session_state.login_attempts >= 3:
        st.error("❌ Access Revoked: Too many failed attempts.")
        st.stop()
    st.title("🔒 Staff Officer Security")
    if undetermined_origin:
        st.warning(
            "Cannot determine whether this is a local connection"
            + (f" ({host_failure})" if host_failure else " (no Host header)")
            + " — treating it as remote. Machine controls stay hidden. If you are sitting at the "
              "capturing Mac, open http://localhost:8501 instead."
        )
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

# ===== State 2: Role =====
# Query param wins when present so lab scripts (`/?role=staff`) are not stuck on a
# previously clicked Speaker Mode still sitting in session_state.
query_role = (st.query_params.get("role") or "").lower()
if query_role in ("speaker", "staff", "archive"):
    st.session_state.selected_role = query_role
elif "selected_role" not in st.session_state:
    st.title("🛡️ Aegis Prompter Initialization")
    st.write("Please select your operational role for this session:")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🎤 Speaker Mode (Teleprompter)", use_container_width=True):
            st.session_state.selected_role = "speaker"
            st.rerun()
    with col2:
        if st.button("💻 Staff Mode (Tactical Override)", use_container_width=True):
            st.session_state.selected_role = "staff"
            st.rerun()
    with col3:
        if st.button("🗂 Archive Mode (Post-meeting)", use_container_width=True):
            st.session_state.selected_role = "archive"
            st.rerun()
    st.caption("Archive Mode opens past sessions and loads no models — pick it when the meeting "
               "is already over.")
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
    /* One block per turn. Newlines cannot do this: the box is rendered as HTML, where a
       newline collapses to a space and every turn runs into the next one. */
    .turn { margin-bottom: 0.7em; }
    .turn-role { font-weight: 600; font-size: 0.8em; letter-spacing: 0.04em;
                 text-transform: uppercase; display: block; opacity: 0.75; }
    /* The operator's own track is tinted, so "who said this" survives a glance from a podium --
       reading role labels is not something someone mid-sentence has attention for (R9). */
    .turn-me .turn-role { color: #58a6ff; }
    .turn-them .turn-role { color: #f0883e; }
    .advisor-box {
        background-color: #0d1117; border-radius: 10px; padding: 20px;
        height: 550px; overflow-y: auto; border: 2px solid #238636; position: relative;
    }
    /* Three kinds of advisor output, three appearances (R42). A reader glancing at this
       mid-sentence must not have to work out which one they are looking at, so the difference
       is carried by border colour, accent and a word — not by a label they have to read. */
    .advice-card {
        border-radius: 8px; padding: 14px 16px; margin-bottom: 14px;
        border-left: 6px solid #30363d; background-color: #161b22;
    }
    .advice-kind { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
                   text-transform: uppercase; display: block; margin-bottom: 6px; }
    .advice-text { color: #f0f6fc; font-size: 1.2rem; font-weight: 500; line-height: 1.5; }
    .advice-meta { font-size: 0.72rem; opacity: 0.6; margin-top: 8px; }
    /* A human instruction from the staff officer. */
    .advice-override { border-left-color: #f59e0b; background-color: #1f2937; }
    .advice-override .advice-kind { color: #fbbf24; }
    /* Pre-written and retrieved: the only kind that is safe to read aloud as-is (R30). */
    .advice-retrieved { border-left-color: #238636; }
    .advice-retrieved .advice-kind { color: #3fb950; }
    /* Generated: unverified, and marked so at a glance rather than in prose (R30, R42). */
    .advice-generated { border-left-color: #db6d28; border: 1px dashed #db6d28;
                        border-left: 6px solid #db6d28; background-color: #1c1410; }
    .advice-generated .advice-kind { color: #ffa657; }
    .advice-generated .advice-text { color: #ffd7ba; }
    .advisor-status { font-size: 0.75rem; color: #8b949e; border-top: 1px solid #30363d;
                      padding-top: 8px; margin-top: 4px; }
    .staff-box {
        background-color: #1f2937; border-radius: 10px; padding: 15px; margin-top: 15px;
        border: 2px dashed #f59e0b;
    }
    .cheatsheet-section { color: #58a6ff; font-size: 1.1rem; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    .script-section { color: #f0f6fc; font-size: 1.25rem; font-weight: 500; }
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #238636, #2ea043); }
</style>
""", unsafe_allow_html=True)


# ===== State 3: Configure (local only — R34) =====
def choose_folder(prompt):
    """Raise the native macOS folder dialog. Returns (path, error).

    The dialog is opt-in behind a button rather than the primary input, because whether it can
    be raised from inside a Streamlit callback without stalling the re-run is still unmeasured
    (V45). The validated text field beside it is the path that is known to work.
    """
    import subprocess
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True, timeout=180)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return "", (result.stderr or "").strip() or "cancelled"
    return result.stdout.strip(), ""


def points_off_machine(url):
    """Whether a configured backend URL leaves this machine."""
    value = (url or "").strip()
    if not value:
        return False
    without_scheme = value.split("://", 1)[-1]
    hostpart = without_scheme.split("/", 1)[0]
    return not bootstrap.is_local_host(hostpart)


def render_model_availability(model_id):
    """Say whether the configured model can still be obtained, and what to do when it cannot.

    **The default is a dated suggestion, not a promise.** Whatever is pinned eventually stops
    being downloadable — `docs/decisions/0008` reasoned that way about the package and assumed
    weights were safer because they are vendor repositories, which is too optimistic: a vendor
    repository can acquire a gate without disappearing. So the field says which of five states it
    is in, and when the news is bad it hands over a prompt rather than a list.

    Checked behind a button, not on every rerun. This screen is rendered on every keystroke, and
    a Hub call per keystroke would be both slow and a network request nobody asked for.
    """
    state_key = f"modelcheck_{model_id}"
    col_button, col_state = st.columns([1, 3])
    with col_button:
        if st.button("🔍 Check availability", key="cfg_check_asr_model"):
            with st.spinner("Asking the Hub…"):
                st.session_state[state_key] = model_search.availability(model_id)
    result = st.session_state.get(state_key)
    with col_state:
        if result is None:
            st.caption("The default is what measured best on 2026-08-11 — not a promise that it "
                       "still downloads. Check before you rely on it.")
            return
    render = {
        model_search.CACHED: st.success,
        model_search.AVAILABLE: st.success,
        model_search.GATED: st.error,
        model_search.MISSING: st.error,
        model_search.UNKNOWN: st.warning,
    }[result["state"]]
    render(f"`{result['model']}` — {result['state']}: {result['detail']}")

    if result["state"] in (model_search.CACHED, model_search.AVAILABLE):
        return

    # Bad news, so hand over the requirements rather than a ranked list. This app does not
    # enumerate or recommend models: that would be a judgement it has to keep maintaining, and it
    # is exactly what goes stale. The operator's own agent does the searching.
    st.caption(model_search.replacement_advice())
    with st.expander("📋 A prompt for your own agent, to find a replacement", expanded=True):
        st.code(model_search.build_search_prompt(model_id), language="markdown")


def render_configure(values):
    st.title("⚙️ Configure this machine")
    st.caption(
        "These settings are written to `.env` by this form. You never edit that file by hand, "
        "and deleting it is how you reset (R18, R22)."
    )
    st.info(
        "Remote devices are served over plain HTTP on the LAN — the transcript and the access "
        "code cross the network unencrypted. This form is shown only on this machine, so no "
        "credential is ever rendered to a remote browser."
    )

    draft = dict(values)
    for field in bootstrap.SETTINGS_FIELDS:
        label = field.label + (" *" if field.required else "")
        disabled_reason = ""
        if field.key == "QDRANT_API_KEY" and not (draft.get("QDRANT_URL") or "").strip():
            disabled_reason = "Set a Qdrant URL first."
        if field.key in ("LLM_API_KEY", "LLM_MODEL") and not (draft.get("LLM_BASE_URL") or "").strip():
            disabled_reason = "Set an LLM base URL first."

        # A path picked by the folder dialog on the previous run. Streamlit forbids assigning to
        # a widget's session_state key once that widget exists, so the dialog stashes its result
        # under a separate key and the widget is rebuilt from it here, before instantiation.
        pending_key = f"picked_{field.key}"
        if pending_key in st.session_state:
            st.session_state.pop(f"cfg_{field.key}", None)
            initial = st.session_state.pop(pending_key)
        else:
            initial = values.get(field.key, "")

        if field.secret:
            reveal_key = f"reveal_{field.key}"
            col_input, col_eye = st.columns([6, 1])
            with col_eye:
                st.write("")
                reveal = st.checkbox("👁", key=reveal_key, disabled=bool(disabled_reason),
                                     help="Show the value")
            with col_input:
                draft[field.key] = st.text_input(
                    label, value=initial, key=f"cfg_{field.key}",
                    type="default" if reveal else "password",
                    help=disabled_reason or field.help, disabled=bool(disabled_reason),
                )
        else:
            draft[field.key] = st.text_input(
                label, value=initial, key=f"cfg_{field.key}",
                help=disabled_reason or field.help, disabled=bool(disabled_reason),
            )
            if field.kind == "path":
                if st.button("📁 Browse…", key=f"browse_{field.key}"):
                    picked, error = choose_folder(f"Select the {field.label.lower()}")
                    if picked:
                        st.session_state[pending_key] = picked
                        st.rerun()
                    else:
                        st.caption(f"No folder chosen ({error}). Type the path instead.")

        if disabled_reason:
            st.caption(f"🔒 {disabled_reason}")
        if field.key == "ASR_MODEL":
            render_model_availability(draft[field.key] or field.default)
        # Warn at the moment the operator changes a field that costs something (R41).
        if field.warning and draft[field.key] != values.get(field.key, ""):
            st.warning(f"⚠️ {field.warning}")

    if points_off_machine(draft.get("QDRANT_URL")) or points_off_machine(draft.get("LLM_BASE_URL")):
        st.warning(
            "⚠️ A backend URL points off this machine. Transcript text and the credential you "
            "entered will leave it. That is your call to make — this notice exists so it is an "
            "informed one."
        )

    # Report what is already under the root, before anything is written (R48, V47).
    root = (draft.get("STORAGE_ROOT") or "").strip()
    if root:
        report = bootstrap.inspect_root(root)
        paths = report["paths"]
        st.markdown("**What this root resolves to**")
        st.code(f"{paths['models']}   # weights (HF_HOME)\n{paths['audio']}    # retained audio",
                language="text")
        if report["models"]["files"]:
            st.success(
                f"Existing model cache found — {bootstrap.format_bytes(report['models']['bytes'])} "
                f"across {report['models']['files']} files. It will be reused, not re-downloaded."
            )
        else:
            st.info("No model cache under this root yet. Weights will be downloaded after saving.")
        if report["audio"]["files"]:
            st.caption(
                f"Existing recordings: {report['audio']['files']} files, "
                f"{bootstrap.format_bytes(report['audio']['bytes'])}."
            )
        if not report["writable"]:
            st.error("This location is not writable by the app. Choose another root.")

    missing = bootstrap.missing_required(draft)
    col_save, col_reset = st.columns([3, 1])
    with col_save:
        if st.button("💾 Save configuration", type="primary", use_container_width=True,
                     disabled=bool(missing)):
            bootstrap.write_settings(draft)
            st.session_state.pop("show_configure", None)
            st.rerun()
        if missing:
            st.caption(f"🔒 Required before saving: {', '.join(missing)}")
    with col_reset:
        if st.button("♻️ Reset", use_container_width=True):
            st.session_state.confirm_reset = True

    if st.session_state.get("confirm_reset"):
        st.markdown("---")
        st.subheader("Reset deletes `.env` and nothing else")
        report = bootstrap.inspect_root(values.get("STORAGE_ROOT", ""))
        st.write(
            "Nothing on disk is removed. These paths simply stop being referenced — this is the "
            "last screen that shows you where your data is:"
        )
        st.code(
            f"{report['paths']['models'] or '(none)'}   "
            f"{bootstrap.format_bytes(report['models']['bytes'])}\n"
            f"{report['paths']['audio'] or '(none)'}    "
            f"{bootstrap.format_bytes(report['audio']['bytes'])}",
            language="text",
        )
        st.caption("Re-entering the same storage root later restores both, weights included.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Delete .env", type="primary", use_container_width=True):
                bootstrap.delete_settings()
                st.session_state.pop("confirm_reset", None)
                for field in bootstrap.SETTINGS_FIELDS:
                    st.session_state.pop(f"cfg_{field.key}", None)
                st.rerun()
        with col_no:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("confirm_reset", None)
                st.rerun()


if is_local and (not is_configured or st.session_state.get("show_configure")):
    render_configure(settings)
    st.stop()

if not is_local and not is_configured:
    # A remote device cannot configure the capturing machine (R34), and must not be left with a
    # blank screen (R35, R39).
    st.title("⏳ Waiting for the capturing machine")
    st.info("This Mac has not been configured yet. The staff officer sets it up on the machine "
            "itself; this page will follow along once they do.")
    time.sleep(2)
    st.rerun()

def render_archive():
    """Past sessions: where each transcript is, and the prompt at the end of it.

    **Loads nothing.** No model, no audio device, no advisor -- a `listdir` and a substring
    search per file. That is what makes this reachable without paying for warm-up, and it is why
    it is routed before the boot sequence rather than after it.

    It reads only this application's own output. `history/` is the operator's meeting record and
    nothing here writes to it.
    """
    st.title("🗂 Archive")
    st.caption("Finished sessions. Nothing is loaded on this screen — no models, no devices — so "
               "it opens as fast on a cold start as on a warm one.")

    sessions = postmeeting.list_sessions()
    if not sessions:
        # R39: no dead ends. An empty archive is a state, not a blank page.
        st.info("No sessions yet. They appear here after a capture is stopped, as "
                "`history/Meeting_<session id>.md`.")
        return

    labels = [f"{s['session_id']}  ·  {s['bytes'] / 1024:.0f} KB"
              + ("" if s["has_prompt"] else "  ·  no prompt block") for s in sessions]
    chosen = st.selectbox(f"{len(sessions)} sessions, newest first", range(len(sessions)),
                          format_func=lambda i: labels[i], key="archive_pick")
    session = sessions[chosen]

    st.write(f"📝 `{session['path']}`")
    audio = postmeeting.audio_paths(bootstrap.resolve_archive_dir(settings),
                                    session["session_id"])
    if audio:
        for track, path in sorted(audio.items()):
            st.write(f"🎧 {track}: `{path}`")
    else:
        st.caption("No audio was retained for this session, so the transcript is the only record.")

    prompt = postmeeting.read_prompt(session["path"])
    if prompt:
        st.code(f"sed -n '/{postmeeting.MARKER_TOKEN}/,$p' {session['path']}", language="sh")
        with st.expander("📋 The prompt at the end of this transcript", expanded=False):
            st.code(prompt, language="markdown")
    else:
        # Sessions written before the prompt existed, or a run that never reached Stop. Saying
        # which is more useful than an empty expander.
        st.warning("This transcript has no prompt block — it was written before the prompt "
                   "existed, or the session never stopped cleanly. The transcript itself is "
                   "unaffected.")

    st.markdown("---")
    st.subheader("Re-listen")
    st.caption("The one post-meeting job an outside agent cannot do: it re-runs speech "
               "recognition over the retained audio with a longer silence flush, so sentences "
               "arrive whole and what voice detection threw away is read again. It loads the "
               "model when you press it, not before.")
    if not audio:
        # R40: a control that cannot work names what is missing rather than being absent.
        st.button("🎧 Re-listen", disabled=True, key="archive_relisten")
        st.caption("🔒 Needs retained audio, and this session has none. Arm **Retain dual-track "
                   "audio** on the pre-flight panel before a meeting to keep it.")
        return
    # Speaker separation: opt-in, installed on the press and never before, so a process that
    # never asks for it contains no telemetry exporter and no cloud SDK (R15).
    import diarize
    has_diarizer = diarize.available()
    token = (settings.get("HF_TOKEN") or "").strip()
    diarize_model = ((settings.get("DIARIZE_MODEL") or "").strip()
                     or diarize.DEFAULT_MODEL_ID)
    gated_default = diarize_model == diarize.DEFAULT_MODEL_ID
    # **Default off, and it used to default to `has_diarizer`.** That was a fair inference while
    # installing `pyannote` was a deliberate act -- they installed it, so they wanted it. It stopped
    # being fair on 2026-08-18, when `docs/decisions/0013` made the package a hard dependency for
    # the voice gate: presence now says nothing about intent, and the old default silently switched
    # on a feature nobody asked for.
    want_voices = st.checkbox("Also separate the voices on the far side", value=False,
                              key="archive_diarize")
    if want_voices:
        st.caption("Lines that share a voice get `與會者1`, `與會者2`… — **sound alone, no names**. "
                   "A guessed name-to-label table goes at the end for you to check and apply "
                   "yourself with a find-and-replace. Nothing is applied for you.")
        if not has_diarizer:
            st.warning(
                "⚠️ Not installed, and it is a real addition: **47 packages**, mostly a research "
                "lab's training apparatus rather than anything inference needs — and "
                "`pyannote-audio` requires **OpenTelemetry** and a **cloud SDK** as core "
                "dependencies. Neither transmits anything unconfigured, but this application's "
                "offline guarantee stops being checkable by reading the dependency list."
            )
            if st.button("⬇️ Install speaker separation", key="archive_install_diarizer"):
                with st.spinner("Installing — this takes a few minutes…"):
                    error = diarize.install()
                if error:
                    st.error(f"❌ {error}")
                else:
                    st.success("✅ Installed. Re-run this screen.")
                    st.rerun()
            want_voices = False
        else:
            st.caption(f"Model: `{diarize_model}`")
        if want_voices and gated_default and not token:
            # Naming the way out matters as much as naming the problem: an operator who does not
            # want to create a token has a fully local, ungated path and would not otherwise
            # know it exists.
            st.error(
                f"🔒 `{diarize_model}` is **gated**: it needs a Hugging Face account that has "
                f"accepted its terms, and that account's token in Settings.\n\n"
                f"If you would rather not, set **Speaker separation model** to "
                f"`{diarize.UNGATED_ALTERNATIVE}` — an MIT mirror of the older 3.1 pipeline that "
                f"runs entirely on this machine and needs **no token**. It is a third party "
                f"re-hosting the weights, so that is a supply-chain judgement rather than a free "
                f"lunch."
            )
            # **Not a `return`.** Speaker separation is optional; re-listening is not conditional
            # on it. Returning here made an unmet precondition for one feature remove a different
            # one from the screen entirely -- a dead end (R39), and a control missing rather than
            # disabled-with-a-reason (R40). Found 2026-08-18 when the package became a hard
            # dependency and this branch started executing for everyone without a token.
            want_voices = False

    if st.button("🎧 Re-listen and fill in what was dropped", key="archive_relisten"):
        import relisten
        with st.status("🎧 Re-listening…", expanded=True) as status:
            def _progress(label):
                status.update(label=f"🎧 Re-listening — {label}")

            outcome = relisten.run(
                session["path"], audio,
                model_path=(settings.get("ASR_MODEL") or "").strip(),
                on_progress=_progress,
                diarize=want_voices,
                hf_token=token,
                diarize_model=diarize_model,
            )
            if outcome["output"]:
                st.write(f"Written to `{outcome['output']}` — {outcome['segments']} lines.")
                if outcome.get("diarized"):
                    st.write(f"🗣️ {outcome['voices']} voices separated on the far side. The "
                             f"name table at the end of the file is a **guess** — check it, then "
                             f"do the replacement yourself.")
                if outcome.get("diarize_error"):
                    st.warning(f"⚠️ Voices not separated: {outcome['diarize_error']}")
                if not outcome["aligned"]:
                    st.warning("⚠️ The per-track start times were not in the live transcript, so "
                               "the two tracks were aligned as if they began together. They did "
                               "not; cross-track ordering is approximate.")
                st.caption("The live transcript is unchanged. This is a second reading of the "
                           "same hour, not a correction of that one.")
            if outcome["error"]:
                st.error(f"❌ {outcome['error']}")
                status.update(label="🎧 Re-listening incomplete", state="error")
            else:
                status.update(label="🎧 Re-listening finished", state="complete")


# ===== State 3.5: Archive Mode — past sessions, and nothing loaded =====
#
# Routed **before** the boot below, and that placement is the whole point. Opening the app days
# later to read last week's transcript should not cost 1794 MB of speech-recognition weights and
# a warm-up nobody is waiting on. Warm-up exists to serve the live path's latency requirement
# (R9, R24) -- nothing else should inherit it.
#
# It still applies the environment, because that is what exports `HF_HOME` from the storage root
# (R48). Skipping it would leave a later re-listening pass downloading weights into
# `~/.cache/huggingface` instead, which is the exact failure V19 describes and the reason the
# configuration work was ordered first.
if is_local and current_role == "archive":
    bootstrap.apply_environment(settings)
    # **The lock.** Archive Mode is refused whenever anything of ours is loaded or a capture is
    # running, and it guards three things in descending order of how much they matter:
    #
    # 1. **The accelerator.** Re-listening re-runs speech recognition, and a live capture already
    #    has two tracks queueing on `NPU_LOCK` (V56, V57, V58). A third consumer does not make
    #    things slower in the abstract — it spends the hearing's timeliness on work that can wait.
    # 2. **This screen's own promise**, which is that entering it finds no model of ours in
    #    memory. During a capture that sentence is simply false.
    # 3. **The operator's attention.** A meeting is being recorded; the interface should not be
    #    offering a way to go and browse old files. Every other screen already jumps into Running
    #    when a capture starts, so this is that rule applied consistently rather than a new one.
    state_now = bootstrap.get_readiness()["state"]
    if state_now not in (bootstrap.IDLE, bootstrap.NO_CONFIG):
        st.title("🗂 Archive")
        st.warning("The archive is closed while the engine is busy — the models are loaded and "
                   f"the accelerator is in use (`{state_now}`). Stop the capture and it opens; "
                   "stopping also releases the models.")
        st.caption("This is deliberate: re-listening runs speech recognition over retained "
                   "audio, and it must not compete with a hearing that is happening now.")
        st.stop()
    render_archive()
    st.stop()

# ===== Settle the environment. Nothing is fetched and nothing is loaded. =====
if bootstrap.needs_restart(settings):
    # Revoke the in-flight boot first: its warm-up thread may still be about to call READY.
    bootstrap.invalidate_boot()
    bootstrap.set_readiness(bootstrap.RESTART_REQUIRED,
                            "configuration changed after the models were loaded")
else:
    prepare_environment()

readiness = bootstrap.get_readiness()

# ===== State 4: Pre-flight =====
# Two tracks, mono int16, 16 kHz: 115 MB per track per hour (REQUIREMENTS.md sizing table).
# **This read 0.69 until 2026-08-13**, which was the 48 kHz figure and outlived the reversal to
# 16 kHz in `docs/decisions/0001` — so the consent-and-disk warning overstated the cost by 3x.
ARCHIVE_HOURLY_GB = 0.23


def render_readiness(state):
    if state["state"] == bootstrap.READY:
        st.success("✅ Models warmed. Ready to start.")
        return
    if state["state"] == bootstrap.RESTART_REQUIRED:
        st.error(
            "🔁 Restart required. The storage root or a model name changed after this process "
            "loaded its models, and `HF_HOME` cannot be moved in a running process. Stop "
            "Streamlit and run it again to pick up the new configuration."
        )
        return
    if state["state"] == bootstrap.FAILED:
        st.error(f"❌ Start failed: {state['detail']}")
        # **Not "restart the app" any more.** That was true while the boot ran once at startup; a
        # failed boot really was a failed launch. Since 2026-08-14 Start is a repeatable action,
        # so a download that timed out or a device that was unplugged must be retryable in place
        # — telling the operator to quit Streamlit over one failed attempt is a dead end (R39).
        st.caption("Nothing has been captured. Fix the cause and press Start again.")
        return
    if state["state"] == bootstrap.DOWNLOADING:
        st.info(f"⬇️ Downloading model weights — {state['detail']}")
        for repo, entry in bootstrap.progress_snapshot().items():
            if entry["error"]:
                st.error(f"{repo}: {entry['error']}")
            elif entry["finished"]:
                st.caption(f"✅ {repo}")
            elif entry["total"]:
                st.caption(repo)
                st.progress(min(entry["done"] / entry["total"], 1.0))
            else:
                st.caption(f"{repo} — starting")
        return
    if state["state"] == bootstrap.WARMING:
        st.info(f"🔥 Warming the NPU with {state['detail'] or 'the ASR model'}. "
                "Both tracks warm one after the other, so this takes a few minutes.")
        return
    st.info("Preparing…")


FOLLOW_DEFAULT_LABEL = "System default (follow macOS)"


def _input_device_names():
    """Names of every recordable device, or `None` if the audio stack cannot be asked.

    Returns `None` rather than `[]` so the caller can tell "no devices" from "could not look",
    which are different things to show an operator.
    """
    try:
        # `audio_devices` carries no ASR dependency on purpose: the panel renders while the model
        # may still be downloading, and importing `transcriber` here would pull `huggingface_hub`
        # in ahead of the boot sequence (V19, V20).
        import audio_devices
        return [d["name"] for d in audio_devices.list_input_devices()]
    except Exception:
        return None


def _default_input_name():
    """What `""` resolves to right now, for display only. Empty if it cannot be determined."""
    try:
        import audio_devices
        return audio_devices.default_input_name()
    except Exception:
        return ""


def _render_microphone_picker(stored):
    """The R26 dropdown: a sensible default, freely overridable. Returns the value to persist.

    `""` is the default and means *follow whatever macOS calls the default input*, resolved at
    each Start rather than frozen now -- an operator who never expressed a choice should keep
    getting the system's answer, not a snapshot of it.

    Applying the change costs two assignments and never reloads the model (V33). It is applied
    immediately so the meter and the resolved name below react, and persisted only when Start is
    pressed, like every other decision on this panel (R27).
    """
    names = _input_device_names()
    if names is None:
        st.caption("🎤 Device list unavailable until the audio stack loads. "
                   + (f"Stored preference: `{stored}`." if stored else
                      "Capture will follow the system default input."))
        return stored

    options = [""] + names
    labels = {"": FOLLOW_DEFAULT_LABEL}

    # What to preselect. **The session's own choice outranks the persisted one**, and getting this
    # backwards is not a cosmetic bug: the preference is only written to `.env` when Start is
    # pressed, so before that `stored` is whatever the last session left -- usually empty. Deriving
    # `index` from `stored` therefore reset the operator's selection to "system default" on every
    # full rerun, and a full rerun is exactly what plugging in a headset causes, because the device
    # list changes. Observed 2026-08-12: connecting a headset silently moved the selection back and
    # the operator had to choose again, with nothing on screen saying why.
    current = st.session_state.get("pf_mic", stored)

    # A choice that matches no connected device is shown rather than dropped -- whether it came
    # from `.env` or from this session. Silently falling back to the default would leave the panel
    # naming a headset while the built-in microphone recorded the room.
    for absent in (value for value in (current, stored) if value and value not in options):
        options.append(absent)
        labels[absent] = f"{absent} — not connected"

    picked = st.selectbox(
        "Input for the Speaker track",
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda v: labels.get(v, v),
        key="pf_mic",
    )
    st.caption("Sticky: whatever this reads when Start is pressed becomes this machine's "
               "standing preference. The Participant track is not selectable — system audio is "
               "everything by design (R1).")
    if not picked and names:
        # The system default input is whichever device macOS last decided on, which in practice is
        # the headset that connected most recently -- measured on this machine (V63), where the
        # built-in microphone is what the operator actually wants every time. Stated as information
        # rather than corrected silently: which microphone is pointed at their mouth is not
        # something this program can know.
        resolved = _default_input_name()
        if resolved:
            st.info(f"Currently that resolves to **{resolved}**. macOS usually makes the most "
                    f"recently connected headset the default input — if that is not the microphone "
                    f"you are speaking into, choose it above.")

    if picked and picked not in names:
        st.warning(f"⚠️ `{picked}` is not connected. Leaving it selected records nothing on the "
                   "Speaker track; pick another input or reconnect it.")

    # Applying the choice, and saying so when it cannot be applied *yet*. An earlier version of
    # this swallowed every exception here, which produced exactly the failure this project keeps
    # finding: the dropdown showed the operator's choice, the engine kept the old device, and
    # nothing said the two disagreed. Observed 2026-08-12 in the first web-driven session.
    # Only if the engine was already built. Since the boot inverted on 2026-08-14 nothing is
    # loaded until Start, so calling `engine()` here would *create* it -- importing the whole ASR
    # stack on the one screen whose promise is that nothing is loaded. The choice is persisted as
    # `MIC_DEVICE` when Start is pressed and `warm_up` resolves it from there, so applying it
    # live matters only when there is something live to apply it to.
    if "global_state" not in sys.modules:
        st.caption("Applied when capture starts — nothing is loaded until then.")
        return picked
    try:
        eng = engine()
    except Exception as exc:
        st.warning(f"⏳ Selection recorded but not applied yet ({type(exc).__name__}). It takes "
                   f"effect when the engine finishes loading, or at the next launch.")
        return picked

    if eng.is_running:
        st.caption("🔒 Capture is running; the microphone changes at the next session.")
        return picked
    if not eng.is_warm:
        st.caption("⏳ Applies as soon as warm-up finishes — it is read again there.")
        return picked
    if eng.mic_device != picked:
        try:
            resolved = eng.set_microphone(picked)
        except Exception as exc:
            st.error(f"❌ Could not switch microphone: {type(exc).__name__}: {exc}")
            return picked
        if not resolved:
            st.error("❌ No input device matched that choice. The Speaker track would be silent — "
                     "pick a device that is connected.")
    # What the engine will actually open, which is the number that matters and the one that was
    # missing when this disagreed with the dropdown.
    st.caption(f"Engine will open: **{eng.me_name}**")
    return picked


# Safest first, least safe last, and the order never changes between ticks -- a pane that
# reorders itself is unreadable from a podium. The staff officer's own instruction outranks
# both machines; generated text sits at the bottom because it is the one thing that must not be
# read aloud unchecked (R30, R42).
ADVICE_ORDER = (advisors.SOURCE_OVERRIDE, advisors.SOURCE_RETRIEVED, advisors.SOURCE_GENERATED)
ADVICE_STYLE = {
    advisors.SOURCE_OVERRIDE: ("advice-override", "⚡ Staff override"),
    advisors.SOURCE_RETRIEVED: ("advice-retrieved", "🛡️ Retrieved — pre-written"),
    advisors.SOURCE_GENERATED: ("advice-generated", "🤖 Generated — UNVERIFIED"),
}


def _advisor_html(slots):
    """Every filled advisor slot as its own labelled card (V24, R29, R30, R42).

    Escaped for the same reason the transcript is: retrieved text comes from the operator's own
    notes, but generated text comes from a model answering audio nobody controls, and both land
    in a div rendered with `unsafe_allow_html`.
    """
    cards = []
    for source in ADVICE_ORDER:
        slot = slots.get(source) or {}
        text = (slot.get("text") or "").strip()
        if not text:
            continue
        css, label = ADVICE_STYLE[source]
        meta = []
        if slot.get("time"):
            meta.append(html.escape(slot["time"]))
        if slot.get("vendor"):
            meta.append(html.escape(slot["vendor"]))
        if slot.get("score") is not None:
            meta.append(f"score {slot['score']:.2f}")
        if slot.get("is_thinking"):
            meta.append("in flight")
        body = html.escape(text).replace("\n", "<br>")
        cards.append(
            f'<div class="advice-card {css}">'
            f'<span class="advice-kind">{label}</span>'
            f'<div class="advice-text">{body}</div>'
            + (f'<div class="advice-meta">{" · ".join(meta)}</div>' if meta else "")
            + "</div>"
        )
    if not cards:
        return '<div class="advice-meta">Awaiting dialogue…</div>'
    return "".join(cards)


def _advisor_status_html(status):
    """The liveness line (R36): silence has to be distinguishable from failure.

    Every state here is one an operator can act on mid-meeting. `RAG 0.31` says the index is
    alive and nothing matched; a missing score says it never ran; `LLM error` names the host
    that is not answering. A blank pane says all three at once, which is the failure V34
    describes.
    """
    if not status:
        return ('<div class="advisor-status">No advisor armed — transcription only.</div>')
    parts = []
    rag = status.get("rag") or {}
    if rag.get("armed"):
        if not rag.get("ok"):
            parts.append(f"🛡️ RAG unavailable — {html.escape(rag.get('error') or 'no index')}")
        elif rag.get("last_score") is None:
            parts.append(f"🛡️ RAG ready — {rag.get('queries', 0)} queries, nothing scored yet")
        else:
            parts.append(f"🛡️ RAG {rag['last_score']:.2f} — {rag.get('queries', 0)} queries")
    llm = status.get("llm") or {}
    if llm.get("armed"):
        state = llm.get("state", "idle")
        wording = {
            "idle": "idle — nothing has met the send band yet",
            "waiting": "waiting for a reply…",
            "ok": "answered",
            "empty": "declined — nothing worth saying",
            "error": f"error — {html.escape(llm.get('detail') or 'no detail')}",
        }.get(state, state)
        latency = llm.get("latency_ms")
        suffix = f" ({latency:.0f} ms)" if latency is not None else ""
        parts.append(f"🤖 LLM {wording}{suffix} — {llm.get('calls', 0)} calls")
    if not parts:
        return '<div class="advisor-status">No advisor armed — transcription only.</div>'
    return f'<div class="advisor-status">{" &nbsp;·&nbsp; ".join(parts)}</div>'


def _transcript_html(state, max_lines=5):
    """The transcript as HTML: one block per turn, escaped.

    Two defects this replaces, both from rendering `"\n".join(...)` inside an HTML div.

    **Turns ran together.** HTML collapses a newline to a space, so Participant and Speaker
    appeared as one paragraph with no boundary -- reported from the first live session. The advisor
    column had always converted its newlines; the transcript never did.

    **And the text was not escaped.** Transcript content is whatever the model produced from
    audio, which nobody controls: a line containing `<` truncated the box or dropped the rest of
    the session from view. `unsafe_allow_html` is needed for the styling, so the content has to be
    escaped rather than trusted.
    """
    entries = state.buffer.get_full_dialogue()[-max_lines:] if max_lines else state.buffer.get_full_dialogue()
    if not entries:
        return "Awaiting stream..."
    blocks = []
    for entry in entries:
        role = entry.get("role", "")
        # "Speaker (You)" is the operator's own microphone; anything else is the room (R2).
        css = "turn-me" if "You" in role else "turn-them"
        blocks.append(
            f'<div class="turn {css}">'
            f'<span class="turn-role">{html.escape(role)}</span>'
            f'{html.escape(entry.get("text", ""))}'
            f'</div>'
        )
    return "".join(blocks)


def render_last_session():
    """Point at the transcript the previous session wrote, and say what is at the end of it.

    Reads the `history/` directory, **not the engine.** An earlier version called `engine()`,
    which imports the whole ASR stack — on a screen whose entire purpose is that nothing is
    loaded until Start. Caught 2026-08-14 by the test that asserts exactly that, one commit
    after the boot was inverted to make the assertion meaningful.

    Without this panel the post-meeting design is invisible: the whole feature is "the prompt is
    in the file", and until 2026-08-14 nothing in the interface mentioned that a file exists. A
    feature delivered somewhere the operator is never told to look is this system's
    characteristic bug wearing different clothes.
    """
    sessions = postmeeting.list_sessions()
    if not sessions:
        return
    session = sessions[0]

    st.subheader("Last session")
    st.write(f"📝 `{session['path']}`")
    if session["has_prompt"]:
        st.caption("It ends with a prompt for your own agent — how this file is written, how the "
                   "transcript is lossy, and what to produce from it. Copy it, or lift it out:")
        st.code(f"sed -n '/{postmeeting.MARKER_TOKEN}/,$p' {session['path']}", language="sh")
    else:
        st.caption("No prompt block — this session predates it, or it never stopped cleanly.")
    for track, path in sorted(
        postmeeting.audio_paths(bootstrap.resolve_archive_dir(settings),
                                session["session_id"]).items()
    ):
        st.caption(f"🎧 {track}: `{path}`")
    st.markdown("---")


def render_preflight():
    """Local pre-Start panel (R27). Refreshes via an inner fragment — never sleep+full rerun.

    A full-script `time.sleep` + `st.rerun` poll stacked with other timers and could paint
    **two** Start capture buttons. Readiness/Start live in `_preflight_live` instead.
    """
    st.title("🚦 Pre-flight")
    st.caption("Every per-meeting decision is made here. Pressing Start commits all of them for "
               "the session.")
    render_last_session()

    # --- Microphone, retention, advisors: session widgets, stable across fragment ticks ---
    # Outside the fragment on purpose. A widget rebuilt every tick loses focus mid-interaction,
    # and re-enumerating devices at 1 Hz would query PortAudio for a list that changes only when
    # hardware does.
    st.subheader("Microphone")
    stored_mic = (settings.get("MIC_DEVICE") or "").strip()
    mic_choice = _render_microphone_picker(stored_mic)

    st.subheader("Recording")
    archive_on = (settings.get("ARCHIVE_AUDIO") or "").strip().lower() == "true"
    archive_dir = bootstrap.resolve_archive_dir(settings)
    retain = st.checkbox("Retain dual-track audio for this and future sessions", value=archive_on,
                         key="pf_retain")
    st.caption("Sticky: whatever this reads when Start is pressed becomes this machine's "
               "standing preference.")
    if retain and not archive_on:
        st.warning(
            f"⚠️ About {ARCHIVE_HOURLY_GB:.2f} GB per hour across both tracks — roughly "
            f"{ARCHIVE_HOURLY_GB * 3:.1f} GB for a three-hour hearing. Recording also carries "
            "consent expectations this system does not assume on your behalf."
        )
    # R46: a sticky setting is disclosed in its current state every session, not merely applied.
    # Naming the directory is part of that — "retained" without "where" is not something the
    # operator can act on, and R45 makes finding the files afterwards the point.
    if retain:
        st.write(f"💾 Two WAV files per session, 16 kHz mono, into `{archive_dir}`")
        st.caption("Named `Meeting_<session id>_mic.wav` and `_system.wav`, sharing the session "
                   "id with the transcript in `history/`. Written from the raw stream, before "
                   "voice detection — so what the transcript drops is still on disk.")
    else:
        st.caption("Off: whatever voice detection and the filters discard this session is gone "
                   "for good. The session record will say so.")

    st.subheader("Advisors")
    index = bootstrap.index_status(settings)
    if index["error"]:
        st.warning(f"🛡️ Retrieval index: {index['error']}")
    else:
        st.write(
            f"🛡️ Retrieval index: **{index['chunks']} chunks**, built {index['built']}"
            + (f", model `{index['model']}`" if index["model"] else "")
        )
        st.caption(f"Collection `{index.get('collection', '')}` in {index.get('target', '')}.")
        # Retrieval queries with the model the collection names, so a mismatch cannot corrupt a
        # score (V36) -- but the operator is then running against an index their setting no
        # longer describes, and only they can decide whether to rebuild.
        configured = (settings.get("EMBEDDING_MODEL")
                      or bootstrap.FIELDS_BY_KEY["EMBEDDING_MODEL"].default or "").strip()
        if index["model"] and configured and index["model"] != configured:
            st.warning(
                f"⚠️ This index was built with `{index['model']}`, but the embedding model "
                f"setting is now `{configured}`. Retrieval uses the model the index was built "
                f"with, so scores are still valid — but the two disagree until you rebuild."
            )
    rag_available = index["chunks"] > 0 and not index["error"]
    enable_rag = st.checkbox("Arm the retrieval advisor", value=rag_available,
                            key="pf_rag", disabled=not rag_available)
    if not rag_available:
        st.caption("🔒 Needs a compiled index. Run `python src/build_index.py` after putting "
                   "notes in `context/docs/`.")

    # Hidden entirely, not disabled, when no LLM base URL is configured: offering something that
    # cannot work is worse than not offering it (R28, R40).
    llm_base_url = (settings.get("LLM_BASE_URL") or "").strip()
    enable_llm = False
    if llm_base_url:
        enable_llm = st.checkbox("Arm the generative advisor", value=False, key="pf_llm")
        if enable_llm:
            st.warning(
                "⚠️ Generated text is **unverified** and is never safe to read aloud as written. "
                "It appears in its own pane, marked, and never replaces a retrieved cue (R30)."
                + (" Utterances and the recent transcript leave this machine."
                   if points_off_machine(llm_base_url) else "")
            )
        st.caption(
            "Every Participant utterance is sent, with the recent transcript. The two advisors "
            "do not gate each other: retrieval serves a prepared cue when it has one, this "
            "answers separately, and both appear in their own labelled pane."
        )

        # **A rehearsal, not a gate** (`STATE.md`, open decision 2). It never blocks Start, it is
        # never required, and this app does not judge the answers — the operator does, which is
        # the only party able to. It doubles as the liveness probe R36 asks for *before* a
        # meeting without being one, and it narrows R36 deliberately: a button makes "before"
        # available on request rather than always shown, which is proportionate because an LLM
        # announces its own death on the first call while V34's RAG failure is silent forever.
        #
        # The prompt is the production one, so what is rehearsed is what will happen. That is
        # what makes V23's flooding risk visible here rather than mid-hearing — a model that
        # answers the small-talk line instead of declining it will not stop talking during a
        # meeting, and no liveness signal would ever have shown that.
        with st.expander("🎭 Rehearse — ask your own endpoint your own questions", expanded=False):
            st.caption("Nothing here is a test this app can pass or fail for you. It sends the "
                       "real prompt and shows you what comes back; whether that is worth reading "
                       "aloud at a hearing is your judgement.")
            questions = st.text_area("One per line", value=advisors.REHEARSAL_DEFAULT,
                                     key="pf_llm_rehearsal", height=110)
            if st.button("▶ Run the rehearsal", key="pf_llm_rehearse"):
                probe = advisors.LlmAdvisor(
                    base_url=llm_base_url,
                    api_key=settings.get("LLM_API_KEY") or "",
                    model=settings.get("LLM_MODEL") or "",
                    timeout=20.0,
                )
                st.caption(f"`{probe.url}`")
                with st.spinner("Asking your endpoint…"):
                    results = advisors.rehearse(probe, questions)
                if not results:
                    st.info("No questions to ask. Type at least one line.")
                for result in results:
                    st.markdown(f"**{result['question']}**")
                    if result["error"]:
                        st.error(f"❌ {result['error']}")
                    elif result["declined"]:
                        st.success(f"— declined, {result['ms']:.0f} ms. It stayed quiet, which is "
                                   f"what it should do most of the time.")
                    else:
                        st.warning(f"🤖 {result['answer']}")
                        st.caption(f"{result['ms']:.0f} ms · unverified, and never safe to read "
                                   f"aloud without checking it")

    st.markdown("---")

    @st.fragment(run_every=timedelta(seconds=1.0))
    def _preflight_live():
        # Re-read each tick — warm-up finishes without a full-script rerun.
        state_now = bootstrap.get_readiness()
        render_readiness(state_now)
        # **Inverted 2026-08-14.** Start used to require READY, because warm-up ran on page load
        # and READY meant "the models are in". Now Start is what *causes* all of that, so it is
        # live in `idle` and the wait happens behind it — one process-global state every browser
        # session polls, so the spinner is the same wherever you are logged in from (R23, R39).
        idle = state_now["state"] == bootstrap.IDLE
        loading = state_now["state"] in (bootstrap.DOWNLOADING, bootstrap.WARMING)
        ready = state_now["state"] == bootstrap.READY

        st.subheader("Capture")
        if ready:
            eng = engine()
            # Another tab may have started capture; jump the whole app to Running.
            if eng.is_running:
                st.rerun()
            st.write(f"🎤 Microphone: **{eng.me_name}**")
            if eng.transcriber_me is not None and eng.transcriber_me.device_idx is None:
                st.error(
                    "No input device resolved, so the Speaker track will be silent. Pick a "
                    "different microphone above."
                )
            elif not eng.mic_device:
                st.caption("Following the system default input; it is re-read at Start.")
            st.write(f"🎧 System audio: **{eng.other_name}**")
            if eng.transcriber_other is None:
                st.warning(
                    "No system-audio device was found, so the Participant track will stay "
                    "silent. Install BlackHole and select a Multi-Output Device."
                )
        else:
            st.caption("Devices are resolved during warm-up.")
        # Capability, not enumeration: the tap's device exists only while the helper runs, and
        # the helper must not run before Start (R25) -- so this cannot be derived from the device
        # list. A helper that then fails at Start is reported there instead (R39).
        try:
            import system_audio
            backend, detail = system_audio.available_backend()
            label = {
                system_audio.BACKEND_TAP: "🎧 Active backend: **Core Audio process tap** — no "
                                          "virtual driver, and your output device is untouched.",
                system_audio.BACKEND_BLACKHOLE: f"🎧 Active backend: **BlackHole loopback** "
                                                f"({detail}).",
            }.get(backend, f"⚠️ No system-audio backend: {detail}. The Participant track will be "
                           f"silent — only what you say is transcribed.")
            (st.warning if backend == system_audio.BACKEND_NONE else st.caption)(label)
        except Exception as exc:
            st.caption(f"Active backend could not be determined ({type(exc).__name__}).")
        st.caption("Input meters go live after Start — no audio device is opened before it.")

        # R34: machine controls are local-only. R35's operator story is the staff officer
        # presses Start — Speaker Mode on this Mac is teleprompter, not the capture desk.
        can_control = current_role == "staff"
        col_start, col_settings = st.columns([3, 1])
        with col_start:
            if can_control:
                if st.button(
                    "▶️ Start capture",
                    type="primary",
                    use_container_width=True,
                    disabled=not idle,
                    key="pf_start_capture",
                ):
                    # Persist the sticky choices before the wait, so a download that fails or is
                    # abandoned still leaves the operator's preferences where they put them.
                    persisted = dict(settings)
                    persisted["ARCHIVE_AUDIO"] = "true" if retain else "false"
                    persisted["MIC_DEVICE"] = mic_choice
                    bootstrap.write_settings(persisted)
                    begin_capture(
                        enable_rag=enable_rag,
                        enable_llm=enable_llm,
                        archive_audio=retain,
                        archive_dir=archive_dir,
                    )
                    st.rerun()
                if loading:
                    st.caption("⏳ Fetching and warming what this session needs. Every tab waits "
                               "on the same state; capture begins by itself when it is in.")
                elif state_now["state"] == bootstrap.FAILED:
                    if st.button("↻ Try again", key="pf_retry_start"):
                        clear_failure()
                        st.rerun()
                elif not idle:
                    st.caption("🔒 Start unlocks once the configuration above is settled.")
            else:
                st.info(
                    "Speaker Mode has no Start capture. Use **Staff Mode** on this Mac "
                    "(or open `/?role=staff`) to start; this tab will follow into the transcript."
                )
        with col_settings:
            if can_control and st.button(
                "⚙️ Settings", use_container_width=True, key="pf_open_settings",
            ):
                st.session_state.show_configure = True
                st.rerun()

    _preflight_live()


running = False
if readiness["state"] == bootstrap.READY:
    try:
        running = engine().is_running
    except Exception:
        running = False

if not running:
    if is_local:
        render_preflight()
    else:
        # R35: the speaker routinely connects before the staff officer presses Start.
        st.title("⏳ Waiting for the staff officer to start")
        st.info("Capture has not begun. This page will switch to the transcript by itself.")
        st.caption("Remote viewing runs over plain HTTP on the LAN and is not encrypted.")

        @st.fragment(run_every=timedelta(seconds=1.5))
        def _remote_wait_for_start():
            try:
                if engine().is_running:
                    st.rerun()
            except Exception:
                pass

        _remote_wait_for_start()
    st.stop()

# ===== State 5: Running =====
# Define the live fragment ONLY on the running path, with run_every set here — not at module
# import. A module-level `@st.fragment(run_every=…)` kept firing after Stop and could stack
# with Pre-flight's full-script poll, which showed duplicate controls (e.g. two Start capture).
g_state = engine()

st.title(f"🕵️‍♂️ Staff Officer ({'Staff Mode' if current_role == 'staff' else 'Speaker Mode'})")

# Three sessions is the intended hearing; 0.5s holds while fragment work stays cheap (V52 / 7.3).
_running_poll = timedelta(seconds=0.5)


@st.fragment(run_every=_running_poll)
def _running_live_panes():
    """Meters, transcript, and advisor — the only panes that must refresh while capturing."""
    state = engine()
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        rms_me = state.transcriber_me.get_rms() if state.transcriber_me else 0
        st.caption(f"🎤 {state.me_name}")
        st.progress(min(rms_me * 15, 1.0))
    with col_v2:
        rms_other = state.transcriber_other.get_rms() if state.transcriber_other else 0
        st.caption(f"🎧 {state.other_name}")
        st.progress(min(rms_other * 15, 1.0))

    # Recording is the one thing whose absence and presence look identical from the outside, and
    # it writes to the operator's disk. It says which it is, for as long as it is doing it.
    if getattr(state, "archive_audio", False):
        dropped = sum(getattr(t.archive, "dropped_blocks", 0)
                      for t in (state.transcriber_me, state.transcriber_other)
                      if t is not None and getattr(t, "archive", None) is not None)
        seconds = max((getattr(t.archive, "duration_s", 0.0)
                       for t in (state.transcriber_me, state.transcriber_other)
                       if t is not None and getattr(t, "archive", None) is not None),
                      default=0.0)
        line = f"🔴 Recording both tracks — {seconds / 60:.0f} min to `{state.archive_dir}`"
        (st.warning if dropped else st.caption)(
            line + (f" · ⚠️ {dropped} blocks dropped" if dropped else "")
        )

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.markdown(
            f'<div class="transcript-box">{_transcript_html(state, max_lines=5)}</div>',
            unsafe_allow_html=True,
        )
    with col_right:
        cards = _advisor_html(state.buffer.get_advice_slots())
        status = state.advisor.status() if state.advisor is not None else None
        st.markdown(
            f'<div class="advisor-box">{cards}{_advisor_status_html(status)}</div>',
            unsafe_allow_html=True,
        )


_running_live_panes()

# Staff form and Stop stay outside the fragment so typing / clicking is not torn down each tick.
if current_role == "staff":
    st.markdown('<div class="staff-box">', unsafe_allow_html=True)
    st.caption("⚡ Manual Override (Pushes instantly to Speaker)")
    with st.form("staff_injection_form", clear_on_submit=True):
        manual_hint = st.text_input("Enter tactical cue...")
        submitted = st.form_submit_button("Launch Cue")
        if submitted and manual_hint.strip():
            # The label is the card, not the text: embedding it in the string was what made the
            # three kinds indistinguishable once a second backend could write to the same slot.
            g_state.buffer.set_advice(manual_hint, source=advisors.SOURCE_OVERRIDE,
                                      vendor="staff officer")
    st.markdown("</div>", unsafe_allow_html=True)

# Stop operates the capturing machine: local staff only (R34 + R35 operator story).
if is_local and current_role == "staff":
    st.markdown("---")
    if st.button("⏹️ Stop capture", key="pf_stop_capture"):
        # Stop stops, and nothing else. Review used to run here and block until it finished;
        # the operator reversed that on 2026-08-13 — see R49 and the review item in STATE.md.
        # Nothing is lost by deciding later, because a transcript on disk does not expire the
        # way unrecorded audio does.
        freed = end_capture()
        if freed > 1:
            st.caption(f"退駕 — released {freed:.0f} MB of speech-recognition weights.")
        st.rerun()

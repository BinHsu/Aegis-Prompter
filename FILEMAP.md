<!-- GENERATED FILE -- DO NOT EDIT.
     Regenerate with: python tools/gen_filemap.py
     Source of truth is the code itself; this file is derived from it. -->

# File Map

Mechanical inventory of the Python surface, derived from the AST. Use it to check
whether a module, class, or function exists and where it lives. Line numbers are
accurate only as of the last regeneration -- if something looks wrong, regenerate
rather than trusting this file:

```bash
python tools/gen_filemap.py
```

**10 Python files.**

## `src/`

### `src/app.py` — 205 lines

- `mute_event_loop_closed()` (L12)
- `cleanup_resources()` (L29)
- `get_global_access_code()` (L37)

### `src/build_index.py` — 78 lines

- `build_knowledge_index()` (L10)

### `src/dialogue_buffer.py` — 111 lines

- `class DialogueBuffer` (L5)
  - `start_session()`
  - `add_entry()`
  - `set_advice()`
  - `get_advice()`
  - `get_full_dialogue()`
  - `get_formatted_dialogue()`
  - `get_last_role()`
  - `clear()`

### `src/global_state.py` — 152 lines

- `class GlobalState` (L28)
  - `_init_once()`
  - `start_recording()`
  - `stop_recording()`
  - `_local_rag_worker_loop()`
- `get_global_state()` (L151)

### `src/local_advisor.py` — 91 lines

- `class LocalAdvisor` (L10)
  - `load_index()`
  - `analyze_dialogue()`

### `src/transcriber.py` — 196 lines

- `class Transcriber` (L17)
  - `find_device_index()`
  - `_audio_callback()`
  - `get_rms()`
  - `_processing_thread()`
  - `_inference_thread()`
  - `start()`
  - `stop()`

## `tests/unit/`

### `tests/unit/test_advisor.py` — 79 lines

- `mock_knowledge_index()` (L10)
- `test_local_advisor_loading()` (L34)
- `test_local_advisor_matching()` (L56)

### `tests/unit/test_buffer.py` — 95 lines

- `test_buffer_initialization()` (L6)
- `test_buffer_add_entry_sliding_window()` (L14)
- `test_buffer_get_last_role()` (L30)
- `test_buffer_clear()` (L41)
- `test_buffer_session_logging()` (L52)
- `test_buffer_concurrency()` (L75)

## `tools/`

### `tools/check_state.py` — 128 lines

Checks that the requirement documents still hold together.

- `read()` (L33)
- `decision_records()` (L38)
- `main()` (L47)

### `tools/gen_filemap.py` — 152 lines

Generates FILEMAP.md: a mechanical inventory of the repo's Python surface.

- `find_python_files()` (L35)
- `summarize()` (L47)
- `render()` (L81)
- `main()` (L124)

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

**75 Python files.**

## `fixtures/asr/results/20260817-model-swap/`

### `fixtures/asr/results/20260817-model-swap/E7_release_models.py` — 62 lines

How much does release_models() actually free for the new backend, and does the pipeline work?

*No top-level classes or functions.*

## `src/`

### `src/advisors.py` — 496 lines

Advisor backends: retrieval, generation, and the routing between them.

- `class Retrieval` (L92)
- `class Advice` (L107)
- `class AdvisorBackend` (L116)
  - `analyze_dialogue()`
- `chat_endpoint()` (L136)
- `class LlmAdvisor` (L153)
  - `_post()`
  - `complete()`
- `rehearse()` (L221)
- `build_messages()` (L251)
- `is_pass()` (L264)
- `class _Liveness` (L273)
- `class AdvisorPipeline` (L290)
  - `submit()`
  - `_retrieve()`
  - `_llm_loop()`
  - `_run_one()`
  - `_emit()`
  - `shutdown()`
  - `status()`
- `build_advisor()` (L462)

### `src/app.py` — 1415 lines

- `mute_event_loop_closed()` (L14)
- `read_host_header()` (L43)
- `prepare_environment()` (L87)
- `begin_capture()` (L96)
- `clear_failure()` (L141)
- `end_capture()` (L158)
- `engine()` (L168)
- `get_global_access_code()` (L176)
- `choose_folder()` (L315)
- `points_off_machine()` (L334)
- `render_model_availability()` (L344)
- `render_configure()` (L388)
- `render_archive()` (L541)
- `render_readiness()` (L748)
- `_input_device_names()` (L790)
- `_default_input_name()` (L806)
- `_render_microphone_picker()` (L815)
- `_advisor_html()` (L930)
- `_advisor_status_html()` (L966)
- `_transcript_html()` (L1003)
- `render_last_session()` (L1034)
- `render_preflight()` (L1068)
- `_running_live_panes()` (L1345)

### `src/asr_eval.py` — 143 lines

Pure helpers for ASR bake-off fixtures and scoring.

- `assert_fixture_path_allowed()` (L19)
- `write_wav_mono_int16()` (L28)
- `load_wav_mono_float32()` (L41)
- `iter_fixture_wavs()` (L86)
- `score_nonspeech_texts()` (L99)
- `looks_traditional_chinese()` (L131)

### `src/audio_archive.py` — 194 lines

Durable per-track WAV capture. stdlib `wave`, a queue, and a writer thread.

- `track_path()` (L58)
- `class TrackWriter` (L63)
  - `open()`
  - `write()`
  - `close()`
  - `_writer_loop()`
  - `duration_s()`
  - `summary()`

### `src/audio_devices.py` — 83 lines

Input-device enumeration. Nothing here loads a model or opens a stream.

- `list_input_devices()` (L25)
- `default_input_name()` (L43)
- `resolve_input_device()` (L55)

### `src/bootstrap.py` — 800 lines

Configuration, path derivation and startup readiness.

- `class Field` (L44)
- `read_settings()` (L161)
- `_quote()` (L181)
- `render_env()` (L191)
- `write_settings()` (L217)
- `delete_settings()` (L252)
- `normalize_root()` (L268)
- `derive_paths()` (L282)
- `resolve_archive_dir()` (L296)
- `is_configured()` (L304)
- `missing_required()` (L309)
- `format_bytes()` (L316)
- `_tree_stats()` (L325)
- `inspect_root()` (L353)
- `_is_writable()` (L369)
- `fingerprint()` (L391)
- `enforce_offline()` (L406)
- `apply_environment()` (L440)
- `applied_fingerprint()` (L465)
- `needs_restart()` (L470)
- `begin_boot()` (L503)
- `invalidate_boot()` (L511)
- `current_boot_id()` (L523)
- `get_readiness()` (L528)
- `set_readiness()` (L533)
- `is_ready()` (L543)
- `progress_snapshot()` (L547)
- `_record_progress()` (L553)
- `resolved_model()` (L565)
- `required_repos()` (L570)
- `essential_repos()` (L580)
- `weights_present()` (L607)
- `repo_cache_dir()` (L627)
- `expected_repo_bytes()` (L640)
- `_watch_repo_bytes()` (L667)
- `download_models()` (L692)
- `index_status()` (L753)
- `_host_only()` (L776)
- `is_local_host()` (L787)

### `src/build_index.py` — 115 lines

- `build_knowledge_index()` (L23)

### `src/dialogue_buffer.py` — 212 lines

- `_empty_slot()` (L18)
- `class DialogueBuffer` (L22)
  - `start_session()`
  - `finish_session()`
  - `_append()`
  - `add_entry()`
  - `set_advice()`
  - `get_advice_slots()`
  - `get_full_dialogue()`
  - `get_formatted_dialogue()`
  - `get_last_role()`
  - `clear()`

### `src/diarize.py` — 420 lines

Voice separation: which lines share a speaker, and a proposal for who they are.

- `label_for()` (L90)
- `available()` (L95)
- `install()` (L104)
- `is_cloud_pipeline()` (L125)
- `_pinned_python()` (L160)
- `_run_pinned()` (L168)
- `run()` (L206)
- `_annotation_from()` (L283)
- `_auth_hint()` (L304)
- `speaker_at()` (L313)
- `candidate_names()` (L350)
- `propose_titles()` (L366)
- `render_table()` (L395)

### `src/global_state.py` — 504 lines

- `class GlobalState` (L33)
  - `_init_once()`
  - `warm_up()`
  - `set_microphone()`
  - `start_recording()`
  - `_start_system_audio()`
  - `_stop_system_audio()`
  - `stop_recording()`
  - `release_engine()`
  - `_close_session_record()`
  - `_atexit_stop()`
  - `_publish_advice()`
  - `_local_rag_worker_loop()`
- `get_global_state()` (L503)

### `src/knowledge_store.py` — 207 lines

The knowledge index, in Qdrant. One API for the local collection and a remote one (V29).

- `describe_target()` (L54)
- `open_client()` (L60)
- `write_index()` (L88)
- `read_manifest()` (L133)
- `cosine_pinned()` (L163)
- `status()` (L168)
- `_close()` (L202)

### `src/local_advisor.py` — 192 lines

- `is_worth_embedding()` (L30)
- `class LocalAdvisor` (L42)
  - `open()`
  - `close()`
  - `analyze_dialogue()`

### `src/model_search.py` — 203 lines

Whether a configured model still exists, and a prompt for finding a replacement.

- `disqualified_reason()` (L78)
- `family_for()` (L87)
- `availability()` (L110)
- `build_search_prompt()` (L153)
- `replacement_advice()` (L193)

### `src/postmeeting.py` — 262 lines

The post-meeting prompt appended to every session transcript.

- `build_prompt()` (L49)
- `render_block()` (L172)
- `extract()` (L189)
- `audio_paths()` (L202)
- `list_sessions()` (L219)
- `read_prompt()` (L256)

### `src/relisten.py` — 380 lines

Re-transcribe a retained meeting from its audio, and fill in what the live path dropped.

- `default_model()` (L62)
- `relistened_path()` (L74)
- `read_wav_mono_int16()` (L80)
- `segment()` (L99)
- `_join()` (L145)
- `vocabulary_from()` (L150)
- `track_starts()` (L183)
- `run()` (L213)
- `_render()` (L323)

### `src/system_audio.py` — 226 lines

Lifecycle of the system-audio capture helper, and which backend a machine can use.

- `_macos_version()` (L42)
- `tap_capability()` (L50)
- `blackhole_device()` (L71)
- `available_backend()` (L85)
- `reinitialize_portaudio()` (L101)
- `wait_for_device()` (L116)
- `class SystemAudioTap` (L149)
  - `start()`
  - `stop()`

### `src/text_filters.py` — 109 lines

Pure text filters applied to ASR output before it reaches the dialogue buffer.

- `normalize_phrase()` (L63)
- `is_acceptable()` (L72)

### `src/transcriber.py` — 565 lines

- `resolve_backend()` (L21)
- `release_models()` (L78)
- `class Transcriber` (L134)
  - `find_device_index()`
  - `warm_model()`
  - `_audio_callback()`
  - `get_rms()`
  - `_processing_thread()`
  - `_inference_thread()`
  - `feed_wav()`
  - `set_device()`
  - `start()`
  - `stop()`

### `src/voice_gate.py` — 155 lines

Decide whether a segment contains speech, before it costs a decode.

- `available()` (L53)
- `_load()` (L62)
- `has_speech()` (L92)
- `settings_from()` (L116)
- `is_live()` (L132)

## `tests/unit/`

### `tests/unit/test_advisor.py` — 252 lines

The retrieval backend: what it scores, what it serves, and what it says when it cannot.

- `class _StubEmbedder` (L37)
  - `encode()`
- `local_index()` (L50)
- `_build()` (L60)
- `test_the_advisor_loads_the_model_the_collection_names()` (L67)
- `test_a_match_above_the_threshold_is_served()` (L80)
- `test_a_below_threshold_query_still_returns_its_score()` (L92)
- `test_a_repeated_match_is_suppressed_for_display_but_still_scored()` (L108)
- `test_a_missing_index_reports_why_rather_than_returning_nothing()` (L122)
- `test_a_collection_with_the_wrong_distance_metric_refuses_to_serve()` (L135)
- `test_an_empty_collection_says_it_is_empty_rather_than_missing()` (L161)
- `test_filler_shorter_than_ten_characters_is_not_scored()` (L180)
- `test_closing_releases_the_lock_and_reopening_keeps_the_loaded_model()` (L194)
- `test_the_serve_threshold_is_the_one_the_router_uses()` (L214)
- `test_a_short_chinese_question_is_not_filler()` (L222)
- `test_genuine_filler_is_still_dropped_in_both_scripts()` (L236)
- `test_latin_behaviour_is_unchanged()` (L241)
- `test_the_weighting_is_declared_a_heuristic_not_a_measurement()` (L247)

### `tests/unit/test_advisor_backends.py` — 556 lines

Fanning an utterance out to the two advisor slots, and the transport to the generative one.

- `class _StubRetriever` (L34)
  - `analyze_dialogue()`
- `class _StubLlm` (L44)
  - `complete()`
- `_collector()` (L65)
- `_wait_for()` (L76)
- `test_both_slots_receive_the_same_utterance()` (L92)
- `test_a_high_scoring_match_does_not_suppress_the_generative_slot()` (L108)
- `test_a_low_scoring_utterance_still_reaches_the_generative_slot()` (L123)
- `test_a_broken_index_does_not_change_what_the_generative_slot_receives()` (L138)
- `test_the_retrieved_cue_is_gated_by_its_own_threshold_and_only_its_own()` (L157)
- `test_no_grounding_is_attached_to_the_request()` (L170)
- `test_llm_only_sends_unconditionally_because_the_prompt_is_the_threshold()` (L188)
- `test_submit_returns_before_the_remote_call_finishes()` (L206)
- `test_a_newer_utterance_replaces_a_queued_one()` (L219)
- `test_a_declined_generation_is_reported_as_declined_not_as_silence()` (L246)
- `test_an_unreachable_host_is_an_error_state_with_the_reason()` (L260)
- `test_a_retrieval_backend_that_raises_does_not_take_the_session_down()` (L273)
- `test_the_score_reaches_the_status_even_when_nothing_matched()` (L285)
- `test_the_system_prompt_permits_returning_nothing()` (L298)
- `test_declining_is_recognised_through_the_punctuation_models_add()` (L309)
- `test_a_real_answer_is_not_mistaken_for_a_decline()` (L313)
- `test_both_shapes_of_base_url_reach_the_same_endpoint()` (L325)
- `test_the_credential_is_sent_as_a_bearer_token_and_the_reply_is_unwrapped()` (L331)
- `test_an_unreachable_endpoint_returns_an_error_rather_than_raising()` (L353)
- `test_an_unrecognised_response_shape_is_reported_not_swallowed()` (L363)
- `stub_llm_server()` (L383)
- `test_a_real_round_trip_over_a_socket()` (L422)
- `test_a_host_that_does_not_answer_in_time_is_an_error_not_a_hang()` (L437)
- `test_neither_slot_armed_builds_nothing_at_all()` (L454)
- `test_arming_the_llm_without_a_base_url_leaves_the_slot_empty()` (L459)
- `test_the_factory_reuses_a_retriever_rather_than_reloading_the_model()` (L463)
- `test_the_llm_slot_is_built_from_a_host_and_a_credential_only()` (L473)
- `test_the_rehearsal_uses_the_production_prompt()` (L493)
- `test_a_decline_is_reported_as_a_decline_and_not_as_a_failure()` (L506)
- `test_an_answer_comes_back_verbatim_and_unjudged()` (L517)
- `test_a_dead_endpoint_is_reported_per_question_rather_than_aborting()` (L527)
- `test_blank_lines_are_not_sent()` (L537)
- `test_no_questions_is_no_calls()` (L546)
- `test_the_default_questions_include_something_that_should_be_declined()` (L552)

### `tests/unit/test_analyze_soak_contention.py` — 116 lines

Unit tests for tools/analyze_soak_contention.py (no audio, no devices, no NPU).

- `segment_line()` (L24)
- `accepted_line()` (L29)
- `write()` (L33)
- `parse()` (L39)
- `test_text_attaches_to_the_segment_it_followed()` (L46)
- `test_a_dropped_segment_keeps_none_and_does_not_steal_the_next_text()` (L53)
- `test_text_does_not_cross_roles()` (L64)
- `test_a_matching_ms_is_required_so_a_later_line_cannot_be_claimed()` (L71)
- `test_shifting_preserves_every_window_length()` (L80)
- `test_shifting_can_change_the_labels()` (L89)
- `test_a_shift_of_exactly_the_span_is_a_no_op()` (L101)
- `test_median_ratio_withholds_itself_when_a_group_is_too_small()` (L113)

### `tests/unit/test_app_screens.py` — 802 lines

Screen-routing tests for `src/app.py`, driven through Streamlit's own app-test harness.

- `app_env()` (L40)
- `configure()` (L74)
- `assert_nothing_heavy_was_imported()` (L82)
- `test_an_undeterminable_origin_is_treated_as_remote_and_says_so()` (L90)
- `test_an_unconfigured_local_machine_gets_a_blank_form_not_an_error()` (L104)
- `test_credentials_render_masked_and_their_dependants_are_disabled()` (L119)
- `test_saving_is_blocked_until_the_one_required_field_is_filled()` (L139)
- `test_the_folder_dialog_fills_the_field_it_belongs_to()` (L155)
- `test_reset_through_the_ui_deletes_the_env_file_and_nothing_else()` (L178)
- `test_a_configured_machine_reaches_preflight_with_nothing_loaded()` (L203)
- `test_local_speaker_mode_has_no_start_capture()` (L235)
- `test_the_retrieval_toggle_cannot_be_armed_without_an_index()` (L255)
- `_grant_local_origin_only()` (L272)
- `test_the_generative_row_is_hidden_entirely_until_a_host_is_configured()` (L284)
- `test_arming_the_generative_advisor_warns_that_its_output_is_unverified()` (L300)
- `test_a_local_llm_host_is_not_warned_about_as_if_it_left_the_machine()` (L325)
- `test_an_off_machine_llm_host_says_the_transcript_leaves()` (L340)
- `test_archive_mode_loads_nothing()` (L353)
- `test_archive_mode_still_exports_the_storage_root()` (L373)
- `test_an_empty_archive_is_a_state_not_a_blank_page()` (L393)
- `_archive_with()` (L410)
- `test_relisten_is_disabled_when_no_audio_was_retained()` (L421)
- `test_relisten_is_offered_when_the_audio_is_there()` (L438)
- `test_relisten_survives_an_unmet_precondition_of_speaker_separation()` (L456)
- `test_speaker_separation_is_off_until_asked_for_even_when_installed()` (L483)
- `test_speaker_separation_states_its_cost_before_it_is_installed()` (L502)
- `test_speaker_separation_asks_for_the_token_only_once_it_is_installed()` (L525)
- `test_the_labels_are_declared_anonymous_before_anything_runs()` (L548)
- `test_a_remote_device_before_start_gets_a_waiting_state()` (L569)
- `test_moving_the_storage_root_in_a_live_process_demands_a_restart()` (L587)
- `_fake_devices()` (L609)
- `test_the_microphone_dropdown_defaults_to_following_the_system()` (L623)
- `test_a_stored_microphone_that_is_gone_is_shown_rather_than_dropped()` (L647)
- `test_the_participant_track_is_not_selectable()` (L668)
- `test_a_device_appearing_does_not_reset_the_operators_choice()` (L683)
- `test_a_selected_device_that_goes_away_is_kept_and_flagged()` (L713)
- `test_the_archive_is_closed_while_the_engine_is_busy()` (L733)
- `test_the_archive_opens_once_the_engine_has_been_released()` (L753)
- `test_a_failed_start_can_be_retried_in_place()` (L767)
- `test_retrying_returns_to_idle_so_the_promise_of_idle_stays_true()` (L788)

### `tests/unit/test_asr_eval.py` — 78 lines

Unit tests for ASR bake-off helpers (tmp_path only — no real fixtures/asr audio).

- `test_write_load_roundtrip()` (L16)
- `test_resample_halves_length()` (L29)
- `test_refuse_private_trees()` (L39)
- `test_iter_fixture_wavs()` (L47)
- `test_score_nonspeech_texts_separates_model_from_filter()` (L59)
- `test_looks_traditional_chinese()` (L75)

### `tests/unit/test_audio_archive.py` — 319 lines

Durable capture: what lands on disk, and what happens when it cannot.

- `_block()` (L26)
- `_read()` (L30)
- `_drain()` (L41)
- `test_what_goes_in_is_what_comes_out()` (L47)
- `test_the_header_carries_the_final_length_after_close()` (L67)
- `test_the_callback_is_never_blocked_by_the_disk()` (L84)
- `test_a_full_queue_drops_and_counts_rather_than_blocking_or_lying()` (L102)
- `test_the_start_time_is_the_first_frame_not_the_file_creation()` (L128)
- `test_a_file_that_cannot_be_opened_reports_why_and_does_not_raise()` (L148)
- `test_an_unwritten_track_reports_zero_rather_than_a_plausible_duration()` (L164)
- `test_filenames_pair_with_the_transcript_by_session_id()` (L177)
- `test_two_tracks_are_two_files_and_are_never_mixed()` (L190)
- `stub_transcriber()` (L213)
- `test_the_archive_is_tapped_upstream_of_voice_detection()` (L231)
- `test_stopping_closes_the_wav_before_waiting_on_the_npu()` (L254)
- `test_an_unarmed_session_writes_nothing_and_creates_nothing()` (L293)
- `test_a_writer_that_cannot_open_leaves_capture_running()` (L306)

### `tests/unit/test_bootstrap.py` — 501 lines

Unit tests for the configuration bootstrap.

- `env_file()` (L16)
- `blank_settings()` (L20)
- `test_round_trip_preserves_awkward_values()` (L26)
- `test_blank_field_survives_as_blank_not_the_string_none()` (L44)
- `test_write_drops_keys_the_form_does_not_own()` (L57)
- `test_hf_home_is_derived_not_taken_from_the_caller()` (L69)
- `test_failure_between_temp_write_and_replace_leaves_the_original_intact()` (L81)
- `test_one_root_produces_the_fixed_layout()` (L108)
- `test_equivalent_roots_normalise_to_byte_identical_paths()` (L114)
- `test_tilde_expands_to_the_same_place_as_the_absolute_form()` (L132)
- `test_empty_root_derives_nothing_rather_than_the_filesystem_root()` (L137)
- `test_archive_directory_falls_back_to_the_derived_path()` (L142)
- `test_missing_file_yields_a_blank_form()` (L154)
- `test_empty_file_yields_a_blank_form()` (L160)
- `test_file_without_the_required_key_names_what_is_missing()` (L167)
- `test_bare_key_with_no_value_reads_as_blank()` (L175)
- `test_reset_deletes_only_the_env_file()` (L185)
- `test_inspect_root_reports_an_existing_cache()` (L201)
- `test_cache_size_counts_each_byte_once_despite_symlinks()` (L216)
- `test_inspect_root_of_a_nonexistent_path_reports_empty_and_writable()` (L240)
- `test_changing_a_baked_in_setting_requires_a_restart()` (L248)
- `test_a_revoked_boot_cannot_overwrite_restart_required()` (L270)
- `test_asr_model_warning_names_a_restart_not_a_live_rewarm()` (L288)
- `test_expected_repo_bytes_passes_a_timeout_and_returns_zero_on_failure()` (L296)
- `test_watch_repo_bytes_reports_growth_not_preexisting_cache()` (L312)
- `test_offline_is_entered_after_configuration_not_at_boot()` (L344)
- `test_required_repos_falls_back_to_the_documented_defaults()` (L361)
- `test_default_model_names_are_fully_qualified_repository_ids()` (L372)
- `test_the_download_filter_excludes_formats_this_runtime_cannot_load()` (L383)
- `test_only_the_asr_model_can_block_startup()` (L396)
- `test_is_local_host()` (L426)
- `test_is_local_host_treats_an_unusable_value_as_remote()` (L430)
- `test_enforce_offline_patches_the_loaded_library_not_only_the_environment()` (L441)
- `test_enforce_offline_is_safe_when_the_library_was_never_loaded()` (L470)
- `test_every_settings_field_appears_in_the_env_template()` (L480)
- `test_the_template_does_not_claim_a_count_that_can_drift()` (L496)

### `tests/unit/test_buffer.py` — 379 lines

The dialogue buffer, and the advisor slots it now keeps apart (V24).

- `test_buffer_initialization()` (L18)
- `test_buffer_add_entry_sliding_window()` (L27)
- `test_buffer_get_last_role()` (L43)
- `test_buffer_clear()` (L54)
- `test_a_generated_reply_does_not_overwrite_a_retrieved_cue()` (L68)
- `test_an_unknown_source_raises_rather_than_landing_somewhere()` (L84)
- `test_the_session_log_records_which_kind_produced_each_line()` (L90)
- `test_an_in_flight_slot_shows_but_is_not_logged()` (L103)
- `test_buffer_session_logging()` (L110)
- `test_buffer_concurrency()` (L133)
- `class _FakeState` (L158)
  - `get_full_dialogue()`
- `_transcript()` (L167)
- `test_each_turn_is_its_own_block_not_a_newline()` (L180)
- `test_transcript_text_is_escaped()` (L197)
- `test_an_empty_buffer_says_it_is_waiting_rather_than_rendering_nothing()` (L209)
- `test_only_the_most_recent_turns_are_rendered()` (L214)
- `_advisor_renderers()` (L223)
- `_slot()` (L236)
- `test_the_three_kinds_are_rendered_as_three_distinct_cards()` (L242)
- `test_advisor_text_is_escaped()` (L260)
- `test_an_empty_advisor_pane_says_it_is_waiting()` (L269)
- `test_a_live_index_that_matched_nothing_reads_differently_from_a_dead_one()` (L276)
- `test_an_llm_that_declined_reads_differently_from_one_that_failed()` (L289)
- `test_no_advisor_armed_is_stated_rather_than_left_blank()` (L301)
- `test_the_header_says_audio_was_retained_and_where()` (L309)
- `test_the_header_says_so_when_nothing_was_kept()` (L325)
- `test_the_header_carries_a_precise_start_so_timestamps_convert_to_offsets()` (L334)
- `test_the_outcome_is_appended_with_durations_and_any_loss()` (L347)
- `test_a_session_that_never_finishes_still_says_it_was_armed()` (L371)

### `tests/unit/test_diarize.py` — 258 lines

Voice separation: the label is a fact, the name is a proposal, and they stay apart.

- `test_labels_are_numbered_and_carry_no_identity()` (L19)
- `test_importing_this_module_still_loads_nothing()` (L25)
- `test_running_without_it_installed_says_so_rather_than_raising()` (L48)
- `test_a_line_inside_a_turn_takes_that_voice()` (L60)
- `test_a_line_just_off_a_boundary_still_matches()` (L66)
- `test_a_line_in_a_long_silence_matches_nothing()` (L73)
- `test_a_guess_comes_with_the_evidence_and_the_timestamp()` (L89)
- `test_a_label_with_no_evidence_gets_no_guess()` (L101)
- `test_one_row_per_label_in_first_appearance_order()` (L107)
- `test_the_table_states_that_nothing_has_been_applied()` (L112)
- `test_names_the_transcript_contains_but_no_voice_claims_are_listed_separately()` (L122)
- `test_candidate_names_are_titles_a_hearing_actually_uses()` (L130)
- `test_ordinary_prose_does_not_become_a_candidate_name()` (L137)
- `test_a_preceding_particle_is_not_absorbed_into_the_name()` (L142)
- `test_a_compound_surname_survives()` (L150)
- `test_an_unknown_surname_produces_no_guess_rather_than_a_wrong_one()` (L154)
- `class _Annotation` (L166)
  - `itertracks()`
- `class _DiarizeOutput` (L175)
- `test_the_four_x_dataclass_is_unwrapped()` (L183)
- `test_the_overlapping_field_is_the_fallback_not_the_default()` (L191)
- `test_a_three_x_annotation_still_works()` (L199)
- `test_something_with_no_diarization_is_reported_rather_than_crashing()` (L204)
- `test_a_cloud_pipeline_is_refused_before_it_runs()` (L210)
- `test_a_local_pipeline_is_allowed()` (L229)
- `test_an_unreadable_config_does_not_block_a_good_model()` (L242)
- `test_the_ungated_alternative_is_named_in_the_gated_failure()` (L254)

### `tests/unit/test_global_state_locking.py` — 100 lines

Warm-up must not hold the lock that singleton construction needs.

- `class SlowTranscriber` (L21)
  - `find_device_index()`
  - `resolve_input_device()`
- `fresh_singleton()` (L44)
- `test_warm_up_does_not_block_singleton_construction()` (L59)
- `test_the_construction_lock_and_the_state_lock_are_different_objects()` (L87)
- `test_start_recording_refuses_before_warm_up()` (L93)

### `tests/unit/test_knowledge_store.py` — 229 lines

The Qdrant knowledge collection, and the two migrations traps that fail silently.

- `_vector()` (L23)
- `store()` (L29)
- `_build()` (L37)
- `test_a_built_collection_reports_its_chunks_model_and_metric()` (L44)
- `test_the_distance_metric_is_cosine_and_that_is_read_back_not_assumed()` (L57)
- `test_a_collection_built_with_the_wrong_metric_is_refused_rather_than_scored()` (L72)
- `test_the_embedding_model_is_stored_in_the_collection()` (L93)
- `test_rebuilding_replaces_rather_than_appends()` (L101)
- `test_a_missing_index_says_how_to_build_one()` (L111)
- `test_a_leftover_pickle_is_reported_as_rebuild_me_not_as_never_built()` (L117)
- `test_the_local_collection_lives_beside_the_documents_not_under_the_storage_root()` (L126)
- `test_a_remote_url_selects_the_remote_client_without_a_second_code_path()` (L132)
- `test_a_second_reader_is_told_the_index_is_locked_rather_than_a_generic_failure()` (L140)
- `test_the_compiler_writes_a_queryable_collection()` (L166)
- `test_the_compiler_reports_a_locked_index_instead_of_failing_obscurely()` (L199)

### `tests/unit/test_measure_asr_latency.py` — 52 lines

Unit tests for tools/measure_asr_latency.py helpers (tmp_path only).

- `test_extract_and_summarise()` (L14)
- `test_cli_writes_md()` (L32)

### `tests/unit/test_measure_overlap_turns.py` — 157 lines

Unit tests for tools/measure_overlap_turns.py (tmp_path only).

- `test_merge_unions_overlapping_and_touching_runs()` (L29)
- `test_intersect_finds_only_genuine_simultaneity()` (L38)
- `_turns_file()` (L51)
- `test_load_turns_parses_times_as_floats()` (L60)
- `test_describe_fixture_measures_overlap_as_seconds_not_pairs()` (L67)
- `test_describe_fixture_reports_no_overlap_when_speakers_take_turns()` (L85)
- `_line()` (L97)
- `test_contention_requires_two_roles()` (L101)
- `test_contention_marks_both_sides_of_a_cross_role_collision()` (L111)
- `test_solo_lines_are_not_contended_when_windows_do_not_meet()` (L120)
- `test_early_break_does_not_miss_a_later_overlapping_window()` (L129)
- `test_zero_length_window_never_contends()` (L144)
- `test_stats_reports_n_median_p95_max()` (L154)

### `tests/unit/test_microphone_selection.py` — 155 lines

Microphone selection (R26): resolve by name, override the default, never reload the model.

- `devices()` (L29)
- `test_empty_preference_follows_the_system_default()` (L46)
- `test_exact_name_wins_over_substring()` (L51)
- `test_substring_match_survives_a_renamed_device()` (L61)
- `test_unmatched_preference_resolves_to_nothing_not_to_the_default()` (L68)
- `test_no_devices_and_no_default_is_reported_not_guessed()` (L77)
- `class _FakeTranscriber` (L85)
- `test_set_device_changes_only_the_device_fields()` (L97)
- `test_set_device_refuses_while_running()` (L111)
- `test_set_device_to_a_missing_device_reports_it()` (L119)
- `test_mic_device_is_sticky_and_round_trips()` (L129)
- `test_mic_device_does_not_force_a_restart()` (L136)
- `test_mic_device_is_absent_from_a_fresh_env_as_empty_not_missing()` (L150)

### `tests/unit/test_model_search.py` — 219 lines

Whether a configured model still exists, and what the operator is handed when it does not.

- `_stub_hub()` (L19)
- `_no_cache()` (L31)
- `_cached()` (L37)
- `test_the_family_rule_matches_what_resolve_backend_dispatches_on()` (L45)
- `test_a_disqualified_vendor_id_gets_no_backend_of_its_own()` (L52)
- `test_the_removed_family_is_refused_by_name_rather_than_failing_inside_mlx()` (L65)
- `test_the_whisper_family_records_the_files_the_metadata_does_not_expose()` (L82)
- `test_the_requirement_is_no_longer_labelled_a_guess()` (L97)
- `test_a_downloaded_model_needs_no_network_and_outranks_everything()` (L108)
- `test_a_gate_is_a_failure_not_a_warning()` (L119)
- `test_a_missing_repository_is_reported_as_missing()` (L131)
- `test_an_unreachable_hub_is_unknown_rather_than_missing()` (L141)
- `test_availability_can_be_asked_not_to_touch_the_network()` (L152)
- `test_an_empty_model_id_is_answered_rather_than_queried()` (L160)
- `test_the_prompt_states_requirements_rather_than_naming_candidates()` (L167)
- `test_the_prompt_carries_the_constraint_no_hub_field_expresses()` (L177)
- `test_the_prompt_warns_that_the_trap_is_invisible_in_metadata()` (L187)
- `test_the_prompt_asks_the_agent_to_separate_verified_from_assumed()` (L194)
- `test_the_prompt_does_not_claim_its_own_search_is_complete()` (L200)
- `test_an_empty_model_id_still_produces_a_usable_prompt()` (L208)
- `test_the_durable_answer_points_at_the_bake_off_not_at_a_list()` (L216)

### `tests/unit/test_postmeeting.py` — 336 lines

The post-meeting prompt: what an outside agent is told, and what it is warned about.

- `test_the_three_deliverables_are_named_in_order()` (L24)
- `test_the_line_format_is_explained()` (L34)
- `test_the_two_roles_are_explained_as_two_unmixed_tracks()` (L41)
- `test_the_advisor_lines_are_flagged_as_not_speech()` (L49)
- `test_the_known_failure_modes_are_named_with_their_measurements()` (L58)
- `test_speaker_attribution_is_declared_absent_and_forbidden()` (L70)
- `test_the_rules_forbid_inventing_and_forbid_answering()` (L78)
- `test_retained_audio_is_named_rather_than_alluded_to()` (L85)
- `test_no_audio_is_stated_as_a_limit_on_the_answer()` (L97)
- `test_the_block_is_delimited_by_a_stable_marker()` (L105)
- `test_extracting_from_a_file_without_the_marker_returns_nothing()` (L116)
- `test_audio_is_resolved_by_session_id_not_by_sitting_next_to_the_transcript()` (L120)
- `test_building_the_prompt_touches_no_disk_and_needs_no_model()` (L129)
- `class _FakeSt` (L148)
  - `_record()`
  - `code()`
  - `text()`
- `_last_session_renderer()` (L167)
- `_session()` (L189)
- `test_a_finished_session_names_its_transcript_and_the_way_out()` (L194)
- `test_the_extraction_line_is_the_marker_the_file_actually_carries()` (L205)
- `test_a_session_written_before_the_prompt_existed_says_so()` (L216)
- `test_retained_audio_is_named_in_the_panel_too()` (L225)
- `test_nothing_is_shown_before_the_first_session()` (L234)
- `test_the_panel_reads_history_rather_than_the_engine()` (L240)
- `test_the_review_pass_is_not_asked_to_place_participant_titles()` (L255)
- `test_the_transcript_rule_stays_strict()` (L271)
- `test_the_relistened_variant_does_not_promise_wall_clock_or_a_millisecond_header()` (L288)
- `test_the_relistened_variant_does_not_send_the_agent_looking_for_advisor_lines()` (L298)
- `test_the_relistened_variant_states_its_own_flush_not_the_live_one()` (L304)
- `test_the_relistened_variant_says_simplified_characters_are_expected()` (L312)
- `test_the_relistened_variant_does_not_claim_material_is_unrecoverable()` (L320)
- `test_both_variants_still_forbid_inventing_and_relabelling()` (L330)

### `tests/unit/test_queue_wait_instrumentation.py` — 210 lines

Queue dwell reporting, and the log-format contract it must not break.

- `test_segment_line_is_invisible_to_every_transcribed_in_parser()` (L57)
- `test_transcribed_in_line_still_parses_and_carries_only_the_text()` (L63)
- `stub_transcriber()` (L74)
- `_run_inference_thread_once()` (L92)
- `test_dwell_is_reported_and_reflects_the_time_actually_waited()` (L121)
- `test_segment_line_is_emitted_even_when_the_filter_drops_the_text()` (L139)
- `test_appended_lock_fields_do_not_break_the_soak_parser()` (L154)
- `test_lock_wait_is_measured_when_the_accelerator_is_already_held()` (L165)
- `test_uncontended_call_reports_no_lock_wait()` (L201)

### `tests/unit/test_rag_gate.py` — 257 lines

Arming an advisor slot is a per-meeting choice — disarming it must actually stop it.

- `GlobalState()` (L24)
- `_run_worker_briefly()` (L39)
- `_started()` (L50)
- `test_disarming_retrieval_leaves_no_advisor_at_all()` (L65)
- `test_the_worker_does_nothing_when_no_slot_is_armed()` (L78)
- `test_an_armed_pipeline_receives_the_utterance_and_the_bounded_transcript()` (L88)
- `test_only_the_participant_track_reaches_the_advisor()` (L106)
- `test_published_advice_lands_in_the_slot_its_source_names()` (L119)
- `_armed()` (L137)
- `test_arming_retention_gives_each_track_its_own_file()` (L147)
- `test_an_unarmed_session_passes_no_path_at_all()` (L165)
- `test_arming_without_a_directory_records_nothing_and_says_so()` (L174)
- `test_the_session_record_is_told_what_was_armed()` (L186)
- `test_stopping_writes_the_outcome_including_dropped_blocks()` (L197)
- `test_every_session_ends_with_a_post_meeting_prompt()` (L224)
- `test_the_prompt_names_the_retained_audio_when_there_is_some()` (L236)
- `test_the_prompt_says_so_when_nothing_was_kept()` (L250)

### `tests/unit/test_relisten.py` — 380 lines

Re-listening: segmentation, the timebase, the vocabulary, and what the output declares.

- `class _Vad` (L26)
  - `is_speech()`
- `_tone()` (L33)
- `_silence()` (L37)
- `_write()` (L41)
- `test_what_retention_wrote_is_what_this_reads_back()` (L51)
- `test_a_file_that_is_not_mono_sixteen_bit_is_refused_rather_than_converted()` (L62)
- `test_a_missing_file_is_reported_rather_than_raising()` (L78)
- `test_a_pause_shorter_than_the_flush_no_longer_splits_a_sentence()` (L84)
- `test_a_real_gap_still_separates_two_utterances()` (L94)
- `test_unbroken_speech_is_capped_rather_than_growing_without_bound()` (L103)
- `test_noise_shorter_than_the_floor_is_not_an_utterance()` (L112)
- `test_a_segment_reports_where_in_the_track_it_started()` (L117)
- `test_each_track_start_is_read_back_so_the_merge_is_not_a_guess()` (L147)
- `test_a_transcript_without_an_audio_section_yields_no_starts()` (L159)
- `test_the_vocabulary_comes_from_this_meeting_not_the_knowledge_base()` (L167)
- `test_the_vocabulary_excludes_the_post_meeting_prompt()` (L178)
- `test_an_unreadable_transcript_yields_no_vocabulary_rather_than_raising()` (L191)
- `stub_asr()` (L198)
- `test_a_run_writes_a_new_file_and_leaves_the_live_transcript_alone()` (L232)
- `test_the_harvested_vocabulary_is_handed_to_the_decoder_as_its_prompt()` (L247)
- `test_biasing_can_be_declined_and_then_nothing_is_prepended()` (L264)
- `test_the_output_says_when_the_tracks_could_not_be_aligned()` (L277)
- `test_two_tracks_are_merged_on_their_own_recorded_starts()` (L291)
- `test_the_output_declares_that_speakers_were_not_separated()` (L310)
- `test_the_output_carries_the_same_post_meeting_prompt()` (L324)
- `test_a_session_with_no_audio_is_refused_with_a_reason()` (L337)
- `test_an_unreadable_track_is_reported_per_track_and_does_not_abort_the_rest()` (L346)
- `test_the_appended_prompt_describes_the_relistened_file_not_the_live_one()` (L362)

### `tests/unit/test_soak_capture_dwell.py` — 90 lines

Unit tests for the queue-dwell report in tools/soak_capture.py (no audio, no devices).

- `line()` (L28)
- `test_parses_role_queue_and_inference_from_a_real_line()` (L35)
- `test_ignores_the_transcribed_line_so_the_denominator_stays_every_segment()` (L46)
- `test_survives_a_truncated_final_line()` (L54)
- `test_overlapping_windows_on_different_roles_are_contended()` (L61)
- `test_same_role_overlap_is_not_contention()` (L68)
- `test_disjoint_windows_are_solo_even_on_different_roles()` (L76)
- `test_contention_is_read_from_inference_not_from_the_dwell()` (L83)

### `tests/unit/test_system_audio.py` — 209 lines

Participant-track backend selection and helper lifecycle (R1, R5, R6, R7, R25, R39).

- `never_touch_portaudio()` (L23)
- `fake_helper()` (L30)
- `test_capability_is_decided_without_looking_for_the_device()` (L55)
- `test_a_missing_helper_is_a_reason_not_a_crash()` (L66)
- `test_a_helper_that_is_not_executable_is_reported_distinctly()` (L73)
- `test_an_old_macos_names_the_floor()` (L82)
- `test_the_tap_wins_where_it_is_possible()` (L92)
- `test_blackhole_is_the_fallback_and_says_why()` (L98)
- `test_no_backend_at_all_is_a_reported_state()` (L106)
- `test_blackhole_lookup_survives_an_unavailable_audio_stack()` (L115)
- `test_start_returns_what_the_helper_published()` (L124)
- `test_a_helper_that_reports_failure_raises_rather_than_returning_none()` (L134)
- `test_a_helper_that_dies_silently_raises()` (L144)
- `test_a_helper_that_emits_garbage_raises()` (L150)
- `test_stop_is_idempotent_and_safe_when_nothing_ran()` (L156)
- `test_starting_twice_is_refused()` (L162)
- `test_a_published_device_that_never_appears_is_a_failure_not_a_silent_session()` (L172)
- `test_wait_for_device_gives_up_rather_than_hanging_start()` (L189)
- `test_wait_for_device_tolerates_enumeration_failing_mid_wait()` (L196)

### `tests/unit/test_text_filters.py` — 111 lines

Boundary tests for the anti-hallucination filter.

- `test_acceptable_phrase_matching()` (L34)
- `test_acceptable_len_boundary()` (L38)
- `test_every_blacklisted_phrase_is_dropped_bare()` (L46)
- `test_every_blacklisted_phrase_survives_inside_real_speech()` (L52)
- `test_normalize_phrase_is_not_used_to_alter_stored_text()` (L58)
- `test_the_blacklist_is_empty_until_something_is_measured()` (L65)
- `test_only_the_length_guard_remains()` (L84)
- `test_short_noise_reaches_the_buffer_on_purpose()` (L94)
- `test_only_a_lone_punctuation_mark_is_removed()` (L109)

### `tests/unit/test_transcriber_feed_wav.py` — 132 lines

WAV feed path for V52 lab inject (no mic device required).

- `tone_wav()` (L18)
- `test_feed_wav_enqueues_frames()` (L27)
- `class FakeClock` (L65)
  - `monotonic()`
  - `sleep()`
  - `do_frame_work()`
- `_feed_with_clock()` (L84)
- `test_realtime_pacing_absorbs_per_frame_work_instead_of_adding_it()` (L106)
- `test_falling_far_behind_resyncs_and_says_so_rather_than_sprinting()` (L121)

### `tests/unit/test_voice_gate.py` — 251 lines

The gate that decides what never reaches the record.

- `_reset_module_state()` (L22)
- `test_the_gate_is_off_unless_it_is_turned_on()` (L34)
- `test_the_ways_an_operator_might_write_yes()` (L44)
- `test_the_floor_falls_back_rather_than_raising_on_nonsense()` (L50)
- `test_an_empty_model_id_uses_the_ungated_default()` (L58)
- `test_a_missing_package_transcribes_everything()` (L67)
- `test_a_pipeline_that_raises_mid_segment_transcribes_that_segment()` (L74)
- `test_a_load_failure_is_recorded_once_and_not_retried_per_segment()` (L85)
- `_real_import_that_fails_for_pyannote()` (L104)
- `_pipeline_returning()` (L120)
- `test_speech_above_the_floor_is_transcribed()` (L127)
- `test_a_transient_below_the_floor_is_not()` (L132)
- `test_speech_split_across_pauses_is_summed_not_maximised()` (L139)
- `test_silence_produces_no_timeline_and_is_rejected()` (L147)
- `_run_processing_with()` (L154)
- `test_a_rejected_segment_never_reaches_the_inference_queue()` (L193)
- `test_an_accepted_segment_is_queued_as_before()` (L200)
- `test_with_the_gate_off_nothing_is_screened_even_if_it_would_reject()` (L204)
- `test_an_unavailable_gate_reports_itself_as_not_live()` (L212)
- `test_a_gate_that_rejects_silence_is_live()` (L220)
- `test_a_pipeline_that_calls_silence_speech_is_not_trusted_as_live()` (L228)
- `test_the_probe_is_two_seconds_at_the_rate_it_was_given()` (L235)

## `tools/`

### `tools/analyze_soak_contention.py` — 203 lines

Does a second track actually slow inference, or does the label just select slow segments?

- `attach_accepted_text()` (L64)
- `median_ratio()` (L90)
- `relabelled_after_shift()` (L98)
- `band_table()` (L116)
- `main()` (L141)

### `tools/asr_bakeoff.py` — 750 lines

CLI ASR bake-off harness for R37 / R8 / R10 / latency (STATE 7.2).

- `_prefer_homebrew_ssl_bundle()` (L27)
- `_boot_hf_home()` (L81)
- `vad_speech_segments()` (L119)
- `backend_kind_for()` (L171)
- `resolve_qwen_backend()` (L186)
- `make_transcribe_fn()` (L197)
- `class ResourceSampler` (L260)
  - `_sample()`
  - `_loop()`
  - `_mlx_peak_mb()`
  - `_mlx_reset_peak()`
  - `summary()`
- `codeswitch_through_vad()` (L348)
- `evaluate_candidate()` (L381)
- `_cs_str()` (L478)
- `_range_str()` (L489)
- `format_table()` (L498)
- `write_results()` (L532)
- `toolchain_fingerprint()` (L545)
- `fixture_fingerprint()` (L568)
- `main()` (L588)

### `tools/build_conversation_fixture.py` — 226 lines

Build a two-track conversation fixture with an exact reference timeline.

- `class TrackWriter` (L49)
  - `append()`
  - `append_silence()`
  - `close()`
- `_to_int16()` (L73)
- `build()` (L90)
- `main()` (L210)

### `tools/check_state.py` — 130 lines

Checks that the requirement documents still hold together.

- `read()` (L35)
- `decision_records()` (L40)
- `main()` (L49)

### `tools/derive_hallucination_list.py` — 119 lines

Derive the hallucination list from measured output instead of guessing it.

- `load()` (L46)
- `by_bucket()` (L51)
- `derive()` (L59)
- `main()` (L78)

### `tools/diarize_runner.py` — 119 lines

Run speaker diarization in the pinned venv, and print turns as JSON on stdout.

- `_prepare_caches()` (L45)
- `_allow_known_pickle_globals()` (L57)
- `main()` (L79)

### `tools/evaluate_text_filters.py` — 186 lines

What does a text-side filter remove, and what does it destroy? Scored on already-collected data.

- `foreign_script_chars()` (L80)
- `is_repetitive()` (L95)
- `make_filters()` (L116)
- `main()` (L144)

### `tools/fetch_real_fixtures.py` — 135 lines

Build speech fixtures from a public corpus instead of macOS TTS.

- `_resample_linear()` (L39)
- `_write_wav()` (L53)
- `fetch()` (L68)
- `main()` (L116)

### `tools/gen_asr_fixtures.py` — 299 lines

Synthesize ASR bake-off fixtures under fixtures/asr/ (gitignored WAVs).

- `_sine()` (L29)
- `_silence()` (L34)
- `_mix()` (L38)
- `_noise()` (L50)
- `gen_layered_tones()` (L55)
- `gen_noise_bed()` (L74)
- `gen_single_chimes()` (L86)
- `gen_glass_cascade()` (L103)
- `gen_click_burst()` (L121)
- `gen_typing_run()` (L136)
- `_pick_zh_voice()` (L140)
- `_say_to_wav()` (L166)
- `_tts_fallback_tone_speech()` (L191)
- `write_speech_clip()` (L201)
- `maybe_skip()` (L209)
- `main()` (L213)

### `tools/gen_filemap.py` — 152 lines

Generates FILEMAP.md: a mechanical inventory of the repo's Python surface.

- `find_python_files()` (L35)
- `summarize()` (L47)
- `render()` (L81)
- `main()` (L124)

### `tools/gen_v52_prompt_audio.py` — 204 lines

Build a reusable V52 / 7.3 prompt audio fixture.

- `_silence()` (L58)
- `_say_line_to_samples()` (L62)
- `build_tts()` (L78)
- `teleprompter_record()` (L95)
- `play()` (L139)
- `print_script()` (L154)
- `main()` (L160)

### `tools/hf_curl_place.py` — 67 lines

Populate a Hugging Face cache entry with curl, because Python cannot reach the Hub here.

- `curl()` (L34)

### `tools/measure_asr_latency.py` — 258 lines

Parse ASR inference latencies from a captured log and summarise for V52 / 7.3.

- `extract_latencies_ms()` (L32)
- `percentile()` (L36)
- `summarise()` (L51)
- `format_row()` (L75)
- `load_path()` (L85)
- `watch_resources()` (L90)
- `main()` (L117)

### `tools/measure_biasing.py` — 224 lines

Does decoder biasing still recover rare proper nouns, now that the mechanism has changed?

- `all_terms()` (L92)
- `build_clips()` (L101)
- `prompts_for()` (L118)
- `recovered()` (L129)
- `main()` (L134)

### `tools/measure_decode_thresholds.py` — 284 lines

Can Whisper's decoding thresholds buy back R37, and what does that cost on speech?

- `make_fn()` (L81)
- `nonspeech_segments()` (L101)
- `synthetic_segments()` (L115)
- `score_arm()` (L129)
- `_range()` (L203)
- `main()` (L212)

### `tools/measure_dual_track.py` — 159 lines

Measure what a second capture track costs, without a second capture device.

- `class LatencyCollector` (L38)
  - `emit()`
  - `summary()`
- `run_arm()` (L66)
- `main()` (L111)

### `tools/measure_overlap_turns.py` — 378 lines

What two tracks cost at the pace people actually speak, and what overlap does to it.

- `load_turns()` (L72)
- `load_events()` (L84)
- `merge()` (L97)
- `intersect()` (L108)
- `describe_fixture()` (L124)
- `label_contention()` (L146)
- `stats()` (L175)
- `row()` (L187)
- `contamination()` (L193)
- `main()` (L237)

### `tools/measure_segmentation.py` — 285 lines

Does letting speech segments grow beat flushing them at 0.4 s of silence?

- `load_samples()` (L54)
- `segment_by_silence()` (L70)
- `segment_by_window()` (L114)
- `reference_buckets()` (L151)
- `main()` (L165)

### `tools/measure_speaker_leakage.py` — 232 lines

On speakers, how much of the far party lands in the Operator track — with ground truth this time.

- `class CollectingBuffer` (L67)
  - `add_entry()`
- `bucket_reference()` (L84)
- `reference_text()` (L94)
- `set_volume()` (L104)
- `main()` (L121)

### `tools/measure_tap_stream.py` — 134 lines

Measure what actually arrives when PortAudio opens the system-audio tap.

- `start_helper()` (L36)
- `find_device()` (L54)
- `measure()` (L67)
- `main()` (L107)

### `tools/measure_vad_gate.py` — 183 lines

Would a neural VAD in front of the decoder stop the false lines? The stage nobody searched.

- `bucket_for()` (L64)
- `segments()` (L77)
- `main()` (L98)

### `tools/npu_lock_trial.py` — 370 lines

Trial: does `NPU_LOCK` still have to exist? Protocol in `fixtures/asr/NPU_LOCK_TRIAL.md`.

- `emit()` (L48)
- `run_child()` (L53)
- `load_turns()` (L170)
- `run_arm()` (L179)
- `decile_drift()` (L243)
- `score_against_reference()` (L258)
- `compare_content()` (L280)
- `main()` (L303)

### `tools/probe_advisor.py` — 199 lines

Turn V94's "both failures are reachable" into a rate, unattended.

- `wait_for_server()` (L79)
- `classify()` (L93)
- `main()` (L102)

### `tools/probe_music.py` — 208 lines

Does music — especially music with a voice in it — become an utterance? The V41 question.

- `parse_annotations()` (L73)
- `collect_clips()` (L95)
- `main()` (L131)

### `tools/probe_nonspeech_real.py` — 399 lines

R37 on non-speech that is not a synthesized tone. The measurement behind V60, and now V71.

- `segments_for()` (L62)
- `control_speech()` (L74)
- `build_inputs()` (L84)
- `group_of()` (L93)
- `bucket_of()` (L117)
- `summarise()` (L130)
- `main()` (L241)

### `tools/probe_rag_cues.py` — 207 lines

Does a retrieval cue fire when it should, and stay quiet when it should not?

- `build_temp_index()` (L83)
- `main()` (L105)

### `tools/probe_ui_flow.py` — 160 lines

Drive the real application through Start, a fed transcript, and Stop.

- `main()` (L43)

### `tools/score_real_fixtures.py` — 207 lines

Score ASR candidates against real recorded speech with published ground truth.

- `normalise()` (L36)
- `cer()` (L43)
- `load_refs()` (L59)
- `score()` (L71)
- `main()` (L106)

### `tools/soak_capture.py` — 483 lines

Run capture for an hour through the real device path, and report whether it degrades.

- `newest_log()` (L125)
- `parse_segments()` (L131)
- `mark_contended()` (L153)
- `sample_memory()` (L166)
- `main()` (L175)

### `tools/verify_capture_end_to_end.py` — 135 lines

Run the capture pipeline for real, once, and report what came out.

- `synthesize()` (L47)
- `main()` (L61)

### `tools/verify_repeat_sessions.py` — 115 lines

Start and stop capture several times in one process, and check the later sessions still work.

- `main()` (L38)

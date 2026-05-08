PRODUCT REQUIREMENTS DOCUMENT
ARIA  —  Agentic Reactive Intelligence Assistant
A local-first, vision-driven PC automation agent built on Gemma 4 E2B (4-bit) — a single unified model for text, vision, and audio — with smart overlay UI, CDP-based tab control, tiered file safety, and a comprehensive benchmark harness.
Version: v1.1    Platform: Windows 11    GPU: RTX 3060 6 GB    Stack: Python + Codex CLI
Changes in v1.1: Unified Gemma 4 E2B model (drops moondream2 + separate vision pipeline) · CDP tab control replaces Chromium spawn · File safety tiers added · Whisper retained on CPU for parallel STT


1. Executive Overview
ARIA is a privacy-first, on-device AI assistant running entirely on a local GPU using Gemma 4 E2B in 4-bit quantization — a single unified model that handles text, vision, and audio natively, with no separate vision or speech model required on the GPU. It accepts commands via speech, a smart overlay UI, or text, then takes actions by seeing the screen, reasoning over context, and executing through Python tooling.


2. System Architecture
2.1 Revised Architecture — Single Unified Model


2.2 VRAM Budget — RTX 3060 6 GB


2.3 Module Breakdown
2.3.1 Input Module
Speech: faster-whisper (small.en, CPU) triggered by hotkey (Alt+Space hold) or optional wake word. Runs on a dedicated asyncio thread — does not block GPU inference. Streams 30s chunks; typical command < 5s.
Overlay UI: PySide6 borderless frameless window in a separate process. Communicates with orchestrator via asyncio IPC queue. Auto-opacity: 0% idle → 90% on hover/hotkey. See Section 4 for full state machine.
Text: System tray popup or CLI pipe for scripting and Codex-assisted testing.

2.3.2 Orchestrator — Gemma 4 E2B
Model: Gemma-4-E2B-IT Q4_K_M GGUF via llama-cpp-python (CUDA build). Full GPU offload.
Multimodal input: images passed as llama_cpp image embeds (Llava-style API); audio passed as 30s WAV clips when voice understanding is needed beyond STT transcription.
Context: 8192 tokens default. System prompt injects available tools as JSON schema (ReAct-style). Flush context between independent tasks to reclaim KV cache VRAM.
Inference config: temperature 0.2, top_p 0.95, top_k 64 (Google recommended defaults). Repeat penalty 1.0 (disabled) — Gemma 4 does not need it.
Tool-call parsing: structured JSON output mode via Gemma 4's native function-calling support. Falls back to regex extraction if JSON parse fails.

2.3.3 Vision-Click Agent
Capture: mss for ultra-fast screenshot (< 5 ms), PIL for crop and resize to 1280×720.
Understanding: screenshot passed directly as image token to Gemma 4 E2B. Prompt asks model to return (x, y, action, confidence) as JSON.
Execution: pyautogui with 200 ms guard between actions. Verify-by-screenshot after each click — pass new screenshot back to model to confirm state change.
No separate moondream2 or LLaVA process. Vision is a first-class input to the same model doing reasoning and tool-calling.

2.3.4 CDP Tab Agent — Chrome DevTools Protocol
Connection: Chrome launched once with --remote-debugging-port=9222. ARIA auto-detects on startup; if not found, shows a one-click 'Restart Chrome with debug port' prompt in overlay.
Zero overhead: CDP connects to the user's existing Chrome instance. No second browser process, no extra RAM. Playwright async API used as the CDP client library.
Tab tools: get_open_tabs() → list of {index, title, url, active}, switch_to_tab(index_or_keyword), find_tab_by_keyword(query) → fuzzy match on title+URL, get_recent_history(n) → last n visited URLs, open_url_in_active_tab(url), open_url_in_new_tab(url), close_tab(index).
History search: queries Chrome's SQLite history database directly (read-only) for richer search beyond what CDP exposes — useful for 'find that article I read yesterday about X'.
Vision fallback: if CDP action fails (canvas app, PDF viewer, unusual SPA), falls back to vision-click agent automatically.

2.3.5 File & OS Tools
Read tools (always allowed in any path): list_dir, read_file, search_files (ripgrep), get_file_info.
Write tools (zone-restricted, see Section 5): write_file, move_file, create_dir, rename_file.
Destructive ops (require explicit confirmation every time): delete → moves to Recycle Bin via send2trash, never hard delete in v1. Overwrite of existing file = treated as destructive.
OS tools (no zone restrictions): get_active_window, list_running_apps, set_clipboard, get_clipboard, send_notification, open_with_default_app.

2.3.6 Proactivity Engine (Light)
Clipboard watcher: on clipboard change, model scores relevance. If high, a suggestion chip appears in overlay (e.g. 'Open this URL?' / 'Summarise this?').
Active window monitor: polls foreground window title every 5s; matches configured triggers to surface quick actions.
User can suppress per-session or permanently in settings.json.

3. Overlay UI Specification
3.1 Behaviour States

3.2 UI Principles
Frameless, always-on-top, click-through when hidden — never blocks other apps.
Dark/light mode follows Windows accent colour. DWM ACRYLIC blur if available, fallback to semi-transparent flat.
All animations < 150 ms easing. PySide6 in separate process so GPU contention never freezes the overlay.
Keyboard-first: every action reachable without mouse. Tab-navigable result cards.
Shows CDP connection status icon (green dot = Chrome connected, grey = not connected).

4. File Safety System
4.1 Destructive Operation Definition
Both deletion AND overwriting an existing file are classified as destructive operations. The agent will never silently overwrite content. A backup copy is offered before any overwrite, and all deletes go to the Windows Recycle Bin (via send2trash), never hard-deleted.

4.2 Allowed Zones (v1)

4.3 Confirmation Flow
Write to new file in allowed zone: silent, no confirmation.
Overwrite existing file: overlay shows diff summary + 'Overwrite / Cancel / Save as new' buttons.
Delete file: overlay shows filename + 'Move to Recycle Bin / Cancel'. Never a silent delete.
Write to path outside allowed zones: hard block with explanation. Agent tells user to add the path to allowed_zones in settings.json.


5. Benchmarking & Metrics
5.1 Metric Definitions

5.2 Benchmark Task Suite

5.3 Benchmark Dashboard
JSON telemetry per run stored at ~/.aria/benchmarks/YYYYMMDD_HHMMSS.json with all 11 metrics.
Single-file HTML dashboard (no server needed) reads local JSON and renders metric trends across runs.
Regression detection: if any metric degrades > 10% vs rolling 5-run average, dashboard flags it red.
Export to CSV for Jupyter or Excel analysis.

6. Building with Codex — Best Practices
6.1 What Codex CLI Is
Codex CLI (codex in terminal) is an AI coding agent that reads your repo, writes and edits files, runs commands, and iterates. You give it a scoped task, it acts on your codebase. Think of it as a pair programmer that works on your files directly. You always review its diffs before accepting.

6.2 Recommended Workflow
Always work on a feature branch. Never run Codex directly on main.
Start each session by writing a spec comment at the top of the target file. Codex reads file context — your comments are its instructions.
Write pytest test stubs before asking Codex to implement. TDD: tests define the contract, Codex fills the implementation.
Use --approval-mode suggest always during early development — review every diff before accepting. Switch to full-auto only for low-risk boilerplate (loggers, JSON schemas, dashboard HTML).
Keep each session to one module. Multi-file refactors in a single prompt produce drift.
Point Codex at specific files with --context to prevent it hallucinating across the whole repo.

6.3 Module-Per-Session Plan (Ordered)


6.4 Codex Anti-Patterns to Avoid
Don't paste the full PRD into a Codex prompt — it generates too broadly. Give it one module spec at a time.
Don't skip the spec comment. Codex with no context produces generic boilerplate that you'll rewrite anyway.
Don't run full-auto on file_tools.py or vision_agent.py during development — these touch real filesystem and real screen. Use suggest mode.
Don't let Codex generate API keys or secrets. Use python-dotenv and a .env file that's gitignored.

7. Risks & Mitigations

8. Development Phases
Phase 0 — Foundation (Week 1–2)
Install llama-cpp-python CUDA build. Load Gemma 4 E2B Q4_K_M. Verify TTFT, token throughput, VRAM baseline with pynvml.
Test native vision: pass a 1280×720 screenshot, verify model returns grounding JSON.
Build minimal overlay (Alt+Space toggle, text input, plain text response via IPC).
Benchmark logger skeleton: JSON schema, pynvml poller, per-task context manager.
Chrome CDP connection: verify get_open_tabs() returns live tab list from existing Chrome.

Phase 1 — Core Tools (Week 3–4)
cdp_tab_agent.py: all 7 tab tools + Chrome history SQLite reader. Full pytest suite.
file_tools.py: zone validator, confirmation gate, send2trash integration. Safety gate tests.
os_tools.py: clipboard, active window, notifications.
Wire tool-call parsing in orchestrator. Test with hardcoded JSON prompts. Run first benchmark suite.

Phase 2 — Vision & Speech (Week 5–6)
vision_agent.py: mss capture → Gemma 4 image embed → pyautogui → verify loop.
stt.py: faster-whisper push-to-talk on asyncio thread. End-to-end speech → tab switch test.
Vision fallback routing in cdp_tab_agent: DOM fail → vision agent.
Run full 16-task benchmark suite. Publish first dashboard HTML.

Phase 3 — Polish & Proactivity (Week 7–8)
Overlay polish: all 6 states, animations, CDP status indicator, dark/light mode.
Proactivity engine: clipboard watcher, active window monitor, suggestion chips.
Benchmark regression CI: run suite on every commit, flag > 10% regressions.
Codex-assisted README, inline docstrings, settings.json schema documentation.

9. Technology Stack

10. Open Questions & Future Ideas
10.1 Open Questions (Decide Before Phase 1)
TTS choice: pyttsx3 (zero latency, robotic) vs Kokoro-82M (natural, +150ms, ~200MB RAM). Suggested: pyttsx3 default, Kokoro as opt-in setting.
Wake word: Picovoice Porcupine (free tier, always-on mic) vs push-to-talk only (more private). Privacy vs convenience trade-off — expose as a settings toggle.
Chrome debug port setup: auto-registry run key (seamless but intrusive) vs manual launch script (transparent but requires user action once). Suggest: provide both options at first run.

10.2 Future Ideas (v1.2+)
File policy engine: whitelist/blacklist/confirm tiers per extension and per path (detailed design in Section 4.3 callout).
Memory module: ChromaDB local vector store for task history and user preference learning across sessions.
Plugin system: drop a .py file in ~/aria/plugins/ and the agent auto-discovers new tools at startup.
Gemma 4 E4B upgrade path: when user upgrades to a 12 GB GPU, swap E2B → E4B Q4_K_M in one config line for better reasoning and grounding accuracy.
Screen recording replay: record a workflow once, ARIA learns to repeat it on command.
Multi-monitor support: agent selects which screen to capture based on active window context.

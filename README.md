# ARIA Agent

Runnable Python scaffold for the ARIA assistive desktop agent.

## Development Setup

These steps run the project in a local development environment. This repo is
currently a Python scaffold and does not expose a single application CLI yet, so
development runs are done by importing and exercising the modules directly.

1. Install Python 3.10 or newer.

2. Install `uv` if it is not already available.

   ```powershell
   pip install uv
   ```

3. Create and sync the virtual environment from the lockfile.

   ```powershell
   uv sync --dev
   ```

4. Create or update `.env` in the repo root.

   ```env
   MODEL_PATH=C:/path/to/gemma-4-e2b-q4_k_m.gguf
   CHROME_DEBUG_PORT=9222
   ARIA_ALLOWED_ZONES=~/Documents,~/Downloads,~/Desktop
   ```

   `MODEL_PATH` must point to a local GGUF model file. The orchestrator will
   fail to start until this is set.

5. Install the Playwright browser runtime if you plan to use browser tools.

   ```powershell
   uv run playwright install chromium
   ```

6. Optional: start Chrome with remote debugging enabled before using the CDP tab
   tools.

   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\aria-chrome-dev"
   ```

7. Smoke-run the scaffold from the repo root.

   ```powershell
   uv run python -c "from src.core.config import load_config; print(load_config())"
   ```

8. Run a local model prompt through the orchestrator.

   ```powershell
   uv run python -c "import asyncio; from src.core.orchestrator import Orchestrator; print(asyncio.run(Orchestrator().generate('Say hello from ARIA in one sentence.')))"
   ```

9. Run a browser-tool check after launching Chrome with remote debugging.

   ```powershell
   uv run python -c "import asyncio; from src.tools.cdp_tab_agent import get_open_tabs; print(asyncio.run(get_open_tabs()).model_dump())"
   ```

Keep `settings.json` in the repo root while running locally. It controls enabled
capabilities such as filesystem read access, browser access, and screen read
access.

## Layout

- `src/core`: orchestration, configuration, IPC, shared types, and exceptions.
- `src/tools`: tool interfaces and tool-specific modules.
- `src/input`: input integrations such as speech-to-text.
- `src/overlay`: overlay state management.
- `src/prompts`: prompt assets.
- `src/utils`: shared utilities.
- `tests`: package-aligned test directories.
- `benchmarks`: benchmark assets and scripts.

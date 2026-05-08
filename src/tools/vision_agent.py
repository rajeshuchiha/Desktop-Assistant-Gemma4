"""
SPEC: Vision-based screen interaction using Gemma 4 E2B native vision.

INTERFACE:
  capture_screen(region: dict | None = None) -> PIL.Image
    - use mss for capture (< 5ms)
    - resize to 1280x720 max
    - region: {top, left, width, height} or None for full screen

  async click_element(description: str) -> ToolResult
    - capture_screen()
    - pass image to orchestrator.generate() with prompt:
      "Return JSON {x, y, confidence} for where to click: {description}"
    - parse response, call pyautogui.click(x, y)
    - 200ms guard before every click (time.sleep(0.2))
    - capture again, ask model "did the action succeed? JSON {success, reason}"
    - retry up to 3x if confidence < 0.7 or success == false
    - return ToolResult(success, data={x,y}, latency_ms)

  async read_screen(question: str) -> ToolResult
    - capture_screen()
    - pass image + question to orchestrator.generate()
    - return ToolResult(success=True, data=response)

DEPENDENCIES: src/core/orchestrator.py, src/core/types.py
DO NOT: exceed 1280x720 resolution, click without 200ms guard
"""
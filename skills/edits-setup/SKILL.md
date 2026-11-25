---
name: edits-setup
description: Set up oh-my-edits on a Mac - interview the user about their goal and devices, connect the agent to the Edits Mac app's local MCP server, and prepare ipb to drive the Edits iPhone app. Use when the user installs oh-my-edits, asks to connect Edits, or another oh-my-edits skill reports a missing MCP server or phone.
---

# Set up oh-my-edits

oh-my-edits works on two surfaces. Set up only the surfaces the user's goal needs.

| Surface | What runs it | Needed for |
|---|---|---|
| Edits Mac app | The app's local MCP server | Editing projects, export, captions, music |
| Edits iPhone app | [ipb](https://github.com/ipbtools/ipb) (CoreDevice HID), through the plugin's `scripts/phone.py` helper | Inspiration feed settings, saved reels, anything only the mobile app has |

## 1. Interview

Ask these in one round, with a recommended default for each. Skip a question when the answer is already known.

1. **Goal**: tune the inspiration feed, find references, sort saved reels, or edit on the Mac. This decides which surfaces to set up.
2. **Harness**: Claude Code, Codex, or both.
3. **Mac app**: is the Edits Mac app installed and signed in?
4. **iPhone**: is the Edits iPhone app installed? Is the phone on iOS 27 or later? Can it stay unlocked and connected by USB or the same Wi-Fi during the run?
5. **Account**: which Instagram account is signed in to Edits on the phone? Confirm the user accepts that the agent will act inside that account, within the limits in "Safety" below.

Restate the chosen surfaces in one line before you change anything.

## 2. Edits Mac app MCP

1. Install Edits from the official site (`edits.instagram.com`). It is not in the Mac App Store. "Edits+" in the App Store is a different app.
2. In the Edits app settings, turn on the MCP server. It listens on `http://127.0.0.1:19501/mcp` (Streamable HTTP) and requires a bearer token.
3. The user keeps the token in their own secret store and exports it as `EDITS_MCP_TOKEN`. Never ask the user to paste the token into the conversation, and never print it.
4. Register the server:
    - **Codex**: `codex mcp add edits --url http://127.0.0.1:19501/mcp --bearer-token-env-var EDITS_MCP_TOKEN`. Codex reads the variable at connect time, so the token is not written to `config.toml`.
    - **Claude Code**: add the server to a `.mcp.json` with `"headers": {"Authorization": "Bearer ${EDITS_MCP_TOKEN}"}` so the variable is expanded at load time. Do not run `claude mcp add ... --header "Authorization: Bearer $EDITS_MCP_TOKEN"` from a shell, because the shell expands the token and Claude Code stores it in plain text.
5. Restart the harness, then call the server's `state` tool. Success is a response that names the current screen. The tool list changes with the app's screen (home or editor), so a missing editor tool on the home screen is expected.

Known behavior (Edits 457.0.0):

- Media import and export only work for paths under `~/Movies`.
- Edits sent back to back can drop the earlier edit. Read the result (`state`, `getElement`, `elements`) after each edit.
- `clips` can return values from before the last edit. Read fresh values with `state`, `getElement`, or `elements`.
- Built-in text-to-speech voices are English only. Non-English text fails with `unsupportedLanguage`. Add narration as a voiceover file instead.

## 3. iPhone with ipb

The phone is driven through the helper `scripts/phone.py` in this plugin. It wraps [ipb](https://github.com/ipbtools/ipb) and checks a fresh screenshot (Apple Vision OCR, Korean and English) before every action. Do not call `ipb tap`, `ipb text`, or `ipb scroll` yourself.

**Plugin root.** It is two levels above this skill's directory: the folder that holds `skills/` and `scripts/`. Below, `<plugin-root>` stands for it. The helper needs [uv](https://docs.astral.sh/uv/) (it fetches its own Python dependencies on the first run, which can take several seconds) and macOS.

1. Install ipb by following its README. It needs macOS with CoreDevice and an iPhone on iOS 27 or later.
2. Run `uv run <plugin-root>/scripts/phone.py doctor`. It runs `ipb doctor` and ends with `doctor: PASS` or `doctor: FAIL`. Continue only on PASS (`0 failure(s)`). A `transport: localNetwork` warning is acceptable. USB is more reliable, and accessibility reads (`ipb ui`) need USB.
3. The phone must be unlocked with the screen on. A locked phone returns a black screenshot, and the helper stops with "Screenshot is dark". Ask the user to unlock it.
4. Capture one screen and confirm with the user that it shows their phone:

    ```
    uv run <plugin-root>/scripts/phone.py run <<'PY'
    # task: Set up oh-my-edits.
    # step: Capture one screen to confirm the phone.
    import os, tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="edits-setup-"), "screen.png")
    ph_observe(all_text=True, capture_path=path)
    print(path)
    PY
    ```

    Open the image, ask the user to confirm it, then delete it.

### Running phone scripts

Pass a Python script on stdin to `uv run <plugin-root>/scripts/phone.py run`. The first two lines must be `# task:` (the whole job) and `# step:` (what this script does). The helper prints both to stderr, flushes output line by line, and exits with an error line that names the script line that failed. Run one small step per call.

| Function | What it does |
|---|---|
| `ph_observe(contains=None, capture_path=None, all_text=False)` | Fresh capture and OCR. `contains=[...]` returns only the matching lines. `all_text=True` returns the whole screen as a `Screen`, which hides its text when printed. `capture_path` also saves the image to a new owner-only file |
| `ph_find(text)` | Lines containing `text`, top to bottom, each with `x`, `y` (centre, points), `w`, `h`, and `match` (`exact` or `partial`). For a partial match inside a longer line, `x` and `w` are estimated, and the whole line's `line_x` and `line_w` are kept |
| `ph_screen_size()` | Screen width and height in points |
| `ph_wait(expected, timeout=12, absent=())` | Wait until every expected label is visible and no absent label is |
| `ph_tap(label, on_screen, expected, ...)` | Tap the one line that is `label`, after the `on_screen` labels are confirmed in a fresh capture. Then require a new `expected` label, or an `absent` label to disappear |
| `ph_tap_tab(label, on_screen, expected, lift=0, ...)` | The same for a bottom tab-bar label. `expected` must be a label only the destination shows |
| `ph_tap_point(x, y, on_screen=None, allow_danger=False)` | Tap a point after a fresh capture shows the `on_screen` labels. For icons and for text inside a longer line (use `ph_find` for the point) |
| `ph_type_text(text, replace=False)` | Paste into the focused field and require the text on screen. Answers the one-time "Allow Paste" prompt. Overwrites the phone's clipboard. `replace=True` replaces the field's content |
| `ph_scroll(direction, on_screen, amount=0.3, at=None)` | One scroll after a screen check; returns the screen after |
| `ph_home()` | Home Screen |

Rules the helper enforces:

- Coordinates are points: screenshot pixels divided by 3. `ph_find` and `ph_screen_size` already use points.
- Labels match case-insensitively. Leading and trailing glyphs are ignored (`Projects •` matches `Projects`), a label may sit inside a longer OCR line, and OCR look-alikes are treated as equal (`I`, `l`, `1`, `|`; `0`, `O`), so `AI tools` matches `Al tools`. A label under three characters matches only a whole line when it proves a screen. Use distinctive labels.
- `ph_tap` and `ph_tap_tab` refuse a label that is only inside a longer line, or that appears twice. Locate it with `ph_find` and tap with `ph_tap_point`.
- A tap is refused near a destructive label (Delete, Remove, Reset, Erase, Sign out, and the Korean equivalents) unless you pass `allow_danger=True` for a target the user approved.
- Every ipb call has a time bound. A call that outlives it is killed and raises a timeout error. Its effect on the phone is unknown, so observe the screen before you repeat it.
- Print only the labels you need. Do not print whole-screen results.

Status: unit-tested and OCR-checked on a synthetic image. Not yet run end to end on a device, and the `ph_scroll` direction is unverified. Treat the first device run as the check.

## Safety

The Edits iPhone app is signed in to the user's Instagram account. Inside it:

- Change only what the user approved in this session, for example the topics in the inspiration settings.
- Read a few screens at a time. Do not scroll the feed in bulk.
- Never like, follow, comment, send messages, publish, or use a template on the user's behalf.
- Leave per-video feedback (such as "Not interested") to the user.
- Stop on any login prompt, account warning, CAPTCHA, or rate limit, and hand control back to the user.

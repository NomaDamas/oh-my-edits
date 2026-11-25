---
name: edits-setup
description: Set up oh-my-edits on a Mac - interview the user about their goal and devices, connect the agent to the Edits Mac app's local MCP server, and prepare ipb to drive the Edits iPhone app. Use when the user installs oh-my-edits, asks to connect Edits, or another oh-my-edits skill reports a missing MCP server or phone.
---

# Set up oh-my-edits

oh-my-edits works on two surfaces. Set up only the surfaces the user's goal needs.

| Surface | What runs it | Needed for |
|---|---|---|
| Edits Mac app | The app's local MCP server | Editing projects, export, captions, music |
| Edits iPhone app | [ipb](https://github.com/ipbtools/ipb) (CoreDevice HID) | Inspiration feed settings, saved reels, anything only the mobile app has |

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

1. Install ipb by following its README. It needs macOS with CoreDevice and an iPhone on iOS 27 or later.
2. Run `ipb doctor`. Continue only with `0 failure(s)`. A `transport: localNetwork` warning is acceptable. USB is more reliable, and accessibility reads (`ipb ui`) need USB.
3. The phone must be unlocked with the screen on. A locked phone returns a black screenshot. Stop and ask the user to unlock it.
4. Take one screenshot (`ipb screenshot`) and confirm with the user that it shows their phone.

The phone helper (screen-checked taps, OCR, text entry) is tracked in the repository issues. Until it lands, drive ipb directly and look at a fresh screenshot before every tap.

## Safety

The Edits iPhone app is signed in to the user's Instagram account. Inside it:

- Change only what the user approved in this session, for example the topics in the inspiration settings.
- Read a few screens at a time. Do not scroll the feed in bulk.
- Never like, follow, comment, send messages, publish, or use a template on the user's behalf.
- Leave per-video feedback (such as "Not interested") to the user.
- Stop on any login prompt, account warning, CAPTCHA, or rate limit, and hand control back to the user.

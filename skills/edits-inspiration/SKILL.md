---
name: edits-inspiration
description: Tune the Edits iPhone app's inspiration feed ("Your inspiration" topics) - interview the user about what they want to see more and less of, enter the approved topics on the phone with ipb, and verify every topic chip. Use when the user asks to set up, tune, or reset their Edits algorithm, inspiration feed, or recommended reels.
---

# Tune the Edits inspiration feed

Edits recommends reels in the Inspiration tab. The user steers it with two free-text topic lists on the **Your inspiration** screen:

- **What you want to see more of**
- **What you want to see less of**

This skill fills those lists from a short interview. It needs the iPhone surface from `edits-setup`, including its phone helper: run every phone step as a script with `uv run <plugin-root>/scripts/phone.py run` and use the `ph_*` functions listed in `edits-setup` section 3. `<plugin-root>` is two levels above this skill's directory. Run one step per call.

## 1. Read the current state

1. Save a capture with `ph_observe(all_text=True, capture_path=<new file>)` and look at the image to see which screen is in front. If Edits is not in front, ask the user to open it. Do not launch apps or close what the user is doing.
2. Open the Inspiration tab: the third icon in the bottom tab bar. Save a capture with `ph_observe(all_text=True, capture_path=<new file>)`, read the icon position in the image (points are pixels divided by 3; `ph_screen_size()` gives the screen size), and tap it with `ph_tap_point(x, y, on_screen=[<a label visible now>])`.
3. Tap the icon at the top left of the feed header, to the left of "Inspiration". Get the header row with `ph_find("Inspiration")` (its `y`, and the title's left edge `x - w / 2`), tap the icon just left of that point with `ph_tap_point(..., on_screen=["Inspiration"])`, then confirm with `ph_wait(["Your inspiration"])` that it opened **Your inspiration**.
4. Read both lists and report them before you change anything. `ph_observe(all_text=True)` returns a `Screen` that hides its text when printed; iterate it in the script and print only the topic lines under each heading.

The link "Based on your activity, summarized by AI >" under the first heading opens only a "How it works" sheet. It does not list inferred interests. Close it by tapping the dimmed area above the sheet.

## 2. Interview

Ask in one round. Offer two or three topic bundles built from what you know about the user's work, plus a "write my own" option. Mark one as recommended. Then ask what to see less of. See [interview](references/interview.md) for the question set and how to turn answers into topics.

Restate the final lists (more / less) and get one confirmation. That confirmation covers only these entries.

## 3. Enter topics

For each topic, in its own `run` call:

1. Find the `+ Add` chip under the right heading. It moves as chips are added. `ph_find("Add")` returns every line with that text; pick the one below the heading (`ph_find("What you want to see more of")` or `ph_find("What you want to see less of")`) and above the next one.
2. Tap it with `ph_tap_point(x, y, on_screen=["Your inspiration"])`. A text field opens above the keyboard.
3. Type the topic with `ph_type_text(topic)`. It pastes the text and requires it on screen.
4. Tap the round send button at the right end of the field. Locate it on the same row as the typed text. `ph_find(topic)` lists the candidate rows (an existing chip can match too), and a capture saved with `ph_observe(all_text=True, capture_path=<new file>)` shows which row is the field and where the button is (points are pixels divided by 3). Tap `ph_tap_point(button_x, row_y, on_screen=[topic])`; the typed text is on screen, so it is the safest precondition. The field's height changes with the keyboard layout (for example, when a suggestion bar appears), so do not reuse a fixed position.
5. Take a fresh capture and confirm the new chip under its heading and that no text field is left open. A toast such as "We'll show you more reels on <topic>" may appear, but it fades quickly, so the chip is the proof.

Use short, common phrases (two or three words). Edits capitalizes the first letter of each chip.

## 4. Verify and report

Take a final screenshot of **Your inspiration** and report both lists with the time of the check. Report each topic that did not appear as not added. Do not report a cause you did not see.

Feed changes are not instant. Tell the user to judge the feed over the following days.

## Pitfalls seen on Edits (iOS 27)

- **Header**: the feed header (Inspiration, Templates, search) can stay hidden after the user scrolls or opens a reel. Re-tapping the Inspiration tab and tapping the video did not bring it back. Switching to the Ideas (saved) tab and then back to Inspiration did. Do not scroll the feed to find the header.
- **OCR**: Apple Vision OCR read "AI" as "Al", and read the header as one line (`* Inspiration • Templates o`) and read the label `Projects` as `Projects •`. The helper ignores edge glyphs, accepts a label inside a longer line, and treats I/l (and 1, |, 0/O) as the same character, but `ph_tap` still refuses a label that is only inside a longer line: use `ph_find` and `ph_tap_point`. OCR can also miss the dimmed `+ Add` chip. Fall back to the screenshot image.
- **Rejected topic**: "Beauty and makeup" did not become a chip in two attempts, and no error was shown. "Makeup" worked. When a topic fails twice, stop retrying it, report it, and offer a shorter phrase.
- **Long batches**: run one topic per call, with a timeout on the call. A batch loop stalled once after typing with no output, and the topic was left unsent in the field. The helper bounds every ipb call with a timeout and flushes output per line, so print one progress line per topic. After a timeout, read the screen before you send anything again.

Unverified: the helper steps above are unit-tested but have not yet been run end to end on a device. Check each capture and each chip on the first run.

## Boundaries

Change only the topic lists the user confirmed. Do not like, follow, save, use templates, or give per-video feedback while you are on the feed. See `edits-setup` for the full safety rules.

---
name: edits-inspiration
description: Tune the Edits iPhone app's inspiration feed ("Your inspiration" topics) - interview the user about what they want to see more and less of, enter the approved topics on the phone with ipb, and verify every topic chip. Use when the user asks to set up, tune, or reset their Edits algorithm, inspiration feed, or recommended reels.
---

# Tune the Edits inspiration feed

Edits recommends reels in the Inspiration tab. The user steers it with two free-text topic lists on the **Your inspiration** screen:

- **What you want to see more of**
- **What you want to see less of**

This skill fills those lists from a short interview. It needs the iPhone surface from `edits-setup`.

## 1. Read the current state

1. Take a fresh screenshot. If Edits is not in front, ask the user to open it. Do not launch apps or close what the user is doing.
2. Open the Inspiration tab: the third icon in the bottom tab bar.
3. Tap the icon at the top left of the feed header, to the left of "Inspiration". It opens **Your inspiration**.
4. Read both lists and report them before you change anything.

The link "Based on your activity, summarized by AI >" under the first heading opens only a "How it works" sheet. It does not list inferred interests. Close it by tapping the dimmed area above the sheet.

## 2. Interview

Ask in one round. Offer two or three topic bundles built from what you know about the user's work, plus a "write my own" option. Mark one as recommended. Then ask what to see less of. See [interview](references/interview.md) for the question set and how to turn answers into topics.

Restate the final lists (more / less) and get one confirmation. That confirmation covers only these entries.

## 3. Enter topics

For each topic, in its own step:

1. Take a fresh screenshot and find the `+ Add` chip under the right heading. It moves as chips are added.
2. Tap `+ Add`. A text field opens above the keyboard.
3. Type the topic.
4. Tap the round send button at the right end of the field. Locate it on the same row as the typed text. The field's height changes with the keyboard layout (for example, when a suggestion bar appears), so do not reuse a fixed position.
5. Take a screenshot and confirm the new chip. A toast such as "We'll show you more reels on <topic>" may appear, but it fades quickly, so the chip is the proof.

Use short, common phrases (two or three words). Edits capitalizes the first letter of each chip.

## 4. Verify and report

Take a final screenshot of **Your inspiration** and report both lists with the time of the check. Report each topic that did not appear as not added. Do not report a cause you did not see.

Feed changes are not instant. Tell the user to judge the feed over the following days.

## Pitfalls seen on Edits (iOS 27)

- **Header**: the feed header (Inspiration, Templates, search) can stay hidden after the user scrolls or opens a reel. Re-tapping the Inspiration tab and tapping the video did not bring it back. Switching to the Ideas (saved) tab and then back to Inspiration did. Do not scroll the feed to find the header.
- **OCR**: Apple Vision OCR read "AI" as "Al". It can also miss the dimmed `+ Add` chip. Fall back to the screenshot image.
- **Rejected topic**: "Beauty and makeup" did not become a chip in two attempts, and no error was shown. "Makeup" worked. When a topic fails twice, stop retrying it, report it, and offer a shorter phrase.
- **Long batches**: run one topic per call with a timeout. A batch loop stalled once after typing, and the topic was left unsent in the field.

## Boundaries

Change only the topic lists the user confirmed. Do not like, follow, save, use templates, or give per-video feedback while you are on the feed. See `edits-setup` for the full safety rules.

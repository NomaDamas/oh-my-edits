---
name: edits-mac-editing
description: Build or change a video in the Edits Mac app through its MCP server - place text, shapes, images and audio, animate them with keyframes and masks, set loudness, and verify by exporting. Use when the user asks the agent to edit a project in Edits on the Mac or to recreate a layout from another editor in Edits. Run edits-setup first if the `edits` MCP server is missing.
---

# Edit in the Edits Mac app

Everything here was observed in Edits 457.0.0 on macOS. Re-check a behavior before relying on it in another version.

Before you start, the `edits` MCP server must answer `state` (see `edits-setup`). Also read "Known behavior" in `skills/edits-setup/SKILL.md`: media paths must be under `~/Movies`, and every edit needs a read-back.

## Workflow

1. **Read first.** Call `state`, `tracks`, and `elements` before any edit. `state` can show a stale project name after a rename or a failed project switch, so confirm the open project by its elements.
2. **Keep the window still.** Keyframe, mask, and selection tools act at the playhead. Ask the user not to click or play in the Edits window while the agent edits, because a click moves the playhead and keyframes land at the wrong time.
3. **One edit, one read-back.** After each edit, read the element again with `getElement`, `elements`, `getTransformKeyframes`, or `exactElementValues`.
4. **Fix layer order.** New text and shapes go to any free track. After adding them, check the order and correct it with `moveToLayer`.
5. **Verify on an export.** Export under `~/Movies`, then measure the file (for example ffmpeg `ssim`, `psnr`, `ebur128`). `captureFrame` shows washed-out colors, so do not judge color from it.

## Units

- Positions are fractions of the canvas, 0 to 1, with the origin at the top left.
- `setTextPosition` places the center of the text.
- On a 9:16 canvas, a text size in pt equals the text's pixel size at 1080x1920 divided by 3. Glyph bounds matched another renderer within 1 px at that size.
- The timeline runs at 30 fps. `slipClip` and `addMediaPanelItemsToTimeline` snap source times and lengths to frames.
- `setVolume` is linear gain: 1 is 0 dB, 10 is +20 dB.

## Recipes

### Animate a shape

`addShape` draws the shape on a transparent image the size of the whole canvas. Transform keyframes move and scale that whole image, so a shape away from the center drifts twice as far and shrinks toward the canvas center. Choose one:

- Draw the shape at the canvas center and move it with transform keyframes.
- Keep the shape still and animate a mask on it.

### Animate a mask

`setMask` sets the starting mask, but it does not write keyframe values. To key a mask:

1. `setMask` with the starting shape.
2. `seek` to the keyframe time, then `selectById` the element.
3. `toggleMaskKeyframe` with `true`.
4. Read the fields with `valueFields`, then set them with `editValueField`.

Field values are in source pixels: the full canvas size for a shape, or the image size for a photo. When several fields show the same value (for example `0`), address the field by index.

### Follow a curve that the easing presets lack

`setKeyframeEasing` offers presets only: 0 is linear, 4 to 12 are sine, quad, and cubic variants (11 is ease-out cubic), and 13 to 14 are back curves. There is no custom bezier. To follow another curve exactly, add one keyframe per frame with the value sampled from that curve and keep linear easing between them. Export samples values only at frame times, so every frame matches.

### Set keyframe times exactly

Edits stores a keyframe time as (playhead - clip start), floored to 1/600 s. A clip that starts at 0.0667 s can store 0.065 s instead of 0.0667 s. Either start the clip at 0 s, or add 0.0001 s to each time you pass to `setTransformKeyframes`. Check the stored times with `getTransformKeyframes` or `exactElementValues`.

`setTransformKeyframes` removes the element's opacity keyframes. Set position and scale keyframes first, then opacity.

More observed behavior for text, tracks, and audio is in [references/pitfalls.md](references/pitfalls.md).

## Safety

The Edits app is signed in to the user's Instagram account. Export to files only. Do not share, post, or publish from Edits on the user's behalf.

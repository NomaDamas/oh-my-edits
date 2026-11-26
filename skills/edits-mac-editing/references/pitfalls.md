# Observed behavior of the Edits Mac MCP

Edits 457.0.0 on macOS. Each item was seen in a real project and checked by reading the element back or by comparing exports.

## Tracks and placement

- New text and shapes go to any free track, not to the top. Fix the stacking with `moveToLayer`.
- `addMediaPanelItemsToTimeline` keeps only one item when the same media alias appears twice in one call. Add the second use in a separate call.
- `addOverlay` places a photo for 3 s by default, on a new track each time.
- A transparent 1440x2560 PNG added with x 0.5, y 0.5, and scale 1 covers a 9:16 canvas 1:1. Use this to add pre-rendered text, for example captions with shadows.
- Placing a clip at the end of a track fails with "occupied" when its start equals the previous clip's end. Start it 0.001 s later.
- Deleting a main clip also deletes the overlays and library sound effects that sit in its time span. Read `elements` after the delete and add back what should stay.
- An audio or overlay track that becomes empty is removed. A later call with its old `trackId` fails with "track not found". Add without `trackId` to get a new track.
- `addMediaPanelItemsToTimeline` floors an audio item's length to whole frames (a 14.3999 s wav became 14.3667 s).

## Text

- `trim` on the right edge of a text element sets a wrong length. A 0.533 s caption trimmed by -2.633 became 24.133 s and pushed other captions to other tracks. Move text with `move` and read it back with `getElement`. Photo overlays trim correctly.
- `setEmphasis` with `backgroundPill` (color `#RRGGBBAA`) draws a dark pill behind a caption without a separate shape.
- `setTextFont` picks up a font that was just installed in `~/Library/Fonts` without restarting the app.

## Audio

- Mono sources play at full level on both channels. A mono file measured alone reads about 3 LU below what it adds to the stereo mix, so compute loudness gain on the stereo equivalent.
- The export has no limiter. True peaks can go above 0 dBTP, and a loudly mastered song peaks about 1.2 dB higher in the AAC export than in the input.
- `setDucking` (`any`, 0.5) on a wav added with `addMediaPanelItemsToTimeline` did not duck: two exports with and without it were the same. Bake volume ramps into the audio file and add it as one clip.
- `replaceAudio` accepts only songs from the music library and rejects imported wav files.
- `addSoundEffect` places the sound at the playhead. It goes on any audio track that has room there, which can be the voiceover track, or on a new track. Check its track with `elements` and move it if needed.
- After `splitAt` on an audio clip, deleting the middle piece does not move the later piece.

## Inspection and export

- `captureFrame` returns colors that look washed out. Exported colors are correct.
- A 9:16 project exports as 1440x2560 HEVC at 30 fps with the default settings.
- `setExportSettings` HDR (HLG, 10-bit) resets to SDR (8-bit bt709) after `closeProject` and `openProject`. Set it again right before each export and check the file with `ffprobe`.
- `importLUT` color differs from ffmpeg `lut3d` on HLG footage (bluer, darker). See "Apply a LUT" in `SKILL.md`.

## Speed and keyframes

- `setSpeed` on a main clip ripples: later main clips move. Read `elements` after each speed change.
- On a speed-changed clip, `setTransformKeyframes` takes timeline seconds from the clip start, but `setKeyframeEasing` takes `sourceInPoint` plus that time. See "Set keyframe times exactly" in `SKILL.md`.
- `setKeyframeEasing` preset 3 is ease-in-out.
- `export` returns before the file is complete. Poll `exportStatus` until it reports completion before reading the file.
- `state.projectName` showed "test" for a project with another name. `state.projectTitle` was correct.
- The tool list follows the screen. `duplicateProject`, `duplicateViaMcomp`, `exportMcomp`, and `importMcomp` appear only on the home screen.
- `exactElementValues` and `getTransformKeyframes` return the stored keyframe times and values, including floored times.

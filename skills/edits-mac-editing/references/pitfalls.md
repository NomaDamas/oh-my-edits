# Observed behavior of the Edits Mac MCP

Edits 457.0.0 on macOS. Each item was seen in a real project and checked by reading the element back or by comparing exports.

## Tracks and placement

- New text and shapes go to any free track, not to the top. Fix the stacking with `moveToLayer`.
- `addMediaPanelItemsToTimeline` keeps only one item when the same media alias appears twice in one call. Add the second use in a separate call.
- `addOverlay` places a photo for 3 s by default, on a new track each time.
- A transparent 1440x2560 PNG added with x 0.5, y 0.5, and scale 1 covers a 9:16 canvas 1:1. Use this to add pre-rendered text, for example captions with shadows.
- Placing a clip at the end of a track fails with "occupied" when its start equals the previous clip's end. Start it 0.001 s later.

## Text

- `trim` on the right edge of a text element sets a wrong length. A 0.533 s caption trimmed by -2.633 became 24.133 s and pushed other captions to other tracks. Move text with `move` and read it back with `getElement`. Photo overlays trim correctly.
- `setEmphasis` with `backgroundPill` (color `#RRGGBBAA`) draws a dark pill behind a caption without a separate shape.
- `setTextFont` picks up a font that was just installed in `~/Library/Fonts` without restarting the app.

## Audio

- Mono sources play at full level on both channels. A mono file measured alone reads about 3 LU below what it adds to the stereo mix, so compute loudness gain on the stereo equivalent.
- The export has no limiter. True peaks can go above 0 dBTP, and a loudly mastered song peaks about 1.2 dB higher in the AAC export than in the input.
- `setDucking` (`any`, 0.5) on a wav added with `addMediaPanelItemsToTimeline` did not duck: two exports with and without it were the same. Bake volume ramps into the audio file and add it as one clip.
- `replaceAudio` accepts only songs from the music library and rejects imported wav files.
- `addSoundEffect` places the sound at the playhead on a new audio track.
- After `splitAt` on an audio clip, deleting the middle piece does not move the later piece.

## Inspection and export

- `captureFrame` returns colors that look washed out. Exported colors are correct.
- A 9:16 project exports as 1440x2560 HEVC at 30 fps with the default settings. `setExportSettings` was not tested.
- `exactElementValues` and `getTransformKeyframes` return the stored keyframe times and values, including floored times.

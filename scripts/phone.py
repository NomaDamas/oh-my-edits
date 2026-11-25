#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyobjc-framework-Vision",
#     "pyobjc-framework-Cocoa",
# ]
# ///
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NomaDamas
"""Drive an iPhone through the `ipb` CLI (https://github.com/ipbtools/ipb).

    uv run scripts/phone.py doctor      # wraps `ipb doctor`, prints PASS or FAIL
    uv run scripts/phone.py run <<'PY'  # runs the script on stdin with ph_* in globals
    # task: <what the whole task is>
    # step: <what this script does>
    ph_tap_tab("Ideas", on_screen=["Inspiration"], expected=["Saved"])
    PY

Every ph_* helper reads a fresh screenshot (Apple Vision OCR, ko-KR and en-US) before
it acts, and returns or prints only the labels you ask for. Coordinates are points:
screenshot pixels divided by PT_SCALE. Only `run` touches the phone, and only as the
submitted script directs. Whole-screen results are `Screen` objects that hide their
text when printed.
"""
from __future__ import annotations

import argparse
import contextlib
import math
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata


PT_SCALE = 3          # px per point. It sizes guard distances and converts to ipb's 0..1; the two cancel.
DARK_PNG_BYTES = 30_000
DOCTOR_TIMEOUT = 120
DEFAULT_TIMEOUT = 30
# Seconds per ipb verb. Every ipb call is bounded; a call that exceeds its bound is killed
# (with its children) and raised as IpbTimeout.
IPB_TIMEOUTS = {"tap": 20, "home": 20, "scroll": 30, "text": 40, "screenshot": 45}
# The iOS paste prompt buttons (English and Korean UI strings).
ALLOW_PASTE = ("Allow Paste", "붙여넣기 허용")
TAB_BAR_TOP = 0.85    # tab-bar labels sit in the bottom 15% of the screen
TAB_LIFT_MAX = 40     # points
MIN_PARTIAL = 3       # in presence proofs, shorter labels match a whole OCR line only
REPLACE_PREFIX = 40   # characters of the first line that must show after a replace

_last_window = None


class IpbTimeout(RuntimeError):
    """An ipb call outlived its bound and was killed."""


# ---------------------------------------------------------------------------
# Subprocess

def _kill_group(process):
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.communicate(timeout=5)


def _run(cmd, timeout):
    """Run a command with a hard bound. On timeout the whole process group is killed,
    so a child that holds the output pipe cannot keep the call hanging."""
    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True)
    except FileNotFoundError as error:
        raise RuntimeError(
            f"{cmd[0]} is not installed or not on PATH; see https://github.com/ipbtools/ipb") from error
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        label = " ".join(str(part) for part in cmd[:2])
        raise IpbTimeout(
            f"{label} timed out after {timeout}s and was killed. Its effect on the phone is "
            "unknown: observe the screen before repeating it.") from None
    except BaseException:
        _kill_group(process)      # Ctrl-C and the like: the new session would otherwise outlive us
        raise
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _ipb(*args, timeout=None):
    bound = timeout if timeout is not None else IPB_TIMEOUTS.get(args[0], DEFAULT_TIMEOUT)
    result = _run(["ipb", *args], bound)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"ipb {args[0]} failed: {detail[0]}")
    return result


# ---------------------------------------------------------------------------
# Matching. One matcher serves on_screen, expected, absent, ph_observe, ph_find and the
# typed-text check. OCR drops or invents edge glyphs ("Projects •", "* Inspiration •
# Templates o") and confuses look-alikes ("AI" read as "Al"), so lines and labels are
# folded: NFKC, casefold, then i/I/l/1/| -> l and 0/O -> o.

_LOOKALIKE = str.maketrans({"i": "l", "1": "l", "|": "l", "0": "o"})
_EDGE = re.compile(r"^[\W_]+|[\W_]+$")


def _fold(text):
    folded = unicodedata.normalize("NFKC", str(text)).casefold().translate(_LOOKALIKE)
    return " ".join(folded.split())


def _core(text):
    """Folded text without leading or trailing glyphs and punctuation."""
    return _EDGE.sub("", _fold(text))


def _match(text, label, min_partial=MIN_PARTIAL):
    """'exact' when the lines are equal after trimming edge glyphs, 'partial' when the label
    sits inside a longer line, else None. Presence proofs (on_screen, expected, absent) use
    MIN_PARTIAL, so a label shorter than that matches a whole line only; searches pass 1."""
    line, core = _fold(text), _core(label)
    if _EDGE.sub("", line) == core:
        return "exact"
    if len(core) >= min_partial and core in line:
        return "partial"
    return None


def _labels(expected):
    labels = [expected] if isinstance(expected, str) else list(expected)
    if not labels or any(not isinstance(s, str) or not _core(s) for s in labels):
        raise ValueError("Expected at least one screen label with a letter or digit in it.")
    return labels


def _seen(boxes, label):
    return any(_match(box["text"], label) for box in boxes)


def _all_seen(boxes, labels):
    return all(_seen(boxes, label) for label in labels)


def _any_seen(boxes, labels):
    return any(_seen(boxes, label) for label in labels)


def _unique(boxes, label):
    """The one OCR line that is the label (after trimming). A label found only inside longer
    lines is never tapped: the centre of the line is not the label."""
    exact = [box for box in boxes if _match(box["text"], label) == "exact"]
    if len(exact) == 1:
        return exact[0]
    if exact:
        raise RuntimeError(f"Expected one match for {label!r}; found {len(exact)}.")
    inside = sum(1 for box in boxes if _match(box["text"], label) == "partial")
    if inside:
        raise RuntimeError(
            f"{label!r} appears only inside {inside} longer OCR line(s); no tap sent. Locate it "
            "with ph_find(...) and tap the returned point with ph_tap_point(...).")
    raise RuntimeError(f"Expected one match for {label!r}; found 0.")


def _locate(box, label):
    """A copy of `box` for a match. For a label inside a longer line, x and w are estimated
    from the character position, because OCR reports only the whole line."""
    kind = _match(box["text"], label, 1)
    found = {**box, "match": kind}
    if kind == "partial" and "w" in box:
        line, core = _fold(box["text"]), _core(label)
        start = line.find(core)
        found["line_x"], found["line_w"] = box["x"], box["w"]
        found["w"] = round(box["w"] * len(core) / len(line), 1)
        found["x"] = round(box["x"] - box["w"] / 2 + box["w"] * (start + len(core) / 2) / len(line), 1)
    return found


# ---------------------------------------------------------------------------
# Screenshot and OCR

def _png_size(path):
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("ipb screenshot is not a PNG.")
    return struct.unpack(">II", head[16:24])


def _read_image(image_path, window):
    """Vision boxes in window points; no screen text is printed."""
    import Vision
    from Foundation import NSURL
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    languages = [s.strip() for s in os.environ.get(
        "EDITS_PHONE_OCR_LANGS", "ko-KR,en-US").split(",") if s.strip()]
    if not languages:
        raise ValueError("EDITS_PHONE_OCR_LANGS must name at least one language.")
    request.setRecognitionLanguages_(languages)
    if hasattr(request, "setAutomaticallyDetectsLanguage_"):
        request.setAutomaticallyDetectsLanguage_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
        NSURL.fileURLWithPath_(str(image_path)), None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision OCR failed: {error}")
    boxes = []
    for result in request.results() or []:
        candidates = result.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        box = result.boundingBox()
        boxes.append({
            "text": str(candidate.string()),
            "confidence": round(float(candidate.confidence()), 3),
            "x": round(window["x"] + (box.origin.x + box.size.width / 2) * window["w"], 1),
            "y": round(window["y"] + (1 - box.origin.y - box.size.height / 2) * window["h"], 1),
            "w": round(box.size.width * window["w"], 1),
            "h": round(box.size.height * window["h"], 1),
        })
    return boxes


def _snapshot(capture_path=None):
    """Fresh `ipb screenshot` -> (OCR boxes in points, window). A dark capture with no text
    means the phone is locked or its screen is off."""
    global _last_window
    output_fd = None
    if capture_path is not None:
        output_fd = os.open(Path(capture_path).expanduser(),
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        # A private directory keeps the temporary capture owner-only whatever the umask.
        with tempfile.TemporaryDirectory(prefix="phone-observe-") as directory:
            destination = Path(directory) / "capture.png"
            _ipb("screenshot", str(destination))
            destination.chmod(0o600)
            width, height = _png_size(destination)
            window = {"x": 0, "y": 0, "w": width / PT_SCALE, "h": height / PT_SCALE}
            _last_window = window
            if output_fd is not None:
                with os.fdopen(output_fd, "wb") as output:
                    output_fd = None
                    with destination.open("rb") as source:
                        shutil.copyfileobj(source, output)
            boxes = _read_image(destination, window)
            if not boxes and destination.stat().st_size < DARK_PNG_BYTES:
                raise RuntimeError(
                    "Screenshot is dark and has no text: the phone is locked or its screen is "
                    "off. Ask the user to unlock it and keep the screen on, then retry.")
            return boxes, window
    finally:
        if output_fd is not None:
            os.close(output_fd)


class Screen(list):
    """OCR boxes whose print/repr hides the text. Whole-screen results of ph_observe(all_text=True),
    ph_wait, ph_tap, ph_tap_tab and ph_scroll are this type so `print(ph_tap(...))` cannot dump
    private content. Iterate it, or filter with `ph_observe(contains=...)`, to read labels."""

    def __repr__(self):
        return (f"<Screen: {len(self)} OCR lines hidden; print only labels you need, e.g. "
                "ph_observe(contains=[...])>")

    __str__ = __repr__


def ph_observe(contains=None, capture_path=None, all_text=False):
    """Read Korean/English text from a fresh screenshot. Pass `contains` to get only the lines
    that match (tolerant matching, see ph_find). Without it the whole screen is returned only
    when `all_text=True`, so a bare `print(ph_observe())` cannot leak unrelated private content.
    `capture_path` also saves the screenshot to a new owner-only file (never overwrites)."""
    if contains is None and not all_text:
        raise ValueError(
            "ph_observe() needs contains=[...] (print only relevant labels) or all_text=True "
            "(whole screen, may include private content; do not print it).")
    terms = _labels(contains) if contains is not None else None
    boxes, _window = _snapshot(capture_path)
    if terms is None:
        return Screen(boxes)
    return [box for box in boxes if any(_match(box["text"], term, 1) for term in terms)]


def ph_find(text):
    """Boxes of the OCR lines that contain `text`, top to bottom, from a fresh screenshot.

    Each box has the OCR line in `text`, `x` and `y` (centre, points), `w`, `h`, and `match`
    ('exact' when the line is the label, 'partial' when it is inside a longer line). For a
    partial match `x` and `w` are estimated from the character position, and the OCR line's own
    centre and width are kept in `line_x` and `line_w`. Use it to locate a
    target, then tap with ph_tap_point(box['x'], box['y'], on_screen=[...])."""
    if not isinstance(text, str):
        raise ValueError("ph_find takes one string.")
    label = _labels(text)[0]
    boxes, _window = _snapshot()
    found = [_locate(box, label) for box in boxes if _match(box["text"], label, 1)]
    return sorted(found, key=lambda box: (box["y"], box["x"]))


def ph_screen_size():
    """(width, height) of the screen in points, from the latest capture (takes one if none yet)."""
    if _last_window is None:
        _snapshot()
    return _last_window["w"], _last_window["h"]


def _timeout(timeout):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    return timeout


def _proof(boxes, expected, absent):
    if _all_seen(boxes, expected) and not _any_seen(boxes, absent):
        raise ValueError("Result is already visible; require a new label or a source label to disappear.")


def ph_wait(expected, timeout=12, absent=()):
    """Wait until every expected label is visible and no `absent` label is. The timeout is the
    polling budget; a capture that returns after it does not count as success."""
    wanted = _labels(expected)
    missing = _labels(absent) if absent else []
    _timeout(timeout)
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Expected screen labels did not appear in time: {wanted!r}")
        boxes = ph_observe(all_text=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Expected screen labels did not appear in time: {wanted!r}")
        if _all_seen(boxes, wanted) and not _any_seen(boxes, missing):
            return Screen(boxes)
        time.sleep(min(0.4, remaining))


# ---------------------------------------------------------------------------
# Taps

# Destructive rows sit next to ordinary ones in Settings-style lists. Matched on the raw
# line and on the folded line, so folding never makes the guard weaker.
_DANGER_TERMS = ("erase", "reset", "delete", "remove", "wipe", "factory", "sign out", "log out",
                 "offload", "초기화", "재설정", "지우기", "삭제", "제거", "로그아웃")
_DANGER_RAW = re.compile("|".join(re.escape(term) for term in _DANGER_TERMS), re.IGNORECASE)
_DANGER_FOLDED = tuple(_fold(term) for term in _DANGER_TERMS)


def _is_danger(text):
    return bool(_DANGER_RAW.search(text)) or any(term in _fold(text) for term in _DANGER_FOLDED)


def _danger_near(boxes, y, reach):
    return [box["text"] for box in boxes if _is_danger(box["text"]) and abs(box["y"] - y) <= reach]


def _refuse_danger(names, allow_danger):
    if names and not allow_danger:
        raise RuntimeError(
            f"Destructive label near the tap target {names!r}; no tap sent. Pass "
            "allow_danger=True only for a target the user explicitly approved.")


def _norm(x, y, window):
    nx, ny = x / window["w"], y / window["h"]
    if not (0 <= nx <= 1 and 0 <= ny <= 1):
        raise RuntimeError(f"Point ({x:.0f}, {y:.0f}) is outside the screen; no tap sent.")
    return f"{nx:.4f}", f"{ny:.4f}"


def _tap(x, y, window):
    nx, ny = _norm(x, y, window)
    _ipb("tap", nx, ny)


def _tap_label(label, on_screen, expected, timeout, absent, allow_danger, tab_lift=None):
    """Shared by ph_tap and ph_tap_tab. `tab_lift` (points) not None means tab-bar mode."""
    before_labels, after_labels = _labels(on_screen), _labels(expected)
    absent_labels = _labels(absent) if absent else []
    _timeout(timeout)
    _labels(label)
    if tab_lift is not None:
        if not 0 <= tab_lift <= TAB_LIFT_MAX:
            raise ValueError(f"lift must be 0..{TAB_LIFT_MAX} points.")
        if any(_match(label, name) for name in after_labels):
            raise ValueError(
                f"{label!r} stays visible after the tap, so it cannot prove the tab opened. "
                "Give a label that only the destination screen shows.")
    boxes, window = _snapshot()
    if not _all_seen(boxes, before_labels):
        raise RuntimeError("Expected source screen is not visible; no tap sent.")
    _proof(boxes, after_labels, absent_labels)
    target = _unique(boxes, label)
    if tab_lift is not None:
        if target["y"] < window["y"] + window["h"] * TAB_BAR_TOP:
            raise RuntimeError(f"{label!r} is not in the tab bar (bottom screen area); no tap sent.")
        _refuse_danger(_danger_near(boxes, target["y"] - tab_lift, 12 + tab_lift), allow_danger)
        target = {**target, "y": target["y"] - tab_lift}
    else:
        _refuse_danger(_danger_near(boxes, target["y"], 12), allow_danger)
    _tap(target["x"], target["y"], window)
    return ph_wait(after_labels, timeout, absent_labels)


def ph_tap(label, on_screen, expected, timeout=12, absent=(), allow_danger=False):
    """Tap the one OCR line that is `label`, then verify the destination. `on_screen` labels
    must all be visible in a fresh capture first, and the result must show a new label
    (`expected`) or lose a source label (`absent`). A label found only inside a longer line is
    refused: use ph_find + ph_tap_point."""
    return _tap_label(label, on_screen, expected, timeout, absent, allow_danger)


def ph_tap_tab(label, on_screen, expected, timeout=12, absent=(), allow_danger=False, lift=0):
    """Tap a bottom tab-bar label. The tab label stays visible afterwards, so `expected` must
    name a label only the destination screen shows (never the tab label itself) and must not
    be visible before the tap. `lift` moves the tap up from the label centre (points) for apps
    whose tab ignores the text and reacts to the icon."""
    return _tap_label(label, on_screen, expected, timeout, absent, allow_danger, tab_lift=lift)


def ph_tap_point(x, y, on_screen=None, *, allow_danger=False):
    """Tap a point (screen points, from ph_find or ph_screen_size) after a fresh capture.
    Every `on_screen` label must be visible in that capture, and a point within 45 points of a
    destructive label is refused. Returns nothing: observe afterwards to confirm the result."""
    required = _labels(on_screen) if on_screen is not None else []
    boxes, window = _snapshot()
    if not _all_seen(boxes, required):
        raise RuntimeError("Expected source screen is not visible; no tap sent.")
    _refuse_danger(_danger_near(boxes, y, 45), allow_danger)
    _tap(x, y, window)


# ---------------------------------------------------------------------------
# Text, home, scroll

def _first_line(text):
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            return line[:REPLACE_PREFIX].rstrip()
    return ""


def ph_type_text(text, replace=False):
    """Paste `text` into the focused field with `ipb text`, then require it on screen. This
    overwrites the device clipboard. The first paste in an app makes iOS ask "Allow Paste";
    the helper answers it once. `replace=True` replaces the field's whole content
    (`ipb text --replace-all`). Apps may trim or rewrite pasted text and long text scrolls, so
    with `replace` only the first non-empty line's first 40 characters must show; a prefilled
    value that starts the same can pass, so read the field afterwards when that matters. Text
    is compared after folding look-alikes, so an OCR read of "AI" as "Al" still passes."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("ph_type_text needs non-empty text.")
    if text.startswith("-"):
        raise ValueError("ipb text cannot start with '-'; add a leading character.")
    _ipb("text", *(["--replace-all"] if replace else []), text)
    boxes, window = _snapshot()
    asks = [box for box in boxes
            if any(_match(box["text"], label) == "exact" for label in ALLOW_PASTE)]
    if len(asks) > 1:
        raise RuntimeError("Several paste prompts are visible; no tap sent. Observe and answer it yourself.")
    if asks:
        # iOS asks once per app. Answer it once, then require the text.
        _tap(asks[0]["x"], asks[0]["y"], window)
        time.sleep(0.6)
        boxes, window = _snapshot()
    wanted = _fold(_first_line(text) if replace else text)
    if wanted not in _fold(" ".join(box["text"] for box in boxes)):
        raise RuntimeError(
            f"Typed text {(_first_line(text) if replace else text)!r} is not visible after input "
            "(stale clipboard or no focused field). Results on screen belong to another query; "
            "do not tap them.")


def ph_home():
    """Go to the Home Screen (`ipb home`)."""
    _ipb("home")


def ph_scroll(direction, on_screen, amount=0.3, at=None):
    """Scroll once after confirming the expected screen; return the screen after (a Screen).

    `direction` is what you want to see ('down' reveals lower content). `at` is {'x', 'y'} in
    points (default: screen centre). Unit-tested only: confirm on the first use that the
    returned screen moved the way you expected."""
    labels = _labels(on_screen)
    if direction not in ("up", "down", "left", "right"):
        raise ValueError("direction must be up, down, left or right.")
    boxes, window = _snapshot()
    if not _all_seen(boxes, labels):
        raise RuntimeError("Expected source screen is not visible; no scroll sent.")
    px, py = (at["x"], at["y"]) if at else (window["w"] / 2, window["h"] / 2)
    nx, ny = _norm(px, py, window)
    dx, dy = {"down": (0, -amount), "up": (0, amount),
              "right": (-amount, 0), "left": (amount, 0)}[direction]
    _ipb("scroll", nx, ny, f"{dx:.3f}", f"{dy:.3f}")
    time.sleep(0.8)
    return ph_observe(all_text=True)


# ---------------------------------------------------------------------------
# Command line

HELPERS = ("ph_observe", "ph_find", "ph_screen_size", "ph_wait", "ph_tap", "ph_tap_tab",
           "ph_tap_point", "ph_type_text", "ph_home", "ph_scroll")


def doctor():
    """Run `ipb doctor` and print PASS or FAIL. Pass means a result line with 0 failures."""
    try:
        result = _run(["ipb", "doctor"], DOCTOR_TIMEOUT)
    except RuntimeError as error:
        print(f"doctor: FAIL - {error}", flush=True)
        return 1
    output = (result.stdout + result.stderr).rstrip()
    print(output, flush=True)
    summary = re.search(r"result:\s*(\d+) failure\(s\)", output)
    failures = int(summary.group(1)) if summary else (0 if result.returncode == 0 else 1)
    warnings = len(re.findall(r"^WARN\b", output, re.MULTILINE))
    if failures == 0:
        print(f"doctor: PASS (0 failures, {warnings} warning(s))", flush=True)
        return 0
    print(f"doctor: FAIL ({failures} failure(s)). Fix the FAIL lines above, then run doctor again.",
          flush=True)
    return 1


def _bootstrap(script):
    lines = script.splitlines(keepends=True)
    if len(lines) < 2 or not lines[0].startswith("# task:") or not lines[1].startswith("# step:"):
        raise ValueError("Start the script with # task: and # step: comments.")
    return lines[0].strip(), lines[1].strip()


def _namespace():
    names = {name: globals()[name] for name in HELPERS}
    names.update({"Screen": Screen, "__name__": "__phone_script__"})
    return names


def _script_line(error):
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        if frame.filename == "<phone-script>":
            return frame.lineno
    return None


def run_script(script):
    """Run a task script with the ph_* helpers in its globals. Output is flushed per line so
    progress shows up while the script is still running."""
    task, step = _bootstrap(script)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(line_buffering=True, write_through=True)
    if not shutil.which("ipb"):
        raise RuntimeError("ipb is not installed or not on PATH; see https://github.com/ipbtools/ipb")
    print(f"phone: {task}", file=sys.stderr, flush=True)
    print(f"phone: {step}", file=sys.stderr, flush=True)
    try:
        exec(compile(script, "<phone-script>", "exec"), _namespace())
    except (RuntimeError, ValueError, TimeoutError, OSError) as error:
        line = _script_line(error)
        where = f" (script line {line})" if line else ""
        raise RuntimeError(f"{type(error).__name__}: {error}{where}") from None
    sys.stdout.flush()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="phone.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="run `ipb doctor` and print PASS or FAIL")
    commands.add_parser("run", help="run the Python script on stdin with the ph_* helpers")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if sys.stdin.isatty():
        raise ValueError("Pipe a script to stdin, for example: phone.py run <<'PY' ... PY")
    return run_script(sys.stdin.read())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"phone: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None

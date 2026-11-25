# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NomaDamas
"""Unit tests for scripts/phone.py. No device, no ipb, and no Vision are needed: ipb is a
fake subprocess runner or a fake executable on PATH, and the screen is a list of OCR boxes."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phone.py"
SPEC = importlib.util.spec_from_file_location("phone_helper", SCRIPT)
phone = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phone)

WIN = {"x": 0, "y": 0, "w": 400, "h": 800}


def box(text, y=100, x=40, **extra):
    return {"text": text, "x": x, "y": y, **extra}


def png(width=1206, height=2622, pad=0):
    head = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    return head + b"\0" * pad


def fake_ipb(directory, body):
    """An executable named `ipb` in `directory`."""
    path = Path(directory) / "ipb"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def path_with(directory):
    return {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}


class Device(unittest.TestCase):
    """ipb calls are recorded instead of run; each capture returns the next screen (the last
    one repeats)."""

    def setUp(self):
        self.calls = []
        self.captures = 0
        self.shots = [[]]
        for target, new in (("_run", self.fake_run), ("_snapshot", self.fake_snapshot),
                            ("_last_window", None)):
            patcher = patch.object(phone, target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        sleep = patch.object(phone.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def fake_run(self, cmd, timeout):
        self.calls.append((list(cmd), timeout))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def fake_snapshot(self, capture_path=None):
        index = min(self.captures, len(self.shots) - 1)
        self.captures += 1
        phone._last_window = dict(WIN)
        return list(self.shots[index]), dict(WIN)

    def screens(self, *shots):
        self.shots, self.captures = list(shots), 0

    def ipb_calls(self, verb):
        return [cmd for cmd, _timeout in self.calls if cmd[:2] == ["ipb", verb]]


class Matching(unittest.TestCase):
    def test_trailing_and_leading_glyphs_are_trimmed(self):
        self.assertEqual(phone._match("Projects •", "Projects"), "exact")
        self.assertEqual(phone._match("• Settings", "Settings"), "exact")
        self.assertEqual(phone._match("+ Add", "+ Add"), "exact")
        self.assertEqual(phone._match("설정 •", "설정"), "exact")

    def test_label_inside_a_longer_line_is_partial(self):
        header = "* Inspiration • Templates o"
        self.assertEqual(phone._match(header, "Inspiration"), "partial")
        self.assertEqual(phone._match(header, "templates"), "partial")
        self.assertIsNone(phone._match(header, "Projects"))

    def test_matching_ignores_case(self):
        self.assertEqual(phone._match("YOUR INSPIRATION", "your inspiration"), "exact")

    def test_ocr_lookalikes_match(self):
        self.assertEqual(phone._match("Al tools", "AI tools"), "exact")
        self.assertEqual(phone._match("AI tools", "Al tools"), "exact")
        self.assertEqual(phone._match("D0ne", "Done"), "exact")
        self.assertEqual(phone._match("Top 1O", "Top lo"), "exact")
        self.assertEqual(phone._match("Maii", "Mail"), "exact")
        self.assertIsNone(phone._match("Al tools", "AI toots"))

    def test_short_labels_never_match_inside_a_line(self):
        self.assertIsNone(phone._match("AI tools", "AI"))
        self.assertEqual(phone._match("AI", "AI"), "exact")
        self.assertEqual(phone._match("AI tools", "AI t"), "partial")

    def test_searches_can_match_short_text_inside_a_line(self):
        self.assertEqual(phone._match("Available 94 GB", "GB", 1), "partial")
        self.assertIsNone(phone._match("Available 94 GB", "GB"))

    def test_labels_need_a_letter_or_digit(self):
        for bad in ("", "  ", "•", ["Done", "+"], []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                phone._labels(bad)


class Observation(Device):
    def test_whole_screen_needs_explicit_opt_in(self):
        self.screens([box("private")])
        with self.assertRaisesRegex(ValueError, "contains"):
            phone.ph_observe()
        self.assertEqual(self.captures, 0)          # refused before any capture

    def test_filters_unrelated_private_text(self):
        self.screens([box("private message"), box("Available 94 GB")])
        self.assertEqual(phone.ph_observe(contains=["GB"]), [box("Available 94 GB")])

    def test_contains_uses_tolerant_matching(self):
        self.screens([box("Projects •"), box("other")])
        self.assertEqual(phone.ph_observe(contains="Projects"), [box("Projects •")])
        self.screens([box("Al tools"), box("other")])
        self.assertEqual(phone.ph_observe(contains="AI tools"), [box("Al tools")])

    def test_whole_screen_results_hide_text_when_printed(self):
        self.screens([box("auth history")])
        screen = phone.ph_observe(all_text=True)
        self.assertIsInstance(screen, phone.Screen)
        self.assertNotIn("auth history", repr(screen))
        self.assertNotIn("auth history", str(screen))
        self.assertEqual(screen[0]["text"], "auth history")     # still readable in code

    def test_wait_returns_a_hidden_screen(self):
        self.screens([box("Done")])
        self.assertIsInstance(phone.ph_wait("Done"), phone.Screen)


class Waiting(Device):
    def test_static_wrong_screen_times_out(self):
        self.screens([box("Pasting...")])
        with patch.object(phone.time, "monotonic", side_effect=[0, 0, 2]):
            with self.assertRaises(TimeoutError):
                phone.ph_wait("Settings", timeout=1)

    def test_late_expected_label_is_not_success(self):
        self.screens([box("Settings")])
        with patch.object(phone.time, "monotonic", side_effect=[0, 0, 2]):
            with self.assertRaises(TimeoutError):
                phone.ph_wait("Settings", timeout=1)

    def test_expected_label_with_source_still_visible_is_not_success(self):
        self.screens([box("General"), box("iPhone Storage")])
        with patch.object(phone.time, "monotonic", side_effect=[0, 0, 0.1, 2]):
            with self.assertRaises(TimeoutError):
                phone.ph_wait("iPhone Storage", timeout=1, absent="General")

    def test_wait_matches_labels_with_ocr_noise(self):
        self.screens([box("Projects •"), box("Al tools")])
        phone.ph_wait(["Projects", "AI tools"])

    def test_invalid_timeout(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    phone.ph_wait("Done", timeout=timeout)
                with self.assertRaises(ValueError):
                    phone.ph_tap("Clear", on_screen="Storage", expected="Done", timeout=timeout)
        self.assertEqual(self.calls, [])


class TapTargets(Device):
    def test_on_screen_tolerates_trailing_glyphs_and_longer_header_lines(self):
        self.screens([box("* Inspiration • Templates o", 50), box("Projects •", 100), box("Add", 300)],
                     [box("Done")])
        phone.ph_tap("Add", on_screen=["Projects", "Inspiration", "Templates"], expected="Done")
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.3750"])

    def test_tap_requires_the_source_screen_and_a_unique_target(self):
        for boxes in ([box("Other"), box("Delete")], [box("Storage"), box("Delete"), box("Delete")]):
            with self.subTest(boxes=boxes):
                self.screens(boxes)
                with self.assertRaises(RuntimeError):
                    phone.ph_tap("Delete", on_screen="Storage", expected="Done")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_label_only_inside_a_longer_line_is_not_tapped(self):
        self.screens([box("* Inspiration • Templates o", 50)])
        with self.assertRaisesRegex(RuntimeError, "ph_find"):
            phone.ph_tap("Templates", on_screen="Inspiration", expected="Done")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_exact_line_wins_over_longer_lines_that_contain_the_label(self):
        self.screens([box("Storage", 50), box("Add", 300), box("Add to story", 400)], [box("Done")])
        phone.ph_tap("Add", on_screen="Storage", expected="Done")
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.3750"])

    def test_two_exact_lines_are_ambiguous(self):
        self.screens([box("Storage", 50), box("Add", 300), box("Add •", 400)])
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            phone.ph_tap("Add", on_screen="Storage", expected="Done")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_existing_destination_label_is_not_proof_of_navigation(self):
        self.screens([box("General"), box("iPhone Storage")])
        with self.assertRaisesRegex(ValueError, "already visible"):
            phone.ph_tap("iPhone Storage", on_screen="General", expected="iPhone Storage")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_source_disappearance_can_prove_navigation(self):
        self.screens([box("General"), box("iPhone Storage")])
        with patch.object(phone, "ph_wait") as wait:
            phone.ph_tap("iPhone Storage", on_screen="General", expected="iPhone Storage", absent="General")
        wait.assert_called_once_with(["iPhone Storage"], 12, ["General"])

    def test_failed_result_check_does_not_repeat_the_tap(self):
        self.screens([box("Storage"), box("Clear")])
        with patch.object(phone, "ph_wait", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                phone.ph_tap("Clear", on_screen="Storage", expected="Done")
        self.assertEqual(len(self.ipb_calls("tap")), 1)

    def test_point_outside_the_screen_is_refused(self):
        self.screens([box("Home")])
        with self.assertRaisesRegex(RuntimeError, "outside"):
            phone.ph_tap_point(500, 10)
        self.assertEqual(self.ipb_calls("tap"), [])


class Guards(Device):
    def test_tap_refuses_destructive_target_and_same_row_neighbour(self):
        for boxes in ([box("Settings"), box("Reset All Settings", 100)],
                      [box("Settings"), box("Erase All Content and Settings", 108)]):
            with self.subTest(boxes=boxes):
                self.screens(boxes)
                with self.assertRaisesRegex(RuntimeError, "Destructive"):
                    phone.ph_tap("Settings", on_screen="Settings", expected="Done")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_guard_sees_through_ocr_lookalikes(self):
        self.screens([box("Settings"), box("DeIete account", 104)])      # capital I for lowercase l
        with self.assertRaisesRegex(RuntimeError, "Destructive"):
            phone.ph_tap("Settings", on_screen="Settings", expected="Done")
        self.screens([box("SIgn out", 100)])
        with self.assertRaisesRegex(RuntimeError, "Destructive"):
            phone.ph_tap_point(40, 100)
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_guard_covers_korean_labels(self):
        self.screens([box("모든 설정 초기화", 120)])
        with self.assertRaisesRegex(RuntimeError, "Destructive"):
            phone.ph_tap_point(40, 100)

    def test_tap_point_refuses_next_to_destructive_row_unless_allowed(self):
        self.screens([box("Record Video", 100), box("Reset All Settings", 130)])
        with self.assertRaisesRegex(RuntimeError, "Destructive"):
            phone.ph_tap_point(40, 100)
        self.assertEqual(self.ipb_calls("tap"), [])
        phone.ph_tap_point(40, 100, allow_danger=True)
        self.assertEqual(len(self.ipb_calls("tap")), 1)

    def test_allow_danger_is_keyword_only(self):
        with self.assertRaises(TypeError):
            phone.ph_tap_point(40, 100, None, True)

    def test_tap_point_far_from_destructive_rows_taps(self):
        self.screens([box("Reset", 400)])
        phone.ph_tap_point(40, 100)
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.1250"])

    def test_tap_point_on_screen_precondition(self):
        self.screens([box("Home", 200)])
        with self.assertRaisesRegex(RuntimeError, "no tap sent"):
            phone.ph_tap_point(40, 750, on_screen=["Settings"])
        self.assertEqual(self.ipb_calls("tap"), [])
        phone.ph_tap_point(40, 750, on_screen="Home")
        self.assertEqual(len(self.ipb_calls("tap")), 1)


class TabTaps(Device):
    SCREEN = [box("Home", 200), box("Inbox", 760), box("Profile", 770)]

    def test_tab_tap_proves_navigation_with_a_new_destination_label(self):
        self.screens(self.SCREEN)
        with patch.object(phone, "ph_wait") as wait:
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Edit profile")
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.9625"])
        wait.assert_called_once_with(["Edit profile"], 12, [])

    def test_tab_label_cannot_prove_its_own_tap(self):
        self.screens(self.SCREEN)
        with self.assertRaisesRegex(ValueError, "stays visible"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Profile")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_tab_expected_labels_already_visible_are_refused(self):
        self.screens(self.SCREEN)
        with self.assertRaisesRegex(ValueError, "already visible"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Inbox")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_tab_label_outside_the_bottom_bar_is_refused(self):
        self.screens([box("Home", 200), box("Profile", 300)])
        with self.assertRaisesRegex(RuntimeError, "not in the tab bar"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Edit profile")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_tab_lift_moves_the_tap_up_and_is_bounded(self):
        self.screens(self.SCREEN)
        with patch.object(phone, "ph_wait"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Edit profile", lift=10)
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.9500"])
        with self.assertRaisesRegex(ValueError, "lift"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Edit profile", lift=100)

    def test_tab_tap_keeps_the_destructive_guard(self):
        self.screens(self.SCREEN + [box("Delete", 765)])
        with self.assertRaisesRegex(RuntimeError, "Destructive"):
            phone.ph_tap_tab("Profile", on_screen="Home", expected="Edit profile")
        self.assertEqual(self.ipb_calls("tap"), [])


class Find(Device):
    HEADER = {"text": "* Inspiration • Templates o", "x": 200, "y": 50, "w": 270, "h": 20}

    def test_returns_matching_boxes_top_to_bottom(self):
        self.screens([box("Al tools", 300, w=60, h=18), box("other", 200),
                      box("AI tools", 120, w=60, h=18)])
        found = phone.ph_find("AI tools")
        self.assertEqual([item["y"] for item in found], [120, 300])
        self.assertEqual({key: found[0][key] for key in ("x", "y", "w", "h", "match")},
                         {"x": 40, "y": 120, "w": 60, "h": 18, "match": "exact"})

    def test_partial_match_estimates_the_position_inside_the_line(self):
        self.screens([self.HEADER, box("Projects •", 300, w=60, h=18)])
        found = phone.ph_find("Inspiration")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["x"], found[0]["w"], found[0]["match"]), (140.0, 110.0, "partial"))
        self.assertEqual((found[0]["line_x"], found[0]["line_w"]), (200, 270))
        left, right = self.HEADER["x"] - self.HEADER["w"] / 2, self.HEADER["x"] + self.HEADER["w"] / 2
        self.assertTrue(left < found[0]["x"] < right)

    def test_search_matches_short_text_inside_a_line(self):
        self.screens([box("Available 94 GB", 200, w=150, h=18), box("other", 300)])
        self.assertEqual([item["text"] for item in phone.ph_find("GB")], ["Available 94 GB"])

    def test_finds_nothing_and_never_returns_other_lines(self):
        self.screens([box("private message")])
        self.assertEqual(phone.ph_find("Projects"), [])
        with self.assertRaises(ValueError):
            phone.ph_find(["Projects"])

    def test_found_point_feeds_ph_tap_point(self):
        self.screens([self.HEADER, box("Projects •", 300, w=60, h=18)])
        target = phone.ph_find("Inspiration")[0]
        phone.ph_tap_point(target["x"], target["y"], on_screen=["Projects"])
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.3500", "0.0625"])

    def test_send_button_row_workflow(self):
        # The typed text row gives the y; the button sits at the right edge of the screen.
        self.screens([box("AI tools", 640, x=120, w=60, h=18), box("Cancel", 700)])
        row = phone.ph_find("AI tools")[0]
        width, _height = phone.ph_screen_size()
        phone.ph_tap_point(width - 30, row["y"], on_screen=["Cancel"])
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.9250", "0.8000"])


class TypeText(Device):
    def test_requires_text_on_screen(self):
        self.screens([box("Settings"), box("Reset All Settings")])
        with self.assertRaisesRegex(RuntimeError, "not visible"):
            phone.ph_type_text("Record Video")
        self.screens([box("Record  Video")])
        phone.ph_type_text("record video")

    def test_ocr_lookalikes_do_not_fail_the_check(self):
        self.screens([box("Al tools", 100)])      # OCR read "AI" as "Al"
        phone.ph_type_text("AI tools")
        self.assertEqual(self.ipb_calls("text")[0][2:], ["AI tools"])
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_the_check_still_catches_other_text(self):
        self.screens([box("old query")])
        with self.assertRaisesRegex(RuntimeError, "not visible"):
            phone.ph_type_text("AI tools")

    def test_answers_allow_paste_once_then_verifies(self):
        self.screens([box("Allow Paste", 400), box("Search")], [box("카메라", 100)])
        phone.ph_type_text("카메라")
        self.assertEqual(len(self.ipb_calls("text")), 1)
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.5000"])

    def test_never_taps_the_decline_button(self):
        self.screens([box("Don't Allow Paste", 380), box("Allow Paste", 400)], [box("AI tools", 100)])
        phone.ph_type_text("AI tools")
        self.assertEqual(len(self.ipb_calls("tap")), 1)
        self.assertEqual(self.ipb_calls("tap")[0][2:], ["0.1000", "0.5000"])

    def test_text_in_the_field_that_mentions_allow_paste_is_not_a_prompt(self):
        self.screens([box("tap Allow Paste when asked", 400), box("tap Allow Paste when asked", 100)])
        phone.ph_type_text("tap Allow Paste when asked")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_without_a_prompt_nothing_is_tapped(self):
        self.screens([box("카메라")])
        phone.ph_type_text("카메라")
        self.assertEqual(self.ipb_calls("tap"), [])

    def test_replace_all_flag_and_first_line_verification(self):
        caption = "첫 줄 캡션입니다 #a #b\n두 번째 줄\n#c #d #e #f #g #h"
        self.screens([box("첫 줄 캡션입니다 #a #b"), box("두 번째 줄")])    # the app trimmed the hashtags
        phone.ph_type_text(caption, replace=True)
        self.assertEqual(self.ipb_calls("text")[0][2:], ["--replace-all", caption])

    def test_replace_fails_when_the_first_line_is_missing(self):
        self.screens([box("old caption")])
        with self.assertRaisesRegex(RuntimeError, "not visible"):
            phone.ph_type_text("new caption\nsecond", replace=True)

    def test_plain_type_requires_the_whole_text(self):
        self.screens([box("new caption")])
        with self.assertRaisesRegex(RuntimeError, "not visible"):
            phone.ph_type_text("new caption\nsecond line")
        self.assertEqual(self.ipb_calls("text")[0][2:], ["new caption\nsecond line"])

    def test_bad_text_is_refused_before_any_ipb_call(self):
        for text in ("-x", "", "   ", None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                phone.ph_type_text(text)
        with self.assertRaises(ValueError):
            phone.ph_type_text("-x", replace=True)
        self.assertEqual(self.calls, [])


class Motion(Device):
    def test_home(self):
        phone.ph_home()
        self.assertEqual(len(self.ipb_calls("home")), 1)

    def test_scroll_checks_the_screen_and_maps_direction(self):
        self.screens([box("Settings")], [box("Wallpaper")])
        screen = phone.ph_scroll("down", on_screen="Settings")
        self.assertIsInstance(screen, phone.Screen)
        self.assertEqual(self.ipb_calls("scroll")[0][2:], ["0.5000", "0.5000", "0.000", "-0.300"])
        self.screens([box("Other")])
        with self.assertRaisesRegex(RuntimeError, "no scroll sent"):
            phone.ph_scroll("down", on_screen="Settings")
        with self.assertRaises(ValueError):
            phone.ph_scroll("sideways", on_screen="Settings")
        self.assertEqual(len(self.ipb_calls("scroll")), 1)


class Bounds(Device):
    def test_every_ipb_call_has_a_positive_bound(self):
        self.screens([box("Home", 200), box("Allow Paste", 400)], [box("AI tools", 100)])
        phone.ph_home()
        phone.ph_tap_point(40, 700)
        phone.ph_type_text("AI tools")
        self.screens([box("Home")], [box("Next")])
        phone.ph_scroll("down", on_screen="Home")
        self.assertGreaterEqual(len(self.calls), 4)
        for cmd, timeout in self.calls:
            with self.subTest(cmd=cmd[:2]):
                self.assertIsInstance(timeout, (int, float))
                self.assertTrue(0 < timeout <= 60)

    def test_a_timed_out_call_stops_the_helper_without_retrying(self):
        with patch.object(phone, "_run", side_effect=phone.IpbTimeout("ipb text timed out after 40s")):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                phone.ph_type_text("AI tools")


class RealSubprocess(unittest.TestCase):
    def test_timeout_kills_the_whole_process_group(self):
        # The fake ipb leaves a grandchild that holds stdout open and records its pid. Only a
        # group kill removes it: the helper's own bounded wait would return later but leave it running.
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "grandchild.pid"
            fake_ipb(directory, 'sleep 30 &\necho $! > "$PID_FILE"\nwait')
            with patch.dict(os.environ, {**path_with(directory), "PID_FILE": str(pid_file)}):
                started = time.monotonic()
                with self.assertRaises(phone.IpbTimeout) as caught:
                    phone._ipb("tap", "0.5", "0.5", timeout=1)
            elapsed = time.monotonic() - started
            pid = int(pid_file.read_text())
        self.addCleanup(self.kill_quietly, pid)
        self.assertLess(elapsed, 4)
        self.assertIn("unknown", str(caught.exception))
        self.assertIn("ipb tap", str(caught.exception))
        for _ in range(40):
            if not self.alive(pid):
                break
            time.sleep(0.05)
        self.assertFalse(self.alive(pid), "the grandchild survived the timeout")

    @staticmethod
    def alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    @staticmethod
    def kill_quietly(pid):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, 9)

    def test_an_interrupt_also_kills_the_group(self):
        created = []
        real_popen = subprocess.Popen

        def popen(*args, **kwargs):
            created.append(real_popen(*args, **kwargs))
            return created[-1]
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "sleep 30 &\nwait")
            with patch.dict(os.environ, path_with(directory)), \
                    patch.object(phone.subprocess, "Popen", popen), \
                    patch.object(real_popen, "communicate", side_effect=[KeyboardInterrupt, ("", "")]), \
                    patch.object(phone.os, "killpg", wraps=os.killpg) as killpg:
                with self.assertRaises(KeyboardInterrupt):
                    phone._ipb("home")
        killpg.assert_called_once()
        for process in created:
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_a_failing_ipb_call_raises_with_its_last_line(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "echo boom >&2\nexit 3")
            with patch.dict(os.environ, path_with(directory)):
                with self.assertRaisesRegex(RuntimeError, "ipb home failed: boom"):
                    phone._ipb("home")

    def test_missing_ipb_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"PATH": directory}):
                with self.assertRaisesRegex(RuntimeError, "not installed"):
                    phone._ipb("home")


class Snapshot(unittest.TestCase):
    """The real _snapshot with a fake runner that writes a PNG."""

    def setUp(self):
        self.calls = []
        self.png_pad = 0
        run = patch.object(phone, "_run", self.fake_run)
        run.start()
        self.addCleanup(run.stop)

    def fake_run(self, cmd, timeout):
        self.calls.append((list(cmd), timeout))
        Path(cmd[-1]).write_bytes(png(pad=self.png_pad))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def test_window_is_in_points_and_the_capture_is_bounded(self):
        with patch.object(phone, "_read_image", return_value=[box("x")]):
            boxes, window = phone._snapshot()
        self.assertEqual(boxes, [box("x")])
        self.assertEqual((window["w"], window["h"]), (402.0, 874.0))
        self.assertEqual(phone.ph_screen_size(), (402.0, 874.0))
        self.assertEqual(self.calls[0][0][:2], ["ipb", "screenshot"])
        self.assertEqual(self.calls[0][1], phone.IPB_TIMEOUTS["screenshot"])

    def test_dark_capture_without_text_means_locked(self):
        with patch.object(phone, "_read_image", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "locked") as caught:
                phone._snapshot()
        self.assertNotIn("irror", str(caught.exception))

    def test_large_capture_without_text_is_not_a_lock(self):
        self.png_pad = phone.DARK_PNG_BYTES
        with patch.object(phone, "_read_image", return_value=[]):
            self.assertEqual(phone._snapshot()[0], [])

    def test_temporary_capture_is_private_and_removed_on_ocr_error(self):
        seen = []

        def read(path, _window):
            seen.append(Path(path))
            self.assertEqual(Path(path).parent.stat().st_mode & 0o777, 0o700)
            raise RuntimeError("OCR error")
        with patch.object(phone, "_read_image", read):
            with self.assertRaisesRegex(RuntimeError, "OCR error"):
                phone._snapshot()
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())

    def test_explicit_capture_is_private_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(phone, "_read_image", return_value=[box("x")]):
            target = Path(directory) / "new.png"
            phone._snapshot(target)
            self.assertEqual(target.read_bytes(), png())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            existing = Path(directory) / "existing.png"
            existing.write_bytes(b"original")
            calls = len(self.calls)
            with self.assertRaises(FileExistsError):
                phone._snapshot(existing)
            self.assertEqual(existing.read_bytes(), b"original")
            self.assertEqual(len(self.calls), calls)        # refused before any capture


class Ocr(unittest.TestCase):
    """_read_image against a fake Vision: checks the languages and the box geometry."""

    def fake_modules(self, observations, languages):
        class Request:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

            def setRecognitionLevel_(self, level):
                pass

            def setRecognitionLanguages_(self, value):
                languages.extend(value)

            def results(self):
                return observations

        class Handler:
            @classmethod
            def alloc(cls):
                return cls()

            def initWithURL_options_(self, url, options):
                return self

            def performRequests_error_(self, requests, error):
                return True, None

        vision = types.SimpleNamespace(VNRecognizeTextRequest=Request, VNImageRequestHandler=Handler,
                                       VNRequestTextRecognitionLevelAccurate=1)
        foundation = types.SimpleNamespace(NSURL=types.SimpleNamespace(fileURLWithPath_=lambda path: path))
        return {"Vision": vision, "Foundation": foundation}

    def observation(self, text, x, y, w, h):
        candidate = types.SimpleNamespace(string=lambda: text, confidence=lambda: 0.98765)
        return types.SimpleNamespace(
            topCandidates_=lambda _n: [candidate],
            boundingBox=lambda: types.SimpleNamespace(origin=types.SimpleNamespace(x=x, y=y),
                                                      size=types.SimpleNamespace(width=w, height=h)))

    def test_boxes_are_window_points_with_the_origin_at_the_top_left(self):
        languages = []
        modules = self.fake_modules([self.observation("Done", 0.25, 0.5, 0.5, 0.1)], languages)
        with patch.dict(sys.modules, modules):
            boxes = phone._read_image("shot.png", {"x": 0, "y": 0, "w": 400, "h": 800})
        self.assertEqual(languages, ["ko-KR", "en-US"])
        self.assertEqual(boxes, [{"text": "Done", "confidence": 0.988, "x": 200.0, "y": 360.0,
                                  "w": 200.0, "h": 80.0}])

    def test_languages_come_from_the_environment(self):
        languages = []
        with patch.dict(sys.modules, self.fake_modules([], languages)), \
                patch.dict(os.environ, {"EDITS_PHONE_OCR_LANGS": "ja-JP, en-US"}):
            phone._read_image("shot.png", WIN)
        self.assertEqual(languages, ["ja-JP", "en-US"])


class Cli(unittest.TestCase):
    def run_cli(self, directory, script, **kwargs):
        return subprocess.run([sys.executable, str(SCRIPT), "run"], input=script, text=True,
                              capture_output=True, timeout=60,
                              env={**os.environ, **path_with(directory)}, **kwargs)

    def doctor(self, directory):
        out = io.StringIO()
        with patch.dict(os.environ, path_with(directory)), contextlib.redirect_stdout(out):
            code = phone.doctor()
        return code, out.getvalue()

    def test_doctor_passes_on_zero_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "echo 'PASS    ipb'\necho 'WARN    transport'\necho '== result: 0 failure(s) =='")
            code, output = self.doctor(directory)
        self.assertEqual(code, 0)
        self.assertIn("doctor: PASS (0 failures, 1 warning(s))", output)
        self.assertIn("PASS    ipb", output)

    def test_doctor_fails_on_a_failure_line_even_when_ipb_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "echo 'FAIL    selection'\necho '== result: 1 failure(s); device checks skipped =='")
            code, output = self.doctor(directory)
        self.assertEqual(code, 1)
        self.assertIn("doctor: FAIL (1 failure(s))", output)

    def test_doctor_falls_back_to_the_exit_code_without_a_result_line(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "echo 'something odd'\nexit 1")
            self.assertEqual(self.doctor(directory)[0], 1)
            fake_ipb(directory, "echo 'something odd'")
            self.assertEqual(self.doctor(directory)[0], 0)

    def test_doctor_reports_a_missing_ipb(self):
        with tempfile.TemporaryDirectory() as directory:
            out = io.StringIO()
            with patch.dict(os.environ, {"PATH": directory}), contextlib.redirect_stdout(out):
                self.assertEqual(phone.doctor(), 1)
        self.assertIn("doctor: FAIL - ipb is not installed", out.getvalue())

    def test_run_requires_task_and_step_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "exit 0")
            for script in ("print('x')\n", "# task: a\nprint('x')\n", "# step: a\n# task: b\n"):
                with self.subTest(script=script):
                    result = self.run_cli(directory, script)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("# task:", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_run_exposes_the_helpers_and_logs_task_and_step(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "exit 0")
            script = ("# task: Tune the feed.\n# step: Check names.\n"
                      "names = ['ph_observe', 'ph_find', 'ph_screen_size', 'ph_wait', 'ph_tap', "
                      "'ph_tap_tab', 'ph_tap_point', 'ph_type_text', 'ph_home', 'ph_scroll', 'Screen']\n"
                      "print(all(callable(globals()[n]) for n in names))\n")
            result = self.run_cli(directory, script)
        self.assertEqual((result.returncode, result.stdout), (0, "True\n"))
        self.assertIn("phone: # task: Tune the feed.", result.stderr)

    def test_run_reports_a_helper_error_with_the_script_line(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "echo nope >&2\nexit 1")
            result = self.run_cli(directory, "# task: a\n# step: b\nph_home()\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ipb home failed: nope", result.stderr)
        self.assertIn("script line 3", result.stderr)

    def test_run_without_ipb_stops_before_the_script(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(SCRIPT), "run"], text=True, capture_output=True,
                                    input="# task: a\n# step: b\nprint('ran')\n", timeout=60,
                                    env={**os.environ, "PATH": directory})
        self.assertEqual(result.returncode, 2)
        self.assertIn("not installed", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_run_flushes_progress_before_the_script_ends(self):
        script = "# task: a\n# step: b\nimport time\nprint('progress 1')\ntime.sleep(10)\nprint('done')\n"
        with tempfile.TemporaryDirectory() as directory:
            fake_ipb(directory, "exit 0")
            process = subprocess.Popen([sys.executable, str(SCRIPT), "run"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                       env={**os.environ, **path_with(directory)})
            self.addCleanup(process.stdout.close)
            self.addCleanup(process.wait)
            self.addCleanup(process.kill)
            process.stdin.write(script)
            process.stdin.close()
            lines = []
            reader = threading.Thread(target=lambda: lines.append(process.stdout.readline()), daemon=True)
            reader.start()
            reader.join(timeout=7)
            alive = process.poll() is None
        self.assertEqual(lines, ["progress 1\n"])
        self.assertTrue(alive)


if __name__ == "__main__":
    unittest.main()

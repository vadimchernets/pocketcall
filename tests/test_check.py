"""Tests for the readiness check.

They build small temporary project folders and settings files and look at what the check
says about them. Nothing here needs a subscription, a network or a phone.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check  # noqa: E402


def find(items, ident):
    return next((i for i in items if i["id"] == ident), None)


class TempProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self._env = dict(os.environ)
        for name in check.KILLERS + check.REDIRECTS + check.NOT_A_SUBSCRIPTION + check.OTHER_CLOUDS:
            os.environ.pop(name, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    def settings(self, name, data):
        d = self.project / ".claude"
        d.mkdir(exist_ok=True)
        (d / name).write_text(json.dumps(data), encoding="utf-8")


class TestPlace(TempProject):
    def test_a_work_folder_is_fine(self):
        self.assertTrue(check.check_place(self.project)["ok"])

    def test_the_home_folder_is_not(self):
        item = check.check_place(Path.home())
        self.assertFalse(item["ok"])
        self.assertIn("home folder", item["says"])


class TestVersion(unittest.TestCase):
    def test_a_version_string_is_parsed(self):
        self.assertEqual(check.parse_version("2.1.280 (Claude Code)"), (2, 1, 280))

    def test_no_version_string_is_not_invented(self):
        self.assertIsNone(check.parse_version("command not found"))


class TestQuietKillers(TempProject):
    def test_a_clean_machine_says_so(self):
        items = check.check_quiet_killers(self.project)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["ok"])

    def test_an_environment_variable_is_caught(self):
        os.environ["DO_NOT_TRACK"] = "1"
        items = check.check_quiet_killers(self.project)
        item = find(items, "env:DO_NOT_TRACK")
        self.assertIsNotNone(item)
        self.assertFalse(item["ok"])
        self.assertIn("this terminal", item["says"])

    def test_a_settings_file_is_caught_and_named(self):
        self.settings("settings.json", {"env": {"DISABLE_TELEMETRY": "1"}})
        items = check.check_quiet_killers(self.project)
        item = find(items, "env:DISABLE_TELEMETRY")
        self.assertIsNotNone(item)
        self.assertIn("settings.json", item["says"])

    def test_an_api_key_is_not_a_subscription(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        item = find(check.check_quiet_killers(self.project), "env:ANTHROPIC_API_KEY")
        self.assertIsNotNone(item)
        self.assertFalse(item["ok"])

    def test_a_written_down_refusal_is_reported(self):
        self.settings("settings.local.json", {"disableRemoteControl": True})
        item = find(check.check_quiet_killers(self.project), "setting:disableRemoteControl")
        self.assertIsNotNone(item)
        self.assertFalse(item["ok"])

    def test_a_false_refusal_is_not_reported(self):
        self.settings("settings.json", {"disableRemoteControl": False})
        items = check.check_quiet_killers(self.project)
        self.assertIsNone(find(items, "setting:disableRemoteControl"))

    def test_an_unreadable_settings_file_does_not_crash(self):
        d = self.project / ".claude"
        d.mkdir(exist_ok=True)
        (d / "settings.json").write_text("{not json", encoding="utf-8")
        items = check.check_quiet_killers(self.project)
        self.assertTrue(items[0]["ok"])


class TestHandover(TempProject):
    def test_missing_folder_and_rule_are_both_reported(self):
        items = check.check_handover(self.project)
        self.assertFalse(find(items, "out-folder")["ok"])
        self.assertFalse(find(items, "handover-rule")["ok"])

    def test_a_folder_and_a_rule_satisfy_it(self):
        (self.project / check.OUT_DIR).mkdir()
        (self.project / "CLAUDE.md").write_text(
            f"Finished work goes to {check.OUT_DIR}/ as a file.", encoding="utf-8")
        items = check.check_handover(self.project)
        self.assertTrue(find(items, "out-folder")["ok"])
        self.assertTrue(find(items, "handover-rule")["ok"])

    def test_a_rules_file_without_the_rule_is_not_enough(self):
        (self.project / "CLAUDE.md").write_text("I am a nurse.", encoding="utf-8")
        self.assertFalse(find(check.check_handover(self.project), "handover-rule")["ok"])


class TestReport(TempProject):
    def test_the_report_shows_every_finding(self):
        items = check.collect(self.project)
        text = check.report(items)
        for item in items:
            self.assertIn(item["says"], text)

    def test_a_failure_is_never_summarised_away(self):
        items = [{"id": "x", "ok": False, "says": "Something is wrong.", "do": "Fix it."}]
        text = check.report(items)
        self.assertIn("NOT", text)
        self.assertIn("Fix it.", text)
        self.assertIn("1 of 1 not ready", text)

    def test_everything_ready_says_what_comes_next(self):
        text = check.report([{"id": "x", "ok": True, "says": "Fine.", "do": ""}])
        self.assertIn("/remote-control", text)


class TestCard(unittest.TestCase):
    def test_the_card_names_the_handover_folder_and_the_date(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import card
        text = card.build("my-out", "23.09.2026")
        self.assertIn("my-out/", text)
        self.assertIn("23.09.2026", text)

    def test_the_card_keeps_the_four_reasons_it_goes_quiet(self):
        import card
        text = card.build("pocket-out", "23.09.2026")
        for reason in ("sleep", "window was closed", "allowance ran out", "notification"):
            self.assertIn(reason, text)

    def test_the_card_refuses_the_third_party_sign_in(self):
        import card
        self.assertIn("Never sign in", card.build("pocket-out", "23.09.2026"))


if __name__ == "__main__":
    unittest.main()

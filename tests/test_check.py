"""Tests for the readiness check.

They build small temporary project folders and settings files and look at what the check
says about them. Nothing here needs a subscription, a network or a phone.
"""

import datetime as dt
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


class TestSharedFolder(TempProject):
    """The seventh check: the folder the phone drops a photo into.

    Every test here points the search at a temporary home folder, so nothing ever walks the
    real cloud drive of whoever is running the tests.
    """

    def drive(self, *parts):
        folder = self.project.joinpath(*parts)
        folder.mkdir(parents=True)
        return folder

    def test_no_folder_a_phone_can_see_is_reported(self):
        item = check.check_sync(self.project, home=self.project)
        self.assertFalse(item["ok"])
        self.assertIn("--shared", item["do"])

    def test_a_named_folder_that_is_not_there_is_reported(self):
        item = check.check_sync(self.project, named=str(self.project / "nowhere"),
                                home=self.project)
        self.assertFalse(item["ok"])
        self.assertIn("is not here", item["says"])

    def test_a_found_folder_is_counted_and_dated(self):
        drive = self.drive("Dropbox")
        (drive / "note.txt").write_text("from town", encoding="utf-8")
        (drive / "photo.jpg").write_bytes(b"x")
        item = check.check_sync(self.project, home=self.project)
        self.assertTrue(item["ok"])
        self.assertIn("Dropbox folder", item["says"])
        self.assertIn("2 files", item["says"])
        self.assertIn("today at", item["says"])

    def test_an_empty_folder_invents_no_date(self):
        self.drive("Dropbox")
        item = check.check_sync(self.project, home=self.project)
        self.assertIn("empty", item["says"])
        self.assertNotIn("last change", item["says"])

    def test_syncing_is_never_claimed_only_tested(self):
        drive = self.drive("Dropbox")
        (drive / "note.txt").write_text("x", encoding="utf-8")
        item = check.check_sync(self.project, home=self.project)
        self.assertNotIn("is syncing", item["says"])
        self.assertNotIn("synced", item["says"])
        self.assertIn("nothing on this machine can prove", item["do"])
        self.assertIn("put one photo in from the phone", item["do"])

    def test_the_handover_folder_inside_the_drive_is_the_one_named(self):
        project = self.drive("Dropbox", "work")
        (project / check.OUT_DIR).mkdir()
        folder, service = check.find_shared(project, home=self.project)
        self.assertEqual(folder, project / check.OUT_DIR)
        self.assertEqual(service, "Dropbox")

    def test_the_mac_cloudstorage_layout_is_found(self):
        self.drive("Library", "CloudStorage", "GoogleDrive-someone@gmail.com")
        folder, service = check.find_shared(self.project, home=self.project)
        self.assertEqual(service, "Google Drive")
        self.assertIn("GoogleDrive-", str(folder))

    def test_icloud_is_told_it_has_no_android(self):
        self.drive("Library", "Mobile Documents", "com~apple~CloudDocs")
        item = check.check_sync(self.project, home=self.project)
        self.assertEqual(item["says"].split(":")[0], "iCloud Drive folder")
        self.assertIn("Android", item["do"])

    def test_a_folder_no_drive_knows_about_is_said_to_be_only_here(self):
        plain = self.drive("just-a-folder")
        item = check.check_sync(self.project, named=str(plain), home=self.project)
        self.assertTrue(item["ok"])
        self.assertIn("Shared folder:", item["says"])
        self.assertIn("only this computer can see", item["do"])

    def test_the_facts_are_names_and_dates_of_real_files_only(self):
        folder = self.drive("Dropbox")
        (folder / ".hidden").write_text("x", encoding="utf-8")
        (folder / "old.txt").write_text("x", encoding="utf-8")
        deeper = folder / "sub"
        deeper.mkdir()
        (deeper / "new.txt").write_text("x", encoding="utf-8")
        os.utime(folder / "old.txt", (1_000_000, 1_000_000))
        facts = check.folder_facts(folder)
        self.assertEqual(facts["files"], 2)
        self.assertEqual(facts["newest_name"], "new.txt")
        self.assertFalse(facts["capped"])

    def test_a_drive_too_big_to_walk_says_it_stopped_counting(self):
        folder = self.drive("Dropbox")
        for n in range(5):
            (folder / f"f{n}.txt").write_text("x", encoding="utf-8")
        facts = check.folder_facts(folder, cap=3)
        self.assertTrue(facts["capped"])
        self.assertEqual(facts["files"], 3)

    def test_a_folder_that_cannot_be_read_does_not_crash(self):
        facts = check.folder_facts(self.project / "not-there")
        self.assertEqual(facts["files"], 0)
        self.assertIsNone(facts["newest"])

    def test_the_seventh_check_is_part_of_the_check(self):
        item = find(check.collect(self.project, home=self.project), "sync")
        self.assertIsNotNone(item)


class TestWhenWords(unittest.TestCase):
    def stamp(self, day, hour=9, minute=5):
        return dt.datetime(2026, 9, day, hour, minute).timestamp()

    def test_today_keeps_the_clock(self):
        words = check.when_words(self.stamp(25, 14, 2), self.stamp(25, 19))
        self.assertEqual(words, "today at 14:02")

    def test_yesterday_is_said_as_yesterday(self):
        self.assertTrue(
            check.when_words(self.stamp(24), self.stamp(25)).startswith("yesterday at"))

    def test_a_few_days_carry_the_date_as_well(self):
        words = check.when_words(self.stamp(22), self.stamp(25))
        self.assertIn("3 days ago", words)
        self.assertIn("22.09.2026", words)

    def test_long_ago_is_only_a_date(self):
        self.assertEqual(check.when_words(self.stamp(1), self.stamp(25)), "on 01.09.2026")


class TestReport(TempProject):
    def test_the_report_shows_every_finding(self):
        items = check.collect(self.project, home=self.project)
        text = check.report(items)
        for item in items:
            self.assertIn(item["says"], text)

    def test_the_closing_paragraph_admits_the_sync_is_unseen(self):
        text = check.report(check.collect(self.project, home=self.project))
        self.assertIn("whether the shared folder is really syncing", text)

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

    def test_the_card_carries_the_five_lines_said_at_the_door(self):
        import card
        text = card.build("pocket-out", "23.09.2026")
        self.assertIn("THIRTY SECONDS AT THE DOOR", text)
        for line in ("Plugged in", "Lid open", "window with the work in it stays open",
                     "The shared folder is there", "Phone in your hand before the door"):
            self.assertIn(line, text)
        self.assertIn("out loud", text)

    def test_the_card_names_the_shared_folder_when_it_is_known(self):
        import card
        text = card.build("pocket-out", "23.09.2026", "/Users/anna/Dropbox/From the phone")
        self.assertIn("/Users/anna/Dropbox/From the phone", text)

    def test_the_card_does_not_invent_a_folder_it_was_not_given(self):
        import card
        text = card.build("pocket-out", "23.09.2026")
        self.assertIn("the one your drive syncs", text)

    def test_the_card_lets_a_person_correct_the_folder_by_hand(self):
        import card
        text = card.build("pocket-out", "23.09.2026", "/Users/anna/Dropbox/guessed")
        self.assertIn("cross\n     it out and write yours in with a pen", text)

    def test_the_card_says_a_stopped_sync_is_silent_too(self):
        import card
        self.assertIn("stopped syncing", card.build("pocket-out", "23.09.2026"))


if __name__ == "__main__":
    unittest.main()

"""Tests for the readiness check.

They build small temporary project folders and settings files and look at what the check
says about them. Nothing here needs a subscription, a network or a phone.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

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
        # The organization's real policy folder is never read by a test: an empty one stands in.
        self.managed = self.project / "managed"
        self.managed.mkdir()
        os.environ["POCKETCALL_MANAGED_DIR"] = str(self.managed)
        check.use_lang("en")

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


class TestWorkAccounts(TempProject):
    """The business side: what a company's key, cloud, gateway or policy does to the remote."""

    def policy(self, data, name="managed-settings.json"):
        (self.managed / name).write_text(json.dumps(data), encoding="utf-8")

    def test_an_api_key_says_the_remote_will_not_work(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        item = find(check.check_quiet_killers(self.project), "env:ANTHROPIC_API_KEY")
        self.assertIn("the remote will not work", item["says"])
        self.assertIn("branch C", item["do"])

    def test_the_api_key_sentence_is_said_in_russian_too(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        check.use_lang("ru")
        item = find(check.check_quiet_killers(self.project), "env:ANTHROPIC_API_KEY")
        self.assertIn("\u043f\u0443\u043b\u044c\u0442 \u043d\u0435 \u0431\u0443\u0434\u0435\u0442 "
                      "\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c", item["says"])

    def test_the_api_key_sentence_reaches_the_printed_report(self):
        env = dict(os.environ, ANTHROPIC_API_KEY="x")
        for code, words in (("en", "the remote will not work"),
                            ("ru", "\u043f\u0443\u043b\u044c\u0442 \u043d\u0435 \u0431\u0443\u0434\u0435\u0442 "
                                   "\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c")):
            done = subprocess.run([sys.executable, str(SCRIPTS / "check.py"), "--dir", str(self.project),
                                   "--lang", code], capture_output=True, text=True, env=env,
                                  encoding="utf-8")
            self.assertIn(words, done.stdout, code)

    def test_an_api_key_in_a_settings_file_is_caught_too(self):
        self.settings("settings.json", {"env": {"ANTHROPIC_API_KEY": "x"}})
        item = find(check.check_quiet_killers(self.project), "env:ANTHROPIC_API_KEY")
        self.assertIsNotNone(item)
        self.assertIn("settings.json", item["says"])

    def test_an_api_key_helper_is_an_api_key(self):
        self.settings("settings.json", {"apiKeyHelper": "/bin/echo key"})
        item = find(check.check_quiet_killers(self.project), "setting:apiKeyHelper")
        self.assertIsNotNone(item)
        self.assertFalse(item["ok"])

    def test_foundry_is_another_company_cloud(self):
        os.environ["CLAUDE_CODE_USE_FOUNDRY"] = "1"
        item = find(check.check_quiet_killers(self.project), "env:CLAUDE_CODE_USE_FOUNDRY")
        self.assertFalse(item["ok"])
        self.assertIn("Tailscale", item["do"])

    def test_the_two_hard_switches_stop_the_remote_on_any_version(self):
        for name in check.HARD_KILLERS:
            os.environ[name] = "1"
            item = find(check.check_quiet_killers(self.project, version=(2, 1, 300)), f"env:{name}")
            self.assertFalse(item["ok"], name)
            os.environ.pop(name)

    def test_telemetry_alone_does_not_stop_a_new_claude_code(self):
        for name in check.SOFT_KILLERS:
            os.environ[name] = "1"
            items = check.check_quiet_killers(self.project, version=(2, 1, 283))
            item = find(items, f"env:{name}")
            self.assertTrue(item["ok"], name)
            self.assertIn("Trusted Devices", item["do"])
            self.assertTrue(all(i["ok"] for i in items))
            os.environ.pop(name)

    def test_telemetry_stops_the_remote_under_trusted_devices(self):
        os.environ["DISABLE_TELEMETRY"] = "1"
        item = find(check.check_quiet_killers(self.project, version=(2, 1, 300), trusted_devices=True),
                    "env:DISABLE_TELEMETRY")
        self.assertFalse(item["ok"])

    def test_telemetry_stops_an_old_claude_code(self):
        os.environ["DO_NOT_TRACK"] = "1"
        item = find(check.check_quiet_killers(self.project, version=(2, 1, 282)), "env:DO_NOT_TRACK")
        self.assertFalse(item["ok"])
        self.assertIn("2.1.283", item["do"])

    def test_a_killer_in_the_managed_settings_is_found(self):
        self.policy({"env": {"DISABLE_GROWTHBOOK": "1"}})
        item = find(check.check_quiet_killers(self.project), "env:DISABLE_GROWTHBOOK")
        self.assertIsNotNone(item)
        self.assertIn("managed-settings.json", item["says"])

    def test_the_administrator_turning_the_remote_off_is_named(self):
        (self.managed / "managed-settings.d").mkdir()
        self.policy({"disableRemoteControl": True}, "managed-settings.d/10-remote.json")
        item = find(check.check_quiet_killers(self.project), "managed:disableRemoteControl")
        self.assertIsNotNone(item)
        self.assertFalse(item["ok"])
        self.assertIn("IT administrator", item["do"])

    def test_no_policy_file_says_nothing_about_channels(self):
        self.assertIsNone(check.check_channels())

    def test_channels_off_by_policy_say_who_turns_them_on(self):
        self.policy({"permissions": {}})
        item = check.check_channels()
        self.assertTrue(item["ok"])
        self.assertIn("channelsEnabled", item["do"])
        self.assertIn("allowedChannelPlugins", item["do"])

    def test_channels_on_by_policy_name_the_allowed_plugins(self):
        self.policy({"channelsEnabled": True, "allowedChannelPlugins": [
            {"marketplace": "claude-plugins-official", "plugin": "telegram"}]})
        item = check.check_channels()
        self.assertIn("telegram", item["says"])
        self.assertIn(item, check.collect(self.project, home=self.project))


class TestLanguages(unittest.TestCase):
    def load(self, code):
        return json.loads((ROOT / "lang" / f"{code}.json").read_text(encoding="utf-8"))

    def test_every_language_has_every_word(self):
        keys = {k for k in self.load("en") if not k.startswith("_")} - {"card_file"}
        for code in check.LANGUAGES:
            have = {k for k in self.load(code) if not k.startswith("_")} - {"card_file"}
            self.assertEqual(have, keys, code)

    def test_every_word_keeps_its_placeholders(self):
        english = self.load("en")
        for code in check.LANGUAGES:
            words = self.load(code)
            for key, text in english.items():
                if isinstance(text, str) and not key.startswith("_") and key != "card_file":
                    self.assertEqual(set(re.findall(r"{(\w+)}", text)),
                                     set(re.findall(r"{(\w+)}", words[key])), f"{code}:{key}")

    def test_the_card_builds_in_every_language_with_the_rule_on_it(self):
        sys.path.insert(0, str(SCRIPTS))
        import card
        for code in check.LANGUAGES:
            words = check.lang_words(code)
            text = card.build("pocket-out", "03.10.2026", "/x/Dropbox/phone", words)
            self.assertIn("pocket-out/", text, code)
            self.assertIn("/x/Dropbox/phone", text, code)
            self.assertEqual(len(words["card"]), len(self.load("en")["card"]), code)
        self.assertIn("DO NOT APPROVE ON THE PHONE WHAT YOU CANNOT SEE", card.build("pocket-out", "x"))

    def test_the_language_is_picked_from_the_flag_then_the_system(self):
        saved = dict(os.environ)
        try:
            for name in ("POCKETCALL_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
                os.environ.pop(name, None)
            self.assertEqual(check.pick_lang(), "en")
            os.environ["LANG"] = "uk_UA.UTF-8"
            self.assertEqual(check.pick_lang(), "uk")
            self.assertEqual(check.pick_lang("es"), "es")
            os.environ["LANG"] = "de_DE.UTF-8"
            self.assertEqual(check.pick_lang(), "en")
        finally:
            os.environ.clear()
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()

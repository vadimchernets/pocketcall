"""Tests for the words a person reads.

The skills and the README are as much of this plugin as the scripts are: a check that finds
something and a skill that never mentions it is a check nobody runs. These tests read the
files themselves and look for the promises that have to be in them, and for the one promise
that must never be in them — that a folder is syncing.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text_of(*parts) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def front_matter(skill: str) -> str:
    return text_of("skills", skill, "SKILL.md").split("---")[1]


def body_of(skill: str) -> str:
    """The part a model reads once the skill is open, without the description above it."""
    return text_of("skills", skill, "SKILL.md").split("---", 2)[2]


class TestLeave(unittest.TestCase):
    def test_the_ritual_at_the_door_has_its_own_heading(self):
        headings = [line for line in body_of("leave").splitlines() if line.startswith("## ")]
        ritual = [h for h in headings if "thirty seconds at the door" in h]
        self.assertEqual(len(ritual), 1, headings)
        self.assertIn("every time", ritual[0])

    def test_the_ritual_names_all_five_things_to_leave_as_they_are(self):
        body = body_of("leave")
        for thing in ("Plugged in", "Lid open", "This window stays open",
                      "shared folder is there", "Phone in hand before the door"):
            self.assertIn(thing, body)

    def test_the_ritual_says_the_two_silent_failures_out_loud(self):
        body = body_of("leave")
        self.assertIn("allowance has", body)
        self.assertIn("stopped syncing", body)

    def test_the_skill_is_findable_by_someone_going_out_with_a_phone(self):
        matter = front_matter("leave")
        self.assertIn("going out with the phone", matter)
        self.assertIn("thirty seconds", matter)


class TestReady(unittest.TestCase):
    def test_the_skill_forbids_claiming_the_folder_syncs(self):
        body = text_of("skills", "ready", "SKILL.md")
        self.assertIn("Do not say the shared folder is syncing", body)

    def test_the_skill_knows_how_to_be_pointed_at_the_right_folder(self):
        self.assertIn("--shared", text_of("skills", "ready", "SKILL.md"))

    def test_the_skill_keeps_its_hands_off_what_is_already_in_the_drive(self):
        body = text_of("skills", "ready", "SKILL.md")
        self.assertIn("never move, rename or open what is already in there", body)


RULE = "do not approve on the phone what you cannot see"


class TestTheRuleForThePhone(unittest.TestCase):
    """One rule a person carries out of the house: no yes to something they could not read."""

    def test_leave_says_the_rule_in_its_own_words_and_heading(self):
        body = body_of("leave")
        self.assertIn(RULE, " ".join(body.lower().split()))
        headings = [line.lower() for line in body.splitlines() if line.startswith("## ")]
        self.assertTrue(any(RULE in h for h in headings), headings)

    def test_handover_keeps_the_assistants_side_of_it(self):
        self.assertIn(RULE, " ".join(body_of("handover").lower().split()))

    def test_the_card_carries_it_in_every_language(self):
        english = json.loads(text_of("lang", "en.json"))["card"]
        self.assertIn(RULE.upper(), english)
        at = english.index(RULE.upper())
        for code in ("es", "pt", "ru", "uk"):
            card = json.loads(text_of("lang", f"{code}.json"))["card"]
            self.assertTrue(card[at].isupper(), (code, card[at]))
            self.assertTrue(card[at + 1].strip() and card[at + 2].strip(), code)


class TestWorkBranches(unittest.TestCase):
    """The ready skill walks a work account down branch A, B or C, with the real commands."""

    def test_three_branches_have_headings(self):
        headings = [line for line in body_of("ready").splitlines() if line.startswith("### ")]
        for letter in ("A - ", "B - ", "C - "):
            self.assertTrue(any(h.startswith("### " + letter) for h in headings), headings)

    def test_branch_a_names_the_owner_toggle_and_trusted_devices(self):
        body = body_of("ready")
        for fact in ("claude.ai/admin-settings/claude-code", "**Remote Control**",
                     "claude.ai/admin-settings/capabilities", "--trusted-devices",
                     "--spawn worktree", "tmux new -s work"):
            self.assertIn(fact, body)

    def test_branch_b_moves_the_work_to_the_cloud_and_back(self):
        body = body_of("ready")
        for fact in ('claude --cloud "', "claude --teleport <session-id>", "CCR_FORCE_BUNDLE=1",
                     'claude -p "message" --cloud <session-id>'):
            self.assertIn(fact, body)

    def test_branch_c_is_ssh_and_tmux_over_tailscale(self):
        body = body_of("ready")
        for fact in ("Bedrock", "ZDR", "HIPAA", "Tailscale", "Blink", "Termius", "tmux attach -t work"):
            self.assertIn(fact, body)

    def test_channels_name_the_two_managed_keys(self):
        body = body_of("ready")
        for fact in ("channelsEnabled", "allowedChannelPlugins", "claude --channels plugin:"):
            self.assertIn(fact, body)

    def test_leave_follows_the_branch_ready_picked(self):
        body = body_of("leave")
        self.assertIn("branch B or C", body)
        self.assertIn("admin-settings/claude-code", body)


class TestVoiceNote(unittest.TestCase):
    def test_a_voice_note_goes_to_chasecall_or_nightcall_not_to_action(self):
        body = body_of("leave")
        self.assertIn("voice note", body)
        self.assertIn("/chasecall:take", body)
        self.assertIn("/nightcall:start", body)
        self.assertIn("you do not act on it on the", body)


class TestLanguagesAreOffered(unittest.TestCase):
    def test_both_scripts_are_run_in_the_persons_language(self):
        self.assertIn("check.py --dir . --lang", body_of("ready"))
        self.assertIn("card.py --dir . --lang", body_of("leave"))


class TestReadme(unittest.TestCase):
    def test_the_readme_counts_seven_and_not_six(self):
        body = text_of("README.md")
        self.assertIn("seven things", body)
        self.assertNotIn("six things", body)

    def test_the_readme_describes_the_shared_folder_check(self):
        body = text_of("README.md")
        self.assertIn("**The shared folder.**", body)
        self.assertIn("--shared", body)

    def test_the_readme_refuses_to_pretend_it_can_see_a_sync(self):
        self.assertIn("Nothing here can tell you a folder is syncing", text_of("README.md"))


class TestManifests(unittest.TestCase):
    def load(self, name):
        return json.loads(text_of(".claude-plugin", name))

    def test_the_plugin_no_longer_promises_six_checks(self):
        described = self.load("plugin.json")["description"]
        self.assertIn("seven things", described)
        self.assertNotIn("six things", described)

    def test_both_manifests_agree_on_the_version(self):
        plugin = self.load("plugin.json")
        market = self.load("marketplace.json")
        self.assertEqual(plugin["version"], market["metadata"]["version"])
        self.assertEqual(plugin["version"], market["plugins"][0]["version"])


if __name__ == "__main__":
    unittest.main()

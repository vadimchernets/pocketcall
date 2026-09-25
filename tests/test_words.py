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

"""The mutation run is part of the tests: a promise whose removal leaves the tests green is a
promise nobody checks. tests/mutate_code.py breaks each one in a copy and expects red."""

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class TestMutations(unittest.TestCase):
    def test_every_mutation_turns_the_tests_red_and_the_control_stays_green(self):
        done = subprocess.run([sys.executable, str(HERE / "mutate_code.py")],
                              capture_output=True, text=True, encoding="utf-8", timeout=900)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("misbehaving: 0", done.stdout)


if __name__ == "__main__":
    unittest.main()

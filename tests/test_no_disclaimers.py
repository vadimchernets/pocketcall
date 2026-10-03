"""The product speaks as a finished thing: no disclaimers, no excuses, no apologies.

Every text the person or the model reads - README, SKILL.md, lang/*.json, hook and script messages,
plugin descriptions, SECURITY/CONTRIBUTING - is scanned for stop phrases. A fact the person needs is
said as a capability ("it starts the moment Python 3 is there"), not as an excuse ("does nothing
for now"). LICENSE/NOTICE (the legal minimum) and CHANGELOG (history) are not scanned; tests are
not scanned either, because the behaviour tests quote bad answers on purpose.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STOP = re.compile("|".join([
    r"own risk", r"no warrant", r"without warrant",
    r"not (?:a |an )?(?:legal|financial|medical|tax|professional) advice",
    r"educational (?:purpose|use)", r"anonymi[sz]ed data only", r"only (?:for )?anonymi[sz]ed",
    r"consult (?:a|an|your) (?:lawyer|professional|specialist|expert|accountant|doctor)",
    r"\bfor now\b", r"\bunfortunately\b", r"\bhonestly\b", r"\bsorry\b", r"\bwe apologi[sz]e",
    r"\bapologies\b", r"can'?t yet", r"cannot yet", r"\bnot yet able\b", r"\bdisclaimer\b",
    # Russian and Ukrainian voice of the same habits
    "\u043a \u0441\u043e\u0436\u0430\u043b\u0435\u043d\u0438\u044e",          # k sozhaleniyu
    "\u0438\u0437\u0432\u0438\u043d\u0438\u0442\u0435",                      # izvinite
    "\u043f\u0440\u043e\u0448\u0443 \u043f\u0440\u043e\u0449\u0435\u043d\u0438\u044f",  # proshu proshcheniya
    "\u043d\u0430 \u0441\u0432\u043e\u0439 \u0440\u0438\u0441\u043a",        # na svoy risk
    "\u0447\u0435\u0441\u0442\u043d\u043e \u0433\u043e\u0432\u043e\u0440\u044f",  # chestno govorya
    "\u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u044e\u0440\u0438\u0434\u0438\u0447",  # ne yavlyaetsya yuridich
    "\u043f\u0440\u043e\u043a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0438\u0440\u0443\u0439\u0442\u0435\u0441\u044c",  # prokonsultiruytes
    "\u043d\u0430 \u0436\u0430\u043b\u044c",                                  # na zhal' (uk)
    "\u0432\u0438\u0431\u0430\u0447\u0442\u0435",                            # vybachte (uk)
]), re.IGNORECASE)

SKIP_NAMES = {"LICENSE", "NOTICE", "CHANGELOG.md"}
SKIP_DIRS = {".git", "tests", "__pycache__"}
SUFFIXES = {".md", ".json", ".py", ".sh", ".ps1", ".cff", ".yml"}


def texts():
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.name in SKIP_NAMES or SKIP_DIRS & set(rel.parts):
            continue
        if path.suffix in SUFFIXES:
            yield rel, path.read_text(encoding="utf-8")


def test_no_disclaimers_excuses_or_apologies():
    found = []
    for rel, text in texts():
        for number, line in enumerate(text.splitlines(), 1):
            hit = STOP.search(line)
            if hit:
                found.append("%s:%d: %r" % (rel, number, hit.group(0)))
    assert not found, "say it as a capability, not as an excuse:\n" + "\n".join(found)


def test_control_each_stop_phrase_is_caught():
    for bad in ("Use at your own risk.", "This is not legal advice.", "It does nothing for now.",
                "Unfortunately the folder is gone.", "Honestly, it may fail.", "Sorry, no second AI.",
                "\u041a \u0441\u043e\u0436\u0430\u043b\u0435\u043d\u0438\u044e, \u043d\u0435\u0442.",
                "\u0418\u0437\u0432\u0438\u043d\u0438\u0442\u0435."):
        assert STOP.search(bad), bad
    for fine in ("Say it plainly, without apologising.", "The copy is made first, always."):
        assert not STOP.search(fine), fine

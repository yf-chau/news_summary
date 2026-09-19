"""Regression test for the PROHIBITED_CONTENT fallback ladder.

Gemini's PROHIBITED_CONTENT filter is non-configurable and deterministic for a
given prompt, so ``translate_digest_to_english()`` escalates through
increasingly lossy responses. The order matters and is easy to disturb
accidentally, so this pins it down:

    1. reorder the grounding text   -- loses nothing
    2. drop one topic's grounding   -- loses that topic's proper-noun spellings
    3. drop all grounding           -- loses every topic's spellings
    4. drop the offending topic     -- last resort

It also pins the surviving-index contract: when a topic is dropped, the links
in ``main.generate_english_digest()`` are realigned from the returned indices,
and getting that wrong silently attaches each later topic's links to the wrong
story.

Runs offline -- ``generate_response`` is stubbed, so no API key is needed:

    uv run python tests/translation_fallback_test.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemini
from gemini import ProhibitedContentError

ZH = {"topics": [{"topic": f"T{i}", "summary": f"s{i}"} for i in range(5)]}
REFS = {f"T{i}": f"body-{i}" for i in range(5)}
ORIGINAL_ORDER = [f"T{i}" for i in range(5)]

failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f" (want {want!r})"))
    if not ok:
        failures.append(label)


def run(blocks) -> tuple[dict | None, list[int] | None, list[str]]:
    """Run the ladder with a stubbed Gemini that blocks when ``blocks(prompt)``."""
    prompts: list[str] = []

    def fake(prompt, validation_class=None, lang="tc", model=None):
        prompts.append(prompt)
        if blocks(prompt):
            raise ProhibitedContentError("PROHIBITED_CONTENT")
        return {"topics": [{"topic": t, "summary": "x"}
                           for t in re.findall(r'"topic": "(T\d)"', prompt)]}

    real, gemini.generate_response = gemini.generate_response, fake
    try:
        return (*gemini.translate_digest_to_english(ZH, REFS), prompts)
    except ProhibitedContentError:
        return None, None, prompts
    finally:
        gemini.generate_response = real


def ref_order(prompt: str) -> list[str]:
    return re.findall(r"### (T\d)", prompt)


print("1. a reshuffle clears it -- nothing is shed")
result, kept, prompts = run(lambda p: ref_order(p) == ORIGINAL_ORDER)
check("topics kept", [t["topic"] for t in result["topics"]], ORIGINAL_ORDER)
check("source indices", kept, [0, 1, 2, 3, 4])
check("grounding intact", len(ref_order(prompts[-1])), 5)
check("retried, did not resend", len(prompts), 2)

print("\n2. one topic's grounding is toxic -- only that grounding is shed")
result, kept, prompts = run(lambda p: "### T4" in p)
check("topics kept", [t["topic"] for t in result["topics"]], ORIGINAL_ORDER)
check("source indices", kept, [0, 1, 2, 3, 4])
check("T4 grounding dropped", "T4" in ref_order(prompts[-1]), False)
check("other grounding kept", len(ref_order(prompts[-1])), 4)

print("\n3. the topic itself is toxic -- it is skipped, and only then")
result, kept, prompts = run(lambda p: "T4" in p)
check("topics kept", [t["topic"] for t in result["topics"]], ["T0", "T1", "T2", "T3"])
check("source indices realigned", kept, [0, 1, 2, 3])
check("tried shedding first", len(prompts) > gemini.TRANSLATION_SHUFFLE_ATTEMPTS, True)

print("\n4. nothing works -- the block is raised, not swallowed")
result, kept, prompts = run(lambda p: True)
check("gave up", result, None)

print("\n5. reorderings are distinct and never the original")
orders = [ref_order(p) for p in run(lambda p: True)[2][1:1 + gemini.TRANSLATION_SHUFFLE_ATTEMPTS]]
check("all distinct", len({tuple(o) for o in orders}), len(orders))
check("original never resent", ORIGINAL_ORDER in orders, False)

print("\nFAILED: " + ", ".join(failures) if failures else "\nAll checks passed.")
sys.exit(1 if failures else 0)

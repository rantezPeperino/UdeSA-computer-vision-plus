"""Runs the positioner/ tests and prints the specs with each scenario checked off.

Reads the spec.md files under upgrade/specs/, finds in each scenario the line
`- **TEST** test_name` (with the name in backticks), runs those tests with unittest
and prints the spec back Cucumber-style: requirement, scenario with ✔ or ✘, and its steps.

Scenario states:
    ✔ passed        the test passed
    ✘ failed        the test failed, raised an error, or is not in the suite
    ↷ skipped       the test is marked as skipped
    ? no test       the scenario has no TEST line (spec written before the test)

A scenario whose name ends in `(Mocked)` is tested with the external API
simulated; the mark is printed in yellow so it is not mistaken for a real integration.

Exits with code 1 if any scenario failed. With --strict, also if any scenario
has no test.

Usage (from the repo root):
    python scripts/spec_report.py
    python scripts/spec_report.py upgrade/specs/merchant-feed/spec.md
    python scripts/spec_report.py --strict
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "upgrade" / "specs"
TESTS = ROOT / "positioner" / "tests"

RE_TEST = re.compile(r"^- \*\*TEST\*\* `(\w+)`")
RE_STEP = re.compile(r"^- \*\*(\w+)\*\* (.*)")
RE_MOCKED = re.compile(r"\s*\(Mocked\)$")


# ── Reading the spec.md files ─────────────────────────────────────────────────

@dataclass
class Scenario:
    name: str
    steps: list[str] = field(default_factory=list)
    test: str | None = None


@dataclass
class Requirement:
    name: str
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class Spec:
    path: Path
    title: str
    requirements: list[Requirement] = field(default_factory=list)


def read_spec(path: Path) -> Spec:
    spec = Spec(path=path, title=path.parent.name)
    requirement = None
    scenario = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            spec.title = line[2:].strip()
        elif line.startswith("### Requirement:"):
            requirement = Requirement(line.split(":", 1)[1].strip())
            spec.requirements.append(requirement)
            scenario = None
        elif line.startswith("#### Scenario:") and requirement is not None:
            scenario = Scenario(line.split(":", 1)[1].strip())
            requirement.scenarios.append(scenario)
        elif line.startswith("#"):
            # Any other heading (## Tests, ## ADDED Requirements) closes the block.
            requirement = None
            scenario = None
        elif scenario is not None:
            if m := RE_TEST.match(line):
                scenario.test = m.group(1)
            elif m := RE_STEP.match(line):
                scenario.steps.append(f"{m.group(1)} {m.group(2)}")
            elif line.startswith("  ") and scenario.steps:
                # Continuation of a step split over several lines.
                scenario.steps[-1] += " " + line.strip()
    return spec


# ── Running the tests ─────────────────────────────────────────────────────────

def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class Results(unittest.TestResult):
    """Keeps the state of each test by method name."""

    def __init__(self) -> None:
        super().__init__()
        self.states: dict[str, tuple[str, str]] = {}

    def addSuccess(self, test):
        self.states[test._testMethodName] = ("passed", "")

    def addFailure(self, test, err):
        self.states[test._testMethodName] = ("failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        self.states[test._testMethodName] = ("failed", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        self.states[test._testMethodName] = ("skipped", reason)


def run_tests(names: set[str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Run the requested tests. Returns their states and the import errors."""
    sys.path.insert(0, str(ROOT))
    discovered = unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(ROOT))

    by_name: dict[str, unittest.TestCase] = {}
    load_errors = []
    for test in flatten(discovered):
        if isinstance(test, unittest.loader._FailedTest):
            load_errors.append(f"{test.id()}: {test._exception}")
            continue
        name = test._testMethodName
        if name in by_name:
            load_errors.append(f"{name} is duplicated: {by_name[name].id()} and {test.id()}")
        by_name[name] = test

    results = Results()
    unittest.TestSuite(by_name[n] for n in sorted(names) if n in by_name).run(results)
    for name in names - by_name.keys():
        results.states[name] = ("failed", f"There is no test named {name} in {TESTS.relative_to(ROOT)}")
    return results.states, load_errors


# ── Report ────────────────────────────────────────────────────────────────────

COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
SYMBOLS = {"passed": ("✔", "32"), "failed": ("✘", "31"), "skipped": ("↷", "33"), "no test": ("?", "33")}


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def summarize(detail: str) -> str:
    """Return the exception line: the first unindented one after the last frame."""
    lines = detail.strip().splitlines()
    frames = [i for i, line in enumerate(lines) if line.startswith("  ")]
    return lines[frames[-1] + 1] if frames and frames[-1] + 1 < len(lines) else lines[0]


def display_path(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("specs", nargs="*", type=Path, help="spec.md files to report (default: all under upgrade/specs/)")
    parser.add_argument("--strict", action="store_true", help="also fail if a scenario has no test")
    parser.add_argument("--no-steps", action="store_true", help="do not print the WHEN/THEN steps of each scenario")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    paths = args.specs or sorted(SPECS.glob("*/spec.md"))
    specs = sorted((read_spec(p.resolve()) for p in paths), key=lambda s: s.title)
    names = {sc.test for s in specs for r in s.requirements for sc in r.scenarios if sc.test}
    states, load_errors = run_tests(names)

    totals = {state: 0 for state in SYMBOLS}
    details = []
    for spec in specs:
        print(paint(spec.title, "1"), paint(f"  {display_path(spec.path)}", "2"))
        for requirement in spec.requirements:
            print(f"  Requirement: {requirement.name}")
            for scenario in requirement.scenarios:
                state, detail = states[scenario.test] if scenario.test else ("no test", "")
                totals[state] += 1
                symbol, code = SYMBOLS[state]
                name = scenario.name
                if m := RE_MOCKED.search(name):
                    name = name[: m.start()] + " " + paint("(Mocked)", "33")
                print(f"    {paint(symbol, code)} Scenario: {name}")
                if not args.no_steps:
                    for step in scenario.steps:
                        print(paint(f"        {step}", "2"))
                if state == "failed":
                    print(paint(f"        {summarize(detail)}", code))
                    details.append((spec.title, scenario, detail))
        print()

    for error in load_errors:
        print(paint(f"Error loading the tests: {error}", "31"))
    for title, scenario, detail in details:
        print(paint(f"── {title} › {scenario.name} ({scenario.test})", "31"))
        print(detail)

    total = sum(totals.values())
    parts = [paint(f"{n} {state}", SYMBOLS[state][1]) for state, n in totals.items() if n]
    print(f"{total} scenarios: " + ", ".join(parts))

    has_failures = totals["failed"] or load_errors or (args.strict and totals["no test"])
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())

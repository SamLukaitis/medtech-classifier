"""The browser port (web/mdr-engine.js) must agree with the Python engine.

Generates thousands of random DeviceAttributes (booleans biased towards
False so individual rules and exceptions actually get isolated, plus the
known example devices), runs them through both engines, and requires
identical results: final class, qualifiers, every rule's applies/class/
ambiguous flag and deciding clauses, the applicable GSPR categories and
standard ids, the regulatory pathway text and the class drivers.
Skipped if Node isn't installed.
"""

from __future__ import annotations

import dataclasses
import json
import random
import shutil
import subprocess
import typing
from enum import Enum
from pathlib import Path

import pytest

from rules_engine.eu_mdr import EUMDRClassificationEngine
from rules_engine.models import DeviceAttributes, DeviceClass
from regulatory_pathway import build_pathway
from rules_engine.sensitivity import class_drivers
from standards_mapper.eu_mdr import EUMDRStandardsMapper

ENGINE = EUMDRClassificationEngine()
MAPPER = EUMDRStandardsMapper()

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "web" / "mdr-engine.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

RUNNER = """
const eng = require(process.argv[1]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(c => {
  const r = eng.classify(c);
  return {
    cls: r.device_class, q: r.qualifiers,
    rules: r.all_rule_outcomes.map(o => [o.rule_id, o.applies, o.device_class, o.ambiguous, o.matched_clauses]),
    gspr: eng.mapStandards(c).filter(g => g.applies).map(g => [g.requirement_id, g.standards.map(s => s.standard_id)]),
    path: eng.buildPathway(c).map(i => [i.item_id, i.title, i.applies, i.summary, i.citation, i.caveat]),
    drivers: eng.classDrivers(c).map(x => [x.attribute, x.value, x.class_without]),
  };
});
process.stdout.write(JSON.stringify(out));
"""


def _fields():
    hints = typing.get_type_hints(DeviceAttributes)
    return [(f.name, hints[f.name]) for f in dataclasses.fields(DeviceAttributes) if f.name not in ("name", "description")]


def _random_value(rng: random.Random, t):
    if typing.get_origin(t) is typing.Union:
        return rng.choice([None, None] + [c.value for c in DeviceClass])
    if isinstance(t, type) and issubclass(t, Enum):
        return rng.choice([m.value for m in t])
    if t is bool:
        return rng.random() < 0.2
    raise TypeError(t)


def _random_device(rng: random.Random) -> dict:
    d = {}
    for name, t in _fields():
        if rng.random() < 0.6 and t is not bool:
            continue  # leave many enums at default
        d[name] = _random_value(rng, t)
    return d


def _python_result(attrs: dict):
    from cli import device_attributes_from_dict

    device = device_attributes_from_dict(attrs)
    r = ENGINE.classify(device)
    m = MAPPER.map(device, r)
    return {
        "cls": r.device_class.value if r.device_class else None,
        "q": [q.value for q in r.qualifiers],
        "rules": [[o.rule_id, o.applies, o.device_class.value if o.device_class else None, o.ambiguous, o.matched_clauses] for o in r.all_rule_outcomes],
        "gspr": [[g.requirement_id, [s.standard_id for s in g.standards]] for g in m.applicable_requirements],
        "path": [[i.item_id, i.title, i.applies, i.summary, i.citation, i.caveat] for i in build_pathway(device, r)],
        "drivers": [[d.attribute, d.value, d.class_without] for d in class_drivers(device, ENGINE)],
    }


def _run_js(cases: list[dict]) -> list[dict]:
    proc = subprocess.run(
        [NODE, "-e", RUNNER, str(JS)],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_js_defaults_match_python_fields():
    proc = subprocess.run(
        [NODE, "-e", "process.stdout.write(JSON.stringify(require(process.argv[1]).DEFAULTS))", str(JS)],
        capture_output=True, text=True, check=True,
    )
    js_defaults = json.loads(proc.stdout)
    py = DeviceAttributes()
    expected = {}
    for name, _ in _fields():
        v = getattr(py, name)
        expected[name] = v.value if isinstance(v, Enum) else v
    expected["name"] = ""
    assert js_defaults == expected


def test_js_engine_matches_python_on_random_and_example_devices():
    rng = random.Random(20261110)
    cases = [_random_device(rng) for _ in range(6000)]
    cases += [json.loads(p.read_text()) for p in (ROOT / "examples").glob("*.json")]
    for c in cases:
        c.pop("description", None)
    js = _run_js(cases)
    mismatches = []
    for attrs, got in zip(cases, js):
        want = _python_result(attrs)
        if got != want:
            mismatches.append((attrs, want, got))
    assert not mismatches, f"{len(mismatches)} mismatches; first: {mismatches[0]}"
    # Sanity: the random set actually reaches every class and every rule.
    classes = {r["cls"] for r in js}
    assert {"I", "IIa", "IIb", "III"} <= classes
    fired = {rule[0] for r in js for rule in r["rules"] if rule[1]}
    assert len(fired) == 22

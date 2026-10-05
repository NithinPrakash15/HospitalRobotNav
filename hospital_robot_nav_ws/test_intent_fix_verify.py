#!/usr/bin/env python3
"""Standalone verification of the intent-parser confidence fix.

Imports ONLY language.intent_parser + entity_extractor (no networkx/pygame),
so it runs in any Python 3.11+ environment without ROS 2.
"""
import sys
import os

WS = "/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav"
if WS not in sys.path:
    sys.path.insert(0, WS)

from language.intent_parser import IntentParser, IntentType  # noqa: E402
from language.entity_extractor import EntityExtractor        # noqa: E402

# (command, expected_intent)
CASES = [
    ("take paracetamol to room 204",   "DELIVER_MEDICINE"),
    ("navigate to the pharmacy",       "NAVIGATE"),
    ("deliver medicine to room 205",   "DELIVER_MEDICINE"),
    ("emergency code blue in icu",     "EMERGENCY"),
    ("guide patient to radiology",     "GUIDE_PATIENT"),
    ("go to icu",                      "NAVIGATE"),
    ("call nurse to room 101",         "CALL_NURSE"),
    ("bring wheelchair to room 205",   "FETCH_WHEELCHAIR"),
    ("deliver the lab results to ICU", "DELIVER_REPORT"),
    ("transport a blood sample to lab","TRANSPORT_SAMPLE"),
    ("escort the visitor to radiology","ESCORT_VISITOR"),
    ("what is your battery level",     "STATUS_QUERY"),
    ("cancel that mission",            "CANCEL"),
]

p = IntentParser()
e = EntityExtractor()
print(f"{'COMMAND':44} -> {'GOT':20} {'WANT':20} {'CONF':>7}  {'PASS':>4}")
print("-" * 100)
passed = 0
for text, want in CASES:
    r = p.parse(text)
    ok = r.intent.name == want and r.is_valid
    passed += bool(ok)
    print(f"{text!r:44} -> {r.intent.name:20} {want:20} {r.confidence:7.3f}  {'OK' if ok else 'FAIL'}")

# Also confirm entities are still extracted
ent = e.extract("take paracetamol to room 204")
print("\nEntity check 'take paracetamol to room 204':")
print(f"  medicines={ent.medicines}, locations={ent.locations}, room={ent.room_number}")

print(f"\n{'='*60}")
print(f"RESULT: {passed}/{len(CASES)} intent cases pass")
if passed == len(CASES):
    print("ALL CASES PASS — intent parser fix verified.")
    sys.exit(0)
else:
    print("SOME CASES FAILED — check output above.")
    sys.exit(1)


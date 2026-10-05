#!/usr/bin/env python3
"""Reproduce the intent-parser confidence scoring to confirm the NLU bug.

Runs against the project-root language modules (same ones the ROS 2 core
package wraps), printing intent classification + confidence for typical
hospital robot commands.
"""
import sys
import os

WS = "/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav"
if WS not in sys.path:
    sys.path.insert(0, WS)

from language.intent_parser import IntentParser  # noqa: E402

CASES = [
    "take paracetamol to room 204",
    "navigate to the pharmacy",
    "deliver medicine to room 205",
    "emergency code blue in icu",
    "guide patient to radiology",
    "go to icu",
    "call nurse to room 101",
    "bring wheelchair to room 205",
]

p = IntentParser()
print(f"{'COMMAND':46} -> {'INTENT':20} {'CONF':>7}  triggers")
print("-" * 100)
for text in CASES:
    r = p.parse(text)
    trig = ", ".join(r.matched_triggers[:2])
    print(f"{text!r:46} -> {r.intent.name:20} {r.confidence:7.3f}  {trig}")

print("\nThreshold (MIN_CONFIDENCE) is 0.20 — any valid intent below it is misclassified as UNKNOWN.")


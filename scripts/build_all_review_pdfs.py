"""
AAROGYA — Master PDF Builder Runner
Compiles all 4 Team Member Code Review PDFs + Master Team Map PDF.
"""

import os
import sys

# Ensure scripts directory on path
scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

from generate_person_1_doc import generate_person_1_pdf
from generate_person_2_doc import generate_person_2_pdf
from generate_person_3_doc import generate_person_3_pdf
from generate_person_4_doc import generate_person_4_pdf
from generate_team_map_doc import generate_team_map_pdf


def main():
    root_dir = os.path.dirname(scripts_dir)
    print("=" * 72)
    print("  AAROGYA — COMPILING 4-PERSON CODE REVIEW & DEFENSE PACKAGE")
    print("=" * 72)

    targets = [
        ("Person 1 (Frontend & Visualization)", "AAROGYA_Code_Review_Person_1.pdf", generate_person_1_pdf),
        ("Person 2 (Backend & Clinical DB)", "AAROGYA_Code_Review_Person_2.pdf", generate_person_2_pdf),
        ("Person 3 (Agents & Cognitive AI)", "AAROGYA_Code_Review_Person_3.pdf", generate_person_3_pdf),
        ("Person 4 (Robotics & Isaac Sim)", "AAROGYA_Code_Review_Person_4.pdf", generate_person_4_pdf),
        ("Master Team Review Map", "AAROGYA_Team_Code_Review_Map.pdf", generate_team_map_pdf),
    ]

    for label, filename, fn in targets:
        out_path = os.path.join(root_dir, filename)
        print(f"\n>> Generating {label}...")
        fn(out_path)
        if os.path.exists(out_path):
            size_kb = os.path.getsize(out_path) / 1024.0
            print(f"   + [OK] File: {filename} ({size_kb:.1f} KB)")
        else:
            print(f"   - [FAIL] File {filename} was not generated!")
            sys.exit(1)

    print("\n" + "=" * 72)
    print("  ALL 5 CODE REVIEW PDF DOCUMENTS SUCCESSFULLY COMPILED!")
    print("=" * 72)


if __name__ == "__main__":
    main()

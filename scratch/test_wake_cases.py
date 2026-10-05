import sys
import os

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from isaac_sim_hospital.environments.command_interface import detect_wake_word, clean_text

test_phrases = [
    'Hey Arogya',
    'Hey Arogya!',
    'hey arogya',
    'Hey Arōgya',
    'Hey Arogyā',
    'Hey Arogia',
    'Hi Arogya',
    'Hey Arogy',
    'Hey, Arogya',
    'Hey Aarogya',
    'Hey Arogyam',
    'Arogya',
    'Hey Arogya go to ICU',
    'Hey Arogya, deliver medicine to P003',
    'Go to ICU',
    'Deliver Paracetamol to Room 205',
]

print("--- WAKE WORD DETECTION BENCHMARK ---")
for p in test_phrases:
    det, rem = detect_wake_word(p)
    print(f"{p:<38} -> Detected: {str(det):<5} | Rem: '{rem}'")

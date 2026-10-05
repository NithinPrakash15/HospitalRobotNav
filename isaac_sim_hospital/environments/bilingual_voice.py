"""
Bilingual Voice & Dialogue Engine for Arogya Hospital Service Robot
====================================================================
Provides offline, non-blocking text-to-speech synthesis and bilingual
clinical dialogue in English and Hindi (हिंदी).

Features:
- Asynchronous Windows SAPI.SpVoice synthesis (runs on dedicated daemon thread)
- Zero blocking of Isaac Sim simulation or physics stepping
- 8 Clinical Activity Voice Announcements (Dispatched, Reception, Pharmacy,
  Nurse Station, Patient Bedside, Emergency Trauma, ICU Patrol, Docking)
- Formatted bilingual HUD and console notification banners
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass
class ClinicalAnnouncement:
    """Bilingual announcement pair for a clinical hospital milestone."""
    activity_id: str
    activity_name: str
    english_text: str
    hindi_text: str
    spoken_text: str  # Phonetic English string fed to Windows SAPI synthesizer


CLINICAL_VOICE_DATABASE: dict[str, ClinicalAnnouncement] = {
    "DISPATCH": ClinicalAnnouncement(
        activity_id="ACT-01",
        activity_name="Mission Dispatch & Self-Diagnostic",
        english_text="Mission activated. Battery 98 percent. All navigation sensors nominal.",
        hindi_text="मिशन सक्रिय। बैटरी 98 प्रतिशत। सभी नेविगेशन सेंसर सामान्य हैं।",
        spoken_text="Mission activated. Battery 98 percent. All navigation sensors nominal.",
    ),
    "RECEPTION": ClinicalAnnouncement(
        activity_id="ACT-02",
        activity_name="Reception & Patient Triage Check-in",
        english_text="Arrived at Main Reception. Checking inpatient registry and visitor queue.",
        hindi_text="मुख्य रिसेप्शन पर पहुंचे। मरीज पंजीयन और आगंतुक सूची की पुष्टि की जा रही है।",
        spoken_text="Arrived at Main Reception. Checking inpatient registry and visitor queue.",
    ),
    "PHARMACY": ClinicalAnnouncement(
        activity_id="ACT-03",
        activity_name="Medication Collection & Verification",
        english_text="Main Pharmacy reached. Loading prescribed Paracetamol and IV fluids onto medicine tray.",
        hindi_text="मुख्य फार्मेसी पहुंचे। ट्रे पर निर्धारित पैरासिटामोल और आईवी ड्रिप दवाएं लोड की जा रही हैं।",
        spoken_text="Main Pharmacy reached. Loading prescribed medication onto delivery tray.",
    ),
    "NURSE_STATION": ClinicalAnnouncement(
        activity_id="ACT-04",
        activity_name="Central Nurse Station Chart Handoff",
        english_text="Nurse Station hub reached. Delivering updated patient diagnostic chart to Sister Priya.",
        hindi_text="सेंट्रल नर्स स्टेशन पहुंचे। सिस्टर प्रिया को मरीज का डायग्नोस्टिक चार्ट सौंपा जा रहा है।",
        spoken_text="Nurse Station hub reached. Delivering updated patient chart to Sister Priya.",
    ),
    "WARD_BEDSIDE": ClinicalAnnouncement(
        activity_id="ACT-05",
        activity_name="Patient Bedside Delivery & Vitals Check",
        english_text="Delivering prescribed medication to Patient Bed 1 in Recovery Ward 101.",
        hindi_text="वार्ड 101 में मरीज बेड 1 के लिए दवा वितरित की जा रही है। कृपया दवा स्वीकार करें।",
        spoken_text="Delivering prescribed medication to Patient Bed 1 in Recovery Ward 101.",
    ),
    "EMERGENCY_ALERT": ClinicalAnnouncement(
        activity_id="ACT-06",
        activity_name="Emergency Trauma Resuscitation Supply Drop",
        english_text="Code Blue Alert! Expedited transit to Emergency Trauma Bay with resuscitation kit.",
        hindi_text="आपातकालीन चेतावनी! आपातकालीन विभाग के लिए प्राथमिकता मार्ग। कृपया रास्ता साफ करें।",
        spoken_text="Code Blue Alert! Expedited transit to Emergency Trauma Bay with resuscitation kit.",
    ),
    "ICU_PATROL": ClinicalAnnouncement(
        activity_id="ACT-07",
        activity_name="Critical Care & Telemetry Escort Patrol",
        english_text="Passing ICU and NICU Critical Care corridor. Maintaining silent mode.",
        hindi_text="आईसीयू और एनआईसीयू वार्ड से गुजर रहे हैं। शांत क्षेत्र प्रोटोकॉल सक्रिय है।",
        spoken_text="Passing Intensive Care Unit corridor. Maintaining silent mode.",
    ),
    "DOCKING": ClinicalAnnouncement(
        activity_id="ACT-08",
        activity_name="Autonomous Return & Recharging",
        english_text="Hospital delivery mission accomplished. Successfully docking on Charging Pad 1.",
        hindi_text="अस्पताल डिलीवरी मिशन पूर्ण हुआ। चार्जिंग स्टेशन पर सफलतापूर्वक डॉकिंग हो रही है।",
        spoken_text="Hospital delivery mission accomplished. Successfully docking on Charging Pad 1.",
    ),
}


class BilingualVoiceEngine:
    """Asynchronous bilingual speech synthesizer and clinical HUD broadcaster."""

    def __init__(self, enable_audio: bool = True) -> None:
        self.enable_audio = enable_audio
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self._running = True
        self._current_activity: ClinicalAnnouncement | None = None
        self.is_speaking: bool = False

        # Start dedicated background worker for non-blocking speech
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker_thread.start()

    def _speech_worker(self) -> None:
        """Background thread worker to synthesize speech via Windows SAPI."""
        while self._running:
            try:
                text_to_speak = self._speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if not self.enable_audio or not text_to_speak:
                self._speech_queue.task_done()
                continue

            try:
                self.is_speaking = True
                # Sanitize text for PowerShell COM invocation
                clean_text = text_to_speak.replace("'", "").replace('"', '').replace(';', ',')
                cmd = f"(New-Object -ComObject SAPI.SpVoice).Speak('{clean_text}')"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                    check=False,
                )
            except Exception:
                pass
            finally:
                self.is_speaking = False
                self._speech_queue.task_done()

    def trigger_clinical_announcement(self, key: str) -> None:
        """Broadcast and speak a clinical hospital milestone announcement."""
        announcement = CLINICAL_VOICE_DATABASE.get(key)
        if not announcement:
            return

        self._current_activity = announcement

        # Print rich bilingual visual banner to console & HUD
        banner = (
            "\n"
            + "=" * 76 + "\n"
            + f"  [VOICE / आवाज़] AROGYA ROBOT CLINICAL ANNOUNCEMENT\n"
            + f"  Activity: {announcement.activity_id} -- {announcement.activity_name}\n"
            + "-" * 76 + "\n"
            + f"  EN (English) : \"{announcement.english_text}\"\n"
            + f"  HI (हिंदी)    : \"{announcement.hindi_text}\"\n"
            + "=" * 76 + "\n"
        )
        try:
            print(banner, flush=True)
        except UnicodeEncodeError:
            ascii_banner = (
                "\n"
                + "=" * 76 + "\n"
                + f"  [VOICE] AROGYA ROBOT CLINICAL ANNOUNCEMENT\n"
                + f"  Activity: {announcement.activity_id} -- {announcement.activity_name}\n"
                + "-" * 76 + "\n"
                + f"  EN (English) : \"{announcement.english_text}\"\n"
                + f"  HI (Hindi)   : \"{announcement.hindi_text.encode('ascii', 'backslashreplace').decode('ascii')}\"\n"
                + "=" * 76 + "\n"
            )
            print(ascii_banner, flush=True)

        # Enqueue voice synthesis for audible speaker playback
        if self.enable_audio:
            self._speech_queue.put(announcement.spoken_text)

    def speak_bilingual(self, english_text: str, hindi_text: str, title: str = "MISSION UPDATE") -> None:
        """Dynamically broadcast and speak any clinical bilingual update."""
        banner = (
            "\n"
            + "=" * 76 + "\n"
            + f"  [VOICE / आवाज़] AROGYA ROBOT -- {title.upper()}\n"
            + "-" * 76 + "\n"
            + f"  EN (English) : \"{english_text}\"\n"
            + f"  HI (हिंदी)    : \"{hindi_text}\"\n"
            + "=" * 76 + "\n"
        )
        try:
            print(banner, flush=True)
        except UnicodeEncodeError:
            ascii_banner = (
                "\n"
                + "=" * 76 + "\n"
                + f"  [VOICE] AROGYA ROBOT -- {title.upper()}\n"
                + "-" * 76 + "\n"
                + f"  EN (English) : \"{english_text}\"\n"
                + f"  HI (Hindi)   : \"{hindi_text.encode('ascii', 'backslashreplace').decode('ascii')}\"\n"
                + "=" * 76 + "\n"
            )
            print(ascii_banner, flush=True)

        if self.enable_audio and english_text:
            self._speech_queue.put(english_text)

    def get_current_activity_name(self) -> str:
        """Return human-readable active activity name."""
        if self._current_activity:
            return f"{self._current_activity.activity_id}: {self._current_activity.activity_name}"
        return "Standby"

    def speak_idle_greeting(self) -> None:
        """Announce system ready in IDLE state on startup."""
        self.speak_bilingual(
            english_text=(
                "Arogya hospital assistant robot online. "
                "All systems nominal. Awaiting your command."
            ),
            hindi_text=(
                "आरोग्य अस्पताल सहायक रोबोट ऑनलाइन है। "
                "सभी सिस्टम सामान्य हैं। आपके आदेश की प्रतीक्षा है।"
            ),
            title="SYSTEM READY",
        )

    def speak_command_acknowledgment(self, english_text: str, hindi_text: str) -> None:
        """Acknowledge a received voice or keyboard command."""
        self.speak_bilingual(
            english_text=english_text,
            hindi_text=hindi_text,
            title="COMMAND RECEIVED",
        )

    def speak_mission_complete(self) -> None:
        """Announce mission completion and return to charging bay."""
        self.speak_bilingual(
            english_text=(
                "All clinical tasks completed successfully. "
                "Returning to charging bay. Mission accomplished."
            ),
            hindi_text=(
                "सभी क्लिनिकल कार्य सफलतापूर्वक पूर्ण हुए। "
                "चार्जिंग बे पर वापस जा रहे हैं। मिशन सफल।"
            ),
            title="MISSION COMPLETE",
        )

    def shutdown(self) -> None:
        """Clean shutdown of speech worker thread."""
        self._running = False
        try:
            # Drain any remaining items
            while not self._speech_queue.empty():
                try:
                    self._speech_queue.get_nowait()
                    self._speech_queue.task_done()
                except Exception:
                    break
        except Exception:
            pass
        # Give the worker a moment to exit cleanly
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

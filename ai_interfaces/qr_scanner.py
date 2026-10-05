"""
HospitalRobotNav — QR Code Scanner Interface
===============================================
QR code scanning for medicine verification and patient wristband reading.

In the simulation, QR codes are generated synthetically. In deployment,
the camera feed is processed with ``pyzbar`` or ``cv2.QRCodeDetector``.

Architecture Note (ROS2):
    Publishes verified scan results to /robot/qr_scan (std_msgs/String).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np

from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class QRScanResult:
    """Result of a QR code scan.

    Attributes:
        raw_data:     Decoded QR string.
        scan_type:    Category — 'medicine', 'patient', 'room', 'unknown'.
        item_id:      Parsed item identifier.
        verified:     True if the QR content passed validation.
        error:        Error message if verification failed.
    """
    raw_data: str = ""
    scan_type: str = "unknown"
    item_id: str = ""
    verified: bool = False
    error: str = ""


class QRScanner:
    """QR code scanner with simulated and real modes.

    Simulated mode generates deterministic QR content from item names.
    Real mode uses OpenCV or pyzbar to decode from camera frames.
    """

    def __init__(self, simulated: bool = True) -> None:
        self._simulated = simulated
        self._scan_count = 0

    # ── Simulated scanning ───────────────────────────────────────────────────

    def generate_medicine_qr(self, medicine_name: str, batch_id: str = "B001") -> str:
        """Generate a simulated QR data string for a medicine item."""
        payload = {
            "type": "medicine",
            "name": medicine_name,
            "batch": batch_id,
            "hash": hashlib.sha256(f"{medicine_name}:{batch_id}".encode()).hexdigest()[:12],
        }
        return json.dumps(payload)

    def generate_patient_qr(self, patient_id: str, room: str) -> str:
        """Generate a simulated QR data string for a patient wristband."""
        payload = {
            "type": "patient",
            "id": patient_id,
            "room": room,
            "hash": hashlib.sha256(f"{patient_id}:{room}".encode()).hexdigest()[:12],
        }
        return json.dumps(payload)

    # ── Scanning ─────────────────────────────────────────────────────────────

    def scan_frame(self, frame: Optional[np.ndarray] = None) -> Optional[QRScanResult]:
        """Attempt to scan a QR code from a camera frame.

        In simulated mode, returns None (no QR in simulated scene).
        In real mode, processes the frame with OpenCV QR detector.

        Args:
            frame: BGR image (or None in simulated mode).

        Returns:
            ``QRScanResult`` if a QR was found, else None.
        """
        if self._simulated:
            return None

        if frame is None:
            return None

        # Real QR detection
        try:
            import cv2
            detector = cv2.QRCodeDetector()
            data, vertices, _ = detector.detectAndDecode(frame)
            if data:
                self._scan_count += 1
                return self._parse_qr_data(data)
        except ImportError:
            log.warning("cv2 not available for QR scanning")
        except Exception as exc:
            log.error("QR scan failed: %s", exc)

        return None

    def verify_medicine(self, qr_data: str, expected_name: str) -> QRScanResult:
        """Verify a medicine QR code matches the expected medicine name.

        Args:
            qr_data:       Raw QR data string (JSON).
            expected_name: The medicine name we expect.

        Returns:
            ``QRScanResult`` with verified=True/False.
        """
        result = self._parse_qr_data(qr_data)
        if result.scan_type != "medicine":
            result.verified = False
            result.error = f"Expected medicine QR, got '{result.scan_type}'"
            return result

        if result.item_id.lower() != expected_name.lower():
            result.verified = False
            result.error = f"Medicine mismatch: expected '{expected_name}', got '{result.item_id}'"
            return result

        result.verified = True
        log.info("Medicine QR verified: %s", expected_name)
        return result

    def verify_patient(self, qr_data: str, expected_id: str) -> QRScanResult:
        """Verify a patient wristband QR code."""
        result = self._parse_qr_data(qr_data)
        if result.scan_type != "patient":
            result.verified = False
            result.error = f"Expected patient QR, got '{result.scan_type}'"
            return result

        if result.item_id != expected_id:
            result.verified = False
            result.error = f"Patient mismatch: expected '{expected_id}', got '{result.item_id}'"
            return result

        result.verified = True
        return result

    # ── Internal ─────────────────────────────────────────────────────────────

    def _parse_qr_data(self, raw: str) -> QRScanResult:
        """Parse a raw QR data string into a structured result."""
        try:
            payload = json.loads(raw)
            scan_type = payload.get("type", "unknown")
            item_id = payload.get("name", payload.get("id", ""))
            return QRScanResult(
                raw_data=raw,
                scan_type=scan_type,
                item_id=item_id,
            )
        except json.JSONDecodeError:
            return QRScanResult(raw_data=raw, error="Invalid JSON")

    @property
    def scan_count(self) -> int:
        return self._scan_count

    def __repr__(self) -> str:
        mode = "simulated" if self._simulated else "real"
        return f"QRScanner(mode={mode}, scans={self._scan_count})"

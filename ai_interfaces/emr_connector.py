"""
HospitalRobotNav — Electronic Medical Record (EMR) Connector
==============================================================
Connector interface for Electronic Medical Records (EMR/EHR) system
using HL7 FHIR (Fast Healthcare Interoperability Resources) data models.

Allows the autonomous robot platform to query active medication orders,
verify patient prescriptions, and log completion of medicine deliveries.

Architecture Note (ROS2):
    Acts as a bridge service between ROS2 mission node and RESTful EMR API endpoint.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class MedicationOrder:
    """FHIR-compatible MedicationOrder resource."""
    order_id: str
    patient_id: str
    medicine_name: str
    dosage: str
    frequency: str
    status: str = "active"  # active | completed | cancelled
    prescribed_by: str = ""
    timestamp: float = field(default_factory=time.time)


class EMRConnector:
    """Connector interface to simulated or RESTful FHIR EMR system."""

    def __init__(self, endpoint: str = "https://fhir.hospital.org/api/v1") -> None:
        self.endpoint = endpoint
        self._mock_orders: Dict[str, MedicationOrder] = {
            "ORD-001": MedicationOrder(
                order_id="ORD-001",
                patient_id="P205",
                medicine_name="Paracetamol",
                dosage="500mg",
                frequency="Q8H",
                prescribed_by="Dr. Sharma",
            ),
            "ORD-002": MedicationOrder(
                order_id="ORD-002",
                patient_id="P101",
                medicine_name="Amoxicillin",
                dosage="250mg",
                frequency="Q12H",
                prescribed_by="Dr. Smith",
            ),
        }

    def get_medication_order(self, order_id: str) -> Optional[MedicationOrder]:
        """Fetch medication order by ID."""
        return self._mock_orders.get(order_id)

    def get_active_orders_for_patient(self, patient_id: str) -> List[MedicationOrder]:
        """Fetch all active medication orders for a patient."""
        return [
            order for order in self._mock_orders.values()
            if order.patient_id.upper() == patient_id.upper() and order.status == "active"
        ]

    def verify_prescription(self, patient_id: str, medicine_name: str) -> bool:
        """Verify whether a patient has a valid active prescription for a given medicine."""
        orders = self.get_active_orders_for_patient(patient_id)
        for order in orders:
            if order.medicine_name.lower() == medicine_name.lower():
                return True
        return False

    def log_delivery_complete(self, order_id: str, robot_id: str) -> bool:
        """Log medication delivery completion to the EMR system."""
        order = self.get_medication_order(order_id)
        if not order:
            log.warning("EMR order %s not found for completion log", order_id)
            return False

        order.status = "completed"
        log.info("EMR updated: Order %s delivered to patient %s by robot %s",
                 order_id, order.patient_id, robot_id)
        return True

    def __repr__(self) -> str:
        return f"EMRConnector(endpoint='{self.endpoint}', active_orders={len(self._mock_orders)})"

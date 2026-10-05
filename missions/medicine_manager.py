"""
HospitalRobotNav — Medicine Manager
======================================
Medicine database, pharmacy inventory, and collection/delivery logic.

Responsibilities:
    - Maintain a pharmacy inventory of 30+ medications.
    - Track medicine stock levels (simulated).
    - Validate medicine requests (name exists, in stock).
    - Manage robot carrying state (what medicine is on-board).
    - Record collection/delivery history for audit trail.

Design:
    The MedicineManager is the single source of truth for medicine state.
    It is queried by the MissionExecutor during COLLECT and DELIVER steps,
    and by the MedicineAnimation for visual state updates.

ROS2 Deployment Note:
    Maps to a ``pharmacy_inventory_node`` with services:
        /pharmacy/check_stock (custom_msgs/CheckStock)
        /pharmacy/dispense (custom_msgs/Dispense)
        /pharmacy/receive (custom_msgs/Receive)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from language.language_config import MEDICINE_FORMULARY, KNOWN_MEDICINES
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Medicine Item
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MedicineItem:
    """A specific medicine instance being carried or delivered.

    Attributes:
        item_id:    Unique identifier for this item instance.
        name:       Medicine name (e.g., "Paracetamol").
        category:   Drug category (e.g., "analgesic").
        quantity:   Number of units.
        source:     Where it was collected from.
        destination: Where it is being delivered to.
        collected_at: Timestamp of collection.
        delivered_at: Timestamp of delivery (0 if not yet delivered).
    """
    item_id: str = ""
    name: str = ""
    category: str = ""
    quantity: int = 1
    source: str = "Pharmacy"
    destination: str = ""
    collected_at: float = 0.0
    delivered_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = f"MED-{str(uuid.uuid4())[:6].upper()}"

    @property
    def is_delivered(self) -> bool:
        return self.delivered_at > 0.0

    @property
    def transit_time_sec(self) -> float:
        """Time in transit (collection to delivery) in seconds."""
        if self.delivered_at > 0 and self.collected_at > 0:
            return self.delivered_at - self.collected_at
        if self.collected_at > 0:
            return time.monotonic() - self.collected_at
        return 0.0

    def __repr__(self) -> str:
        status = "DELIVERED" if self.is_delivered else "IN TRANSIT"
        return f"MedicineItem({self.item_id}, '{self.name}', {status})"


# ─────────────────────────────────────────────────────────────────────────────
# Inventory Slot
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InventorySlot:
    """A single medicine slot in the pharmacy inventory.

    Attributes:
        name:       Medicine name.
        category:   Drug category.
        stock:      Current stock count.
        max_stock:  Maximum capacity.
        dispensed:  Total units dispensed.
    """
    name: str
    category: str
    stock: int = 50
    max_stock: int = 100
    dispensed: int = 0

    @property
    def is_available(self) -> bool:
        return self.stock > 0

    @property
    def stock_percent(self) -> float:
        if self.max_stock == 0:
            return 0.0
        return (self.stock / self.max_stock) * 100

    def dispense(self, quantity: int = 1) -> bool:
        """Attempt to dispense units from stock.

        Returns:
            True if successful, False if insufficient stock.
        """
        if self.stock >= quantity:
            self.stock -= quantity
            self.dispensed += quantity
            return True
        return False

    def restock(self, quantity: int = 50) -> None:
        """Restock the slot."""
        self.stock = min(self.stock + quantity, self.max_stock)


# ─────────────────────────────────────────────────────────────────────────────
# Robot Carrying State
# ─────────────────────────────────────────────────────────────────────────────

class CarryingState(Enum):
    """Robot medicine-carrying states."""
    EMPTY       = auto()    # Not carrying anything
    LOADING     = auto()    # In the process of collecting
    CARRYING    = auto()    # Medicine on-board, in transit
    UNLOADING   = auto()    # In the process of delivering
    DELIVERED   = auto()    # Just delivered (transition state)


# ─────────────────────────────────────────────────────────────────────────────
# Medicine Manager
# ─────────────────────────────────────────────────────────────────────────────

class MedicineManager:
    """Pharmacy inventory and medicine lifecycle manager.

    Usage::

        manager = MedicineManager()

        # Check if medicine is available
        if manager.is_available("Paracetamol"):
            # Collect it
            item = manager.collect("Paracetamol", destination="Room 205")
            # Robot carries it...
            # Deliver it
            manager.deliver(item)

    Attributes:
        inventory:      Medicine inventory dictionary.
        carrying_state: Current robot carrying state.
        carrying_item:  Medicine item currently on the robot (or None).
        delivery_history: List of completed deliveries.
    """

    def __init__(self) -> None:
        # Build inventory from formulary
        self.inventory: Dict[str, InventorySlot] = {}
        for name, info in MEDICINE_FORMULARY.items():
            # Avoid duplicates (some medicines have aliases)
            if name not in self.inventory:
                self.inventory[name] = InventorySlot(
                    name=name.title(),
                    category=info.get("category", "general"),
                    stock=50,
                    max_stock=100,
                )

        # Carrying state
        self.carrying_state: CarryingState = CarryingState.EMPTY
        self.carrying_item: Optional[MedicineItem] = None

        # History
        self.delivery_history: List[MedicineItem] = []
        self._history_max = 100

        # Statistics
        self.total_collected: int = 0
        self.total_delivered: int = 0

        log.info(
            "MedicineManager initialised with %d medicines in inventory.",
            len(self.inventory),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Query API
    # ─────────────────────────────────────────────────────────────────────────

    def is_available(self, medicine_name: str) -> bool:
        """Check if a medicine is in stock.

        Args:
            medicine_name: Medicine name (case-insensitive).

        Returns:
            True if available and in stock.
        """
        key = medicine_name.strip().lower()
        slot = self.inventory.get(key)
        return slot is not None and slot.is_available

    def get_medicine(self, medicine_name: str) -> Optional[InventorySlot]:
        """Get inventory slot object by name."""
        key = medicine_name.strip().lower()
        return self.inventory.get(key)

    def verify_stock(self, medicine_name: str, quantity: int = 1) -> bool:
        """Verify that at least quantity units of medicine are available."""
        slot = self.get_medicine(medicine_name)
        return slot is not None and slot.stock >= quantity

    def get_stock(self, medicine_name: str) -> int:
        """Get current stock count for a medicine.

        Args:
            medicine_name: Medicine name (case-insensitive).

        Returns:
            Stock count, or 0 if not found.
        """
        key = medicine_name.strip().lower()
        slot = self.inventory.get(key)
        return slot.stock if slot else 0

    def lookup(self, medicine_name: str) -> Optional[InventorySlot]:
        """Look up a medicine in the inventory.

        Args:
            medicine_name: Medicine name (case-insensitive).

        Returns:
            InventorySlot if found, else None.
        """
        key = medicine_name.strip().lower()
        return self.inventory.get(key)

    def search(self, query: str) -> List[InventorySlot]:
        """Search inventory by partial name or category.

        Args:
            query: Search query string.

        Returns:
            List of matching InventorySlots.
        """
        query_lower = query.strip().lower()
        results = []
        for key, slot in self.inventory.items():
            if query_lower in key or query_lower in slot.category:
                results.append(slot)
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Collection & Delivery API
    # ─────────────────────────────────────────────────────────────────────────

    def collect(
        self,
        medicine_name: str,
        quantity: int = 1,
        destination: str = "",
        source: str = "Pharmacy",
    ) -> Optional[MedicineItem]:
        """Collect medicine from the pharmacy.

        Dispenses from inventory and creates a MedicineItem for the robot.

        Args:
            medicine_name: Medicine to collect.
            quantity: Number of units.
            destination: Where it will be delivered.
            source: Where it is being collected from.

        Returns:
            MedicineItem if successful, None if out of stock.
        """
        key = medicine_name.strip().lower()
        slot = self.inventory.get(key)

        if slot is None:
            log.warning("MedicineManager: Unknown medicine '%s'.", medicine_name)
            return None

        if not slot.dispense(quantity):
            log.warning(
                "MedicineManager: Insufficient stock for '%s' (have %d, need %d).",
                medicine_name, slot.stock, quantity,
            )
            return None

        item = MedicineItem(
            name=slot.name,
            category=slot.category,
            quantity=quantity,
            source=source,
            destination=destination,
            collected_at=time.monotonic(),
        )

        self.carrying_state = CarryingState.CARRYING
        self.carrying_item = item
        self.total_collected += 1

        log.info(
            "MedicineManager: Collected %s (qty=%d, stock remaining=%d).",
            item.name, quantity, slot.stock,
        )

        return item

    def deliver(self, item: Optional[MedicineItem] = None) -> bool:
        """Deliver the currently carried medicine.

        Args:
            item: Specific MedicineItem to deliver (uses carrying_item if None).

        Returns:
            True if delivery was successful.
        """
        target = item or self.carrying_item

        if target is None:
            log.warning("MedicineManager: Nothing to deliver.")
            return False

        target.delivered_at = time.monotonic()

        # Record in history
        self.delivery_history.append(target)
        if len(self.delivery_history) > self._history_max:
            self.delivery_history.pop(0)

        self.total_delivered += 1
        self.carrying_state = CarryingState.EMPTY
        self.carrying_item = None

        log.info(
            "MedicineManager: Delivered %s to %s (transit: %.1f s).",
            target.name, target.destination, target.transit_time_sec,
        )

        return True

    def drop(self) -> None:
        """Drop/cancel the currently carried medicine (return to inventory)."""
        if self.carrying_item:
            key = self.carrying_item.name.lower()
            slot = self.inventory.get(key)
            if slot:
                slot.restock(self.carrying_item.quantity)
            log.info("MedicineManager: Dropped %s — returned to inventory.", self.carrying_item.name)
            self.carrying_item = None
            self.carrying_state = CarryingState.EMPTY

    # ─────────────────────────────────────────────────────────────────────────
    # State Queries
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def is_carrying(self) -> bool:
        """True if the robot is currently carrying medicine."""
        return self.carrying_state == CarryingState.CARRYING and self.carrying_item is not None

    @property
    def carrying_description(self) -> str:
        """Human-readable description of what the robot is carrying."""
        if self.carrying_item:
            return f"{self.carrying_item.name} (qty: {self.carrying_item.quantity})"
        return "Nothing"

    @property
    def low_stock_medicines(self) -> List[InventorySlot]:
        """List of medicines with stock below 20%."""
        return [
            slot for slot in self.inventory.values()
            if slot.stock_percent < 20.0
        ]

    def get_inventory_summary(self) -> List[Dict[str, any]]:
        """Get a summary of the full inventory for display.

        Returns:
            List of dicts with name, category, stock, max_stock.
        """
        return [
            {
                "name": slot.name,
                "category": slot.category,
                "stock": slot.stock,
                "max_stock": slot.max_stock,
                "dispensed": slot.dispensed,
            }
            for slot in sorted(self.inventory.values(), key=lambda s: s.name)
        ]

"""
HospitalRobotNav — Dialogue Templates
========================================
Response template database for the robot's conversational interface.

Provides 50+ contextual response templates organised by dialogue phase:
    - Greetings (wake word responses)
    - Confirmations (mission confirmation prompts)
    - Progress updates (navigation/delivery progress)
    - Completion messages (mission finished)
    - Error / failure messages
    - Clarification requests
    - Status reports
    - Emergency announcements

Design:
    Templates use Python ``str.format()`` placeholders for dynamic
    content insertion.  Each template category has multiple variants
    to avoid repetitive robot speech.

Usage:
    templates = DialogueTemplates()
    msg = templates.confirmation(
        task="Deliver Paracetamol",
        destination="Room 205",
    )
"""

from __future__ import annotations

import random
from typing import Any, Dict, List


# ─────────────────────────────────────────────────────────────────────────────
# Template Database
# ─────────────────────────────────────────────────────────────────────────────

class DialogueTemplates:
    """Contextual response template engine for the hospital robot.

    Each method returns a randomly selected template with the given
    parameters filled in.  This prevents the robot from sounding
    repetitive across interactions.
    """

    # ── Greetings ────────────────────────────────────────────────────────────

    _GREETINGS = [
        "Hello! How may I assist you?",
        "I'm listening. What can I do for you?",
        "Hi there! Ready to help.",
        "Yes? How can I help you today?",
        "I'm here. Please tell me what you need.",
        "Good day! What task would you like me to perform?",
        "At your service. What do you need?",
        "Hello! I'm ready for your instructions.",
    ]

    def greeting(self) -> str:
        """Return a random greeting response."""
        return random.choice(self._GREETINGS)

    # ── Confirmations ────────────────────────────────────────────────────────

    _CONFIRMATIONS = [
        "I understood your request.\n{task_summary}\nWould you like me to begin?",
        "Got it. Here's what I'll do:\n{task_summary}\nShall I proceed?",
        "Understood. My plan is:\n{task_summary}\nReady to start?",
        "I've parsed your request:\n{task_summary}\nDo you want me to go ahead?",
        "Confirmed. I will:\n{task_summary}\nShould I start now?",
    ]

    def confirmation(self, task_summary: str, **kwargs: Any) -> str:
        """Generate a confirmation prompt for a parsed mission.

        Args:
            task_summary: Human-readable summary of the planned task.
        """
        template = random.choice(self._CONFIRMATIONS)
        return template.format(task_summary=task_summary, **kwargs)

    # ── Mission Start ────────────────────────────────────────────────────────

    _MISSION_STARTED = [
        "Mission started. I'm on my way.",
        "Understood. Beginning mission now.",
        "Starting the task. I'll keep you updated.",
        "On it! I'll notify you when I'm done.",
        "Mission accepted. Moving out now.",
    ]

    def mission_started(self) -> str:
        """Announce mission commencement."""
        return random.choice(self._MISSION_STARTED)

    # ── Navigation Progress ──────────────────────────────────────────────────

    _PROGRESS_NAV = [
        "I'm on my way to {destination}. ETA: {eta}.",
        "Heading to {destination} now. Estimated arrival in {eta}.",
        "Navigating to {destination}. I should arrive in {eta}.",
        "En route to {destination}. Approximately {eta} remaining.",
    ]

    def navigation_progress(self, destination: str, eta: str) -> str:
        """Report navigation progress.

        Args:
            destination: Where the robot is heading.
            eta: Estimated time of arrival string.
        """
        template = random.choice(self._PROGRESS_NAV)
        return template.format(destination=destination, eta=eta)

    # ── Collection Progress ──────────────────────────────────────────────────

    _COLLECTING = [
        "I've arrived at {location}. Collecting {item} now.",
        "At {location}. Picking up {item}.",
        "Reached {location}. Acquiring {item} for delivery.",
        "I'm at {location}. Loading {item} onto my tray.",
    ]

    def collecting(self, location: str, item: str) -> str:
        """Announce item collection at a location.

        Args:
            location: Where the robot is collecting.
            item: What is being collected.
        """
        template = random.choice(self._COLLECTING)
        return template.format(location=location, item=item)

    # ── Delivery Progress ────────────────────────────────────────────────────

    _DELIVERING = [
        "Delivering {item} to {destination} now.",
        "Handing over {item} at {destination}.",
        "I've reached {destination}. Delivering {item}.",
        "Arrived at {destination}. Placing {item} for collection.",
    ]

    def delivering(self, item: str, destination: str) -> str:
        """Announce delivery at destination.

        Args:
            item: What is being delivered.
            destination: Where delivery is happening.
        """
        template = random.choice(self._DELIVERING)
        return template.format(item=item, destination=destination)

    # ── Mission Completion ───────────────────────────────────────────────────

    _MISSION_COMPLETE = [
        "Mission complete! {summary}",
        "Task finished successfully. {summary}",
        "Done! {summary}",
        "I've completed the mission. {summary}",
        "All done. {summary} Returning to standby.",
    ]

    def mission_complete(self, summary: str) -> str:
        """Announce mission completion.

        Args:
            summary: What was accomplished.
        """
        template = random.choice(self._MISSION_COMPLETE)
        return template.format(summary=summary)

    # ── Error Messages ───────────────────────────────────────────────────────

    _ERRORS = [
        "I'm sorry, I encountered an issue. {error}",
        "An error occurred: {error}. I'll need assistance.",
        "Something went wrong. {error}",
        "I apologise — {error}. Please try again.",
        "Error: {error}. Mission paused.",
    ]

    def error(self, error: str) -> str:
        """Report an error or failure.

        Args:
            error: Description of the error.
        """
        template = random.choice(self._ERRORS)
        return template.format(error=error)

    # ── Clarification Requests ───────────────────────────────────────────────

    _CLARIFICATIONS = [
        "I didn't quite understand. Could you repeat that?",
        "Sorry, I'm not sure what you meant. Can you say that again?",
        "I didn't catch that. Could you rephrase your request?",
        "Could you be more specific? I need a bit more detail.",
        "I'm not sure I understood correctly. Please try again.",
    ]

    _CLARIFY_LOCATION = [
        "Which room or department should I go to?",
        "Could you specify the destination?",
        "Where exactly should I deliver that?",
        "I need a destination. Which room or department?",
    ]

    _CLARIFY_MEDICINE = [
        "Which medicine should I collect?",
        "What medication do you need?",
        "Could you specify the medicine name?",
        "Which drug should I pick up from the pharmacy?",
    ]

    _CLARIFY_CHOICE = [
        "Did you mean {option_a} or {option_b}?",
        "I found two options: {option_a} and {option_b}. Which one?",
        "Could you clarify — {option_a} or {option_b}?",
    ]

    def clarification_general(self) -> str:
        """Request general clarification."""
        return random.choice(self._CLARIFICATIONS)

    def clarification_location(self) -> str:
        """Request location/destination clarification."""
        return random.choice(self._CLARIFY_LOCATION)

    def clarification_medicine(self) -> str:
        """Request medicine name clarification."""
        return random.choice(self._CLARIFY_MEDICINE)

    def clarification_choice(self, option_a: str, option_b: str) -> str:
        """Present two options for disambiguation.

        Args:
            option_a: First option.
            option_b: Second option.
        """
        template = random.choice(self._CLARIFY_CHOICE)
        return template.format(option_a=option_a, option_b=option_b)

    # ── Status Reports ───────────────────────────────────────────────────────

    _STATUS = [
        "Current status: {state}. Battery at {battery}%. {extra}",
        "I'm currently {state}. Battery: {battery}%. {extra}",
        "Status: {state}. Battery level is {battery}%. {extra}",
    ]

    def status_report(self, state: str, battery: int, extra: str = "") -> str:
        """Report current robot status.

        Args:
            state: Current robot state (e.g., "idle", "navigating").
            battery: Battery percentage.
            extra: Additional status information.
        """
        template = random.choice(self._STATUS)
        return template.format(state=state, battery=battery, extra=extra)

    # ── Cancellation ─────────────────────────────────────────────────────────

    _CANCELLED = [
        "Mission cancelled. Returning to standby.",
        "Understood. I've cancelled the current task.",
        "Mission aborted. Standing by for new instructions.",
        "Cancelled. What would you like me to do instead?",
    ]

    def cancelled(self) -> str:
        """Announce mission cancellation."""
        return random.choice(self._CANCELLED)

    # ── Emergency ────────────────────────────────────────────────────────────

    _EMERGENCY = [
        "EMERGENCY ALERT! {alert}. Responding immediately!",
        "Code alert received: {alert}. All non-critical tasks suspended.",
        "URGENT: {alert}. I'm responding to this emergency now.",
        "Emergency response activated: {alert}.",
    ]

    def emergency_alert(self, alert: str) -> str:
        """Announce an emergency.

        Args:
            alert: Emergency description.
        """
        template = random.choice(self._EMERGENCY)
        return template.format(alert=alert)

    # ── Waiting / Blocked ────────────────────────────────────────────────────

    _WAITING = [
        "I'm waiting for the corridor to clear.",
        "Path is blocked. Waiting for clearance.",
        "Obstacle ahead. I'll continue once the path is clear.",
        "Temporarily paused — waiting for a safe passage.",
    ]

    def waiting(self) -> str:
        """Announce that the robot is waiting."""
        return random.choice(self._WAITING)

    # ── Battery / Charging ───────────────────────────────────────────────────

    _BATTERY_LOW = [
        "Battery is low ({battery}%). I need to return to the charging dock.",
        "Low battery alert: {battery}%. Heading to the charging station.",
        "My battery is at {battery}%. I must recharge before continuing.",
    ]

    _CHARGING = [
        "I'm charging now. I'll be ready in approximately {time}.",
        "Currently charging at the dock. Estimated time to full: {time}.",
        "Recharging... I'll resume operations once charged ({time} remaining).",
    ]

    def battery_low(self, battery: int) -> str:
        """Announce low battery.

        Args:
            battery: Current battery percentage.
        """
        template = random.choice(self._BATTERY_LOW)
        return template.format(battery=battery)

    def charging(self, time: str) -> str:
        """Announce charging status.

        Args:
            time: Estimated time to full charge.
        """
        template = random.choice(self._CHARGING)
        return template.format(time=time)

    # ── Farewell ─────────────────────────────────────────────────────────────

    _FAREWELL = [
        "Is there anything else I can help with?",
        "Task complete. Let me know if you need anything else.",
        "I'm standing by. Just say my name if you need me.",
        "All done. I'll be here if you need me again.",
    ]

    def farewell(self) -> str:
        """Say farewell after completing a task."""
        return random.choice(self._FAREWELL)

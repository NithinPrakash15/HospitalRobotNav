"""
HospitalRobotNav — Agent Configuration
=========================================
Parameters governing multi-agent coordination, task allocation, and
agent lifecycle management.

Architecture Note (ROS2):
    These parameters map to:
        ros2 param set /agent_coordinator max_agents 5
        ros2 param set /agent_coordinator bid_timeout_sec 2.0
"""

from __future__ import annotations


# ─── Agent Fleet ──────────────────────────────────────────────────────────────
MAX_AGENTS: int = 16                    # Maximum concurrent agents in the fleet
DEFAULT_AGENT_SPEED: float = 2.0        # Cells / second
AGENT_HEARTBEAT_INTERVAL: float = 5.0   # Seconds between heartbeat broadcasts
AGENT_HEARTBEAT_TIMEOUT: float = 15.0   # Seconds before agent marked offline

# ─── Contract-Net Protocol ───────────────────────────────────────────────────
BID_TIMEOUT_SEC: float = 2.0            # Seconds to wait for bids
MIN_BID_CONFIDENCE: float = 0.3         # Minimum bid score to accept
TIE_BREAK_STRATEGY: str = "nearest"     # nearest | highest_battery | random

# ─── Priority Levels ─────────────────────────────────────────────────────────
PRIORITY_CRITICAL: int  = 1             # Emergency — preempt all
PRIORITY_HIGH: int      = 2             # Urgent nurse call
PRIORITY_NORMAL: int    = 3             # Standard delivery / guide
PRIORITY_LOW: int       = 4             # Routine tasks
PRIORITY_BACKGROUND: int = 5            # Return-to-dock, patrol

# ─── Agent Capabilities (bitmask-like tags) ──────────────────────────────────
CAPABILITY_DELIVER   = "deliver"
CAPABILITY_GUIDE     = "guide"
CAPABILITY_ESCORT    = "escort"
CAPABILITY_EMERGENCY = "emergency"
CAPABILITY_TRANSPORT = "transport"
CAPABILITY_FETCH     = "fetch"
CAPABILITY_NAVIGATE  = "navigate"
CAPABILITY_VISION    = "vision"
CAPABILITY_SPEECH    = "speech"
CAPABILITY_ALLOCATE  = "allocate"
CAPABILITY_DETECT    = "detect"
CAPABILITY_INTERACT  = "interact"
CAPABILITY_MEDICINE  = "medicine"
CAPABILITY_MONITOR   = "monitor"
CAPABILITY_HEALTH    = "health"
CAPABILITY_PLAN      = "plan"

# ─── Collision Avoidance ─────────────────────────────────────────────────────
INTER_AGENT_SAFETY_DIST: float = 3.0    # Minimum cells between two agents
CORRIDOR_YIELD_PRIORITY: bool = True    # Lower-priority agent yields corridor

# ─── Logging ─────────────────────────────────────────────────────────────────
AGENT_LOG_LEVEL: str = "INFO"           # DEBUG for per-tick agent logging

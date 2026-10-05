"""
HospitalRobotNav — Main Application Entry Point
=================================================
Multi-Agent Autonomous Hospital Robot Navigation System

Title: "Multi-Agent Embodied AI Robot for Autonomous Hospital Assistance
        using Vision-Language Reasoning"

This is the production-grade entry point for the Pygame simulation.

System Architecture:
    ┌──────────────────────────────────────────────────────────────────┐
    │  Speech Layer  │  NLU/Dialogue  │  Mission System  │  Navigation │
    │  WakeWord STT  │  Intent+Entity │  Planner+Executor│  A*/D*Lite  │
    └──────────────────────────────────────────────────────────────────┘
              ↕ EventBus                      ↕ Robot FSM
    ┌──────────────────────────────────────────────────────────────────┐
    │  Multi-Agent   │  AI Interfaces │  Dashboard       │  Renderer   │
    │  Coordinator   │  LLM/VLM/YOLO │  Speech/Mission  │  Pygame GPU │
    └──────────────────────────────────────────────────────────────────┘

Controls:
    Left Click on Map     → Navigate robot to clicked cell
    Left Click Dest List  → Select a semantic destination
    Mouse Wheel           → Zoom In / Zoom Out
    Middle Mouse Drag     → Pan Map Viewport
    Spacebar              → Pause / Resume Simulation
    R Key                 → Reset Simulation
    + / -                 → Speed Up / Slow Down
    Escape                → Quit

Author: Hospital Robot Navigation Research Team
Project: Multi-Agent Embodied AI Robot for Autonomous Hospital Navigation
"""

from __future__ import annotations

import sys
import pygame

from config.settings import DISPLAY, APP_SETTINGS
from simulation.simulator import Simulator
from visualization.renderer import Renderer
from visualization.hud import HUD
from utilities.event_bus import EVENT_BUS, HospitalEvent
from utilities.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HUD Event Subscriptions
# ─────────────────────────────────────────────────────────────────────────────

def _subscribe_hud_events(hud: "HUD", colors) -> None:
    """Subscribe HUD to hospital events for the event log feed."""

    def _on_path_planned(payload):
        planner = payload.data.get("planner", "")
        cells   = payload.data.get("path_len", 0)
        hud.log_event(f"Path planned: {planner} [{cells} cells]", colors.TEXT_SUCCESS)

    def _on_path_failed(payload):
        hud.log_event("Path planning FAILED", colors.TEXT_DANGER)
        hud.show_alert("PATH FAILED — BLOCKED", duration_s=2.0)

    def _on_replan_start(payload):
        hud.log_event("Replanning triggered...", colors.TEXT_WARNING)

    def _on_replan_done(payload):
        hud.log_event("Replanning complete.", colors.TEXT_SUCCESS)

    def _on_emergency(payload):
        room = payload.data.get("room", "")
        hud.log_event(f"EMERGENCY ALERT! Room: {room}", colors.TEXT_DANGER)
        hud.show_alert("!! EMERGENCY ALERT !!", duration_s=4.0, color=colors.TEXT_DANGER)

    def _on_battery_low(payload):
        hud.log_event("Battery LOW — returning to dock", colors.TEXT_WARNING)
        hud.show_alert("LOW BATTERY — Auto-Docking", duration_s=3.0,
                       color=colors.TEXT_WARNING)

    def _on_goal_reached(payload):
        hud.log_event("Destination reached!", colors.TEXT_SUCCESS)

    def _on_obstacle_add(payload):
        hud.log_event("Dynamic obstacle spawned", colors.TEXT_SECONDARY)

    def _on_planner_changed(payload):
        name = payload.data.get("planner", "")
        hud.log_event(f"Planner switched: {name}", colors.TEXT_ACCENT)

    def _on_reset(payload):
        hud.log_event("Simulation reset", colors.TEXT_SECONDARY)

    def _on_mission_start(payload):
        desc = payload.data.get("description", "")
        hud.log_event(f"Mission started: {desc}", colors.TEXT_ACCENT)

    def _on_mission_complete(payload):
        mission_id = payload.data.get("mission_id", "")
        hud.log_event(f"Mission complete: {mission_id}", colors.TEXT_SUCCESS)

    def _on_mission_failed(payload):
        mission_id = payload.data.get("mission_id", "")
        reason = payload.data.get("reason", "")
        hud.log_event(f"Mission FAILED: {mission_id} ({reason})", colors.TEXT_DANGER)

    def _on_medicine_collected(payload):
        medicine = payload.data.get("medicine", "")
        hud.log_event(f"Medicine collected: {medicine}", colors.TEXT_SUCCESS)

    def _on_medicine_delivered(payload):
        medicine = payload.data.get("medicine", "")
        room = payload.data.get("room", "")
        hud.log_event(f"Delivered {medicine} to {room}", colors.TEXT_SUCCESS)

    def _on_wake_word(payload):
        hud.log_event("Wake word detected — listening...", colors.TEXT_ACCENT)
        hud.show_alert("LISTENING...", duration_s=1.5, color=colors.TEXT_ACCENT)

    def _on_speech_recognised(payload):
        text = payload.data.get("text", "")
        hud.log_event(f"Speech: \"{text}\"", colors.TEXT_SECONDARY)

    def _on_agent_assigned(payload):
        agent_id   = payload.data.get("agent_id", "")
        mission_id = payload.data.get("mission_id", "")
        hud.log_event(f"Agent {agent_id} → mission {mission_id}", colors.TEXT_ACCENT)

    # ── Subscribe all handlers ────────────────────────────────────────────────
    EVENT_BUS.subscribe(HospitalEvent.PATH_PLANNED,        _on_path_planned)
    EVENT_BUS.subscribe(HospitalEvent.PATH_FAILED,         _on_path_failed)
    EVENT_BUS.subscribe(HospitalEvent.REPLANNING_STARTED,  _on_replan_start)
    EVENT_BUS.subscribe(HospitalEvent.REPLANNING_COMPLETE, _on_replan_done)
    EVENT_BUS.subscribe(HospitalEvent.EMERGENCY_ALERT,     _on_emergency)
    EVENT_BUS.subscribe(HospitalEvent.BATTERY_LOW,         _on_battery_low)
    EVENT_BUS.subscribe(HospitalEvent.ROBOT_GOAL_REACHED,  _on_goal_reached)
    EVENT_BUS.subscribe(HospitalEvent.DYNAMIC_OBSTACLE_ADD,_on_obstacle_add)
    EVENT_BUS.subscribe(HospitalEvent.PLANNER_CHANGED,     _on_planner_changed)
    EVENT_BUS.subscribe(HospitalEvent.SIMULATION_RESET,    _on_reset)
    EVENT_BUS.subscribe(HospitalEvent.MISSION_STARTED,     _on_mission_start)
    EVENT_BUS.subscribe(HospitalEvent.MISSION_COMPLETE,    _on_mission_complete)
    EVENT_BUS.subscribe(HospitalEvent.MISSION_FAILED,      _on_mission_failed)
    EVENT_BUS.subscribe(HospitalEvent.MEDICINE_COLLECTED,  _on_medicine_collected)
    EVENT_BUS.subscribe(HospitalEvent.MEDICINE_DELIVERED,  _on_medicine_delivered)
    EVENT_BUS.subscribe(HospitalEvent.WAKE_WORD_DETECTED,  _on_wake_word)
    EVENT_BUS.subscribe(HospitalEvent.SPEECH_RECOGNIZED,   _on_speech_recognised)
    EVENT_BUS.subscribe(HospitalEvent.AGENT_TASK_ASSIGNED, _on_agent_assigned)


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Initialize Pygame and run the main simulation + render loop."""
    log.info("=" * 60)
    log.info("  Hospital Robot Navigation System  — Starting")
    log.info("  Multi-Agent Embodied AI Platform v2.0")
    log.info("=" * 60)

    # ── Pygame Initialization ─────────────────────────────────────────────────
    pygame.init()
    pygame.display.set_caption(DISPLAY.WINDOW_TITLE)
    screen = pygame.display.set_mode(
        (DISPLAY.WINDOW_WIDTH, DISPLAY.WINDOW_HEIGHT),
        pygame.DOUBLEBUF | pygame.HWSURFACE | getattr(pygame, "SCALED", 0),
    )

    clock = pygame.time.Clock()

    # ── Build All Subsystems ──────────────────────────────────────────────────
    simulator = Simulator()
    simulator.initialize()
    simulator.initialize_speech()

    renderer = Renderer(screen)
    hud      = HUD(screen)

    from config.settings import COLORS          # import after pygame init
    _subscribe_hud_events(hud, COLORS)

    # Log system readiness
    fleet_sz = simulator.agent_registry.fleet_size
    hud.log_event(
        f"System ready — {fleet_sz} agents registered. Click a destination.",
        COLORS.TEXT_ACCENT,
    )
    hud.log_event(f"Say 'Hey Arogya' to activate voice commands.", COLORS.TEXT_SECONDARY)

    log.info("Main loop started at target %d FPS.", DISPLAY.TARGET_FPS)

    # ── Main Loop ─────────────────────────────────────────────────────────────
    running = True
    text_input_active = False
    text_buffer = ""

    while running:

        # ── Event Handling ────────────────────────────────────────────────────
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if text_input_active:
                    # ── Text command input box ──────────────────────────────
                    if event.key == pygame.K_RETURN:
                        cmd = text_buffer.strip()
                        text_buffer = ""
                        text_input_active = False
                        if cmd:
                            simulator.process_spoken_command(cmd)
                            hud.log_event(f"> {cmd}", COLORS.TEXT_ACCENT)
                    elif event.key == pygame.K_ESCAPE:
                        text_buffer = ""
                        text_input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        text_buffer = text_buffer[:-1]
                    else:
                        if event.unicode and event.unicode.isprintable():
                            text_buffer += event.unicode
                elif event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_t:
                    # Open text command input box (no-mic fallback)
                    text_input_active = True
                    text_buffer = ""
                    hud.show_alert("TYPE COMMAND — Enter to submit", duration_s=2.0,
                                   color=COLORS.TEXT_ACCENT)

                elif event.key == pygame.K_SPACE:
                    if simulator.clock.is_paused:
                        simulator.resume()
                        hud.log_event("Simulation RESUMED")
                    else:
                        simulator.pause()
                        hud.log_event("Simulation PAUSED")

                elif event.key == pygame.K_r:
                    simulator.reset()
                    renderer.selected_dest = None
                    hud.log_event("Simulation RESET", COLORS.TEXT_WARNING)

                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    simulator.set_speed(min(5, simulator.clock.speed_index + 1))
                    hud.log_event(f"Speed x{simulator.clock.speed_multiplier:.1f}")

                elif event.key == pygame.K_MINUS:
                    simulator.set_speed(max(0, simulator.clock.speed_index - 1))
                    hud.log_event(f"Speed x{simulator.clock.speed_multiplier:.1f}")

                # ── Keyboard medicine delivery shortcuts (demo mode) ────────────
                elif event.key == pygame.K_m:
                    # Broadcast medicine delivery via multi-agent coordinator
                    winner, bid, message = simulator.dispatch_demo_medicine_delivery()
                    if winner:
                        hud.log_event(
                            f"[M] Medicine mission → {winner.agent_id}",
                            COLORS.TEXT_SUCCESS,
                        )
                    else:
                        hud.log_event(f"[M] {message}", COLORS.TEXT_WARNING)

                elif event.key == pygame.K_e:
                    # Broadcast emergency via multi-agent coordinator
                    winner, bid, message = simulator.dispatch_demo_emergency()
                    if winner:
                        hud.log_event(
                            f"[E] Emergency mission → {winner.agent_id}",
                            COLORS.TEXT_DANGER,
                        )
                        hud.show_alert("EMERGENCY DISPATCHED", duration_s=2.0,
                                       color=COLORS.TEXT_DANGER)
                    else:
                        hud.log_event(f"[E] {message}", COLORS.TEXT_WARNING)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    renderer.handle_click(event.pos[0], event.pos[1], simulator)
                elif event.button == 2:
                    renderer.handle_middle_mouse(True, event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 2:
                    renderer.handle_middle_mouse(False, event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEMOTION:
                renderer.handle_mouse_motion(event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                renderer.handle_mousewheel(event.y, mx, my)

        # ── Simulation Step ───────────────────────────────────────────────────
        simulator.step()
        simulator.process_audio()

        # ── Rendering Pipeline ────────────────────────────────────────────────
        renderer.begin_frame()
        renderer.draw_map(simulator)
        renderer.draw_path_data(simulator)
        renderer.draw_obstacles(simulator)
        renderer.draw_agents(simulator)
        renderer.draw_robot(simulator)
        renderer.draw_left_panel(simulator)
        renderer.draw_right_panel(simulator)
        renderer.draw_minimap(simulator)

        # HUD drawn last (on top of everything)
        hud.update(simulator)
        hud.draw(simulator)

        # Text command input box overlay
        if text_input_active:
            hud.draw_text_input(text_buffer)

        renderer.end_frame()

        clock.tick(DISPLAY.TARGET_FPS)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    pygame.quit()
    log.info("Hospital Robot Navigation System — Shutdown complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()

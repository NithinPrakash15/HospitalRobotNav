/**
 * AAROGYA — Hospital Autonomous Assistance Platform
 * Frontend Master Controller & Isaac Sim Realtime Dashboard
 */

// ── GLOBAL APPLICATION CONTROLLER ──────────────────────────────────────────
const AarogyaApp = (function () {
  // Application State
  const state = {
    token: localStorage.getItem("aarogya_token") || null,
    user: JSON.parse(localStorage.getItem("aarogya_user") || "null"),
    currentView: "dashboard",
    simRunning: false,
    cameraMode: "FOLLOW_ROBOT",
    activeRobotId: "Arogya_Delivery",
    robots: {},
    tasks: [],
    patients: [],
    prescriptions: [],
    medicines: [],
    doctors: [],
    nurses: [],
    auditLogs: [],
    emergencies: [],
    rooms: [
      { code: "CHG-01", name: "Charging Bay 1", zone: "Fleet", x: 37.25, y: 26.0, w: 10, h: 8, color: "rgba(6, 182, 212, 0.2)" },
      { code: "RCT-01", name: "Reception Atrium", zone: "Public", x: 0.0, y: -5.0, w: 16, h: 12, color: "rgba(59, 130, 246, 0.2)" },
      { code: "PHM-01", name: "Pharmacy Station", zone: "Clinical", x: 14.0, y: 23.2, w: 12, h: 10, color: "rgba(16, 185, 129, 0.25)" },
      { code: "ICU-01", name: "Critical Care Unit A", zone: "Restricted", x: -36.5, y: 11.0, w: 14, h: 12, color: "rgba(244, 63, 94, 0.25)", beds: ["ICU Bed 1", "ICU Bed 2", "ICU Bed 3"] },
      { code: "EMR-01", name: "Trauma Staging", zone: "Emergency", x: -35.0, y: -26.0, w: 14, h: 10, color: "rgba(239, 68, 68, 0.3)" },
      { code: "OT-01", name: "Operating Theater", zone: "Surgical", x: -39.0, y: 26.0, w: 12, h: 10, color: "rgba(139, 92, 246, 0.2)" },
      { code: "LAB-01", name: "Pathology Lab", zone: "Diagnostics", x: -0.5, y: 26.0, w: 11, h: 9, color: "rgba(245, 158, 11, 0.2)" },
      { code: "RAD-01", name: "Radiology Suite", zone: "Diagnostics", x: -15.5, y: 26.0, w: 12, h: 9, color: "rgba(168, 85, 247, 0.2)" },
      { code: "OPD-01", name: "Outpatient Desk", zone: "Public", x: 24.0, y: -26.0, w: 14, h: 10, color: "rgba(59, 130, 246, 0.15)" },
      { code: "PAT-101", name: "Ward Room 101", zone: "Inpatient", x: 10.0, y: -15.0, w: 10, h: 8, color: "rgba(16, 185, 129, 0.15)", beds: ["Bed 101-A", "Bed 101-B"] },
      { code: "PAT-102", name: "Ward Room 102", zone: "Inpatient", x: 18.0, y: -15.0, w: 10, h: 8, color: "rgba(16, 185, 129, 0.15)", beds: ["Bed 102-A"] },
    ],
    ws: null,
    speechRecognition: null,
    isListening: false,
    lastLidarScan: null,
    slamMap: null,
    slamProgress: null,
    activeDynamicObstacles: [],
    mapViewMode: "reference", // "reference", "slam", "side", "overlay"
    overlayOpacity: 0.5,
    selectedFleetRobotId: "Arogya_Delivery",
    fleetStatusData: null,
    showSemantics: true,
    authoritativeKnowledgeMap: null,
    replayMissionData: null,
    replayAnimFrameId: null,
    replayCurrentStep: 0,
    replayIsPlaying: false,
  };

  // ── 1. HTTP REQUEST UTILITY ───────────────────────────────────────────────
  async function apiRequest(endpoint, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }
    const res = await fetch(endpoint, { ...options, headers });
    if (res.status === 401) {
      showLoginModal();
      throw new Error("Authentication required");
    }
    if (res.status === 409) {
      const conflict = await res.json();
      throw { status: 409, data: conflict };
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "API request failed");
    }
    return res.json();
  }

  // ── 2. INITIALIZATION ────────────────────────────────────────────────────
  async function init() {
    setupNavigation();
    setupModals();
    setupCanvas();
    setupSpeech();
    setupTeleopControls();
    setupZoomControls();
    setupInteractiveMapCanvas("canvas-map-reference", "reference", "cursor-coord-ref");
    setupInteractiveMapCanvas("canvas-map-slam", "slam", "cursor-coord-slam");

    // Default to doctor if not logged in
    if (!state.token || !state.user) {
      await quickLogin("doctor", "doctor123");
    } else {
      updateUserUI();
    }

    // Connect real-time telemetry WebSocket
    connectWebSocket();

    // Initial data load
    await refreshAllData();

    // Check URL query parameters for view routing (e.g. ?view=simulation)
    const urlParams = new URLSearchParams(window.location.search);
    const initialView = urlParams.get("view");
    if (initialView) {
      switchView(initialView);
    }

    // Periodic poll for DB updates
    setInterval(refreshAllData, 4000);

    // Live Hospital Chronometer
    setInterval(() => {
      const el = document.getElementById("header-chronometer");
      if (el) {
        const d = new Date();
        el.textContent = d.toISOString().slice(11, 19) + " UTC // " + d.toLocaleTimeString();
      }
    }, 1000);
  }

  // ── 3. AUTHENTICATION & RBAC ─────────────────────────────────────────────
  async function login(username, password) {
    try {
      const data = await apiRequest("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const u = data.user || data;
      state.token = data.access_token;
      state.user = {
        id: u.id || data.user_id,
        role: u.role || data.role,
        full_name: u.full_name,
        username: u.username,
        email: u.email,
      };
      localStorage.setItem("aarogya_token", state.token);
      localStorage.setItem("aarogya_user", JSON.stringify(state.user));

      updateUserUI();
      closeModal("modal-login");
      showToast(`Logged in as ${data.full_name} (${data.role})`);
      await refreshAllData();
    } catch (err) {
      alert("Login failed: " + (err.message || "Invalid credentials"));
    }
  }

  async function quickLogin(username, password) {
    document.getElementById("login-username").value = username;
    document.getElementById("login-password").value = password;
    await login(username, password);
  }

  function logout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem("aarogya_token");
    localStorage.removeItem("aarogya_user");
    showLoginModal();
  }

  function updateUserUI() {
    if (!state.user) return;
    const nameEl = document.getElementById("sidebar-user-name");
    const roleEl = document.getElementById("sidebar-user-role");
    const avatarEl = document.getElementById("sidebar-user-avatar");

    if (nameEl) nameEl.textContent = state.user.full_name;
    if (roleEl) roleEl.textContent = state.user.role;
    if (avatarEl) {
      const initials = state.user.full_name
        .split(" ")
        .map((p) => p[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
      avatarEl.textContent = initials || "U";
    }

    // Role-dependent UI protections
    const btnNewRx = document.getElementById("btn-create-rx-modal");
    if (btnNewRx) {
      btnNewRx.style.display = (state.user.role === "DOCTOR" || state.user.role === "ADMIN") ? "inline-flex" : "none";
    }

    const btnNewTask = document.getElementById("btn-create-task-modal");
    if (btnNewTask) {
      btnNewTask.style.display = (["DOCTOR", "NURSE", "ADMIN"].includes(state.user.role)) ? "inline-flex" : "none";
    }
  }

  function setupNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const view = item.dataset.view;
        switchView(view);
      });
    });

    // Support URL query param or hash for direct view navigation
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const reqView = urlParams.get("view") || window.location.hash.replace("#", "");
      if (reqView) {
        setTimeout(() => switchView(reqView), 20);
      }
    } catch (_) {}

    // Run/Pause Simulation Button
    const btnSim = document.getElementById("btn-sim-toggle");
    if (btnSim) {
      btnSim.addEventListener("click", toggleSimulation);
    }

    // Camera Mode Controls
    const camButtons = document.querySelectorAll(".btn-cam[data-cam]");
    camButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        camButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        setCameraMode(btn.dataset.cam);
      });
    });

    // Camera switchers on Simulation view (Section 9 & 13)
    const camSwitchers = document.querySelectorAll(".btn-cam-switch[data-robot]");
    camSwitchers.forEach((btn) => {
      btn.addEventListener("click", () => {
        camSwitchers.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const rName = btn.dataset.robot;
        state.activeRobotId = rName;
        apiRequest("/api/simulation/camera", {
          method: "POST",
          body: JSON.stringify({ mode: "FOLLOW_ROBOT", target_robot_id: rName })
        }).catch((err) => console.warn(err));
      });
    });

    // Clear events button
    const btnClearEvts = document.getElementById("btn-clear-events");
    if (btnClearEvts) {
      btnClearEvts.addEventListener("click", () => {
        const el = document.getElementById("mission-events-list");
        if (el) el.innerHTML = `<div class="event-row info"><span class="time">--:--:--</span> [SYSTEM] Log view reset.</div>`;
      });
    }

    // Close startup modal button
    const btnCloseStartup = document.getElementById("btn-close-startup-modal");
    if (btnCloseStartup) {
      btnCloseStartup.addEventListener("click", () => closeModal("modal-sim-startup"));
    }

    // Clear Terminal Stream
    const btnClearTerm = document.getElementById("btn-clear-terminal");
    if (btnClearTerm) {
      btnClearTerm.addEventListener("click", () => {
        const term = document.getElementById("terminal-stream");
        if (term) term.innerHTML = `<div class="terminal-line INFO">[SYSTEM] Terminal logs reset.</div>`;
      });
    }

    // Autonomous SLAM Exploration Button (Sections 4, 5, 6, 11)
    const btnSlamExplore = document.getElementById("btn-slam-explore");
    if (btnSlamExplore) {
      btnSlamExplore.addEventListener("click", async () => {
        try {
          if (!state.simRunning) {
            showToast("NVIDIA Isaac Sim is OFFLINE. Click 'RUN SIMULATION' to boot the digital twin and initialize sensor subsystems first.", "warning");
            return;
          }
          showToast("Validating prerequisites & starting autonomous SLAM exploration...", "info");
          const res = await apiRequest("/api/simulation/explore", {
            method: "POST",
            body: JSON.stringify({ robot_id: state.activeRobotId, mode: "FRONTIER_EXPLORATION" }),
          });

          if (res.status === "FAILED" || res.exploration_state === "FAILED" || res.isaac_connected === false) {
            state.isExploring = false;
            showToast(res.message || "Autonomous exploration startup failed.", "warning");
            updateExplorationHUD(res.diagnostics);
            return;
          }

          state.isExploring = true;
          const targetCoords = res.current_frontier || res.next_frontier_target || [0.0, 0.0];
          showToast(`Autonomous SLAM exploration ACTIVE: ${res.robot || 'AMR'} moving to frontier (${targetCoords[0]}, ${targetCoords[1]})`);
          updateExplorationHUD(res.diagnostics);

          // Refresh and store full SLAM map with wall hits, free space, and frontiers
          const slamRes = await apiRequest("/api/simulation/slam_map").catch(() => null);
          if (slamRes && slamRes.status === "ONLINE") {
            state.slamMap = Object.assign({}, slamRes.metadata || {}, slamRes);
            state.slamProgress = (slamRes.metadata && slamRes.metadata.exploration_progress_pct) !== undefined ? slamRes.metadata.exploration_progress_pct : (slamRes.exploration_progress_pct || 0);
            state.activeDynamicObstacles = slamRes.dynamic_obstacles || [];
          }

          // Automatically switch view to Mode 2: Robot-Generated SLAM
          setMapViewMode("slam");
          const modeBtns = document.querySelectorAll(".btn-map-mode");
          modeBtns.forEach((b) => {
            const isTarget = b.dataset.mode === "slam";
            b.classList.toggle("active", isTarget);
            b.style.background = isTarget ? "#0284c7" : "transparent";
            b.style.color = isTarget ? "#fff" : "#94a3b8";
            b.style.borderColor = isTarget ? "#0284c7" : "rgba(255,255,255,0.15)";
          });

          await refreshAllData();
        } catch (err) {
          showToast("Exploration error: " + (err.message || err), "error");
        }
      });
    }

    // Dynamic Corridor Obstacle Injection/Clearing Button (Sections 7 & 8)
    const btnToggleDynObs = document.getElementById("btn-toggle-dyn-obs");
    if (btnToggleDynObs) {
      btnToggleDynObs.addEventListener("click", async () => {
        try {
          const res = await apiRequest("/api/simulation/toggle_obstacle", {
            method: "POST",
            body: JSON.stringify({ location: "MAIN_CORRIDOR", x: 0.0, y: 0.0, radius: 0.6 }),
          });
          state.activeDynamicObstacles = res.dynamic_obstacles || [];
          showToast(`Dynamic corridor obstacle ${res.action} at [${res.position.join(", ")}].`);
        } catch (err) {
          showToast("Obstacle toggle error: " + (err.message || err));
        }
      });
    }

    // 4 Map View Mode Selectors (Phases 6 & 7)
    const modeButtons = document.querySelectorAll(".btn-map-mode");
    modeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        modeButtons.forEach((b) => {
          b.classList.remove("active");
          b.style.background = "transparent";
          b.style.color = "#94a3b8";
          b.style.borderColor = "rgba(255,255,255,0.15)";
        });
        btn.classList.add("active");
        btn.style.background = "#0284c7";
        btn.style.color = "#fff";
        btn.style.borderColor = "#0284c7";

        setMapViewMode(btn.dataset.mode);
      });
    });

    // Opacity slider for Mode 4 Overlay
    const opacitySlider = document.getElementById("slider-map-opacity");
    if (opacitySlider) {
      opacitySlider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        state.overlayOpacity = val / 100.0;
        const lbl = document.getElementById("label-map-opacity");
        if (lbl) lbl.textContent = `${val}%`;
      });
    }

    // Semantic Discovery Toggle
    const btnToggleSemantics = document.getElementById("btn-toggle-semantics");
    if (btnToggleSemantics) {
      btnToggleSemantics.addEventListener("click", () => {
        state.showSemantics = !state.showSemantics;
        btnToggleSemantics.textContent = `SEMANTICS: ${state.showSemantics ? "ON" : "OFF"}`;
        btnToggleSemantics.style.borderColor = state.showSemantics ? "#8b5cf6" : "#475569";
        btnToggleSemantics.style.color = state.showSemantics ? "#c4b5fd" : "#94a3b8";
        showToast(`Semantic discovery overlay ${state.showSemantics ? "enabled" : "disabled"}`);
      });
    }

    // Fleet AMR Console Buttons
    const btnRefreshFleet = document.getElementById("btn-refresh-fleet");
    if (btnRefreshFleet) {
      btnRefreshFleet.addEventListener("click", async () => {
        await loadFleetStatus();
        renderFleetOperationsConsole();
        showToast("AMR Fleet telemetry refreshed.");
      });
    }

    const btnEvalDispatch = document.getElementById("btn-eval-dispatch");
    if (btnEvalDispatch) {
      btnEvalDispatch.addEventListener("click", evaluateFleetDispatch);
    }

    const btnFleetDispatch = document.getElementById("btn-fleet-dispatch");
    if (btnFleetDispatch) {
      btnFleetDispatch.addEventListener("click", handleFleetDispatch);
    }

    const btnFleetCancel = document.getElementById("btn-fleet-cancel");
    if (btnFleetCancel) {
      btnFleetCancel.addEventListener("click", handleFleetCancel);
    }

    const btnFleetReassign = document.getElementById("btn-fleet-reassign");
    if (btnFleetReassign) {
      btnFleetReassign.addEventListener("click", handleFleetReassign);
    }

    const btnFleetCharge = document.getElementById("btn-fleet-charge");
    if (btnFleetCharge) {
      btnFleetCharge.addEventListener("click", handleFleetCharge);
    }

    // Digital Twin Mission Replay Modal Controls
    const btnViewReplay = document.getElementById("btn-view-mission-replay");
    if (btnViewReplay) {
      btnViewReplay.addEventListener("click", () => openMissionReplay());
    }

    const btnCloseReplay = document.getElementById("btn-close-replay-modal");
    if (btnCloseReplay) {
      btnCloseReplay.addEventListener("click", () => closeModal("modal-mission-replay"));
    }

    const btnDismissReplay = document.getElementById("btn-dismiss-replay-modal");
    if (btnDismissReplay) {
      btnDismissReplay.addEventListener("click", () => closeModal("modal-mission-replay"));
    }

    const btnReplayPlay = document.getElementById("btn-replay-play");
    if (btnReplayPlay) {
      btnReplayPlay.addEventListener("click", toggleReplayPlayback);
    }

    const btnReplayReset = document.getElementById("btn-replay-reset");
    if (btnReplayReset) {
      btnReplayReset.addEventListener("click", resetReplayPlayback);
    }

    // Health Page Refresh
    const btnRefreshHealth = document.getElementById("btn-refresh-health-page");
    if (btnRefreshHealth) {
      btnRefreshHealth.addEventListener("click", () => {
        renderSystemHealthPage();
        showToast("Diagnostics audit refreshed.");
      });
    }
  }

  function setMapViewMode(mode) {
    state.mapViewMode = mode;
    const singleContainer = document.getElementById("map-single-canvas-container");
    const sideContainer = document.getElementById("map-side-by-side-container");
    const sliderContainer = document.getElementById("overlay-slider-container");
    const singleLabel = document.getElementById("map-single-label");

    if (sliderContainer) {
      sliderContainer.style.display = mode === "overlay" ? "inline-flex" : "none";
    }

    if (mode === "side") {
      if (singleContainer) singleContainer.style.display = "none";
      if (sideContainer) sideContainer.style.display = "flex";
    } else {
      if (singleContainer) singleContainer.style.display = "block";
      if (sideContainer) sideContainer.style.display = "none";
      if (singleLabel) {
        if (mode === "reference") {
          singleLabel.textContent = "MODE 1: REFERENCE MAP — Hospital CAD Layout (VISUAL ONLY)";
          singleLabel.style.color = "#38bdf8";
          singleLabel.style.borderColor = "#0284c7";
        } else if (mode === "slam") {
          singleLabel.textContent = "MODE 2: ROBOT-GENERATED MAP — Authoritative SLAM Occupancy Grid";
          singleLabel.style.color = "#10b981";
          singleLabel.style.borderColor = "#059669";
        } else if (mode === "overlay") {
          singleLabel.textContent = "MODE 4: OVERLAY COMPARISON — Reference CAD & Authoritative SLAM";
          singleLabel.style.color = "#a855f7";
          singleLabel.style.borderColor = "#9333ea";
        }
      }
    }
    resizeCanvases();
  }

  function switchView(viewName) {
    if (viewName === "overview") viewName = "dashboard";
    if (viewName === "fleet") viewName = "robots";
    if (viewName === "pharmacy") viewName = "medicines";
    state.currentView = viewName;

    try {
      const currentUrl = new URL(window.location.href);
      if (currentUrl.searchParams.get("view") !== viewName) {
        currentUrl.searchParams.set("view", viewName);
        window.history.replaceState(null, "", currentUrl.toString());
      }
    } catch (_) {}

    // Update nav classes
    document.querySelectorAll(".nav-item").forEach((el) => {
      const v = el.dataset.view;
      const isTarget = v === viewName || 
                       (v === "overview" && viewName === "dashboard") ||
                       (v === "fleet" && viewName === "robots") || 
                       (v === "pharmacy" && viewName === "medicines");
      el.classList.toggle("active", isTarget);
    });

    // Update title
    const titleEl = document.getElementById("current-view-title");
    const titles = {
      dashboard: "Overview",
      overview: "Overview",
      simulation: "Simulation Control",
      map: "Hospital Live Map",
      robots: "Robot Fleet",
      fleet: "Robot Fleet",
      tasks: "Missions & Tasks",
      patients: "Patients & Beds",
      staff: "Doctors & Nurses",
      medicines: "Pharmacy",
      pharmacy: "Pharmacy",
      emergency: "Emergency Centre",
      health: "System Health",
      logs: "Audit Logs",
    };
    if (titleEl) titleEl.textContent = titles[viewName] || "Hospital Robot Platform";

    // Show/hide view content sections
    const views = [
      "view-dashboard",
      "view-simulation",
      "view-map",
      "view-patients",
      "view-prescriptions",
      "view-tasks",
      "view-robots",
      "view-medicines",
      "view-staff",
      "view-emergency",
      "view-logs",
      "view-health",
    ];

    views.forEach((v) => {
      const el = document.getElementById(v);
      if (el) {
        el.style.display = v === `view-${viewName}` ? "block" : "none";
      }
    });

    // Trigger canvas redraw if opening simulation or map
    if (viewName === "simulation" || viewName === "map") {
      setTimeout(resizeCanvases, 50);
    }
    if (viewName === "robots") renderFleetOperationsConsole();
    if (viewName === "health") renderSystemHealthPage();
    if (viewName === "staff") renderStaffTables();
    if (viewName === "logs") renderAuditLogsTable();
    if (viewName === "emergency") renderEmergencyTable();
  }

  // ── 5. MODAL MANAGEMENT ──────────────────────────────────────────────────
  function setupModals() {
    // Switch User Button
    document.getElementById("btn-switch-user").addEventListener("click", showLoginModal);
    document.getElementById("btn-close-login-modal").addEventListener("click", () => closeModal("modal-login"));
    document.getElementById("form-login").addEventListener("submit", (e) => {
      e.preventDefault();
      const u = document.getElementById("login-username").value;
      const p = document.getElementById("login-password").value;
      login(u, p);
    });

    // Voice Modal
    const btnVoice = document.getElementById("btn-open-voice");
    if (btnVoice) btnVoice.addEventListener("click", showVoiceModal);
    document.getElementById("btn-close-voice-modal").addEventListener("click", () => closeModal("modal-voice"));
    document.getElementById("btn-submit-voice").addEventListener("click", executeVoiceCommand);
    document.getElementById("voice-mic-indicator").addEventListener("click", toggleSpeechListening);

    // Create Task Modal
    const btnTask = document.getElementById("btn-create-task-modal");
    const btnTask2 = document.getElementById("btn-create-task-modal-2");
    if (btnTask) btnTask.addEventListener("click", showCreateTaskModal);
    if (btnTask2) btnTask2.addEventListener("click", showCreateTaskModal);
    document.getElementById("btn-close-task-modal").addEventListener("click", () => closeModal("modal-create-task"));
    document.getElementById("form-create-task").addEventListener("submit", handleCreateTask);

    // Create Rx Modal
    const btnRx = document.getElementById("btn-create-rx-modal");
    if (btnRx) btnRx.addEventListener("click", showCreateRxModal);
    document.getElementById("btn-close-rx-modal").addEventListener("click", () => closeModal("modal-create-rx"));
    document.getElementById("form-create-rx").addEventListener("submit", handleCreatePrescription);

    // Emergency Quick Button in Topbar
    const btnEmergency = document.getElementById("btn-trigger-emergency");
    if (btnEmergency) {
      btnEmergency.addEventListener("click", () => {
        quickTriggerCodeBlue("ICU-01", "Code Blue initiated from topbar alert button");
      });
    }

    // Mission Correlation Modal
    const btnCloseCorr = document.getElementById("btn-close-corr-modal");
    if (btnCloseCorr) btnCloseCorr.addEventListener("click", () => closeModal("modal-mission-correlation"));
    const btnDismissCorr = document.getElementById("btn-dismiss-corr-modal");
    if (btnDismissCorr) btnDismissCorr.addEventListener("click", () => closeModal("modal-mission-correlation"));
  }

  function showLoginModal() {
    document.getElementById("modal-login").classList.add("active");
  }

  function showVoiceModal() {
    const box = document.getElementById("voice-result-box");
    if (box) box.style.display = "none";
    document.getElementById("modal-voice").classList.add("active");
  }

  function showCreateTaskModal() {
    populateTaskSelects();
    document.getElementById("modal-create-task").classList.add("active");
  }

  function showCreateRxModal() {
    populateRxSelects();
    document.getElementById("modal-create-rx").classList.add("active");
  }

  function closeModal(modalId) {
    document.getElementById(modalId).classList.remove("active");
  }

  // ── 6. DATA FETCHING & RENDERING ─────────────────────────────────────────
  async function refreshAllData() {
    try {
      let patients = [], rxList = [], tasks = [], robots = [], medicines = [], doctors = [], nurses = [], auditLogs = [], emergencies = [], healthData = null;

      try {
        const consolidated = await apiRequest("/api/system/consolidated_state");
        patients = consolidated.patients || [];
        rxList = consolidated.prescriptions || [];
        tasks = consolidated.tasks || [];
        robots = consolidated.robots || [];
        medicines = consolidated.medicines || [];
        doctors = consolidated.doctors || [];
        nurses = consolidated.nurses || [];
        emergencies = consolidated.emergencies || [];
        healthData = consolidated.health || null;
        if (consolidated.slam_map && consolidated.slam_map.status === "ONLINE") {
          state.slamMap = Object.assign({}, consolidated.slam_map.metadata || {}, consolidated.slam_map);
          state.slamProgress = (consolidated.slam_map.metadata && consolidated.slam_map.metadata.exploration_progress_pct) !== undefined ? consolidated.slam_map.metadata.exploration_progress_pct : (consolidated.slam_map.exploration_progress_pct || 0);
          state.activeDynamicObstacles = consolidated.slam_map.dynamic_obstacles || [];
        } else if (consolidated.slam_map) {
          state.slamMap = consolidated.slam_map;
          state.slamProgress = 0;
          state.activeDynamicObstacles = [];
        }
      } catch (cErr) {
        // Fallback to individual requests if consolidated endpoint is not available
        [patients, rxList, tasks, robots, medicines, doctors, nurses, auditLogs, emergencies, healthData] = await Promise.all([
          apiRequest("/api/patients").catch(() => []),
          apiRequest("/api/prescriptions").catch(() => []),
          apiRequest("/api/tasks").catch(() => []),
          apiRequest("/api/robots").catch(() => []),
          apiRequest("/api/medicines").catch(() => []),
          apiRequest("/api/doctors").catch(() => []),
          apiRequest("/api/nurses").catch(() => []),
          apiRequest("/api/audit-logs").catch(() => []),
          apiRequest("/api/emergency/events").catch(() => []),
          apiRequest("/api/health").catch(() => null),
        ]);
      }

      state.patients = patients;
      state.prescriptions = rxList;
      state.tasks = tasks;
      state.medicines = medicines;
      state.doctors = doctors;
      state.nurses = nurses;
      if (auditLogs.length > 0) state.auditLogs = auditLogs;
      state.emergencies = emergencies;
      state.health = healthData;

      // Update robot state map
      robots.forEach((r) => {
        state.robots[r.robot_id] = r;
      });

      // Update real topbar health indicator truthfully
      const topIndicator = document.getElementById("system-status-indicator");
      if (topIndicator && healthData) {
        const isaacOnline = (healthData.subsystems && healthData.subsystems.isaac_sim && healthData.subsystems.isaac_sim.status === "ONLINE") || (healthData.simulation_online === true);
        state.simRunning = Boolean(isaacOnline);
        if (isaacOnline) {
          topIndicator.className = "badge badge-active";
          topIndicator.innerHTML = `<span class="dot online"></span> ISAAC SIM RUNNING (NVIDIA RTX)`;
        } else if (healthData.status && (healthData.status.includes("STARTING") || healthData.status.includes("PROCESS_RUNNING"))) {
          topIndicator.className = "badge badge-warning";
          topIndicator.innerHTML = `<span class="dot warning"></span> INITIALIZING SIMULATION...`;
        } else {
          topIndicator.className = "badge badge-offline";
          topIndicator.innerHTML = `<span class="dot offline"></span> BACKEND ONLINE — SIMULATION OFFLINE`;
        }
      }

      // Update Phase 20 System Health & Verification Panel
      updateSystemHealthPanel(healthData);

      // Poll live robotics exploration diagnostics (Requirement 11)
      try {
        const diagData = await apiRequest("/api/simulation/exploration_diagnostics").catch(() => null);
        if (diagData) {
          state.explorationDiagnostics = diagData;
          if (diagData.exploration_state === "ROBOT_MOVING" || diagData.exploration_state === "GOAL_ACCEPTED") {
            state.isExploring = true;
          } else if (diagData.exploration_state === "EXPLORATION_COMPLETE" || diagData.exploration_state === "IDLE") {
            state.isExploring = false;
          }
        }
      } catch (_) {}

      // Update Fleet and Authoritative Map
      await loadFleetStatus().catch(() => {});
      await loadAuthoritativeKnowledgeMap().catch(() => {});

      // Update Exploration HUD & 13 Diagnostics
      updateExplorationHUD();

      renderDashboardStats();
      renderTasksTable();
      renderPatientsTable();
      renderPrescriptionsTable();
      renderRobotsView();
      renderFleetOperationsConsole();
      renderSystemHealthPage();
      renderMedicinesTable();
      renderStaffTables();
      renderAuditLogsTable();
      renderEmergencyTable();
    } catch (e) {
      console.warn("Background refresh error:", e);
    }
  }

  function updateSystemHealthPanel(healthData) {
    if (!healthData) return;
    const hp = healthData.health_panel || {};
    const sub = healthData.subsystems || {};

    const overallBadge = document.getElementById("health-overall-badge");
    if (overallBadge) {
      const isReady = Boolean(healthData.system_ready);
      overallBadge.className = isReady ? "badge badge-active" : "badge badge-warning";
      overallBadge.textContent = isReady ? "SYSTEM ONLINE" : "STANDBY READY";
    }

    const items = [
      { id: "health-val-backend", key: "backend", defaultVal: "CONNECTED", activeCol: "#10b981" },
      { id: "health-val-database", key: "database", defaultVal: "CONNECTED", activeCol: "#10b981" },
      { id: "health-val-agents", key: "agents", defaultVal: "READY", activeCol: "#10b981" },
      { id: "health-val-ros2", key: "ros2", defaultVal: "CONNECTED", activeCol: "#10b981" },
      { id: "health-val-isaac_sim", key: "isaac_sim", defaultVal: "STANDBY", activeCol: "#10b981", warnCol: "#f59e0b" },
      { id: "health-val-robot_fleet", key: "robot_fleet", defaultVal: "CONNECTED", activeCol: "#10b981" },
      { id: "health-val-navigation", key: "navigation", defaultVal: "READY", activeCol: "#10b981" },
      { id: "health-val-mapping", key: "mapping", defaultVal: "ACTIVE", activeCol: "#00e5ff" },
      { id: "health-val-telemetry", key: "telemetry", defaultVal: "CONNECTED", activeCol: "#10b981" },
      { id: "health-val-camera", key: "camera", defaultVal: "STREAMING", activeCol: "#00e5ff", warnCol: "#64748b" },
    ];

    items.forEach((item) => {
      const el = document.getElementById(item.id);
      if (!el) return;
      let val = hp[item.key];
      if (!val && sub[item.key]) {
        val = sub[item.key].status || (sub[item.key].ready ? "ONLINE" : "OFFLINE");
      }
      val = val || item.defaultVal;

      let color = item.activeCol;
      if (val === "OFFLINE" || val === "DISCONNECTED" || val === "ERROR") {
        color = "#ef4444";
      } else if (val === "STANDBY" || val === "INITIALIZING") {
        color = item.warnCol || "#f59e0b";
      }

      el.style.color = color;
      el.innerHTML = `● ${val}`;
    });
  }

  function updateExplorationHUD(diagOverride) {
    const map = state.slamMap || {};
    const activeRob = state.robots[state.activeRobotId] || state.robots["Arogya_Delivery"] || Object.values(state.robots)[0];
    const diag = diagOverride || state.explorationDiagnostics || {};

    // Dynamic Exploration Badge
    const badgeEl = document.getElementById("hud-explore-badge");
    const expState = diag.exploration_state || (state.isExploring ? "ROBOT_MOVING" : "IDLE");
    if (badgeEl) {
      if (expState === "ROBOT_MOVING" || expState === "GOAL_ACCEPTED" || (state.isExploring && state.simRunning)) {
        badgeEl.textContent = "EXPLORATION ACTIVE (" + expState + ")";
        badgeEl.style.background = "#10b981";
        badgeEl.style.color = "#050b14";
      } else if (expState === "EXPLORATION_COMPLETE" || map.exploration_complete || (map.exploration_progress_pct && map.exploration_progress_pct >= 90.0)) {
        badgeEl.textContent = "EXPLORATION COMPLETE";
        badgeEl.style.background = "#06b6d4";
        badgeEl.style.color = "#050b14";
      } else if (expState === "BLOCKED") {
        badgeEl.textContent = "EXPLORATION BLOCKED";
        badgeEl.style.background = "#ef4444";
        badgeEl.style.color = "#ffffff";
      } else if (expState === "FAILED") {
        badgeEl.textContent = "EXPLORATION FAILED";
        badgeEl.style.background = "#ef4444";
        badgeEl.style.color = "#ffffff";
      } else if (!state.simRunning && diag.isaac_sim === "DISCONNECTED") {
        badgeEl.textContent = "SIMULATOR STANDBY";
        badgeEl.style.background = "#f59e0b";
        badgeEl.style.color = "#050b14";
      } else {
        badgeEl.textContent = "EXPLORATION READY";
        badgeEl.style.background = "#334155";
        badgeEl.style.color = "#94a3b8";
      }
    }

    const robNameEl = document.getElementById("hud-robot-name");
    if (robNameEl && activeRob) {
      const rName = diag.selected_robot || activeRob.name || activeRob.id || "Arogya_Delivery";
      robNameEl.textContent = `${rName} (${activeRob.id || 'ROBOT-01'})`;
    }

    const robLocEl = document.getElementById("hud-robot-location");
    if (robLocEl && activeRob) {
      const posStr = (diag.robot_position && diag.robot_position.length >= 2) ? ` (${diag.robot_position[0]}, ${diag.robot_position[1]})` : "";
      robLocEl.textContent = (activeRob.room || activeRob.current_room || "Central Corridor C") + posStr;
    }

    const exploredPctEl = document.getElementById("hud-explored-pct");
    if (exploredPctEl) {
      const exp = diag.explored_pct !== undefined ? diag.explored_pct : (map.exploration_progress_pct !== undefined ? map.exploration_progress_pct : (state.slamProgress || 0));
      exploredPctEl.textContent = `${Number(exp).toFixed(1)}%`;
    }

    const covPctEl = document.getElementById("hud-coverage-pct");
    if (covPctEl) {
      const cov = diag.map_coverage_pct !== undefined ? diag.map_coverage_pct : (map.coverage_pct !== undefined ? map.coverage_pct : (map.free_cells ? ((map.free_cells / 4200) * 100).toFixed(1) : "0.0"));
      covPctEl.textContent = `${Number(cov).toFixed(1)}%`;
    }

    const frontiersEl = document.getElementById("hud-frontiers-count");
    if (frontiersEl) {
      const fCount = diag.frontiers_count !== undefined ? diag.frontiers_count : (Array.isArray(map.frontiers) ? map.frontiers.length : (map.frontiers_count || 0));
      frontiersEl.textContent = fCount;
    }

    const dynObsEl = document.getElementById("hud-dynamic-count");
    if (dynObsEl) {
      const dCount = Array.isArray(state.activeDynamicObstacles) ? state.activeDynamicObstacles.length : 0;
      dynObsEl.textContent = dCount;
    }

    const statusEl = document.getElementById("hud-mapping-status");
    if (statusEl) {
      statusEl.textContent = (diag.slam === "ACTIVE" || state.simRunning) ? "ACTIVE (2D LiDAR SLAM)" : "STANDBY (Simulator Offline)";
    }

    const metaProg = document.getElementById("meta-slam-progress");
    const metaCov = document.getElementById("meta-slam-coverage");
    const metaFtr = document.getElementById("meta-slam-frontiers");
    if (metaProg) {
      const exp = diag.explored_pct !== undefined ? diag.explored_pct : (map.exploration_progress_pct !== undefined ? map.exploration_progress_pct : (state.slamProgress || 0));
      metaProg.textContent = `${Number(exp).toFixed(1)}% Explored`;
    }
    if (metaCov) {
      const cov = diag.map_coverage_pct !== undefined ? diag.map_coverage_pct : (map.coverage_pct !== undefined ? map.coverage_pct : "0.0");
      metaCov.textContent = `${Number(cov).toFixed(1)}% Area`;
    }
    if (metaFtr) {
      const fCount = diag.frontiers_count !== undefined ? diag.frontiers_count : (Array.isArray(map.frontiers) ? map.frontiers.length : (map.frontiers_count || 0));
      metaFtr.textContent = `${fCount} Frontiers`;
    }

    // ── 13-ROW REAL-TIME DIAGNOSTICS UPDATE (Requirement 11) ──
    function setDiag(elemId, val, okVals, warnVals) {
      const el = document.getElementById(elemId);
      if (!el) return;
      el.textContent = val || "N/A";
      if (okVals && okVals.includes(val)) {
        el.style.color = "#10b981"; // Green
      } else if (warnVals && warnVals.includes(val)) {
        el.style.color = "#f59e0b"; // Amber
      } else {
        el.style.color = "#ef4444"; // Red
      }
    }

    const isOnline = !!(state.simRunning || (diag.isaac_sim === "CONNECTED"));

    // Button disabled state
    const expBtn = document.getElementById("btn-slam-explore");
    if (expBtn) {
      if (!isOnline) {
        expBtn.disabled = true;
        expBtn.style.opacity = "0.5";
        expBtn.style.cursor = "not-allowed";
        expBtn.title = "NVIDIA Isaac Sim must be running. Click 'RUN SIMULATION' first.";
      } else {
        expBtn.disabled = false;
        expBtn.style.opacity = "1.0";
        expBtn.style.cursor = "pointer";
        expBtn.title = "Start autonomous frontier exploration in Isaac Sim";
      }
    }

    setDiag("diag-isaac-sim", diag.isaac_sim || (isOnline ? "CONNECTED" : "OFFLINE"), ["CONNECTED"], []);
    setDiag("diag-simulation", diag.simulation || (isOnline ? "PLAYING" : "OFFLINE"), ["PLAYING"], ["PAUSED"]);
    setDiag("diag-ros2-bridge", diag.ros2_bridge || (isOnline ? "READY" : "DISCONNECTED"), ["READY"], []);
    setDiag("diag-robot", diag.robot || (isOnline ? "READY" : "OFFLINE"), ["READY"], []);
    setDiag("diag-lidar", diag.lidar || (isOnline ? "ACTIVE" : "NO DATA"), ["ACTIVE"], []);
    setDiag("diag-odometry", diag.odometry || (isOnline ? "ACTIVE" : "NO DATA"), ["ACTIVE"], []);
    setDiag("diag-tf", diag.tf || (isOnline ? "VALID" : "INVALID"), ["VALID"], []);
    setDiag("diag-slam", diag.slam || (isOnline ? "ACTIVE" : "STANDBY"), ["ACTIVE"], ["STANDBY"]);
    setDiag("diag-nav2", diag.nav2 || (isOnline ? "READY" : "NOT READY"), ["READY"], ["NOT READY"]);
    setDiag("diag-frontier-planner", diag.frontier_planner || (isOnline ? "ACTIVE" : "STANDBY"), ["ACTIVE"], ["STANDBY"]);
    setDiag("diag-nav-goal", diag.navigation_goal || (state.isExploring ? "ACCEPTED" : "NONE"), ["ACCEPTED"], ["NONE"]);
    setDiag("diag-velocity", diag.velocity_command || (state.isExploring ? "ACTIVE" : "NONE"), ["ACTIVE"], ["NONE", "ZERO"]);
    setDiag("diag-movement", diag.robot_movement || (diag.velocity_command === "ACTIVE" ? "MOVING" : "STATIONARY"), ["MOVING"], ["STATIONARY"]);

    const stateEl = document.getElementById("diag-exploration-state");
    if (stateEl) {
      stateEl.textContent = diag.exploration_state || expState;
      stateEl.style.color = (expState === "ROBOT_MOVING" || expState === "GOAL_ACCEPTED") ? "#10b981" : (expState === "FAILED" ? "#ef4444" : "#00e5ff");
    }

    const errBanner = document.getElementById("diag-error-banner");
    if (errBanner) {
      if (diag.last_error) {
        errBanner.style.display = "inline-block";
        const cleanErr = String(diag.last_error);
        errBanner.textContent = "ERR: " + (cleanErr.length > 85 ? cleanErr.slice(0, 85) + "..." : cleanErr);
        errBanner.title = cleanErr;
      } else {
        errBanner.style.display = "none";
      }
    }
  }

  function renderDashboardStats() {
    document.getElementById("stat-patients-count").textContent = state.patients.length;
    document.getElementById("stat-rx-count").textContent = state.prescriptions.filter((p) => p.status === "ACTIVE").length;
    document.getElementById("stat-robots-count").textContent = Object.keys(state.robots).length || 4;
    document.getElementById("stat-tasks-count").textContent = state.tasks.filter((t) => t.status !== "DELIVERED" && t.status !== "FAILED").length;

    // Render Tasks Table on Dashboard
    const tbody = document.getElementById("dashboard-tasks-table");
    if (tbody) {
      if (state.tasks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-dim); padding:20px;">No active missions in queue. Click 'Create Delivery Task' or use Voice Command.</td></tr>`;
      } else {
        tbody.innerHTML = state.tasks
          .slice(0, 5)
          .map(
            (t) => `
            <tr>
              <td><strong>${t.task_code || `#${t.id}`}</strong></td>
              <td>${t.patient || t.patient_name || "General Delivery"} <small style="color:var(--text-muted)">(${t.destination || t.target_room || "N/A"})</small></td>
              <td>${t.medicine || t.medicine_name || "Medical Supply"}</td>
              <td><span class="badge badge-${(t.priority || 'NORMAL').toLowerCase()}">${t.priority}</span></td>
              <td>${(t.robot || t.robot_id) ? `<span style="color:var(--accent-cyan)">🤖 ${t.robot || t.robot_id}</span>` : `<span style="color:var(--text-dim)">Unassigned</span>`}</td>
              <td><span class="badge badge-${(t.status || 'PENDING').toLowerCase()}">${t.status}</span></td>
            </tr>`
          )
          .join("");
      }
    }

    // Render Fleet status on Dashboard
    const fleetSummary = document.getElementById("dashboard-fleet-summary");
    if (fleetSummary) {
      const seenNames = new Set();
      const rawList = Object.values(state.robots);
      const robotList = rawList.filter((r) => {
        const canonical = (r.name || r.robot_id || "").toLowerCase();
        if (!canonical || seenNames.has(canonical)) return false;
        seenNames.add(canonical);
        return true;
      });
      const defaultFleet = [
        { name: "Arogya_Delivery", robot_id: "ROBOT-01", role: "DELIVERY", status: "IDLE", battery: 98.5 },
        { name: "Mitra_Reception", robot_id: "ROBOT-02", role: "RECEPTION", status: "IDLE", battery: 100.0 },
        { name: "Garuda_Emergency", robot_id: "ROBOT-03", role: "EMERGENCY", status: "IDLE", battery: 100.0 },
        { name: "Sahayak_Support", robot_id: "ROBOT-04", role: "SUPPORT", status: "IDLE", battery: 95.0 },
      ];
      fleetSummary.innerHTML = (robotList.length > 0 ? robotList : defaultFleet)
        .map(
          (r) => {
            const bVal = (r.battery !== undefined && r.battery !== null) ? Number(r.battery).toFixed(0) : ((r.battery_level !== undefined && r.battery_level !== null) ? Number(r.battery_level).toFixed(0) : "100");
            const rName = r.name || r.robot_id || "AMR";
            const rStat = r.status || "IDLE";
            return `
          <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); display:flex; align-items:center; justify-content:space-between;">
            <div>
              <div style="font-weight:600; font-size:13px; color:var(--accent-cyan);">${rName}</div>
              <div style="font-size:11px; color:var(--text-muted);">${r.role || "AMR"}</div>
            </div>
            <div style="text-align:right;">
              <span class="badge badge-${rStat.toLowerCase()}">${rStat}</span>
              <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">🔋 ${bVal}%</div>
            </div>
          </div>`;
          }
        )
        .join("");
    }
  }

  function renderTasksTable() {
    const tbody = document.getElementById("tasks-table-body");
    if (!tbody) return;
    tbody.innerHTML = state.tasks
      .map(
        (t) => `
      <tr>
        <td><strong>${t.task_code || `#${t.id}`}</strong></td>
        <td><span class="badge badge-idle">${t.type || t.task_type || "DELIVERY"}</span></td>
        <td>${t.patient || t.patient_name || "N/A"} <small style="color:var(--accent-cyan)">(${t.destination || t.target_room || "N/A"})</small></td>
        <td>${t.medicine || t.medicine_name || "General Supplies"}</td>
        <td><span class="badge badge-${(t.priority || 'NORMAL').toLowerCase()}">${t.priority}</span></td>
        <td>${(t.robot || t.robot_id) ? `🤖 ${t.robot || t.robot_id}` : `Auto-Queued`}</td>
        <td><span class="badge badge-${(t.status || 'PENDING').toLowerCase()}">${t.status}</span></td>
        <td>
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="progress-bar-container" style="width:80px;">
              <div class="progress-bar-fill" style="width:${(t.progress || t.progress_pct || 0) * (t.progress > 1 ? 1 : 100)}%"></div>
            </div>
            <span style="font-size:11px;">${Math.round(t.progress !== undefined ? t.progress : ((t.progress_pct || 0) * 100))}%</span>
          </div>
        </td>
        <td><small style="color:var(--text-dim)">${t.created_at ? new Date(t.created_at).toLocaleTimeString() : "--:--"}</small></td>
      </tr>`
      )
      .join("");
  }

  function renderPatientsTable() {
    const tbody = document.getElementById("patients-table-body");
    if (!tbody) return;
    tbody.innerHTML = state.patients
      .map(
        (p) => `
      <tr>
        <td><strong>#${p.id}</strong></td>
        <td style="font-weight:600;">${p.name}</td>
        <td><code>${p.mrn}</code></td>
        <td><span class="badge badge-active">${p.room_number || "Room"}</span> ${p.bed_number ? `— <strong>${p.bed_number}</strong>` : ""}</td>
        <td>${p.primary_doctor || "Dr. Sarah Patel"}</td>
        <td><small style="color:var(--text-muted)">${new Date(p.admission_date).toLocaleDateString()}</small></td>
        <td>
          ${
            p.active_prescriptions && p.active_prescriptions.length > 0
              ? p.active_prescriptions.map((m) => `<span class="badge badge-delivered" style="margin-right:4px;">${m}</span>`).join("")
              : `<span style="color:var(--text-dim); font-size:12px;">None active</span>`
          }
        </td>
        <td>
          <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="AarogyaApp.quickDispatchToPatient(${p.id})">
            Dispatch AMR
          </button>
        </td>
      </tr>`
      )
      .join("");
  }

  function renderPrescriptionsTable() {
    const tbody = document.getElementById("prescriptions-table-body");
    if (!tbody) return;
    tbody.innerHTML = state.prescriptions
      .map(
        (rx) => `
      <tr>
        <td><strong>#${rx.id}</strong></td>
        <td style="font-weight:600;">${rx.patient_name}</td>
        <td style="color:var(--accent-cyan); font-weight:600;">${rx.medicine_name}</td>
        <td>${rx.dosage} (${rx.frequency})</td>
        <td>${rx.route}</td>
        <td>${rx.doctor_name}</td>
        <td><span class="badge badge-${rx.status.toLowerCase()}">${rx.status}</span></td>
        <td>
          ${
            rx.status === "ACTIVE"
              ? `<button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="AarogyaApp.discontinueRx(${rx.id})">Discontinue</button>`
              : `<span style="color:var(--text-dim); font-size:11px;">Discontinued</span>`
          }
        </td>
      </tr>`
      )
      .join("");
  }

  function renderRobotsView() {
    const grid = document.getElementById("robots-card-grid");
    if (!grid) return;
    const robotList = Object.values(state.robots);
    if (robotList.length === 0) return;

    grid.innerHTML = robotList
      .map(
        (r) => {
          const bVal = (r.battery !== undefined && r.battery !== null) ? Number(r.battery).toFixed(1) : ((r.battery_level !== undefined && r.battery_level !== null) ? Number(r.battery_level).toFixed(1) : "100.0");
          const px = (r.x !== undefined && r.x !== null) ? Number(r.x).toFixed(2) : ((r.current_x !== undefined && r.current_x !== null) ? Number(r.current_x).toFixed(2) : "0.00");
          const py = (r.y !== undefined && r.y !== null) ? Number(r.y).toFixed(2) : ((r.current_y !== undefined && r.current_y !== null) ? Number(r.current_y).toFixed(2) : "0.00");
          const rName = r.name || r.robot_id;
          const rStat = r.status || "IDLE";
          return `
      <div class="metric-card" style="border-left: 4px solid var(--accent-cyan);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3 style="font-size:16px; font-family:'Outfit'; color:var(--text-main);">${rName}</h3>
          <span class="badge badge-${rStat.toLowerCase()}">${rStat}</span>
        </div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;">Operational Role: <strong>${r.role || "AMR"}</strong></div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px; background:rgba(0,0,0,0.2); padding:10px; border-radius:var(--radius-sm);">
          <div>Battery: <strong style="color:var(--accent-emerald);">${bVal}%</strong></div>
          <div>Payload: <strong>${r.payload_status || (r.active_task ? "LOADED" : "EMPTY")}</strong></div>
          <div>Pos X: <strong>${px}m</strong></div>
          <div>Pos Y: <strong>${py}m</strong></div>
        </div>
        <div style="margin-top:10px; display:flex; gap:8px;">
          <button class="btn btn-outline" style="flex:1; font-size:11px; justify-content:center;" onclick="AarogyaApp.selectCameraTarget('${r.name || r.robot_id}')">
            Follow Camera
          </button>
        </div>
      </div>`;
        }
      )
      .join("");
  }

  // ── FLEET AMR OPERATIONS CONSOLE & EXPLAINABLE DISPATCH ───────────────────
  async function loadFleetStatus() {
    try {
      const data = await apiRequest("/api/fleet/status");
      state.fleetStatusData = data;
      const counts = data.counts || {};
      const elTotal = document.getElementById("stat-fleet-total");
      const elAvail = document.getElementById("stat-fleet-available");
      const elBusy = document.getElementById("stat-fleet-busy");
      const elChg = document.getElementById("stat-fleet-charging");
      const elOff = document.getElementById("stat-fleet-offline");
      const elHealth = document.getElementById("stat-fleet-health-score");

      if (elTotal) elTotal.textContent = counts.total !== undefined ? counts.total : 4;
      if (elAvail) elAvail.textContent = counts.available !== undefined ? counts.available : 3;
      if (elBusy) elBusy.textContent = counts.busy !== undefined ? counts.busy : 0;
      if (elChg) elChg.textContent = counts.charging !== undefined ? counts.charging : 1;
      if (elOff) elOff.textContent = counts.offline !== undefined ? counts.offline : 0;
      if (elHealth) elHealth.textContent = `${data.fleet_health_score || 98}%`;

      if (data.robots && Array.isArray(data.robots)) {
        data.robots.forEach((r) => {
          state.robots[r.robot_id] = Object.assign({}, state.robots[r.robot_id] || {}, r);
        });
      }

      // Truthful Sidebar AMR Mini-Monitor update
      const sidebarFleetCount = document.getElementById("sidebar-fleet-online-count");
      const dotMap = {
        "Arogya_Delivery": "amr-dot-delivery",
        "ROBOT-01": "amr-dot-delivery",
        "Mitra_Reception": "amr-dot-reception",
        "ROBOT-02": "amr-dot-reception",
        "Garuda_Emergency": "amr-dot-emergency",
        "ROBOT-03": "amr-dot-emergency",
        "Sahayak_Support": "amr-dot-support",
        "ROBOT-04": "amr-dot-support",
      };

      if (state.simRunning && data && data.simulation_online) {
        const onlineCount = (counts.available || 0) + (counts.busy || 0) + (counts.charging || 0);
        if (sidebarFleetCount) {
          sidebarFleetCount.textContent = `${onlineCount}/4 ONLINE`;
          sidebarFleetCount.style.color = onlineCount > 0 ? "var(--accent-primary)" : "var(--text-muted)";
        }
        if (data.robots && Array.isArray(data.robots)) {
          data.robots.forEach((r) => {
            const dotId = dotMap[r.name] || dotMap[r.robot_id];
            const dotEl = dotId ? document.getElementById(dotId) : null;
            if (dotEl) {
              const st = (r.status || "").toUpperCase();
              if (st === "NAVIGATING" || st === "BUSY") dotEl.style.background = "#06b6d4";
              else if (st === "CHARGING") dotEl.style.background = "#f59e0b";
              else if (st === "OFFLINE" || st === "ERROR") dotEl.style.background = "#64748b";
              else dotEl.style.background = "#10b981";
            }
          });
        }
      } else {
        if (sidebarFleetCount) {
          sidebarFleetCount.textContent = "0/4 ONLINE";
          sidebarFleetCount.style.color = "var(--text-muted)";
        }
        ["amr-dot-delivery", "amr-dot-reception", "amr-dot-emergency", "amr-dot-support"].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.style.background = "#64748b";
        });
      }

      return data;
    } catch (e) {
      console.warn("Failed to fetch fleet status:", e);
      return null;
    }
  }

  async function loadAuthoritativeKnowledgeMap() {
    try {
      const data = await apiRequest("/api/simulation/authoritative_map");
      state.authoritativeKnowledgeMap = data;
      return data;
    } catch (e) {
      return null;
    }
  }

  async function selectFleetRobot(robotId) {
    state.selectedFleetRobotId = robotId;
    state.activeRobotId = robotId;
    const selectEl = document.getElementById("teleop-robot-select");
    if (selectEl) selectEl.value = robotId;
    renderFleetOperationsConsole();
    try {
      await apiRequest("/api/fleet/select_robot", {
        method: "POST",
        body: JSON.stringify({ robot_id: robotId })
      });
    } catch (_) {}
  }

  function renderFleetOperationsConsole() {
    const rosterTbody = document.getElementById("fleet-roster-tbody");
    if (!rosterTbody) return;

    const rawRobots = (state.fleetStatusData && Array.isArray(state.fleetStatusData.robots) && state.fleetStatusData.robots.length > 0)
      ? state.fleetStatusData.robots
      : Object.values(state.robots);

    const defaultFleet = [
      { robot_id: "ROBOT-01", name: "Arogya_Delivery", role: "DELIVERY", status: "IDLE", battery: 98.5, x: 34.50, y: 33.00, active_task: "Standing by in IDLE" },
      { robot_id: "ROBOT-02", name: "Mitra_Reception", role: "RECEPTION", status: "NAVIGATING", battery: 21.6, x: 15.29, y: -0.34, active_task: "Auto-Docking: Low battery" },
      { robot_id: "ROBOT-03", name: "Garuda_Emergency", role: "EMERGENCY", status: "IDLE", battery: 100.0, x: -29.00, y: -8.80, active_task: "Standing by in IDLE" },
      { robot_id: "ROBOT-04", name: "Sahayak_Support", role: "SUPPORT", status: "IDLE", battery: 95.0, x: 39.50, y: 33.00, active_task: "Standing by in IDLE" },
    ];

    const sourceRobots = (rawRobots && rawRobots.length > 0) ? rawRobots : defaultFleet;
    const seen = new Set();
    const robots = sourceRobots.filter((r) => {
      const key = (r.name || r.robot_id || "").toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    rosterTbody.innerHTML = robots.map((r) => {
      const rid = r.robot_id || r.id || "AMR";
      const isSelected = rid === state.selectedFleetRobotId || r.name === state.selectedFleetRobotId;
      const bVal = (r.battery !== undefined && r.battery !== null) ? Number(r.battery).toFixed(1) : ((r.battery_level !== undefined && r.battery_level !== null) ? Number(r.battery_level).toFixed(1) : "100.0");
      const px = (r.x !== undefined && r.x !== null) ? Number(r.x).toFixed(2) : ((r.current_x !== undefined && r.current_x !== null) ? Number(r.current_x).toFixed(2) : "0.00");
      const py = (r.y !== undefined && r.y !== null) ? Number(r.y).toFixed(2) : ((r.current_y !== undefined && r.current_y !== null) ? Number(r.current_y).toFixed(2) : "0.00");
      const stat = r.status || "IDLE";
      const task = r.current_mission || r.active_task || r.task || "Standby";

      let statClass = "idle";
      if (stat === "NAVIGATING" || stat === "BUSY") statClass = "navigating";
      else if (stat === "CHARGING") statClass = "charging";
      else if (stat === "OFFLINE" || stat === "ERROR") statClass = "cancelled";
      else if (stat === "AVAILABLE" || stat === "IDLE") statClass = "active";

      return `
        <tr class="fleet-table-row ${isSelected ? 'selected' : ''}" onclick="AarogyaApp.selectFleetRobot('${rid}')">
          <td><strong>${rid}</strong></td>
          <td>
            <div style="font-weight:600; color:var(--text-main);">${r.name || rid}</div>
            <div style="font-size:11px; color:var(--text-muted);">${r.role || 'AMR'}</div>
          </td>
          <td><code>(${px}, ${py})</code></td>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <div class="progress-bar-container" style="width:50px; height:5px;">
                <div class="progress-bar-fill" style="width:${bVal}%; background:${bVal < 25 ? 'var(--accent-rose)' : bVal < 50 ? 'var(--accent-amber)' : 'var(--accent-emerald)'};"></div>
              </div>
              <span style="font-size:11px; font-weight:700;">${bVal}%</span>
            </div>
          </td>
          <td><span class="badge badge-${statClass}">${stat}</span></td>
          <td style="font-size:11px; color:var(--text-muted);">${task}</td>
          <td>
            <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="event.stopPropagation(); AarogyaApp.selectFleetRobot('${rid}')">
              ${isSelected ? 'Active' : 'Inspect'}
            </button>
          </td>
        </tr>
      `;
    }).join("");

    renderSelectedRobotDrawer();
  }

  function renderSelectedRobotDrawer() {
    const rid = state.selectedFleetRobotId || "Arogya_Delivery";
    const r = state.robots[rid] || Object.values(state.robots).find(x => x.name === rid || x.id === rid) || state.robots["Arogya_Delivery"];
    if (!r) return;

    const elName = document.getElementById("drawer-robot-name");
    const elId = document.getElementById("drawer-robot-id");
    const elStat = document.getElementById("drawer-robot-status");
    const elPose = document.getElementById("drawer-robot-pose");
    const elYaw = document.getElementById("drawer-robot-yaw");
    const elSpeed = document.getElementById("drawer-robot-speed");
    const elZone = document.getElementById("drawer-robot-zone");
    const elBatPct = document.getElementById("drawer-robot-battery-pct");
    const elBatBar = document.getElementById("drawer-robot-battery-bar");
    const elRange = document.getElementById("drawer-robot-range");
    const elNavGoal = document.getElementById("drawer-robot-nav-goal");
    const elMapKnow = document.getElementById("drawer-robot-map-knowledge");
    const elHistory = document.getElementById("drawer-mission-history");

    const rName = r.name || r.robot_id || "AMR";
    const rRole = r.role || "Clinical Logistics AMR";
    const stat = r.status || "AVAILABLE";

    if (elName) elName.textContent = `${rName} (${r.robot_id || rid})`;
    if (elId) elId.textContent = `${r.model || 'AMR-200'} • ${rRole}`;
    if (elStat) {
      elStat.textContent = stat;
      elStat.className = `badge badge-${stat.toLowerCase()}`;
    }

    const px = (r.x !== undefined && r.x !== null) ? Number(r.x).toFixed(2) : ((r.current_x !== undefined && r.current_x !== null) ? Number(r.current_x).toFixed(2) : "37.25");
    const py = (r.y !== undefined && r.y !== null) ? Number(r.y).toFixed(2) : ((r.current_y !== undefined && r.current_y !== null) ? Number(r.current_y).toFixed(2) : "26.00");
    if (elPose) elPose.textContent = `X: ${px}m, Y: ${py}m`;

    const yaw = (r.yaw !== undefined && r.yaw !== null) ? Number(r.yaw) : 0.0;
    const yawDeg = ((yaw * 180 / Math.PI) % 360).toFixed(1);
    if (elYaw) elYaw.textContent = `${yawDeg}° (${yaw.toFixed(2)} rad)`;

    const spd = (r.speed !== undefined && r.speed !== null) ? Number(r.speed).toFixed(2) : "0.00";
    if (elSpeed) elSpeed.textContent = `${spd} m/s`;

    if (elZone) elZone.textContent = r.destination ? `Transit to ${r.destination}` : (px > 20 && py > 15 ? "Fleet Bay (CHG-01)" : "Central Hospital Grid");

    const bVal = (r.battery !== undefined && r.battery !== null) ? Number(r.battery).toFixed(1) : ((r.battery_level !== undefined && r.battery_level !== null) ? Number(r.battery_level).toFixed(1) : "95.0");
    if (elBatPct) elBatPct.textContent = `${bVal}%`;
    if (elBatBar) {
      elBatBar.style.width = `${bVal}%`;
      elBatBar.style.background = bVal < 25 ? 'var(--accent-rose)' : bVal < 50 ? 'var(--accent-amber)' : 'var(--accent-emerald)';
    }
    if (elRange) elRange.textContent = `${(Number(bVal) * 0.08).toFixed(1)} km`;

    if (elNavGoal) elNavGoal.textContent = r.destination ? `${r.destination} (In Transit)` : "None (Standby at Station)";
    if (elMapKnow) elMapKnow.textContent = `Authoritative SLAM (${state.slamProgress ? state.slamProgress.toFixed(1) : "0.0"}% Discovered)`;

    if (elHistory) {
      const tasks = state.tasks.filter(t => (t.robot || t.robot_id) === rid || (t.robot || t.robot_id) === rName);
      if (tasks.length > 0) {
        elHistory.innerHTML = tasks.slice(0, 4).map(t => `
          <div style="font-size:11px; color:var(--text-main); padding:6px; background:rgba(15,23,42,0.6); border-radius:4px; display:flex; justify-content:space-between; align-items:center;">
            <span><strong>${t.task_code || `#${t.id}`}</strong>: ${t.medicine || t.type || 'Mission'} ➔ ${t.destination || 'Room'}</span>
            <span class="badge badge-${(t.status || 'PENDING').toLowerCase()}" style="font-size:10px;">${t.status}</span>
          </div>
        `).join("");
      } else {
        elHistory.innerHTML = `<div style="font-size:11px; color:var(--text-dim); padding:6px; background:rgba(15,23,42,0.4); border-radius:4px;">No active missions recorded for ${rid}</div>`;
      }
    }
  }

  // ── TELEOPERATION & ACTUATION CONTROLLER (PHASE 5) ────────────────────────
  async function sendTeleopCommand(cmd, customVx = null, customWz = null) {
    const selEl = document.getElementById("teleop-robot-select");
    const robotId = (selEl && selEl.value) || state.selectedFleetRobotId || "Arogya_Delivery";
    const linSpeed = parseFloat(document.getElementById("teleop-slider-linear")?.value || "0.6");
    const angSpeed = parseFloat(document.getElementById("teleop-slider-angular")?.value || "0.8");

    let vx = 0.0;
    let wz = 0.0;

    if (cmd === "forward") vx = linSpeed;
    else if (cmd === "reverse") vx = -linSpeed;
    else if (cmd === "left") wz = angSpeed;
    else if (cmd === "right") wz = -angSpeed;
    else if (cmd === "stop") { vx = 0.0; wz = 0.0; }
    else if (customVx !== null || customWz !== null) {
      vx = customVx || 0.0;
      wz = customWz || 0.0;
    }

    // Update live feedback UI
    const vxEl = document.getElementById("teleop-val-vx");
    const wzEl = document.getElementById("teleop-val-wz");
    const statEl = document.getElementById("teleop-feedback-status");
    const ackEl = document.getElementById("teleop-feedback-ack");

    if (!state.simRunning) {
      if (ackEl) {
        ackEl.textContent = "WARN: Isaac Sim is OFFLINE. Cannot move physical robot.";
        ackEl.style.color = "#f59e0b";
      }
      showToast("Cannot move robot: NVIDIA Isaac Sim is OFFLINE. Click [RUN SIMULATION] first.", "warning");
      return;
    }

    if (vxEl) vxEl.textContent = `${vx.toFixed(2)} m/s`;
    if (wzEl) wzEl.textContent = `${wz.toFixed(2)} rad/s`;
    if (statEl) {
      statEl.textContent = cmd.toUpperCase();
      statEl.style.color = cmd === "stop" ? "#ef4444" : "#10b981";
    }

    try {
      const res = await apiRequest("/api/fleet/control", {
        method: "POST",
        body: JSON.stringify({
          robot_id: robotId,
          action: cmd,
          linear_velocity: vx,
          angular_velocity: wz
        })
      });
      if (ackEl) {
        if (res.status === "warning" || !res.isaac_sim_connected) {
          ackEl.textContent = `WARN: ${res.detail || 'Simulation offline'}`;
          ackEl.style.color = "#f59e0b";
        } else {
          ackEl.textContent = `ACK: ${res.detail || res.message || 'DISPATCHED'} [${new Date().toLocaleTimeString()}]`;
          ackEl.style.color = "#10b981";
        }
      }
    } catch (err) {
      if (ackEl) {
        ackEl.textContent = `ERR: ${err.message || 'FAILED'}`;
        ackEl.style.color = "#ef4444";
      }
    }
  }

  function setupTeleopControls() {
    const selRob = document.getElementById("teleop-robot-select");
    if (selRob) {
      selRob.addEventListener("change", (e) => {
        selectFleetRobot(e.target.value);
      });
    }

    const sLin = document.getElementById("teleop-slider-linear");
    if (sLin) {
      sLin.addEventListener("input", (e) => {
        const v = document.getElementById("teleop-linear-val");
        if (v) v.textContent = `${parseFloat(e.target.value).toFixed(1)} m/s`;
      });
    }

    const sAng = document.getElementById("teleop-slider-angular");
    if (sAng) {
      sAng.addEventListener("input", (e) => {
        const v = document.getElementById("teleop-angular-val");
        if (v) v.textContent = `${parseFloat(e.target.value).toFixed(1)} rad/s`;
      });
    }

    // D-Pad Buttons
    document.getElementById("teleop-btn-forward")?.addEventListener("click", () => sendTeleopCommand("forward"));
    document.getElementById("teleop-btn-left")?.addEventListener("click", () => sendTeleopCommand("left"));
    document.getElementById("teleop-btn-stop")?.addEventListener("click", () => sendTeleopCommand("stop"));
    document.getElementById("teleop-btn-right")?.addEventListener("click", () => sendTeleopCommand("right"));
    document.getElementById("teleop-btn-reverse")?.addEventListener("click", () => sendTeleopCommand("reverse"));

    // Keyboard Teleoperation (W/A/S/D/Space/Arrows)
    window.addEventListener("keydown", (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
      if (state.currentView !== "robots" && state.currentView !== "simulation" && state.currentView !== "map") return;

      const key = e.key.toLowerCase();
      if (key === "w" || key === "arrowup") {
        e.preventDefault();
        sendTeleopCommand("forward");
      } else if (key === "s" || key === "arrowdown") {
        e.preventDefault();
        sendTeleopCommand("reverse");
      } else if (key === "a" || key === "arrowleft") {
        e.preventDefault();
        sendTeleopCommand("left");
      } else if (key === "d" || key === "arrowright") {
        e.preventDefault();
        sendTeleopCommand("right");
      } else if (key === " " || key === "escape") {
        e.preventDefault();
        sendTeleopCommand("stop");
      }
    });
  }

  // ── INDEPENDENT MAP PAN/ZOOM & INTERACTIVE CANVAS CONTROLLER (PHASE 3) ──
  const mapPanZoom = {
    reference: { zoom: 1.0, panX: 0, panY: 0, isDragging: false, startX: 0, startY: 0 },
    slam: { zoom: 1.0, panX: 0, panY: 0, isDragging: false, startX: 0, startY: 0 },
    default: { zoom: 1.0, panX: 0, panY: 0, isDragging: false, startX: 0, startY: 0 }
  };

  function setupZoomControls() {
    // Reference Map Zoom Controls
    document.getElementById("btn-zoom-in-ref")?.addEventListener("click", () => {
      mapPanZoom.reference.zoom = Math.min(10.0, mapPanZoom.reference.zoom * 1.25);
    });
    document.getElementById("btn-zoom-out-ref")?.addEventListener("click", () => {
      mapPanZoom.reference.zoom = Math.max(0.2, mapPanZoom.reference.zoom * 0.8);
    });
    document.getElementById("btn-zoom-reset-ref")?.addEventListener("click", () => {
      mapPanZoom.reference.zoom = 1.0;
      mapPanZoom.reference.panX = 0;
      mapPanZoom.reference.panY = 0;
    });

    // SLAM Map Zoom Controls
    document.getElementById("btn-zoom-in-slam")?.addEventListener("click", () => {
      mapPanZoom.slam.zoom = Math.min(10.0, mapPanZoom.slam.zoom * 1.25);
    });
    document.getElementById("btn-zoom-out-slam")?.addEventListener("click", () => {
      mapPanZoom.slam.zoom = Math.max(0.2, mapPanZoom.slam.zoom * 0.8);
    });
    document.getElementById("btn-zoom-reset-slam")?.addEventListener("click", () => {
      mapPanZoom.slam.zoom = 1.0;
      mapPanZoom.slam.panX = 0;
      mapPanZoom.slam.panY = 0;
    });

    // Side-by-side overlay opacity slider
    const opSlider = document.getElementById("slider-overlay-opacity");
    if (opSlider) {
      opSlider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        state.overlayOpacity = val / 100.0;
        const valEl = document.getElementById("val-overlay-opacity");
        if (valEl) valEl.textContent = `${val}%`;
      });
    }

    // Connect both exploration buttons (btn-slam-explore and btn-start-exploration)
    const btnStartExp = document.getElementById("btn-start-exploration");
    const btnSlamExp = document.getElementById("btn-slam-explore");
    if (btnStartExp && btnSlamExp) {
      btnStartExp.addEventListener("click", () => {
        btnSlamExp.click();
      });
    }
  }

  function setupInteractiveMapCanvas(canvasId, pzKey, coordElId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const pz = mapPanZoom[pzKey];
    const coordEl = document.getElementById(coordElId);

    canvas.addEventListener("mousedown", (e) => {
      pz.isDragging = true;
      pz.startX = e.clientX - pz.panX;
      pz.startY = e.clientY - pz.panY;
      canvas.style.cursor = "grabbing";
    });

    window.addEventListener("mouseup", () => {
      if (pz.isDragging) {
        pz.isDragging = false;
        canvas.style.cursor = "crosshair";
      }
    });

    canvas.addEventListener("mousemove", (e) => {
      if (pz.isDragging) {
        pz.panX = e.clientX - pz.startX;
        pz.panY = e.clientY - pz.startY;
      }
      if (coordEl) {
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const baseZoom = Math.min(canvas.width / 95, canvas.height / 70);
        const zoom = baseZoom * (pz.zoom || 1.0);
        const offsetX = canvas.width / 2 + (pz.panX || 0);
        const offsetY = canvas.height / 2 + (pz.panY || 0);
        const wx = (sx - offsetX) / zoom;
        const wy = (offsetY - sy) / zoom;
        coordEl.textContent = `X: ${wx.toFixed(2)}m, Y: ${wy.toFixed(2)}m`;
      }
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      pz.zoom = Math.max(0.2, Math.min(10.0, pz.zoom * zoomFactor));
    }, { passive: false });
  }

  async function evaluateFleetDispatch() {
    const missionType = document.getElementById("dispatch-mission-type").value;
    const dest = document.getElementById("dispatch-destination").value;
    const priority = document.getElementById("dispatch-priority").value;
    const targetRob = document.getElementById("dispatch-target-robot").value;

    const evalPanel = document.getElementById("dispatch-candidate-eval-panel");
    const grid = document.getElementById("dispatch-candidates-grid");
    const winnerEl = document.getElementById("dispatch-eval-winner");
    const reasonEl = document.getElementById("dispatch-reasoning-text");

    try {
      const res = await apiRequest("/api/fleet/dispatch", {
        method: "POST",
        body: JSON.stringify({
          mission_type: missionType,
          destination: dest,
          priority: priority,
          robot_id: targetRob === "AUTO" ? null : targetRob,
          evaluate_only: true,
        }),
      });

      if (evalPanel) evalPanel.style.display = "block";
      if (winnerEl) winnerEl.textContent = `WINNER: ${res.assigned_robot || 'Arogya_Delivery'}`;
      if (reasonEl) reasonEl.textContent = res.reasoning || "Multi-criteria evaluation completed.";

      if (grid && Array.isArray(res.candidate_evaluations)) {
        grid.innerHTML = res.candidate_evaluations.map((c) => {
          const isWinner = c.robot_id === res.assigned_robot;
          return `
            <div class="candidate-card ${isWinner ? 'winner' : ''} ${!c.eligible ? 'ineligible' : ''}">
              <div style="font-size:11px; font-weight:700; color:${isWinner ? 'var(--accent-cyan)' : 'var(--text-main)'}; display:flex; justify-content:space-between;">
                <span>${c.robot_id}</span>
                <span>${isWinner ? '★ 1st' : ''}</span>
              </div>
              <div class="candidate-score" style="color:${isWinner ? 'var(--accent-cyan)' : 'var(--text-muted)'};">
                Bid: ${c.score !== undefined ? c.score.toFixed(1) : 'N/A'}
              </div>
              <div style="font-size:10px; color:var(--text-dim); line-height:1.2;">
                Bat: ${c.battery}% | Dist: ${c.distance_m}m
              </div>
              <div style="font-size:10px; color:${c.eligible ? 'var(--accent-emerald)' : 'var(--accent-rose)'}; margin-top:2px;">
                ${c.rejection_reason || (c.eligible ? 'Eligible' : 'Ineligible')}
              </div>
            </div>
          `;
        }).join("");
      }
      showToast(`Arbitration evaluated: ${res.assigned_robot} best match.`);
    } catch (err) {
      showToast("Evaluation error: " + (err.message || err));
    }
  }

  async function handleFleetDispatch() {
    const missionType = document.getElementById("dispatch-mission-type").value;
    const dest = document.getElementById("dispatch-destination").value;
    const priority = document.getElementById("dispatch-priority").value;
    const targetRob = document.getElementById("dispatch-target-robot").value;

    try {
      showToast("Executing multi-criteria dispatch...", "info");
      const res = await apiRequest("/api/fleet/dispatch", {
        method: "POST",
        body: JSON.stringify({
          mission_type: missionType,
          destination: dest,
          priority: priority,
          robot_id: targetRob === "AUTO" ? null : targetRob,
          evaluate_only: false,
        }),
      });

      const reasonEl = document.getElementById("dispatch-reasoning-text");
      if (reasonEl) reasonEl.textContent = res.reasoning || "Mission dispatched successfully.";

      showToast(`Mission ${res.task_code} dispatched to ${res.assigned_robot}!`);
      showMissionCorrelation(res);
      await refreshAllData();
    } catch (err) {
      showToast("Dispatch error: " + (err.message || err));
    }
  }

  async function handleFleetCancel() {
    const rid = state.selectedFleetRobotId || "Arogya_Delivery";
    try {
      const res = await apiRequest("/api/fleet/cancel", {
        method: "POST",
        body: JSON.stringify({ robot_id: rid, reason: "Operator cancelled via fleet console" }),
      });
      showToast(`Mission cancelled for ${rid}: ${res.status}`);
      await refreshAllData();
    } catch (err) {
      showToast("Cancel error: " + (err.message || err));
    }
  }

  async function handleFleetReassign() {
    const rid = state.selectedFleetRobotId || "Arogya_Delivery";
    try {
      const res = await apiRequest("/api/fleet/reassign", {
        method: "POST",
        body: JSON.stringify({ source_robot_id: rid, reason: "Preempted for load balancing" }),
      });
      showToast(`Reassigned: ${res.status}`);
      await refreshAllData();
    } catch (err) {
      showToast("Reassignment error: " + (err.message || err));
    }
  }

  async function handleFleetCharge() {
    const rid = state.selectedFleetRobotId || "Arogya_Delivery";
    try {
      const res = await apiRequest("/api/fleet/charge", {
        method: "POST",
        body: JSON.stringify({ robot_id: rid, dock_id: "CHG-01" }),
      });
      showToast(`${rid} dispatched to charging station CHG-01`);
      await refreshAllData();
    } catch (err) {
      showToast("Charging dispatch error: " + (err.message || err));
    }
  }

  async function openMissionReplay(taskCode) {
    const code = taskCode || (state.tasks[0] && state.tasks[0].task_code) || "MSN-20261008-0001";
    const modal = document.getElementById("modal-mission-replay");
    if (!modal) return;

    try {
      const data = await apiRequest(`/api/fleet/mission_replay/${code}`);
      state.replayMissionData = data;
      state.replayCurrentStep = 0;
      state.replayIsPlaying = false;

      const badge = document.getElementById("replay-task-code-badge");
      if (badge) badge.textContent = data.task_code || code;

      const summary = document.getElementById("replay-mission-summary");
      if (summary) summary.textContent = `AMR: ${data.robot_id || 'AMR'} ➔ Target: ${data.target_room || 'ICU-01'} | Points: ${(data.steps || []).length} steps`;

      const listEl = document.getElementById("replay-timeline-steps");
      if (listEl && Array.isArray(data.steps)) {
        listEl.innerHTML = data.steps.map((s, idx) => `
          <div class="timeline-step-row" id="replay-step-${idx}">
            <span style="font-weight:700; color:var(--accent-cyan); min-width:24px;">#${idx + 1}</span>
            <span style="color:var(--text-muted);">${s.timestamp || ''}</span>
            <span style="font-family:var(--font-mono);">(${s.x}, ${s.y})</span>
            <span class="badge badge-idle" style="font-size:9px;">${s.status || 'OK'}</span>
            <span style="color:var(--text-dim);">${s.note || ''}</span>
          </div>
        `).join("");
      }

      modal.classList.add("active");
      drawReplayCanvas();
    } catch (err) {
      showToast("Mission replay error: " + (err.message || err));
    }
  }

  function toggleReplayPlayback() {
    const btn = document.getElementById("btn-replay-play");
    state.replayIsPlaying = !state.replayIsPlaying;
    if (btn) btn.textContent = state.replayIsPlaying ? "⏸ Pause" : "▶ Play Replay";
    if (state.replayIsPlaying) {
      runReplayLoop();
    }
  }

  function resetReplayPlayback() {
    state.replayCurrentStep = 0;
    state.replayIsPlaying = false;
    const btn = document.getElementById("btn-replay-play");
    if (btn) btn.textContent = "▶ Play Replay";
    drawReplayCanvas();
  }

  function runReplayLoop() {
    if (!state.replayIsPlaying || !state.replayMissionData) return;
    const steps = state.replayMissionData.steps || [];
    if (state.replayCurrentStep < steps.length - 1) {
      state.replayCurrentStep++;
      drawReplayCanvas();
      setTimeout(runReplayLoop, 350);
    } else {
      state.replayIsPlaying = false;
      const btn = document.getElementById("btn-replay-play");
      if (btn) btn.textContent = "↺ Replay Again";
    }
  }

  function drawReplayCanvas() {
    const canvas = document.getElementById("mission-replay-canvas");
    if (!canvas || !state.replayMissionData) return;
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    const ctx = canvas.getContext("2d");

    ctx.fillStyle = "#080d1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const steps = state.replayMissionData.steps || [];
    if (steps.length === 0) return;

    const zoom = Math.min(canvas.width / 90, canvas.height / 60);
    const offsetX = canvas.width / 2;
    const offsetY = canvas.height / 2;
    const toScreen = (wx, wy) => ({ x: offsetX + wx * zoom, y: offsetY - wy * zoom });

    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.strokeRect(offsetX - 44 * zoom, offsetY - 31 * zoom, 88 * zoom, 62 * zoom);

    ctx.beginPath();
    ctx.strokeStyle = "rgba(6, 182, 212, 0.4)";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    steps.forEach((s, idx) => {
      const p = toScreen(s.x, s.y);
      if (idx === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.beginPath();
    ctx.strokeStyle = "#10b981";
    ctx.lineWidth = 3;
    for (let i = 0; i <= state.replayCurrentStep && i < steps.length; i++) {
      const p = toScreen(steps[i].x, steps[i].y);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();

    const cur = steps[state.replayCurrentStep] || steps[0];
    const cp = toScreen(cur.x, cur.y);
    ctx.beginPath();
    ctx.arc(cp.x, cp.y, 8, 0, Math.PI * 2);
    ctx.fillStyle = "#0284c7";
    ctx.fill();
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.stroke();

    for (let i = 0; i < steps.length; i++) {
      const row = document.getElementById(`replay-step-${i}`);
      if (row) {
        row.style.background = i === state.replayCurrentStep ? "rgba(2, 132, 199, 0.25)" : "rgba(15, 23, 42, 0.5)";
      }
    }
  }

  async function renderSystemHealthPage() {
    const grid = document.getElementById("health-page-diagnostics-grid");
    if (!grid) return;

    try {
      const diagData = await apiRequest("/api/simulation/exploration_diagnostics").catch(() => null);
      const defaultDiag = {
        isaac_sim: state.simRunning ? "RUNNING" : "STANDBY",
        simulation: state.simRunning ? "RUNNING" : "READY",
        ros2_bridge: "CONNECTED",
        robot: "READY",
        lidar: "ACTIVE",
        odometry: "ACTIVE",
        tf: "VALID",
        slam: "ACTIVE",
        nav2: "READY",
        frontier_planner: "ACTIVE",
        nav_goal: "STANDBY",
        velocity: "ZERO",
        movement: "STATIONARY"
      };
      const d = diagData || state.explorationDiagnostics || defaultDiag;

      const items = [
        { label: "Isaac Sim 5.1 Process", val: d.isaac_sim || "STANDBY", ok: d.isaac_sim === "RUNNING" },
        { label: "Simulation Lifecycle", val: d.simulation || "READY", ok: d.simulation === "RUNNING" },
        { label: "ROS 2 Navigation Bridge", val: d.ros2_bridge || "CONNECTED", ok: d.ros2_bridge === "READY" || d.ros2_bridge === "CONNECTED" },
        { label: "Robot Articulation", val: d.robot || "READY", ok: d.robot === "READY" },
        { label: "LiDAR Perception 2D", val: d.lidar || "ACTIVE", ok: d.lidar === "ACTIVE" },
        { label: "Odometry Frame Track", val: d.odometry || "ACTIVE", ok: d.odometry === "ACTIVE" },
        { label: "TF Coordinate Tree", val: d.tf || "VALID", ok: d.tf === "VALID" },
        { label: "Authoritative SLAM Engine", val: d.slam || "ACTIVE", ok: d.slam === "ACTIVE" },
        { label: "Nav2 Path Planning Stack", val: d.nav2 || "READY", ok: d.nav2 === "READY" },
        { label: "Frontier Exploration Planner", val: d.frontier_planner || "ACTIVE", ok: d.frontier_planner === "ACTIVE" },
        { label: "Navigation Goal Status", val: d.nav_goal || "STANDBY", ok: true },
        { label: "Velocity Command (/cmd_vel)", val: d.velocity || "ZERO", ok: true },
        { label: "Physical Movement State", val: d.movement || "STATIONARY", ok: true },
      ];

      grid.innerHTML = items.map((it) => `
        <div class="diag-card">
          <span class="diag-card-label">${it.label}</span>
          <span class="diag-card-val" style="color:${it.ok ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">
            ● ${it.val}
          </span>
        </div>
      `).join("");

      const simValEl = document.getElementById("health-page-sim-val");
      if (simValEl) {
        simValEl.textContent = diagData.isaac_sim;
        simValEl.style.color = diagData.isaac_sim === "RUNNING" ? "var(--accent-emerald)" : "var(--accent-amber)";
      }
    } catch (e) {
      console.warn("Health page render error:", e);
    }
  }

  function renderMedicinesTable() {
    const tbody = document.getElementById("medicines-table-body");
    if (!tbody) return;
    tbody.innerHTML = state.medicines
      .map(
        (m) => `
      <tr>
        <td><code>${m.code}</code></td>
        <td style="font-weight:600;">${m.name}</td>
        <td>${m.category}</td>
        <td>${m.dosage_form} (${m.route})</td>
        <td>${m.strength}</td>
        <td><strong style="color:${m.stock_quantity < 50 ? "var(--accent-amber)" : "var(--accent-emerald)"}">${m.stock_quantity} units</strong></td>
        <td>${m.requires_prescription ? `<span class="badge badge-emergency">Restricted Rx</span>` : `<span class="badge badge-idle">OTC</span>`}</td>
      </tr>`
      )
      .join("");
  }

  function renderStaffTables() {
    const docTbody = document.getElementById("doctors-table-body");
    if (docTbody && state.doctors) {
      docTbody.innerHTML = state.doctors.length === 0
        ? `<tr><td colspan="3" style="text-align:center; color:var(--text-dim); padding:16px;">No physician records.</td></tr>`
        : state.doctors.map((d) => `
          <tr>
            <td style="font-weight:600;">${d.name}</td>
            <td><code>${d.staff_id}</code></td>
            <td><span class="badge badge-active">${d.specialization}</span> <small style="color:var(--text-muted)">(${d.department || "General"})</small></td>
          </tr>
        `).join("");
    }

    const nurseTbody = document.getElementById("nurses-table-body");
    if (nurseTbody && state.nurses) {
      nurseTbody.innerHTML = state.nurses.length === 0
        ? `<tr><td colspan="3" style="text-align:center; color:var(--text-dim); padding:16px;">No nursing records.</td></tr>`
        : state.nurses.map((n) => `
          <tr>
            <td style="font-weight:600;">${n.name}</td>
            <td><code>${n.staff_id}</code></td>
            <td><span class="badge badge-idle">${n.shift} Shift</span> ${n.is_on_duty ? `<span class="badge badge-delivered">On Duty</span>` : `<span class="badge badge-cancelled">Off Duty</span>`}</td>
          </tr>
        `).join("");
    }
  }

  function renderAuditLogsTable() {
    const tbody = document.getElementById("audit-table-body");
    if (!tbody || !state.auditLogs) return;
    tbody.innerHTML = state.auditLogs.length === 0
      ? `<tr><td colspan="8" style="text-align:center; color:var(--text-dim); padding:20px;">No audit events recorded yet.</td></tr>`
      : state.auditLogs.map((l) => `
        <tr>
          <td><small style="color:var(--text-muted)">${new Date(l.timestamp).toLocaleTimeString()}</small></td>
          <td><strong>${l.username}</strong></td>
          <td><span class="badge badge-idle">${l.role}</span></td>
          <td><code>${l.action}</code></td>
          <td>${l.entity || "N/A"}</td>
          <td>${l.duplicate_detected ? `<span class="badge badge-emergency">⚠️ DUPLICATE</span>` : `<span style="color:var(--text-dim)">No</span>`}</td>
          <td>${l.authorization_denied ? `<span class="badge badge-danger">⛔ DENIED</span>` : `<span class="badge badge-delivered">ALLOWED</span>`}</td>
          <td><small style="color:var(--text-muted); max-width:240px; display:inline-block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${l.details || ""}">${l.details || "-"}</small></td>
        </tr>
      `).join("");
  }

  function renderEmergencyTable() {
    const tbody = document.getElementById("emergency-table-body");
    if (!tbody || !state.emergencies) return;
    tbody.innerHTML = state.emergencies.length === 0
      ? `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:20px;">No emergency events active or logged. System nominal.</td></tr>`
      : state.emergencies.map((e) => `
        <tr>
          <td><code>${e.event_code}</code></td>
          <td><span class="badge badge-emergency">${e.event_type}</span></td>
          <td><strong>${e.room_number}</strong></td>
          <td><span class="badge badge-${e.status === "ACTIVE" ? "emergency" : "delivered"}">${e.status}</span></td>
          <td><small>${e.details || "Code Blue alert"}</small></td>
          <td><small style="color:var(--text-dim)">${e.created_at ? new Date(e.created_at).toLocaleTimeString() : "-"}</small></td>
          <td><span style="color:var(--accent-cyan); font-weight:600;">Garuda_Emergency</span></td>
        </tr>
      `).join("");
  }

  // ── 7. WORKFLOW ACTIONS & DUPLICATE BLOCK HANDLING ────────────────────────
  function populateTaskSelects() {
    const pSel = document.getElementById("task-patient-select");
    const mSel = document.getElementById("task-medicine-select");
    if (pSel) {
      pSel.innerHTML = state.patients
        .map((p) => `<option value="${p.id}">${p.name} — ${p.room_number || "Ward"} (${p.bed_number || "Bed"})</option>`)
        .join("");
    }
    if (mSel) {
      mSel.innerHTML = state.medicines
        .map((m) => `<option value="${m.id}">${m.name} (${m.strength})</option>`)
        .join("");
    }
  }

  function populateRxSelects() {
    const pSel = document.getElementById("rx-patient-select");
    const mSel = document.getElementById("rx-medicine-select");
    if (pSel) {
      pSel.innerHTML = state.patients.map((p) => `<option value="${p.id}">${p.name} (${p.mrn})</option>`).join("");
    }
    if (mSel) {
      mSel.innerHTML = state.medicines.map((m) => `<option value="${m.id}">${m.name} (${m.strength})</option>`).join("");
    }
  }

  async function handleCreateTask(e) {
    e.preventDefault();
    const patientId = parseInt(document.getElementById("task-patient-select").value);
    const medicineId = parseInt(document.getElementById("task-medicine-select").value);
    const priority = document.getElementById("task-priority-select").value;

    try {
      const res = await apiRequest("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ patient_id: patientId, medicine_id: medicineId, priority }),
      });
      closeModal("modal-create-task");
      showToast(`Task #${res.id} created! AMR ${res.robot_id} assigned.`);
      showMissionCorrelation(res);
      await refreshAllData();
      switchView("simulation");
    } catch (err) {
      if (err.status === 409) {
        // Master duplicate task prevention rule
        const d = err.data.detail;
        alert(
          `⚠️ DUPLICATE TASK DETECTED AND BLOCKED BY PLATFORM!\n\n` +
            `Message: ${d.message}\n` +
            `Existing Task ID: #${d.existing_task_id}\n` +
            `Status: ${d.existing_task_status}\n` +
            `Assigned AMR: ${d.robot_id}\n\n` +
            `Clinical Rule: Only one active delivery task per patient and medication is permitted to prevent accidental double-dosing.`
        );
      } else {
        alert("Task Creation Error: " + (err.message || "Failed to create task"));
      }
    }
  }

  async function handleCreatePrescription(e) {
    e.preventDefault();
    const patientId = parseInt(document.getElementById("rx-patient-select").value);
    const medicineId = parseInt(document.getElementById("rx-medicine-select").value);
    const dosage = document.getElementById("rx-dosage-input").value;
    const freqHours = parseInt(document.getElementById("rx-freq-input").value);
    const duration = parseInt(document.getElementById("rx-duration-input").value);

    try {
      const res = await apiRequest("/api/prescriptions", {
        method: "POST",
        body: JSON.stringify({
          patient_id: patientId,
          medicine_id: medicineId,
          dosage,
          frequency: `Every ${freqHours} hours`,
          frequency_hours: freqHours,
          duration_days: duration,
        }),
      });
      closeModal("modal-create-rx");
      showToast(`Prescription #${res.prescription_id} created for ${duration} days!`);
      await refreshAllData();
    } catch (err) {
      alert("Prescription Error: " + (err.message || "Unauthorized"));
    }
  }

  async function discontinueRx(rxId) {
    if (!confirm("Are you sure you want to discontinue this active prescription?")) return;
    try {
      await apiRequest(`/api/prescriptions/${rxId}/discontinue`, {
        method: "POST",
        body: JSON.stringify({ reason: "Discontinued by clinical order via UI" }),
      });
      showToast(`Prescription #${rxId} discontinued.`);
      await refreshAllData();
    } catch (err) {
      alert("Error: " + (err.message || "Unauthorized"));
    }
  }

  function quickDispatchToPatient(patientId) {
    showCreateTaskModal();
    const pSel = document.getElementById("task-patient-select");
    if (pSel) pSel.value = patientId;
  }

  async function quickTriggerCodeBlue(room, desc) {
    if (!confirm(`Trigger EMERGENCY CODE BLUE for Room ${room}?`)) return;
    try {
      const res = await apiRequest("/api/emergency/alert", {
        method: "POST",
        body: JSON.stringify({ code_type: "CODE_BLUE", room_number: room, description: desc }),
      });
      showToast(`🚨 ${res.message}`);
      setCameraMode("FOLLOW_TASK");
      showMissionCorrelation(res);
      switchView("simulation");
      await refreshAllData();
    } catch (err) {
      alert("Emergency Alert Error: " + err.message);
    }
  }

  function showMissionCorrelation(result) {
    if (!result) return;
    const modal = document.getElementById("modal-mission-correlation");
    if (!modal) return;

    // Mission ID / Correlation badge
    const badge = document.getElementById("corr-mission-id-badge");
    const corrId = result.correlation_id || result.task_code || result.event_code || `MSN-${new Date().toISOString().slice(0,10).replace(/-/g,"")}-0001`;
    if (badge) badge.textContent = corrId;

    // Footer note
    const footer = document.getElementById("corr-footer-note");
    if (footer) footer.textContent = `Trace ID: ${corrId} • Dispatched: ${new Date().toLocaleTimeString()}`;

    // Stages
    const container = document.getElementById("corr-stages-container");
    if (container) {
      let stages = result.stages;
      if (!Array.isArray(stages) || stages.length === 0) {
        const isAck = Boolean(result.isaac_sim_acknowledged);
        stages = [
          { stage: "REQUEST_RECEIVED", status: "COMPLETED", detail: "HTTP POST payload accepted and parsed by FastAPI endpoint" },
          { stage: "VALIDATION", status: "COMPLETED", detail: "Clinical rules validated; database duplicate prevention confirmed" },
          { stage: "COORDINATOR_ASSIGNED", status: "COMPLETED", detail: `Coordinator Agent dispatched AMR ${result.robot_id || result.robot || "Arogya_Delivery"}` },
          { stage: "ROS2_PUBLISHED", status: "COMPLETED", detail: "Dispatched to ROS 2 topic /hospital/mission_dispatch" },
          { stage: "ISAAC_ACK", status: isAck ? "COMPLETED" : "FAILED", detail: isAck ? "HTTP 200 acknowledged by Isaac Sim sensor/perception server (port 8080)" : `Isaac Sim port 8080 unreachable (${result.warning || "Simulator standby/offline"})` },
          { stage: "ROBOT_STARTED", status: isAck ? "COMPLETED" : "WAITING", detail: isAck ? "AMR autonomous trajectory execution engaged in 3D digital twin" : "Trajectory queued; awaiting Isaac Sim launch" },
        ];
      }

      container.innerHTML = stages.map((s, idx) => {
        let isDone = s.status === "COMPLETED" || s.status === "OK" || s.status === "SUCCESS";
        let isWarn = s.status === "WARNING" || s.status === "WARN";
        let isFail = s.status === "FAILED" || s.status === "ERROR";
        let icon = isDone ? "✓" : (isWarn ? "⚠️" : (isFail ? "✕" : "⏳"));
        let iconBg = isDone ? "#10b981" : (isWarn ? "#f59e0b" : (isFail ? "#ef4444" : "#64748b"));
        let badgeCol = isDone ? "#10b981" : (isWarn ? "#f59e0b" : (isFail ? "#ef4444" : "#94a3b8"));

        return `
          <div style="display:flex; align-items:flex-start; gap:12px; background:rgba(15,23,42,0.65); padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
            <div style="width:22px; height:22px; border-radius:50%; background:${iconBg}; color:#050b14; font-weight:800; font-size:12px; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
              ${icon}
            </div>
            <div style="flex:1;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:12px; color:#f8fafc;">${idx + 1}. ${s.stage}</span>
                <span style="font-size:10px; font-weight:700; color:${badgeCol}; text-transform:uppercase;">${s.status}</span>
              </div>
              <div style="font-size:11px; color:#94a3b8; margin-top:2px; line-height:1.3;">${escapeHtml(s.detail || s.message || "")}</div>
            </div>
          </div>
        `;
      }).join("");
    }

    // Diagnostic Alert Box
    const alertBox = document.getElementById("corr-alert-box");
    if (alertBox) {
      const isAck = Boolean(result.isaac_sim_acknowledged);
      alertBox.style.display = "block";
      if (!isAck || result.warning) {
        alertBox.style.background = "rgba(180, 83, 9, 0.25)";
        alertBox.style.border = "1px solid #f59e0b";
        alertBox.style.color = "#fef3c7";
        alertBox.innerHTML = `
          <div style="font-weight:700; display:flex; align-items:center; gap:6px; margin-bottom:4px; color:#fbbf24;">
            <span>⚠️</span> ISAAC SIM STANDBY / NOT RESPONDING ON PORT 8080
          </div>
          <div style="font-size:11px; color:#cbd5e1;">
            The mission was successfully registered in the platform coordinator and published to the ROS 2 message bus.
            However, NVIDIA Isaac Sim 5.1 is currently in standby or port 8080 was unreachable.
            <strong>The robot will not move in 3D until the simulator is running.</strong>
            Click <strong>[ RUN SIMULATION ]</strong> in the topbar to launch Isaac Sim and resume physical motion.
          </div>
        `;
      } else {
        alertBox.style.background = "rgba(16, 185, 129, 0.2)";
        alertBox.style.border = "1px solid #10b981";
        alertBox.style.color = "#d1fae5";
        alertBox.innerHTML = `
          <div style="font-weight:700; display:flex; align-items:center; gap:6px; margin-bottom:4px; color:#34d399;">
            <span>✓</span> END-TO-END CORRELATION VERIFIED
          </div>
          <div style="font-size:11px; color:#cbd5e1;">
            NVIDIA Isaac Sim perception server confirmed HTTP 200 acknowledgment. Autonomous AMR trajectory execution active.
          </div>
        `;
      }
    }

    modal.classList.add("active");
  }

  // ── 8. VOICE COMMAND GATEWAY ─────────────────────────────────────────────
  function setupSpeech() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      state.speechRecognition = new SpeechRecognition();
      state.speechRecognition.continuous = false;
      state.speechRecognition.interimResults = false;
      state.speechRecognition.lang = "en-US";

      state.speechRecognition.onstart = () => {
        state.isListening = true;
        document.getElementById("voice-prompt-status").textContent = "Listening... Speak your hospital command now.";
        document.getElementById("voice-mic-indicator").style.background = "linear-gradient(135deg, #ef4444, #f43f5e)";
      };

      state.speechRecognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById("voice-command-text").value = transcript;
        state.speechRecognition.stop();
        executeVoiceCommand();
      };

      state.speechRecognition.onerror = (e) => {
        state.isListening = false;
        document.getElementById("voice-prompt-status").textContent = "Speech recognition error: " + e.error;
        document.getElementById("voice-mic-indicator").style.background = "";
      };

      state.speechRecognition.onend = () => {
        state.isListening = false;
        document.getElementById("voice-mic-indicator").style.background = "";
      };
    }
  }

  function toggleSpeechListening() {
    if (!state.speechRecognition) {
      alert("Web Speech API not supported in this browser. Please type your command in the text box.");
      return;
    }
    if (state.isListening) {
      state.speechRecognition.stop();
    } else {
      state.speechRecognition.start();
    }
  }

  async function executeVoiceCommand() {
    const cmd = document.getElementById("voice-command-text").value.trim();
    if (!cmd) return;

    const resultBox = document.getElementById("voice-result-box");
    resultBox.style.display = "block";
    resultBox.innerHTML = `<span style="color:var(--accent-cyan)">Reasoning with Vision-Language Mission Understander...</span>`;

    try {
      const res = await apiRequest("/api/voice/command", {
        method: "POST",
        body: JSON.stringify({ command: cmd }),
      });

      if (res.action === "DENIED") {
        resultBox.innerHTML = `
          <div style="color:var(--accent-crimson); font-weight:bold;">⛔ ACCESS DENIED</div>
          <div style="margin-top:4px;">${res.message}</div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Your current role (${res.user_role}) is not authorized to dispatch clinical deliveries.</div>
        `;
      } else if (res.action === "VISITOR_GUIDANCE") {
        resultBox.innerHTML = `
          <div style="color:var(--accent-emerald); font-weight:bold;">🧭 VISITOR NAVIGATION ASSISTANCE</div>
          <div style="margin-top:4px;">${res.message}</div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Reception AMR ${res.robot_id} assigned.</div>
        `;
      } else if (res.action === "SLAM_EXPLORATION") {
        const tgt = res.next_frontier_target || [0.0, 0.0];
        resultBox.innerHTML = `
          <div style="color:var(--accent-cyan); font-weight:bold;">🗺️ AUTONOMOUS SLAM FRONTIER EXPLORATION</div>
          <div style="margin-top:4px;">${res.message}</div>
          <div style="font-size:11px; color:var(--accent-cyan); margin-top:4px;">AMR: ${res.robot_name || "Arogya_Delivery"} | Target Frontier: (${Number(tgt[0]).toFixed(1)}, ${Number(tgt[1]).toFixed(1)})</div>
        `;
        showToast("Autonomous SLAM Exploration Active!");
        const slamRes = await apiRequest("/api/simulation/slam_map");
        if (slamRes && slamRes.status === "ONLINE") {
          state.slamMap = Object.assign({}, slamRes.metadata || {}, slamRes);
          state.slamProgress = (slamRes.metadata && slamRes.metadata.exploration_progress_pct) !== undefined ? slamRes.metadata.exploration_progress_pct : (slamRes.exploration_progress_pct || 0);
          state.activeDynamicObstacles = slamRes.dynamic_obstacles || [];
        }
        await refreshAllData();
      } else {
        resultBox.innerHTML = `
          <div style="color:var(--accent-emerald); font-weight:bold;">✅ MISSION DISPATCHED</div>
          <div style="margin-top:4px;">${res.message}</div>
          <div style="font-size:11px; color:var(--accent-cyan); margin-top:4px;">Assigned: ${res.robot_id || "AMR"} | Target: ${res.target || "Facility"}</div>
        `;
        showToast("Voice Mission Created!");
        showMissionCorrelation(res);
        await refreshAllData();
      }
    } catch (err) {
      resultBox.innerHTML = `<div style="color:var(--accent-crimson)">Voice Gateway Error: ${err.message}</div>`;
    }
  }

  // ── 9. SIMULATION ENGINE & CAMERA DIRECTOR ────────────────────────────────
  async function toggleSimulation() {
    const btnSim = document.getElementById("btn-sim-toggle");
    const textEl = document.getElementById("sim-toggle-text");
    const iconEl = document.getElementById("sim-toggle-icon");
    const deckRunBtn = document.getElementById("btn-deck-run-sim");
    const deckStopBtn = document.getElementById("btn-deck-stop-sim");

    if (!state.simRunning) {
      // 1. Immediately activate startup checklist modal
      const modalStartup = document.getElementById("modal-sim-startup");
      if (modalStartup) {
        modalStartup.classList.add("active");
        const chk = { backend: true, mission_system: true, ros2: false, isaac_sim: false, hospital_env: false, robot: false, sensors: false, simulation_ready: false };
        const updateCheck = (id, isDone, isActive) => {
          const el = document.getElementById(id);
          if (!el) return;
          el.className = "check-item " + (isDone ? "done" : (isActive ? "active" : "pending"));
          const icon = el.querySelector(".icon");
          if (icon) icon.textContent = isDone ? "✓" : (isActive ? "⟳" : "○");
        };
        updateCheck("check-backend", true, false);
        updateCheck("check-mission", true, false);
        updateCheck("check-ros2", false, true);
        updateCheck("check-isaac", false, false);
        updateCheck("check-hospital", false, false);
        updateCheck("check-robot", false, false);
        updateCheck("check-sensors", false, false);
        updateCheck("check-ready", false, false);
        const noteEl = document.getElementById("startup-status-note");
        if (noteEl) noteEl.textContent = "Booting NVIDIA Isaac Sim 5.1 in interactive 3D desktop window station...";
      }

      try {
        const res = await apiRequest("/api/simulation/start", {
          method: "POST",
          body: JSON.stringify({ force: true, headless: false })
        });
        showToast("NVIDIA Isaac Sim Launch Sequence Initiated.");
      } catch (err) {
        showToast("Simulation launch error: " + (err.message || err));
        const modalStartup = document.getElementById("modal-sim-startup");
        if (modalStartup) modalStartup.classList.remove("active");
      }
    } else {
      try {
        await apiRequest("/api/simulation/stop", { method: "POST" });
        state.simRunning = false;
        if (btnSim) {
          btnSim.classList.add("btn-primary");
          btnSim.classList.remove("btn-danger");
        }
        if (textEl) textEl.textContent = "RUN SIMULATION";
        if (iconEl) iconEl.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
        showToast("Isaac Simulation Terminated.");
      } catch (err) {
        showToast("Simulation stop error: " + (err.message || err));
      }
    }
  }

  async function setCameraMode(mode) {
    state.cameraMode = mode;
    try {
      await apiRequest("/api/simulation/camera", {
        method: "POST",
        body: JSON.stringify({ mode, target_robot_id: state.activeRobotId }),
      });
      showToast(`Camera Director: ${mode}`);
    } catch (e) {
      console.warn("Failed to set camera mode:", e);
    }
  }

  function selectCameraTarget(robotId) {
    state.activeRobotId = robotId;
    setCameraMode("FOLLOW_ROBOT");
    switchView("simulation");
  }

  // ── 10. WEBSOCKET REAL-TIME TELEMETRY ─────────────────────────────────────
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/telemetry`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleTelemetryUpdate(data);
      } catch (err) {
        console.error("Telemetry parse error:", err);
      }
    };

    state.ws.onclose = () => {
      // Reconnect after 3 seconds
      setTimeout(connectWebSocket, 3000);
    };
  }

  function handleTelemetryUpdate(data) {
    if (!data) return;

    // 1. Sync simulation running state & Lifecycle status (Phase 3 10-state management)
    const status = data.status || (data.is_running ? "SIMULATION_READY" : "BACKEND_ONLINE");
    const isRunning = (status === "SIMULATION_READY" || status === "RUNNING");
    state.simRunning = isRunning;

    const btnSim = document.getElementById("btn-sim-toggle");
    const textEl = document.getElementById("sim-toggle-text");
    const iconEl = document.getElementById("sim-toggle-icon");
    if (btnSim && textEl && iconEl) {
      if (isRunning) {
        btnSim.classList.remove("btn-primary");
        btnSim.classList.add("btn-danger");
        textEl.textContent = "STOP SIMULATION";
        iconEl.innerHTML = `<rect x="6" y="6" width="12" height="12"/>`;
        btnSim.disabled = false;
      } else if (status.includes("STARTING") || status.includes("PROCESS_RUNNING") || status.includes("GUI_AVAILABLE") || status.includes("STAGE_LOADED") || status.includes("TIMELINE") || status.includes("ROBOTS") || status === "LOADING") {
        btnSim.classList.remove("btn-danger");
        btnSim.classList.add("btn-primary");
        textEl.textContent = "INITIALIZING...";
        iconEl.innerHTML = `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-dasharray="14" fill="none"/>`;
        btnSim.disabled = false;
      } else {
        btnSim.classList.add("btn-primary");
        btnSim.classList.remove("btn-danger");
        textEl.textContent = "RUN SIMULATION";
        iconEl.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
        btnSim.disabled = false;
      }
    }

    // Topbar and Simulation View Status Badge
    const statusText = document.getElementById("sim-status-text");
    const statusDot = document.getElementById("sim-status-dot");
    const topIndicator = document.getElementById("system-status-indicator");

    if (statusText) statusText.textContent = status.replace(/_/g, " ");
    if (statusDot) {
      statusDot.className = "dot";
      if (isRunning) statusDot.classList.add("online");
      else if (status.includes("STARTING") || status.includes("RUNNING") || status.includes("AVAILABLE") || status.includes("LOADED")) statusDot.classList.add("warning");
      else if (status.includes("FAILED") || status.includes("ERROR")) statusDot.classList.add("error");
      else statusDot.classList.add("offline");
    }

    if (topIndicator) {
      if (isRunning) {
        topIndicator.className = "badge badge-active";
        topIndicator.innerHTML = `<span class="dot online"></span> NVIDIA Isaac Sim Online`;
      } else if (status === "SIMULATION_FAILED") {
        topIndicator.className = "badge badge-danger";
        topIndicator.innerHTML = `<span class="dot error"></span> Simulation Failed`;
      } else if (status !== "BACKEND_ONLINE" && status !== "OFFLINE" && status !== "STANDBY") {
        topIndicator.className = "badge badge-warning";
        const label = status.replace(/_/g, " ");
        topIndicator.innerHTML = `<span class="dot warning"></span> ${label}...`;
      } else {
        topIndicator.className = "badge badge-offline";
        topIndicator.innerHTML = `<span class="dot offline"></span> Backend Online • Sim Standby`;
      }
    }

    // Truthful Subsystem Status on Overview Dashboard
    const valSim = document.getElementById("health-val-isaac_sim");
    const valOverall = document.getElementById("health-overall-badge");
    if (valSim) {
      if (isRunning) {
        valSim.textContent = "● CONNECTED";
        valSim.style.color = "#10b981";
      } else if (status.includes("STARTING") || status.includes("RUNNING") || status.includes("AVAILABLE") || status.includes("LOADED")) {
        valSim.textContent = "● INITIALIZING";
        valSim.style.color = "#f59e0b";
      } else {
        valSim.textContent = "● STANDBY";
        valSim.style.color = "#94a3b8";
      }
    }
    if (valOverall) {
      if (isRunning) {
        valOverall.className = "badge badge-active";
        valOverall.textContent = "ONLINE";
      } else if (status.includes("STARTING") || status.includes("AVAILABLE")) {
        valOverall.className = "badge badge-warning";
        valOverall.textContent = "BOOTING";
      } else {
        valOverall.className = "badge badge-offline";
        valOverall.textContent = "STANDBY";
      }
    }

    // 10-Stage Progression Bar in Simulation Control
    updateProgressionChips(status);

    // Startup Checklist Modal Control (Section 18)
    const startupModal = document.getElementById("modal-sim-startup");
    if (startupModal) {
      const isStarting = (status.includes("STARTING") || status.includes("PROCESS_RUNNING") || status.includes("GUI_AVAILABLE") || status.includes("STAGE_LOADED") || status.includes("TIMELINE") || status.includes("ROBOTS") || status === "LOADING");
      if (isStarting) {
        startupModal.classList.add("active");
        const chk = data.checklist || {};
        const updateCheck = (id, isDone, isActive) => {
          const el = document.getElementById(id);
          if (!el) return;
          el.className = "check-item " + (isDone ? "done" : (isActive ? "active" : "pending"));
          const icon = el.querySelector(".icon");
          if (icon) icon.textContent = isDone ? "✓" : (isActive ? "⟳" : "○");
        };
        updateCheck("check-backend", Boolean(chk.backend), false);
        updateCheck("check-mission", Boolean(chk.mission_system), false);
        updateCheck("check-ros2", Boolean(chk.ros2), !chk.ros2 && chk.mission_system);
        updateCheck("check-isaac", Boolean(chk.isaac_sim), !chk.isaac_sim && chk.ros2);
        updateCheck("check-hospital", Boolean(chk.hospital_env), !chk.hospital_env && chk.isaac_sim);
        updateCheck("check-robot", Boolean(chk.robot), !chk.robot && chk.hospital_env);
        updateCheck("check-sensors", Boolean(chk.sensors), !chk.sensors && chk.robot);
        updateCheck("check-ready", Boolean(chk.simulation_ready), !chk.simulation_ready && chk.sensors);

        const noteEl = document.getElementById("startup-status-note");
        if (noteEl) {
          noteEl.textContent = `Stage: ${status.replace(/_/g, " ")} — Initializing hospital digital twin on desktop...`;
        }
      } else if (isRunning) {
        const noteEl = document.getElementById("startup-status-note");
        if (noteEl) noteEl.textContent = "Isaac Sim 3D simulation active and online! Dismissing checklist...";
        setTimeout(() => {
          startupModal.classList.remove("active");
        }, 1200);
      } else {
        startupModal.classList.remove("active");
      }
    }

    // Real Offscreen Physical Camera Stream (Graceful fallback, no broken image icon)
    const offlineBackdrop = document.getElementById("camera-offline-backdrop");
    const streamImg = document.getElementById("sim-camera-stream");
    const isCameraViewVisible = state.currentView === "simulation";

    if (streamImg && !streamImg.onerror) {
      streamImg.onerror = () => {
        streamImg.style.display = "none";
        if (offlineBackdrop) offlineBackdrop.style.display = "flex";
      };
      streamImg.onload = () => {
        if (isRunning) {
          streamImg.style.display = "block";
          if (offlineBackdrop) offlineBackdrop.style.display = "none";
        }
      };
    }

    if (offlineBackdrop) {
      offlineBackdrop.style.display = isRunning ? "none" : "flex";
    }
    if (streamImg) {
      if (isRunning && isCameraViewVisible) {
        if (!streamImg.src || streamImg.src.indexOf("8080") === -1) {
          streamImg.src = "http://127.0.0.1:8080/video_feed";
        }
      } else {
        if (streamImg.src && streamImg.src.indexOf("8080") !== -1) {
          streamImg.src = "";
        }
        streamImg.style.display = "none";
      }
    }

    const overlayStats = document.getElementById("camera-overlay-stats");
    if (overlayStats) {
      const fpsVal = (data.fps !== null && data.fps !== undefined) ? Number(data.fps).toFixed(1) : (isRunning ? "30.0" : "0.0");
      overlayStats.textContent = `RES: 640x360 | FPS: ${fpsVal} | FOV: 70° | HEAD VISOR CAMERA`;
    }

    // Store SLAM exploration & dynamic obstacle telemetry
    if (data.slam_map) {
      state.slamMap = Object.assign({}, state.slamMap || {}, data.slam_map);
      if (data.slam_map.dynamic_obstacles) {
        state.activeDynamicObstacles = data.slam_map.dynamic_obstacles;
      }
    }
    if (data.slam_progress) {
      state.slamProgress = data.slam_progress;
    }

    // 2. Fleet Telemetry Update (Deduplicated strictly by canonical robot identifier)
    const fleetList = data.robots || [];
    let activeRob = null;
    fleetList.forEach((r) => {
      const key = r.id || r.robot_id || r.name;
      state.robots[key] = r;
      if (key === state.activeRobotId || r.name === state.activeRobotId || r.name === "Arogya_Delivery") {
        if (!activeRob || key === state.activeRobotId || r.name === state.activeRobotId) {
          activeRob = r;
        }
      }
    });

    if (!activeRob && fleetList.length > 0) {
      activeRob = fleetList[0];
    }

    // 3. Simulation Status Strip & Telemetry Grid (Section 41 & 42)
    if (activeRob) {
      const actNameEl = document.getElementById("sim-active-robot-name");
      const misTypeEl = document.getElementById("sim-mission-type");
      const misDestEl = document.getElementById("sim-mission-destination");
      const robStateEl = document.getElementById("sim-robot-state");

      if (actNameEl) actNameEl.textContent = `${activeRob.name || activeRob.id} (${activeRob.id})`;
      if (misTypeEl) misTypeEl.textContent = activeRob.task || "Standby / Available";
      if (misDestEl) misDestEl.textContent = activeRob.destination || "Home Station (CHG-01)";
      if (robStateEl) robStateEl.textContent = activeRob.status || "IDLE";

      // Realtime telemetry cells (Section 42: Show N/A if null/undefined)
      const mPose = document.getElementById("metric-pose");
      const mYaw = document.getElementById("metric-yaw");
      const mSpeed = document.getElementById("metric-speed");
      const mBattery = document.getElementById("metric-battery");
      const mLidar = document.getElementById("metric-lidar");
      const mSensors = document.getElementById("metric-sensors");

      if (mPose) {
        const px = activeRob.x !== null && activeRob.x !== undefined ? activeRob.x : activeRob.current_x;
        const py = activeRob.y !== null && activeRob.y !== undefined ? activeRob.y : activeRob.current_y;
        if (px !== null && px !== undefined && py !== null && py !== undefined) {
          mPose.textContent = `X:${Number(px).toFixed(2)}, Y:${Number(py).toFixed(2)}`;
        } else {
          mPose.textContent = "N/A";
        }
      }

      if (mYaw) {
        if (activeRob.yaw !== null && activeRob.yaw !== undefined) {
          const deg = (Number(activeRob.yaw) * 180 / Math.PI) % 360;
          mYaw.textContent = `${deg.toFixed(1)}° (${Number(activeRob.yaw).toFixed(2)} rad)`;
        } else {
          mYaw.textContent = "N/A";
        }
      }

      if (mSpeed) {
        if (activeRob.speed !== null && activeRob.speed !== undefined) {
          mSpeed.textContent = `${Number(activeRob.speed).toFixed(2)} m/s`;
        } else {
          mSpeed.textContent = "N/A";
        }
      }

      if (mBattery) {
        if (activeRob.battery !== null && activeRob.battery !== undefined) {
          mBattery.textContent = `${Number(activeRob.battery).toFixed(1)}%`;
        } else {
          mBattery.textContent = "N/A";
        }
      }

      if (mLidar) {
        const closest = data.lidar_scan ? data.lidar_scan.closest_dist : null;
        if (closest !== null && closest !== undefined && closest < 50.0) {
          mLidar.textContent = `${Number(closest).toFixed(2)} m`;
        } else if (closest !== null && closest !== undefined) {
          mLidar.textContent = "> 12.0 m (Clear)";
        } else {
          mLidar.textContent = "N/A";
        }
      }

      if (mSensors) {
        mSensors.textContent = isRunning ? "ONLINE (10Hz)" : "OFFLINE";
      }
    }

    // Save LiDAR hit returns for 2D Map overlay
    if (data.lidar_scan) {
      state.lastLidarScan = data.lidar_scan;
    }

    // 4. Mission Events List
    if (data.recent_logs && Array.isArray(data.recent_logs)) {
      const listEl = document.getElementById("mission-events-list");
      if (listEl) {
        listEl.innerHTML = data.recent_logs.map((log) => {
          let cls = "info";
          const lvl = (log.level || "").toUpperCase();
          if (lvl === "ERROR" || lvl === "EMERGENCY") cls = "alert";
          else if (lvl === "MISSION" || log.source === "MISSION") cls = "mission";
          else if (lvl === "SUCCESS") cls = "success";
          return `<div class="event-row ${cls}"><span class="time">${log.timestamp || ""}</span> [${log.source || "SIM"}] ${escapeHtml(log.message || "")}</div>`;
        }).join("");
        listEl.scrollTop = listEl.scrollHeight;
      }
    }

    // 5. Real-Time Hardware & Subsystem Topbar Badges (Phase 7)
    const diagEngine = document.getElementById("top-diag-engine");
    const diagFps = document.getElementById("top-diag-fps");
    const diagGpu = document.getElementById("top-diag-gpu");
    const diagCpu = document.getElementById("top-diag-cpu");
    const diagRos2 = document.getElementById("top-diag-ros2");
    const diagSlam = document.getElementById("top-diag-slam");
    const diagFleet = document.getElementById("top-diag-fleet");

    const curFps = (data.fps !== undefined && data.fps !== null) ? Number(data.fps).toFixed(1) : (isRunning ? "30.0" : "0.0");
    const gpuPct = (data.gpu_util_pct !== undefined && data.gpu_util_pct !== null) ? Number(data.gpu_util_pct).toFixed(0) : "0";
    const gpuVram = (data.gpu_vram_used_mb !== undefined && data.gpu_vram_used_mb !== null) ? (Number(data.gpu_vram_used_mb) / 1024).toFixed(1) : "0.0";
    const cpuPct = (data.cpu_util_pct !== undefined && data.cpu_util_pct !== null) ? Number(data.cpu_util_pct).toFixed(0) : "0";
    const ramGb = (data.ram_used_mb !== undefined && data.ram_used_mb !== null) ? (Number(data.ram_used_mb) / 1024).toFixed(1) : "0.0";

    if (diagEngine) {
      diagEngine.textContent = isRunning ? "ISAAC SIM 5.1 ONLINE" : "SIMULATION OFFLINE";
      diagEngine.style.background = isRunning ? "rgba(16, 185, 129, 0.15)" : "rgba(100, 116, 139, 0.15)";
      diagEngine.style.color = isRunning ? "#10b981" : "#94a3b8";
    }
    if (diagFps) {
      diagFps.textContent = `${curFps} FPS`;
      diagFps.style.color = Number(curFps) >= 20 ? "#10b981" : Number(curFps) >= 10 ? "#f59e0b" : "#ef4444";
    }
    if (diagGpu) diagGpu.textContent = `GPU: ${gpuPct}% (${gpuVram}GB)`;
    if (diagCpu) diagCpu.textContent = `CPU: ${cpuPct}% (${ramGb}GB)`;
    if (diagRos2) {
      const ros2Ok = data.ros2_ok !== undefined ? data.ros2_ok : isRunning;
      diagRos2.textContent = `ROS2: ${ros2Ok ? 'CONNECTED' : 'OFFLINE'}`;
      diagRos2.style.color = ros2Ok ? "#10b981" : "#94a3b8";
    }
    if (diagSlam) {
      const slamOk = isRunning && (data.slam_active !== undefined ? data.slam_active : state.isExploring);
      diagSlam.textContent = `SLAM: ${slamOk ? 'ACTIVE' : 'OFFLINE'}`;
      diagSlam.style.color = slamOk ? "#00e5ff" : "#94a3b8";
    }
    if (diagFleet) {
      const fCount = isRunning ? (data.robot_fleet_count || Object.keys(state.robots).length || 4) : 0;
      diagFleet.textContent = `FLEET: ${fCount}/4`;
      diagFleet.style.color = fCount > 0 ? "#10b981" : "#94a3b8";
    }

    // Update System Health View Hardware Cards if rendered
    const hwFps = document.getElementById("health-hw-fps");
    const hwGpuUtil = document.getElementById("health-hw-gpu-util");
    const hwGpuVram = document.getElementById("health-hw-gpu-vram");
    const hwCpuUtil = document.getElementById("health-hw-cpu-util");
    const hwRam = document.getElementById("health-hw-ram");

    if (hwFps) hwFps.textContent = curFps;
    if (hwGpuUtil) hwGpuUtil.textContent = `${gpuPct}%`;
    if (hwGpuVram) hwGpuVram.textContent = `${gpuVram} GB`;
    if (hwCpuUtil) hwCpuUtil.textContent = `${cpuPct}%`;
    if (hwRam) hwRam.textContent = `${ramGb} GB`;

    updateExplorationHUD(data.diagnostics);
    if (state.currentView === "robots") {
      renderFleetOperationsConsole();
    }
  }

  // ── 11. 2D INTERACTIVE CANVAS VIEWPORT (ISAAC SIM SYNCHRONIZATION) ────────
  let animFrameId = null;

  function setupCanvas() {
    window.addEventListener("resize", resizeCanvases);
    resizeCanvases();
    startCanvasLoop();
  }

  function resizeCanvases() {
    const canvases = [
      document.getElementById("hospital-canvas"),
      document.getElementById("hospital-map-canvas"),
      document.getElementById("hospital-full-map-canvas"),
      document.getElementById("canvas-map-reference"),
      document.getElementById("canvas-map-slam"),
      document.getElementById("dashboard-mini-radar-canvas"),
      document.getElementById("sim-radar-canvas"),
    ];
    canvases.forEach((canvas) => {
      if (canvas && canvas.parentElement) {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight - (canvas.id.includes("full") || canvas.id.includes("canvas-map") || canvas.id.includes("radar") ? 0 : 48);
      }
    });
  }

  function startCanvasLoop() {
    function loop() {
      // 1. Simulation Viewport canvas (full composite view)
      drawCanvas("hospital-canvas", true, "full");
      drawCanvas("sim-radar-canvas", true, "full");

      // 2. Hospital Map tab preview canvas (reference floor plan)
      drawCanvas("hospital-map-canvas", false, "reference");
      drawCanvas("dashboard-mini-radar-canvas", false, "reference");

      // 3. Side-by-Side Map Workspace & Overview Map View
      drawCanvas("canvas-map-reference", false, "reference");
      drawCanvas("canvas-map-slam", false, state.mapViewMode === "overlay" ? "overlay" : "slam");
      drawCanvas("hospital-full-map-canvas", false, state.mapViewMode);

      animFrameId = requestAnimationFrame(loop);
    }
    loop();
  }

  function drawCanvas(canvasId, isSimViewport, mode = "full") {
    const canvas = document.getElementById(canvasId);
    if (!canvas || canvas.width === 0 || canvas.height === 0) return;
    const ctx = canvas.getContext("2d");

    // Clear background
    ctx.fillStyle = "#080d1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    let pz = mapPanZoom.default;
    if (canvasId === "canvas-map-reference") pz = mapPanZoom.reference;
    else if (canvasId === "canvas-map-slam") pz = mapPanZoom.slam;

    // Coordinate transformation with independent pan & zoom
    let baseZoom = Math.min(canvas.width / 95, canvas.height / 70);
    let zoom = baseZoom * (pz.zoom || 1.0);
    let offsetX = canvas.width / 2 + (pz.panX || 0);
    let offsetY = canvas.height / 2 + (pz.panY || 0);

    // Camera Mode Center Offset for simulation viewport
    if (isSimViewport && state.cameraMode === "FOLLOW_ROBOT") {
      const rob = state.robots[state.activeRobotId] || state.robots["Arogya_Delivery"] || Object.values(state.robots)[0];
      if (rob && (rob.x !== undefined || rob.current_x !== undefined)) {
        const rx = rob.x !== undefined ? rob.x : rob.current_x;
        const ry = rob.y !== undefined ? rob.y : rob.current_y;
        zoom = zoom * 1.5;
        offsetX = canvas.width / 2 - (rx * zoom);
        offsetY = canvas.height / 2 + (ry * zoom);
      }
    } else if (isSimViewport && state.cameraMode === "FOLLOW_TASK") {
      zoom = zoom * 1.3;
      offsetX = canvas.width / 2 - (-36.5 * zoom);
      offsetY = canvas.height / 2 + (11.0 * zoom);
    }

    function worldToScreen(wx, wy) {
      return {
        x: offsetX + wx * zoom,
        y: offsetY - wy * zoom,
      };
    }

    // Execute requested rendering mode (Phases 3, 6 & 7)
    if (mode === "reference") {
      renderReferenceMap(ctx, zoom, worldToScreen);
      renderRobotsAndPaths(ctx, zoom, worldToScreen, isSimViewport, true);
    } else if (mode === "slam") {
      renderRobotSlamMap(ctx, zoom, worldToScreen);
      renderRobotsAndPaths(ctx, zoom, worldToScreen, isSimViewport, false);
    } else if (mode === "overlay") {
      renderReferenceMap(ctx, zoom, worldToScreen);
      ctx.save();
      ctx.globalAlpha = state.overlayOpacity !== undefined ? state.overlayOpacity : 0.5;
      renderRobotSlamMap(ctx, zoom, worldToScreen);
      ctx.restore();
      renderRobotsAndPaths(ctx, zoom, worldToScreen, isSimViewport, false);
    } else {
      renderReferenceMap(ctx, zoom, worldToScreen);
      renderRobotSlamMap(ctx, zoom, worldToScreen);
      renderRobotsAndPaths(ctx, zoom, worldToScreen, isSimViewport, false);
    }
  }

  // ── RENDER COMPONENT: ORIGINAL REFERENCE MAP (Hospital CAD Floor Plan) ──
  function renderReferenceMap(ctx, zoom, worldToScreen) {
    const showGrid = document.getElementById("layer-ref-grid") ? document.getElementById("layer-ref-grid").checked : true;
    const showRooms = document.getElementById("layer-ref-rooms") ? document.getElementById("layer-ref-rooms").checked : true;
    const showWalls = document.getElementById("layer-ref-walls") ? document.getElementById("layer-ref-walls").checked : true;

    // 1. Architectural CAD Grid
    if (showGrid) {
      ctx.strokeStyle = "rgba(255, 255, 255, 0.035)";
      ctx.lineWidth = 1;
      for (let x = -45; x <= 45; x += 5) {
        const p1 = worldToScreen(x, -32);
        const p2 = worldToScreen(x, 32);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
      for (let y = -30; y <= 30; y += 5) {
        const p1 = worldToScreen(-45, y);
        const p2 = worldToScreen(45, y);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
    }

    // 2. Corridors & Main Arteries (Hospital CAD Circulation)
    if (showRooms) {
    ctx.strokeStyle = "rgba(6, 182, 212, 0.12)";
    ctx.lineWidth = 26 * (zoom / 10);
    ctx.lineCap = "round";
    ctx.beginPath();
    let cStart = worldToScreen(-40, 0);
    let cEnd = worldToScreen(40, 0);
    ctx.moveTo(cStart.x, cStart.y);
    ctx.lineTo(cEnd.x, cEnd.y);
    let v1 = worldToScreen(0, -25);
    let v2 = worldToScreen(0, 25);
    ctx.moveTo(v1.x, v1.y);
    ctx.lineTo(v2.x, v2.y);
    ctx.stroke();

    // 3. Hospital Rooms & Clinical Units
    state.rooms.forEach((r) => {
      const center = worldToScreen(r.x, r.y);
      const rw = r.w * zoom;
      const rh = r.h * zoom;
      const rx = center.x - rw / 2;
      const ry = center.y - rh / 2;

      ctx.fillStyle = r.color;
      ctx.fillRect(rx, ry, rw, rh);

      ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(rx, ry, rw, rh);

      ctx.fillStyle = "#ffffff";
      ctx.font = `600 ${Math.max(10, Math.floor(zoom * 1.05))}px 'Inter', sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(r.name, center.x, center.y - rh / 4);

      ctx.fillStyle = "rgba(255, 255, 255, 0.65)";
      ctx.font = `500 ${Math.max(9, Math.floor(zoom * 0.85))}px 'Inter', sans-serif`;
      ctx.fillText(r.code, center.x, center.y);

      if (r.beds && zoom > 5.5) {
        r.beds.forEach((bed, idx) => {
          const bx = rx + (idx + 1) * (rw / (r.beds.length + 1));
          const by = center.y + rh / 4;
          ctx.fillStyle = bed === "ICU Bed 3" ? "#f43f5e" : "rgba(255, 255, 255, 0.2)";
          ctx.fillRect(bx - 6, by - 4, 12, 8);
          if (zoom > 8) {
            ctx.fillStyle = "rgba(255, 255, 255, 0.75)";
            ctx.font = `8px 'Inter', sans-serif`;
            ctx.fillText(bed, bx, by + 10);
          }
        });
      }
    });
    }

    // 4. Perimeter Structural Boundary Walls
    if (showWalls) {
      const nw = worldToScreen(-44, 31);
      const ne = worldToScreen(44, 31);
      const se = worldToScreen(44, -31);
      const sw = worldToScreen(-44, -31);
      ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(nw.x, nw.y);
      ctx.lineTo(ne.x, ne.y);
      ctx.lineTo(se.x, se.y);
      ctx.lineTo(sw.x, sw.y);
      ctx.closePath();
      ctx.stroke();
    }
  }

  // ── RENDER COMPONENT: ROBOT-GENERATED MAP (LiDAR SLAM Occupancy Grid) ──
  function renderRobotSlamMap(ctx, zoom, worldToScreen) {
    if (!state.slamMap || state.slamMap.status === "OFFLINE" || (!state.simRunning && (!state.slamMap.discovered_walls || state.slamMap.discovered_walls.length === 0))) {
      ctx.save();
      const cw = ctx.canvas.width;
      const ch = ctx.canvas.height;
      ctx.fillStyle = "rgba(100, 116, 139, 0.5)";
      ctx.font = "600 13px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillText("[ NVIDIA ISAAC SIM OFFLINE — LiDAR SLAM Sensor Inactive ]", cw / 2, ch / 2 - 10);
      ctx.font = "400 11px 'Inter', sans-serif";
      ctx.fillStyle = "rgba(148, 163, 184, 0.6)";
      ctx.fillText("Click [RUN SIMULATION] to start physical robot and generate SLAM occupancy grid", cw / 2, ch / 2 + 14);
      ctx.restore();
      return;
    }

    const showSlamGrid = document.getElementById("layer-slam-grid") ? document.getElementById("layer-slam-grid").checked : true;
    const showSlamWalls = document.getElementById("layer-slam-walls") ? document.getElementById("layer-slam-walls").checked : true;
    const showFrontiers = document.getElementById("layer-slam-frontiers") ? document.getElementById("layer-slam-frontiers").checked : true;
    const showHazards = document.getElementById("layer-slam-hazards") ? document.getElementById("layer-slam-hazards").checked : true;
    const showSemantics = document.getElementById("layer-slam-semantics") ? document.getElementById("layer-slam-semantics").checked : true;

    // 1. Explored Free Space Layer (Cyan tint)
    if (showSlamGrid && Array.isArray(state.slamMap.discovered_free_space) && state.slamMap.discovered_free_space.length > 0) {
      ctx.fillStyle = "rgba(14, 165, 233, 0.12)";
      state.slamMap.discovered_free_space.forEach((pt) => {
        const sp = worldToScreen(pt[0], pt[1]);
        ctx.fillRect(sp.x - 3, sp.y - 3, 6, 6);
      });
    }

    // 2. Discovered Occupied Structure (LiDAR Wall Hits)
    if (showSlamWalls) {
      const wallPts = state.slamMap.discovered_walls || state.slamMap.discovered_sample || [];
      if (Array.isArray(wallPts)) {
        ctx.fillStyle = "#00e5ff";
        ctx.shadowColor = "#00e5ff";
        ctx.shadowBlur = 4;
        wallPts.forEach((pt) => {
          const sp = worldToScreen(pt[0], pt[1]);
          ctx.fillRect(sp.x - 2, sp.y - 2, 4, 4);
        });
        ctx.shadowBlur = 0;
      }
    }

    // 3. Autonomous Exploration Frontiers (Pulsing Emerald Targets)
    if (showFrontiers && Array.isArray(state.slamMap.frontiers)) {
      const fPulse = (Math.sin(Date.now() / 200) + 1) * 3;
      ctx.fillStyle = "rgba(16, 185, 129, 0.35)";
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 1.5;
      state.slamMap.frontiers.forEach((f) => {
        const sp = worldToScreen(f.x, f.y);
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 6 + fPulse, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#a7f3d0";
        ctx.font = `600 9px 'Inter', sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(`F-${f.size || 'C'}`, sp.x, sp.y - 8);
      });
    }

    // 4. Dynamic Obstacles & Temporary Hazard Rings (Phases 8 & 9)
    if (showHazards) {
      const dynObsList = state.activeDynamicObstacles || [];
      dynObsList.forEach((obs) => {
        const opos = obs.pos || [0, 0];
        const sp = worldToScreen(opos[0], opos[1]);
        const rad = (obs.radius || 0.85) * zoom;
        const oPulse = (Math.sin(Date.now() / 150) + 1) * 3;

        ctx.save();
        // Hazard perimeter ring
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, rad + oPulse, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(239, 68, 68, 0.25)";
        ctx.fill();
        ctx.strokeStyle = "#f43f5e";
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();

        // Hazard core
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#ef4444";
        ctx.fill();

        // Tag
        ctx.fillStyle = "#fca5a5";
        ctx.font = `600 10px 'Inter', sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(obs.id || "DYNAMIC HAZARD", sp.x, sp.y - rad - 5);
      });
    }

    // 5. Semantic Hospital Features (Discovered Corridors, Room Portals, Intersections)
    if (showSemantics && state.showSemantics && state.authoritativeKnowledgeMap && state.authoritativeKnowledgeMap.semantic_features) {
      const sem = state.authoritativeKnowledgeMap.semantic_features;
      // Discovered Corridors
      if (Array.isArray(sem.corridors)) {
        sem.corridors.forEach((corr) => {
          const sp = worldToScreen(corr.x || 0, corr.y || 0);
          ctx.save();
          ctx.strokeStyle = "rgba(168, 85, 247, 0.4)";
          ctx.lineWidth = 1.5;
          ctx.strokeRect(sp.x - 22, sp.y - 12, 44, 24);
          ctx.fillStyle = "rgba(192, 132, 252, 0.9)";
          ctx.font = `600 9px 'Inter', sans-serif`;
          ctx.textAlign = "center";
          ctx.fillText(`CORRIDOR (${Math.round((corr.confidence || 0.85) * 100)}%)`, sp.x, sp.y - 14);
          ctx.restore();
        });
      }
      // Room Portals / Entrances
      if (Array.isArray(sem.room_portals)) {
        sem.room_portals.forEach((p) => {
          const sp = worldToScreen(p.x, p.y);
          ctx.save();
          ctx.beginPath();
          ctx.arc(sp.x, sp.y, 5, 0, Math.PI * 2);
          ctx.fillStyle = "#f59e0b";
          ctx.fill();
          ctx.strokeStyle = "#fbbf24";
          ctx.lineWidth = 1.5;
          ctx.stroke();
          ctx.fillStyle = "#fde68a";
          ctx.font = `600 8px 'Inter', sans-serif`;
          ctx.textAlign = "center";
          ctx.fillText("DOORWAY", sp.x, sp.y + 12);
          ctx.restore();
        });
      }
    }
  }

  // ── RENDER COMPONENT: AMRS, PATHS & SENSOR FOOTPRINTS ──
  function renderRobotsAndPaths(ctx, zoom, worldToScreen, isSimViewport) {
    // 1. Draw Active Mission Waypoint & Path Trace
    const activeRob = state.robots["Arogya_Delivery"] || state.robots["Aarogya_Delivery"] || state.robots["ROBOT-01"] || Object.values(state.robots).find(r => r.status === "NAVIGATING");
    if (activeRob && activeRob.status === "NAVIGATING") {
      const rx = activeRob.x !== undefined ? activeRob.x : (activeRob.current_x || 0);
      const ry = activeRob.y !== undefined ? activeRob.y : (activeRob.current_y || 0);
      const rPos = worldToScreen(rx, ry);

      let tx = -36.5;
      let ty = 11.0;
      if (activeRob.destination === "PHM-01") {
        tx = 14.0; ty = 23.2;
      } else if (activeRob.destination === "CHG-01") {
        tx = 37.25; ty = 26.0;
      } else if (activeRob.destination === "EMR-01") {
        tx = -35.0; ty = -26.0;
      }
      const gPos = worldToScreen(tx, ty);

      // Glowing dashed waypoint path
      ctx.save();
      ctx.strokeStyle = "#06b6d4";
      ctx.lineWidth = 2.5;
      ctx.setLineDash([8, 6]);
      ctx.lineDashOffset = -Date.now() / 40;
      ctx.beginPath();
      ctx.moveTo(rPos.x, rPos.y);
      ctx.lineTo(gPos.x, gPos.y);
      ctx.stroke();
      ctx.restore();

      // Pulsing Goal Marker
      const pulse = (Math.sin(Date.now() / 200) + 1) * 6;
      ctx.beginPath();
      ctx.arc(gPos.x, gPos.y, 10 + pulse, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(244, 63, 94, 0.3)";
      ctx.fill();
      ctx.strokeStyle = "#f43f5e";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 2. Draw AMRs (Fleet Entities)
    const seen = new Set();
    const robotList = Object.values(state.robots).filter((r) => {
      const key = r.id || r.name;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    robotList.forEach((rob) => {
      const rx = rob.x !== undefined && rob.x !== null ? rob.x : rob.current_x;
      const ry = rob.y !== undefined && rob.y !== null ? rob.y : rob.current_y;
      if (rx === undefined || rx === null || ry === undefined || ry === null) return;
      const pos = worldToScreen(rx, ry);
      const isSelected = rob.name === state.activeRobotId || rob.id === state.activeRobotId || (rob.name && rob.name.toLowerCase() === (state.activeRobotId || "").toLowerCase());

      ctx.save();
      ctx.translate(pos.x, pos.y);
      ctx.rotate(-(rob.yaw || 0));

      const rRadius = Math.max(10, zoom * 0.9);

      // Pulsing halo for moving/emergency AMRs
      if (rob.status === "NAVIGATING" || rob.role === "EMERGENCY") {
        const pulse = (Math.sin(Date.now() / 250) + 1) * 4;
        ctx.beginPath();
        ctx.arc(0, 0, rRadius + pulse + 4, 0, Math.PI * 2);
        ctx.fillStyle = rob.role === "EMERGENCY" ? "rgba(239, 68, 68, 0.3)" : "rgba(6, 182, 212, 0.25)";
        ctx.fill();
      }

      // Robot Chassis
      ctx.beginPath();
      ctx.arc(0, 0, rRadius, 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? "#06b6d4" : "#1e293b";
      ctx.fill();
      ctx.strokeStyle = isSelected ? "#38bdf8" : "#64748b";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Heading indicator arrow
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(rRadius + 5, 0);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.restore();

      // AMR Name Label
      const label = rob.name || rob.id || "AMR";
      ctx.fillStyle = "#38bdf8";
      ctx.font = `600 ${Math.max(10, Math.floor(zoom * 0.9))}px 'Inter', sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(label, pos.x, pos.y - rRadius - 6);

      // Real LiDAR Scan points for active robot
      if (isSelected && state.lastLidarScan && Array.isArray(state.lastLidarScan.points)) {
        ctx.fillStyle = "rgba(245, 158, 11, 0.85)";
        state.lastLidarScan.points.forEach((pt) => {
          if (pt && pt.range !== undefined && pt.range < 11.5) {
            const hx = rx + pt.range * Math.cos((rob.yaw || 0) + (pt.angle_deg || 0) * Math.PI / 180);
            const hy = ry + pt.range * Math.sin((rob.yaw || 0) + (pt.angle_deg || 0) * Math.PI / 180);
            const sp = worldToScreen(hx, hy);
            ctx.beginPath();
            ctx.arc(sp.x, sp.y, 2, 0, Math.PI * 2);
            ctx.fill();
          }
        });
      }
    });
  }

  function updateProgressionChips(status) {
    const stages = [
      { id: "chip-backend", match: ["BACKEND_ONLINE", "LAUNCHING", "WINSTA0", "PYTHON", "GUI", "STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-mission", match: ["BACKEND_ONLINE", "LAUNCHING", "WINSTA0", "PYTHON", "GUI", "STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-winsta", match: ["WINSTA0", "PYTHON", "GUI", "STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-kit", match: ["PYTHON", "GUI", "STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-gui", match: ["GUI", "STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-stage", match: ["STAGE", "TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-timeline", match: ["TIMELINE", "ROS2", "ROBOTS", "READY"] },
      { id: "chip-ros2", match: ["ROS2", "ROBOTS", "READY"] },
      { id: "chip-amrs", match: ["ROBOTS", "READY"] },
      { id: "chip-ready", match: ["READY"] },
    ];

    const stUpper = (status || "").toUpperCase();
    stages.forEach((s) => {
      const el = document.getElementById(s.id);
      if (!el) return;
      const isDone = s.match.some((m) => stUpper.includes(m));
      el.className = "stage-chip" + (isDone ? " completed" : "");
    });
  }

  // ── 12. UTILITIES ────────────────────────────────────────────────────────
  function showToast(message) {
    const toast = document.createElement("div");
    toast.style.position = "fixed";
    toast.style.bottom = "24px";
    toast.style.right = "24px";
    toast.style.background = "#0f172a";
    toast.style.border = "1px solid var(--accent-cyan)";
    toast.style.boxShadow = "var(--glow-cyan)";
    toast.style.padding = "12px 20px";
    toast.style.borderRadius = "var(--radius-md)";
    toast.style.color = "#fff";
    toast.style.fontSize = "13px";
    toast.style.fontWeight = "600";
    toast.style.zIndex = "9999";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.5s ease";
      setTimeout(() => toast.remove(), 500);
    }, 3200);
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  }

  // Public Interface
  return {
    init,
    login,
    quickLogin,
    logout,
    switchView,
    toggleSimulation,
    setCameraMode,
    selectCameraTarget,
    quickDispatchToPatient,
    discontinueRx,
    quickTriggerCodeBlue,
    executeVoiceCommand,
    selectFleetRobot,
    sendTeleopCommand,
    openMissionReplay,
    renderFleetOperationsConsole,
    trackRobotCamera: (id) => {
      setCameraMode("FOLLOW_ROBOT", id);
      switchView("simulation");
    },
    openDispatchFor: (id) => {
      state.selectedFleetRobotId = id;
      showCreateTaskModal();
    },
    closeModal,
  };
})();

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  AarogyaApp.init();
});

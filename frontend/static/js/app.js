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
    activeRobotId: "Aarogya_Delivery",
    robots: {},
    tasks: [],
    patients: [],
    prescriptions: [],
    medicines: [],
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

    // Periodic poll for DB updates
    setInterval(refreshAllData, 4000);
  }

  // ── 3. AUTHENTICATION & RBAC ─────────────────────────────────────────────
  async function login(username, password) {
    try {
      const data = await apiRequest("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      state.token = data.access_token;
      state.user = {
        id: data.user_id,
        role: data.role,
        full_name: data.full_name,
        username: data.username,
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

  // ── 4. NAVIGATION & VIEWS ────────────────────────────────────────────────
  function setupNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const view = item.dataset.view;
        switchView(view);
      });
    });

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

    // Clear Terminal Stream
    const btnClearTerm = document.getElementById("btn-clear-terminal");
    if (btnClearTerm) {
      btnClearTerm.addEventListener("click", () => {
        const term = document.getElementById("terminal-stream");
        if (term) term.innerHTML = `<div class="terminal-line INFO">[SYSTEM] Terminal logs reset.</div>`;
      });
    }
  }

  function switchView(viewName) {
    state.currentView = viewName;

    // Update nav classes
    document.querySelectorAll(".nav-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.view === viewName);
    });

    // Update title
    const titleEl = document.getElementById("current-view-title");
    const titles = {
      dashboard: "Executive Operational Dashboard",
      simulation: "NVIDIA Isaac Sim Synchronization & Viewport",
      map: "Hospital Facility Interactive Spatial Map",
      patients: "Admitted Inpatients & Clinical Registry",
      prescriptions: "Prescriptions & Medication Schedules",
      tasks: "Autonomous Robot Mission Dispatch",
      robots: "Autonomous Mobile Robot (AMR) Fleet",
      medicines: "Central Pharmacy Formulary & Stock",
      staff: "Physician & Nursing Staff",
      emergency: "Emergency Center & Code Blue Control",
      logs: "System Audit Trail & Compliance",
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
    ];

    views.forEach((v) => {
      const el = document.getElementById(v);
      if (el) {
        el.style.display = v === `view-${viewName}` ? (v === "view-simulation" || v === "view-map" ? "block" : "flex") : "none";
      }
    });

    // Trigger canvas redraw if opening simulation or map
    if (viewName === "simulation" || viewName === "map") {
      setTimeout(resizeCanvases, 50);
    }
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
      const [patients, rxList, tasks, robots, medicines] = await Promise.all([
        apiRequest("/api/patients").catch(() => []),
        apiRequest("/api/prescriptions").catch(() => []),
        apiRequest("/api/tasks").catch(() => []),
        apiRequest("/api/robots").catch(() => []),
        apiRequest("/api/medicines").catch(() => []),
      ]);

      state.patients = patients;
      state.prescriptions = rxList;
      state.tasks = tasks;
      state.medicines = medicines;

      // Update robot state map
      robots.forEach((r) => {
        state.robots[r.robot_id] = r;
      });

      renderDashboardStats();
      renderTasksTable();
      renderPatientsTable();
      renderPrescriptionsTable();
      renderRobotsView();
      renderMedicinesTable();
    } catch (e) {
      console.warn("Background refresh error:", e);
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
              <td><strong>#${t.id}</strong></td>
              <td>${t.patient_name || "General Delivery"} <small style="color:var(--text-muted)">(${t.target_room || "N/A"})</small></td>
              <td>${t.medicine_name || "Medical Supply"}</td>
              <td><span class="badge badge-${t.priority.toLowerCase()}">${t.priority}</span></td>
              <td>${t.robot_id ? `<span style="color:var(--accent-cyan)">🤖 ${t.robot_id}</span>` : `<span style="color:var(--text-dim)">Unassigned</span>`}</td>
              <td><span class="badge badge-${t.status.toLowerCase()}">${t.status}</span></td>
            </tr>`
          )
          .join("");
      }
    }

    // Render Fleet status on Dashboard
    const fleetSummary = document.getElementById("dashboard-fleet-summary");
    if (fleetSummary) {
      const robotList = Object.values(state.robots);
      fleetSummary.innerHTML = (robotList.length > 0 ? robotList : [
        { robot_id: "Aarogya_Delivery", role: "DELIVERY", status: "IDLE", battery_level: 98.5 },
        { robot_id: "Nandi_Guide", role: "RECEPTION", status: "IDLE", battery_level: 100.0 },
        { robot_id: "Garuda_Emergency", role: "EMERGENCY", status: "IDLE", battery_level: 100.0 },
        { robot_id: "Dhanvantari_General", role: "COORDINATOR", status: "IDLE", battery_level: 95.0 },
      ])
        .map(
          (r) => `
          <div style="background:rgba(255,255,255,0.02); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-subtle); display:flex; align-items:center; justify-content:space-between;">
            <div>
              <div style="font-weight:600; font-size:13px; color:var(--accent-cyan);">${r.robot_id}</div>
              <div style="font-size:11px; color:var(--text-muted);">${r.role} AMR</div>
            </div>
            <div style="text-align:right;">
              <span class="badge badge-${r.status.toLowerCase()}">${r.status}</span>
              <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">🔋 ${r.battery_level ? r.battery_level.toFixed(0) : 100}%</div>
            </div>
          </div>`
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
        <td><strong>#${t.id}</strong></td>
        <td><span class="badge badge-idle">${t.task_type}</span></td>
        <td>${t.patient_name || "N/A"} <small style="color:var(--accent-cyan)">(${t.target_room || "N/A"})</small></td>
        <td>${t.medicine_name || "General Supplies"}</td>
        <td><span class="badge badge-${t.priority.toLowerCase()}">${t.priority}</span></td>
        <td>${t.robot_id ? `🤖 ${t.robot_id}` : `Auto-Queued`}</td>
        <td><span class="badge badge-${t.status.toLowerCase()}">${t.status}</span></td>
        <td>
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="progress-bar-container" style="width:80px;">
              <div class="progress-bar-fill" style="width:${(t.progress_pct || 0) * 100}%"></div>
            </div>
            <span style="font-size:11px;">${Math.round((t.progress_pct || 0) * 100)}%</span>
          </div>
        </td>
        <td><small style="color:var(--text-dim)">${new Date(t.created_at).toLocaleTimeString()}</small></td>
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
        (r) => `
      <div class="metric-card" style="border-left: 4px solid var(--accent-cyan);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3 style="font-size:16px; font-family:'Outfit'; color:var(--text-main);">${r.robot_id}</h3>
          <span class="badge badge-${r.status.toLowerCase()}">${r.status}</span>
        </div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;">Operational Role: <strong>${r.role}</strong></div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px; background:rgba(0,0,0,0.2); padding:10px; border-radius:var(--radius-sm);">
          <div>Battery: <strong style="color:var(--accent-emerald);">${r.battery_level ? r.battery_level.toFixed(1) : 100}%</strong></div>
          <div>Payload: <strong>${r.payload_status || "EMPTY"}</strong></div>
          <div>Pos X: <strong>${r.current_x ? r.current_x.toFixed(2) : 0}m</strong></div>
          <div>Pos Y: <strong>${r.current_y ? r.current_y.toFixed(2) : 0}m</strong></div>
        </div>
        <div style="margin-top:10px; display:flex; gap:8px;">
          <button class="btn btn-outline" style="flex:1; font-size:11px; justify-content:center;" onclick="AarogyaApp.selectCameraTarget('${r.robot_id}')">
            Follow Camera
          </button>
        </div>
      </div>`
      )
      .join("");
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
      switchView("simulation");
      await refreshAllData();
    } catch (err) {
      alert("Emergency Alert Error: " + err.message);
    }
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
      } else {
        resultBox.innerHTML = `
          <div style="color:var(--accent-emerald); font-weight:bold;">✅ MISSION DISPATCHED</div>
          <div style="margin-top:4px;">${res.message}</div>
          <div style="font-size:11px; color:var(--accent-cyan); margin-top:4px;">Assigned: ${res.robot_id || "AMR"} | Target: ${res.target || "Facility"}</div>
        `;
        showToast("Voice Mission Created!");
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

    if (!state.simRunning) {
      await apiRequest("/api/simulation/start", { method: "POST" });
      state.simRunning = true;
      btnSim.classList.remove("btn-primary");
      btnSim.classList.add("btn-danger");
      textEl.textContent = "PAUSE SIMULATION";
      iconEl.innerHTML = `<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>`;
      showToast("Isaac Simulation Orchestrator Running (10Hz)");
    } else {
      await apiRequest("/api/simulation/pause", { method: "POST" });
      state.simRunning = false;
      btnSim.classList.add("btn-primary");
      btnSim.classList.remove("btn-danger");
      textEl.textContent = "RUN SIMULATION";
      iconEl.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
      showToast("Isaac Simulation Paused");
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
    // 1. Sync simulation running state
    if (typeof data.simulation_running === "boolean") {
      state.simRunning = data.simulation_running;
      const textEl = document.getElementById("sim-toggle-text");
      const btnSim = document.getElementById("btn-sim-toggle");
      if (textEl && btnSim) {
        textEl.textContent = state.simRunning ? "PAUSE SIMULATION" : "RUN SIMULATION";
        if (state.simRunning) {
          btnSim.classList.remove("btn-primary");
          btnSim.classList.add("btn-danger");
        } else {
          btnSim.classList.add("btn-primary");
          btnSim.classList.remove("btn-danger");
        }
      }
    }

    // 2. Update robot poses & statuses
    if (data.active_robots) {
      for (const [rId, rData] of Object.entries(data.active_robots)) {
        if (!state.robots[rId]) {
          state.robots[rId] = {};
        }
        Object.assign(state.robots[rId], rData);
      }
    }

    // 3. Update active telemetry display
    const activeRob = state.robots[state.activeRobotId] || Object.values(state.robots)[0];
    if (activeRob) {
      const nameEl = document.getElementById("sim-active-robot-name");
      const xEl = document.getElementById("sim-pos-x");
      const yEl = document.getElementById("sim-pos-y");
      const yawEl = document.getElementById("sim-yaw");
      const vEl = document.getElementById("sim-v-lin");
      const battEl = document.getElementById("sim-battery");
      const statusEl = document.getElementById("sim-status");

      if (nameEl) nameEl.textContent = activeRob.robot_id || state.activeRobotId;
      if (xEl) xEl.textContent = (activeRob.current_x || 0).toFixed(2);
      if (yEl) yEl.textContent = (activeRob.current_y || 0).toFixed(2);
      if (yawEl) yawEl.textContent = (activeRob.yaw || 0).toFixed(2);
      if (vEl) vEl.textContent = (activeRob.v_lin || 0).toFixed(2);
      if (battEl) battEl.textContent = `${(activeRob.battery_level || 98).toFixed(0)}%`;
      if (statusEl) statusEl.textContent = activeRob.status || "IDLE";
    }

    // 4. Update task progress bar
    if (data.tasks && data.tasks.length > 0) {
      const activeTask = data.tasks[0];
      const pct = Math.round((activeTask.progress_pct || 0) * 100);
      const pctEl = document.getElementById("sim-task-pct");
      const barEl = document.getElementById("sim-task-progress-bar");
      if (pctEl) pctEl.textContent = `${pct}%`;
      if (barEl) barEl.style.width = `${pct}%`;
    }

    // 5. Append terminal logs
    if (data.terminal_logs && Array.isArray(data.terminal_logs)) {
      const term = document.getElementById("terminal-stream");
      if (term) {
        term.innerHTML = data.terminal_logs
          .slice(-30)
          .map((line) => {
            let cls = "INFO";
            if (line.includes("EMERGENCY") || line.includes("ALERT")) cls = "EMERGENCY";
            else if (line.includes("MISSION") || line.includes("DELIVER")) cls = "MISSION";
            return `<div class="terminal-line ${cls}">${escapeHtml(line)}</div>`;
          })
          .join("");
        term.scrollTop = term.scrollHeight;
      }
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
    const c1 = document.getElementById("hospital-canvas");
    const c2 = document.getElementById("hospital-map-canvas");
    [c1, c2].forEach((canvas) => {
      if (canvas && canvas.parentElement) {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight - (canvas.id === "hospital-canvas" ? 48 : 48);
      }
    });
  }

  function startCanvasLoop() {
    function loop() {
      drawCanvas("hospital-canvas", true);
      drawCanvas("hospital-map-canvas", false);
      animFrameId = requestAnimationFrame(loop);
    }
    loop();
  }

  function drawCanvas(canvasId, isSimViewport) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || canvas.width === 0 || canvas.height === 0) return;
    const ctx = canvas.getContext("2d");

    // Clear background
    ctx.fillStyle = "#080d1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Coordinate transformation
    // Hospital bounds: X: -45 to +45 (span 90), Y: -32 to +32 (span 64)
    let zoom = Math.min(canvas.width / 95, canvas.height / 70);
    let offsetX = canvas.width / 2;
    let offsetY = canvas.height / 2;

    // Camera Mode Center Offset
    if (isSimViewport && state.cameraMode === "FOLLOW_ROBOT") {
      const rob = state.robots[state.activeRobotId] || Object.values(state.robots)[0];
      if (rob && rob.current_x !== undefined) {
        zoom = zoom * 1.5;
        offsetX = canvas.width / 2 - (rob.current_x * zoom);
        offsetY = canvas.height / 2 + (rob.current_y * zoom);
      }
    } else if (isSimViewport && state.cameraMode === "FOLLOW_TASK") {
      // Focus on ICU Bed 3 (Master Target)
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

    // 1. Draw subtle grid
    ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
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

    // 2. Draw Main Hallways & Corridors
    ctx.strokeStyle = "rgba(6, 182, 212, 0.12)";
    ctx.lineWidth = 28 * (zoom / 10);
    ctx.lineCap = "round";
    ctx.beginPath();
    // Spine corridor from X=-40 to +40 at Y=0
    let cStart = worldToScreen(-40, 0);
    let cEnd = worldToScreen(40, 0);
    ctx.moveTo(cStart.x, cStart.y);
    ctx.lineTo(cEnd.x, cEnd.y);
    // Vertical branches
    let v1 = worldToScreen(0, -25);
    let v2 = worldToScreen(0, 25);
    ctx.moveTo(v1.x, v1.y);
    ctx.lineTo(v2.x, v2.y);
    ctx.stroke();

    // 3. Draw Hospital Rooms
    state.rooms.forEach((r) => {
      const center = worldToScreen(r.x, r.y);
      const rw = r.w * zoom;
      const rh = r.h * zoom;
      const rx = center.x - rw / 2;
      const ry = center.y - rh / 2;

      // Fill Room
      ctx.fillStyle = r.color;
      ctx.fillRect(rx, ry, rw, rh);

      // Stroke Room
      ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(rx, ry, rw, rh);

      // Room Title
      ctx.fillStyle = "#ffffff";
      ctx.font = `600 ${Math.max(10, Math.floor(zoom * 1.1))}px 'Inter', sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(r.name, center.x, center.y - rh / 4);

      // Room Code & Beds
      ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
      ctx.font = `500 ${Math.max(9, Math.floor(zoom * 0.85))}px 'Inter', sans-serif`;
      ctx.fillText(r.code, center.x, center.y);

      // Render Beds if present
      if (r.beds) {
        r.beds.forEach((bed, idx) => {
          const bx = rx + (idx + 1) * (rw / (r.beds.length + 1));
          const by = center.y + rh / 4;
          ctx.fillStyle = bed === "ICU Bed 3" ? "#f43f5e" : "rgba(255, 255, 255, 0.2)";
          ctx.fillRect(bx - 8, by - 5, 16, 10);
          ctx.fillStyle = "#fff";
          ctx.font = `9px 'Inter', sans-serif`;
          ctx.fillText(bed, bx, by + 12);
        });
      }
    });

    // 4. Draw Active Mission Waypoint & Path Trace
    const activeRob = state.robots["Aarogya_Delivery"];
    if (activeRob && activeRob.status === "NAVIGATING") {
      const rPos = worldToScreen(activeRob.current_x || 0, activeRob.current_y || 0);
      const gPos = worldToScreen(-36.5, 11.0); // Target ICU Bed 3

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

      // Pulsing Goal Marker at ICU-01
      const pulse = (Math.sin(Date.now() / 200) + 1) * 6;
      ctx.beginPath();
      ctx.arc(gPos.x, gPos.y, 10 + pulse, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(244, 63, 94, 0.3)";
      ctx.fill();
      ctx.strokeStyle = "#f43f5e";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 5. Draw AMRs
    const robotList = Object.values(state.robots);
    robotList.forEach((rob) => {
      if (rob.current_x === undefined) return;
      const pos = worldToScreen(rob.current_x, rob.current_y);
      const isSelected = rob.robot_id === state.activeRobotId;

      ctx.save();
      ctx.translate(pos.x, pos.y);
      ctx.rotate(-(rob.yaw || 0)); // Note canvas rotation direction

      // Robot Base Radius
      const rRadius = Math.max(10, zoom * 0.9);

      // Pulsing halo for moving/emergency robots
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

      // AMR Name & Battery Label
      ctx.fillStyle = "#38bdf8";
      ctx.font = `600 ${Math.max(10, Math.floor(zoom * 0.9))}px 'Inter', sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(rob.robot_id, pos.x, pos.y - rRadius - 6);
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
  };
})();

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  AarogyaApp.init();
});

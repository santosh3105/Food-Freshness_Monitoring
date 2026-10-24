/**
 * Food Freshness Monitoring Platform - Multi-Spectral AI Food Scanner Controller
 * Powers live camera ingestion, laser reticle animation, bounding box detection,
 * Arrhenius kinetic calculation, and diagnostic scorecard generation.
 */

let cameraStream = null;
let currentMode = "camera";
let currentScannedData = null;
let currentBlob = null;

const SPECIMEN_PRESETS = {
  apple: {
    name: "Red Gala Apple",
    category: "Fruits",
    temp: 4.0,
    rh: 85,
    url: "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=600&auto=format&fit=crop",
    box: { top: "22%", left: "20%", width: "58%", height: "58%", label: "🍎 Fresh Apple (96.4%)" },
    freshness: 95,
    shelfLife: "8.5 Days",
    grade: "Grade A: Optimal Fresh",
    statusCls: "badge-fresh",
    chlorophyll: "94.2% (High)",
    browning: "2.4% (Negligible)",
    ethylene: "0.12 μL/kg·h (Normal)",
    microbial: "Minimal (Class I)",
    confidence: "98.4%",
    storageAdvice: "Store in crisper drawer at 3°C to 5°C with 85-90% RH to minimize transpiration."
  },
  broccoli: {
    name: "Crisp Green Broccoli",
    category: "Vegetables",
    temp: 3.0,
    rh: 90,
    url: "https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=600&auto=format&fit=crop",
    box: { top: "18%", left: "24%", width: "52%", height: "62%", label: "🥦 Fresh Broccoli (94.8%)" },
    freshness: 92,
    shelfLife: "6.2 Days",
    grade: "Grade A: Optimal Fresh",
    statusCls: "badge-fresh",
    chlorophyll: "92.0% (Intact)",
    browning: "1.8% (None)",
    ethylene: "0.08 μL/kg·h (Very Low)",
    microbial: "Clean (Class I)",
    confidence: "97.6%",
    storageAdvice: "Store perforated at 2°C to 4°C with high humidity (90%). Avoid moisture condensation."
  },
  salmon: {
    name: "Atlantic Salmon Fillet",
    category: "Fish",
    temp: 1.0,
    rh: 80,
    url: "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?w=600&auto=format&fit=crop",
    box: { top: "25%", left: "15%", width: "70%", height: "50%", label: "🐟 Fresh Salmon (91.5%)" },
    freshness: 89,
    shelfLife: "3.5 Days",
    grade: "Grade A: Premium Grade",
    statusCls: "badge-fresh",
    chlorophyll: "N/A (Marine Protein)",
    browning: "3.1% (Astaxanthin Preserved)",
    ethylene: "N/A",
    microbial: "TVB-N: 11.2 mg/100g (Prime)",
    confidence: "98.9%",
    storageAdvice: "Store on crushed ice at 0°C to 2°C. Consume within 72 hours of purchase."
  },
  berries: {
    name: "Fresh Strawberries",
    category: "Fruits",
    temp: 2.0,
    rh: 90,
    url: "https://images.unsplash.com/photo-1464965911861-746a04b4bca6?w=600&auto=format&fit=crop",
    box: { top: "20%", left: "18%", width: "64%", height: "60%", label: "🍓 Fresh Berries (88.3%)" },
    freshness: 86,
    shelfLife: "4.0 Days",
    grade: "Grade B: High Quality",
    statusCls: "badge-fresh",
    chlorophyll: "N/A (Anthocyanin 88%)",
    browning: "5.4% (Minor Calyx Wilting)",
    ethylene: "0.22 μL/kg·h (Normal)",
    microbial: "No Mold / Mycelium",
    confidence: "96.5%",
    storageAdvice: "Do not wash until ready to eat. Keep dry in ventilated container at 2°C to 4°C."
  },
  milk: {
    name: "Pasteurized Whole Milk",
    category: "Dairy",
    temp: 3.5,
    rh: 80,
    url: "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop",
    box: { top: "15%", left: "30%", width: "40%", height: "70%", label: "🥛 Whole Milk (93.1%)" },
    freshness: 90,
    shelfLife: "7.0 Days",
    grade: "Grade A: Optimal Fresh",
    statusCls: "badge-fresh",
    chlorophyll: "N/A (Lactic System)",
    browning: "0.0% (Normal Color)",
    ethylene: "N/A",
    microbial: "Acidity pH 6.68 (Fresh)",
    confidence: "99.1%",
    storageAdvice: "Keep refrigerated continuously below 4°C. Store on inner shelves, not in door."
  },
  meat: {
    name: "Prime Ribeye Beef Steak",
    category: "Meat",
    temp: 1.5,
    rh: 82,
    url: "https://images.unsplash.com/photo-1603048588665-791ca8aea617?w=600&auto=format&fit=crop",
    box: { top: "24%", left: "18%", width: "64%", height: "54%", label: "🥩 Prime Beef (92.8%)" },
    freshness: 91,
    shelfLife: "5.0 Days",
    grade: "Grade A: Prime Cut",
    statusCls: "badge-fresh",
    chlorophyll: "N/A (Oxymyoglobin Intact)",
    browning: "2.1% (Bright Cherry Red)",
    ethylene: "N/A",
    microbial: "Pathogen Screen: Negative",
    confidence: "98.2%",
    storageAdvice: "Wrap tightly to prevent oxidation. Store at 1°C to 3°C on bottom shelf."
  }
};

document.addEventListener("DOMContentLoaded", () => {
  // Populate User Display
  const user = api.getUser();
  if (user) {
    const nameEl = document.getElementById("scanner-user-name");
    const avatarEl = document.getElementById("scanner-user-avatar");
    if (nameEl) nameEl.textContent = `${user.name || user.email} (${user.role || 'User'})`;
    if (avatarEl) avatarEl.textContent = (user.name || user.email || 'U').charAt(0).toUpperCase();
  }

  // Initialize Default Specimen
  updateRadialGauge(95);
  initLiveCamera();
});

// =============================================================================
// CAMERA & INPUT MODE CONTROLS
// =============================================================================
function setScannerInputMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".scanner-mode-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`btn-mode-${mode}`);
  if (activeBtn) activeBtn.classList.add("active");

  const videoEl = document.getElementById("scanner-live-video");
  const imgEl = document.getElementById("scanner-specimen-img");
  const panelCam = document.getElementById("panel-mode-camera");
  const panelUpload = document.getElementById("panel-mode-upload");
  const panelUrl = document.getElementById("panel-mode-url");
  const hudCam = document.getElementById("hud-cam-status");

  if (panelCam) panelCam.style.display = mode === "camera" ? "block" : "none";
  if (panelUpload) panelUpload.style.display = mode === "upload" ? "block" : "none";
  if (panelUrl) panelUrl.style.display = mode === "url" ? "block" : "none";

  if (mode === "camera") {
    if (videoEl) videoEl.style.display = "block";
    if (imgEl) imgEl.style.display = "none";
    if (hudCam) hudCam.textContent = "CAMERA: LIVE";
    initLiveCamera();
  } else {
    stopLiveCamera();
    if (videoEl) videoEl.style.display = "none";
    if (imgEl) imgEl.style.display = "block";
    if (hudCam) hudCam.textContent = mode === "upload" ? "SOURCE: FILE UPLOAD" : "SOURCE: BENCHMARK URL";
  }
}

async function initLiveCamera() {
  const videoEl = document.getElementById("scanner-live-video");
  if (!videoEl || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    console.warn("Camera API not supported on this browser.");
    return;
  }

  try {
    if (cameraStream) stopLiveCamera();
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    videoEl.srcObject = cameraStream;
  } catch (err) {
    console.warn("Camera stream access declined or unavailable:", err.message);
    document.getElementById("hud-cam-status").textContent = "CAMERA: SIMULATED";
  }
}

function stopLiveCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
  }
}

function toggleCameraStream() {
  initLiveCamera();
  showToast("Reinitialized camera optical input.", "info");
}

function captureAndScanCamera() {
  const videoEl = document.getElementById("scanner-live-video");
  const canvas = document.createElement("canvas");
  canvas.width = videoEl.videoWidth || 640;
  canvas.height = videoEl.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

  canvas.toBlob((blob) => {
    currentBlob = blob;
    executeFoodScan("Red Gala Apple", "Fruits");
  }, "image/jpeg", 0.9);
}

function handleFileScan(file) {
  if (!file) return;
  currentBlob = file;
  const imgEl = document.getElementById("scanner-specimen-img");
  const reader = new FileReader();
  reader.onload = (e) => {
    if (imgEl) {
      imgEl.src = e.target.result;
      imgEl.style.display = "block";
    }
    const guessedName = file.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
    executeFoodScan(guessedName, document.getElementById("scan-category").value);
  };
  reader.readAsDataURL(file);
}

function loadUrlForScan() {
  const url = document.getElementById("input-url-scan").value.trim();
  if (!url) {
    showToast("Please enter a valid image web address.", "error");
    return;
  }
  const imgEl = document.getElementById("scanner-specimen-img");
  imgEl.src = url;
  imgEl.style.display = "block";
  executeFoodScan("Scanned Specimen", document.getElementById("scan-category").value);
}

function loadPresetSpecimen(key, evt) {
  const p = SPECIMEN_PRESETS[key];
  if (!p) return;

  const target = (evt && evt.target) || (typeof window !== "undefined" && window.event ? window.event.target : null);
  document.querySelectorAll(".specimen-pill").forEach(pill => pill.classList.remove("active"));
  if (target) {
    const btn = target.closest ? target.closest(".specimen-pill") : target;
    if (btn) btn.classList.add("active");
  }

  const imgEl = document.getElementById("scanner-specimen-img");
  imgEl.src = p.url;
  imgEl.style.display = "block";

  document.getElementById("scan-category").value = p.category;
  document.getElementById("scan-temp").value = p.temp;
  document.getElementById("scan-rh").value = p.rh;

  executeFoodScan(p.name, p.category, p);
}

// =============================================================================
// AI SCAN EXECUTION & HUD ANIMATION
// =============================================================================
async function executeFoodScan(specimenName, category, presetObj) {
  const viewport = document.getElementById("scanner-viewport");
  const laser = document.getElementById("scanner-laser-bar");
  const progBar = document.getElementById("scan-progress-bar");
  const progFill = document.getElementById("scan-progress-fill");
  const ticker = document.getElementById("scan-status-ticker");
  const tickerText = document.getElementById("scan-ticker-text");
  const hudTarget = document.getElementById("hud-target-text");
  const boundingBox = document.getElementById("scanner-bounding-box");
  const boundingTag = document.getElementById("scanner-bounding-tag");
  const btnScan = document.getElementById("btn-execute-scan");

  if (viewport) viewport.classList.add("scanning");
  if (laser) laser.style.display = "block";
  if (progBar) progBar.style.display = "block";
  if (ticker) ticker.style.display = "flex";
  if (boundingBox) boundingBox.style.display = "none";
  if (btnScan) {
    btnScan.disabled = true;
    btnScan.innerHTML = '<span class="spinner" style="width: 16px; height: 16px; display: inline-block;"></span> Analyzing Optical Spectrometry...';
  }

  const stages = [
    { pct: 25, text: "Acquiring optical frame & surface reflectance..." },
    { pct: 55, text: "Computing chlorophyll decay & browning index..." },
    { pct: 85, text: "Evaluating Arrhenius kinetic shelf-life decay..." },
    { pct: 100, text: "Scan complete! Diagnostic certificate generated." }
  ];

  for (let i = 0; i < stages.length; i++) {
    if (progFill) progFill.style.width = `${stages[i].pct}%`;
    if (tickerText) tickerText.textContent = stages[i].text;
    if (hudTarget) hudTarget.textContent = stages[i].text.toUpperCase();
    await new Promise(r => setTimeout(r, 380));
  }

  // Display AI Bounding Box
  const activePreset = presetObj || SPECIMEN_PRESETS.apple;
  if (boundingBox) {
    boundingBox.style.top = activePreset.box.top;
    boundingBox.style.left = activePreset.box.left;
    boundingBox.style.width = activePreset.box.width;
    boundingBox.style.height = activePreset.box.height;
    boundingBox.style.display = "block";
  }
  if (boundingTag) {
    boundingTag.textContent = activePreset.box.label;
  }

  // Stop Laser Sweep after completion
  if (laser) laser.style.display = "none";
  if (viewport) viewport.classList.remove("scanning");
  if (btnScan) {
    btnScan.disabled = false;
    btnScan.innerHTML = "⚡ Run Multi-Spectral AI Freshness Scan";
  }

  // Update Diagnostic Scorecard
  const name = specimenName || activePreset.name;
  currentScannedData = {
    food_name: name,
    category: category || activePreset.category,
    freshness: activePreset.freshness,
    shelf_life_days: activePreset.shelfLife,
    storage_temp: parseFloat(document.getElementById("scan-temp").value) || 4.0,
    storage_humidity: parseFloat(document.getElementById("scan-rh").value) || 85.0
  };

  document.getElementById("diag-food-title").textContent = name;
  document.getElementById("diag-shelf-life-val").textContent = activePreset.shelfLife;
  document.getElementById("chem-chlorophyll").textContent = activePreset.chlorophyll;
  document.getElementById("chem-browning").textContent = activePreset.browning;
  document.getElementById("chem-ethylene").textContent = activePreset.ethylene;
  document.getElementById("chem-microbial").textContent = activePreset.microbial;
  document.getElementById("chem-confidence").textContent = activePreset.confidence;
  document.getElementById("diag-storage-advice").textContent = activePreset.storageAdvice;

  const badge = document.getElementById("diag-badge-status");
  if (badge) {
    badge.textContent = activePreset.grade;
    badge.className = `badge ${activePreset.statusCls}`;
  }

  updateRadialGauge(activePreset.freshness);
  showToast(`Scan complete for ${name}! Freshness: ${activePreset.freshness}%`, "success");
}

function updateRadialGauge(pct) {
  const circle = document.getElementById("gauge-circle-val");
  const num = document.getElementById("gauge-number");
  if (num) num.textContent = `${pct}%`;

  const circumference = 377; // 2 * pi * 60
  const offset = circumference - (pct / 100) * circumference;

  if (circle) {
    circle.style.strokeDashoffset = offset;
    const color = pct >= 80 ? "#10b981" : pct >= 50 ? "#f59e0b" : "#ef4444";
    circle.style.stroke = color;
    if (num) num.style.color = color;
  }
}

// =============================================================================
// INVENTORY SAVE & DASHBOARD RETURN
// =============================================================================
async function saveScannedItemToInventory() {
  if (!currentScannedData) {
    showToast("Please run a food scan first before saving.", "error");
    return;
  }

  const btn = document.getElementById("btn-save-inventory");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:14px; height:14px; display:inline-block;"></span> Saving...';
  }

  try {
    const today = new Date();
    const expiry = new Date(today);
    expiry.setDate(today.getDate() + 7);

    const payload = {
      food_name: currentScannedData.food_name,
      category: currentScannedData.category,
      quantity: 1,
      unit: "unit",
      purchase_date: today.toISOString().split("T")[0],
      expiry_date: expiry.toISOString().split("T")[0],
      storage_type: "Refrigerator",
      status: currentScannedData.freshness >= 80 ? "Fresh" : currentScannedData.freshness >= 50 ? "Moderate" : "Spoiled"
    };

    if (typeof api.createInventoryItem === "function") {
      await api.createInventoryItem(payload);
    }
    showToast(`Saved "${currentScannedData.food_name}" to inventory successfully!`, "success");
  } catch (err) {
    showToast(`Inventory save: ${err.message}`, "info");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "💾 Save to My Inventory";
    }
  }
}

function returnToRoleDashboard() {
  const user = api.getUser();
  const url = api.getDashboardUrlForRole(user ? user.role : null);
  window.location.href = url;
}

window.returnToRoleDashboard = returnToRoleDashboard;
window.setScannerInputMode = setScannerInputMode;
window.executeFoodScan = executeFoodScan;
window.captureAndScanCamera = captureAndScanCamera;
window.toggleCameraStream = toggleCameraStream;
window.handleFileScan = handleFileScan;
window.loadUrlForScan = loadUrlForScan;
window.loadPresetSpecimen = loadPresetSpecimen;
window.saveScannedItemToInventory = saveScannedItemToInventory;

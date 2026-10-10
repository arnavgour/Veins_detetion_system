const GROUPS = {
  capture: "Capture",
  enhance: "Enhance",
  segment: "Segment",
  extract: "Extract",
};

const STATUS = {
  idle: "Waiting for an image",
  running: "Running the vein pipeline",
  ready: "Pipeline complete",
};

const state = {
  steps: [],
  active: 0,
  features: null,
  metrics: null,
  original: null,
  overlay: null,
  playing: false,
  follow: true,
  invert: false,
  explainerTab: "why",
  guideId: "original",
  guideGroup: "all",
};

const els = {
  body: document.body,
  fileInput: document.getElementById("fileInput"),
  dropzone: document.getElementById("dropzone"),
  invertToggle: document.getElementById("invertToggle"),
  samples: document.getElementById("samples"),
  emptyState: document.getElementById("emptyState"),
  viewer: document.getElementById("viewer"),
  facts: document.getElementById("facts"),
  strip: document.getElementById("strip"),
  film: document.getElementById("film"),
  stripProgress: document.getElementById("stripProgress"),
  statusPill: document.getElementById("statusPill"),
  stepKicker: document.getElementById("stepKicker"),
  stepTitle: document.getElementById("stepTitle"),
  stepCopy: document.getElementById("stepCopy"),
  stepStats: document.getElementById("stepStats"),
  lossTab: document.getElementById("lossTab"),
  stageImage: document.getElementById("stageImage"),
  compare: document.getElementById("compare"),
  compareClip: document.getElementById("compareClip"),
  compareRange: document.getElementById("compareRange"),
  compareBase: document.getElementById("compareBase"),
  compareTop: document.getElementById("compareTop"),
  sliderToggle: document.getElementById("sliderToggle"),
  sliderToggleWrap: document.getElementById("sliderToggleWrap"),
  prevBtn: document.getElementById("prevBtn"),
  nextBtn: document.getElementById("nextBtn"),
  replayBtn: document.getElementById("replayBtn"),
  downloadBtn: document.getElementById("downloadBtn"),
  metrics: document.getElementById("metrics"),
  endList: document.getElementById("endList"),
  branchList: document.getElementById("branchList"),
  toast: document.getElementById("toast"),
  aboutPage: document.getElementById("aboutPage"),
  navLinks: [...document.querySelectorAll(".nav-link")],
  explainer: document.getElementById("explainer"),
  explainerTabs: document.getElementById("explainerTabs"),
  explainerBody: document.getElementById("explainerBody"),
  explainerMore: document.getElementById("explainerMore"),
  guideNav: document.getElementById("guideNav"),
  guideDetail: document.getElementById("guideDetail"),
  guideFilters: document.getElementById("guideFilters"),
};

let replayTimer = null;
let toastTimer = null;

function setMode(mode) {
  els.body.classList.remove("idle", "running", "ready");
  els.body.classList.add(mode);
  els.statusPill.textContent = STATUS[mode] || mode;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.add("hidden"), 3200);
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function resetAnalysis() {
  clearInterval(replayTimer);
  state.steps = [];
  state.active = 0;
  state.features = null;
  state.metrics = null;
  state.original = null;
  state.overlay = null;
  state.playing = false;
  state.follow = true;
  els.film.innerHTML = "";
  els.metrics.innerHTML = "";
  els.endList.innerHTML = "";
  els.branchList.innerHTML = "";
  els.sliderToggle.checked = false;
  els.emptyState.classList.add("hidden");
  els.emptyState.hidden = true;
  els.viewer.classList.remove("hidden");
  els.viewer.hidden = false;
  els.strip.classList.remove("hidden");
  els.strip.hidden = false;
  els.facts.classList.add("hidden");
  els.facts.hidden = true;
}

async function readNdjson(response, onEvent) {
  if (!response.ok) {
    let detail = "Analysis failed.";
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

function handleEvent(event) {
  if (event.type === "error") {
    showToast(event.message || "Pipeline error");
    setMode("idle");
    return;
  }
  if (event.type === "meta") {
    els.statusPill.textContent = `${event.filename} · ${event.width}×${event.height}`;
    return;
  }
  if (event.type === "step") {
    state.steps.push(event);
    addFilmCard(event, state.steps.length - 1);
    els.stripProgress.textContent = `${state.steps.length} stages`;
    if (state.follow) {
      state.active = state.steps.length - 1;
      renderStage();
    }
    return;
  }
  if (event.type === "features") {
    state.features = event;
    state.metrics = event.metrics;
    state.original = event.original;
    state.overlay = event.overlay;
    renderFacts();
    els.facts.classList.remove("hidden");
    els.facts.hidden = false;
    return;
  }
  if (event.type === "done") {
    setMode("ready");
    els.statusPill.textContent = `Ready · ${event.elapsed_ms} ms`;
    state.follow = false;
    const overlayIndex = state.steps.findIndex((s) => s.id === "overlay");
    if (overlayIndex >= 0) {
      state.active = overlayIndex;
      renderStage();
    }
  }
}

function addFilmCard(step, index) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "card";
  card.dataset.index = String(index);
  card.style.animationDelay = `${Math.min(index * 40, 400)}ms`;
  card.innerHTML = `
    <img src="${step.image}" alt="${step.title}" />
    <div class="meta">
      <small>${GROUPS[step.group] || step.group} · ${pad(index + 1)}</small>
      <b>${step.title}</b>
    </div>
  `;
  card.addEventListener("click", () => {
    state.follow = false;
    state.active = index;
    renderStage();
  });
  els.film.appendChild(card);
  els.film.scrollTo({ left: els.film.scrollWidth, behavior: "smooth" });
}

function renderStage() {
  const step = state.steps[state.active];
  if (!step) return;
  const total = state.steps.length;
  els.stepKicker.textContent = `${GROUPS[step.group] || step.group} · ${pad(state.active + 1)} / ${pad(total)}`;
  els.stepTitle.textContent = step.title;
  els.stepCopy.textContent = step.description;
  renderStepStats(step.stats);
  els.stageImage.src = step.image;
  els.prevBtn.disabled = state.active === 0;
  els.nextBtn.disabled = state.active === total - 1;

  const canCompare = Boolean(state.original && state.overlay) && step.id === "overlay";
  els.sliderToggleWrap.classList.toggle("hidden", !canCompare);

  const useSlider = canCompare && els.sliderToggle.checked;
  els.compare.classList.toggle("hidden", !useSlider);
  els.stageImage.classList.toggle("hidden", useSlider);
  if (useSlider) {
    els.compareBase.src = state.overlay;
    els.compareTop.src = state.original;
    updateCompare(els.compareRange.value);
  }

  [...els.film.children].forEach((card, i) => {
    card.classList.toggle("active", i === state.active);
  });
  renderExplainer();
}

function updateCompare(value) {
  const pct = Math.min(100, Math.max(0, Number(value)));
  els.compareRange.value = String(pct);
  els.compare.style.setProperty("--split", `${pct}%`);
}

function splitFromClientX(clientX) {
  const rect = els.compare.getBoundingClientRect();
  if (!rect.width) return Number(els.compareRange.value);
  return ((clientX - rect.left) / rect.width) * 100;
}

function renderStepStats(stats) {
  if (!els.stepStats) return;
  const has = Boolean(stats);
  if (els.lossTab) els.lossTab.hidden = !has;
  if (!has) {
    els.stepStats.hidden = true;
    els.stepStats.classList.add("hidden");
    els.stepStats.innerHTML = "";
    if (state.explainerTab === "loss") state.explainerTab = "why";
    return;
  }
  els.stepStats.hidden = false;
  els.stepStats.classList.remove("hidden");
  const chips = [
    [`${stats.entropy_drop_pct}%`, "Entropy gone"],
    [`${stats.gray_levels_in}→${stats.gray_levels_out}`, "Gray levels"],
    [`${stats.entropy_in}→${stats.entropy_out}`, "Bits / pixel"],
    [`${stats.dark_pct_palm}%`, "Palm marked vein"],
    [`${stats.median_blob_px} px`, "Typical blob"],
    [Number(stats.components).toLocaleString(), "Islands"],
  ];
  els.stepStats.innerHTML = chips
    .map(([value, label]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`)
    .join("");
}

function renderFacts() {
  const m = state.metrics;
  if (!m) return;
  const items = [
    [m.endpoints, "Endpoints"],
    [m.branches, "Bifurcations"],
    [m.skeleton_pixels, "Skeleton px"],
    [m.vein_pixels, "Vein pixels"],
    [`${m.width}×${m.height}`, "Working size"],
    [`${m.elapsed_ms} ms`, "Elapsed"],
  ];
  els.metrics.innerHTML = items
    .map(
      ([value, label]) =>
        `<div class="metric"><b>${typeof value === "number" ? value.toLocaleString() : value}</b><span>${label}</span></div>`
    )
    .join("");

  const fill = (node, points) => {
    const shown = points.slice(0, 36);
    node.innerHTML =
      shown.map((p) => `<li>${p.x}, ${p.y}</li>`).join("") +
      (points.length > shown.length ? `<li>+ ${points.length - shown.length} more</li>` : "");
  };
  fill(els.endList, state.features.endpoints || []);
  fill(els.branchList, state.features.branches || []);
}

async function analyze(formData) {
  resetAnalysis();
  setMode("running");
  try {
    const endpoint = formData.has("name") ? "/api/analyze-sample" : "/api/analyze";
    const response = await fetch(endpoint, { method: "POST", body: formData });
    await readNdjson(response, handleEvent);
  } catch (err) {
    setMode("idle");
    els.emptyState.classList.remove("hidden");
    els.emptyState.hidden = false;
    els.viewer.classList.add("hidden");
    els.viewer.hidden = true;
    els.strip.classList.add("hidden");
    els.strip.hidden = true;
    showToast(err.message || "Could not analyze that image.");
  }
}

function analyzeFile(file) {
  const form = new FormData();
  form.append("file", file);
  form.append("invert", els.invertToggle.checked ? "true" : "false");
  analyze(form);
}

function analyzeSample(name) {
  const form = new FormData();
  form.append("name", name);
  form.append("invert", els.invertToggle.checked ? "true" : "false");
  analyze(form);
}

function replay() {
  if (!state.steps.length) return;
  clearInterval(replayTimer);
  state.playing = true;
  state.active = 0;
  renderStage();
  replayTimer = setInterval(() => {
    if (state.active >= state.steps.length - 1) {
      clearInterval(replayTimer);
      state.playing = false;
      return;
    }
    state.active += 1;
    renderStage();
    const card = els.film.children[state.active];
    if (card) card.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, 720);
}

async function loadSamples() {
  try {
    const res = await fetch("/api/samples");
    const samples = await res.json();
    if (!samples.length) {
      els.samples.innerHTML = `<p class="hint">No files in data/sample_veins</p>`;
      return;
    }
    els.samples.innerHTML = "";
    samples.forEach((sample) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sample";
      btn.innerHTML = `
        <img src="${sample.url}" alt="${sample.name}" />
        <span><b>${sample.name}</b><span>Built-in capture</span></span>
      `;
      btn.addEventListener("click", () => {
        [...els.samples.children].forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        analyzeSample(sample.id);
      });
      els.samples.appendChild(btn);
    });
  } catch {
    els.samples.innerHTML = `<p class="hint">Could not load samples</p>`;
  }
}

els.fileInput.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (file) analyzeFile(file);
});

["dragenter", "dragover"].forEach((type) => {
  window.addEventListener(type, (e) => {
    e.preventDefault();
    els.body.classList.add("dragging");
    els.dropzone.classList.add("over");
  });
});

["dragleave", "drop"].forEach((type) => {
  window.addEventListener(type, (e) => {
    e.preventDefault();
    els.body.classList.remove("dragging");
    els.dropzone.classList.remove("over");
  });
});

window.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file && file.type.startsWith("image/")) analyzeFile(file);
});

els.prevBtn.addEventListener("click", () => {
  if (state.active > 0) {
    state.active -= 1;
    renderStage();
  }
});

els.nextBtn.addEventListener("click", () => {
  if (state.active < state.steps.length - 1) {
    state.active += 1;
    renderStage();
  }
});

els.replayBtn.addEventListener("click", replay);
els.downloadBtn.addEventListener("click", () => {
  const step = state.steps[state.active];
  if (!step) return;
  const a = document.createElement("a");
  a.href = step.image;
  a.download = `${pad(state.active + 1)}-${step.id}.png`;
  a.click();
});

els.compareRange.addEventListener("input", (e) => updateCompare(e.target.value));
els.compare.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  els.compare.setPointerCapture(e.pointerId);
  updateCompare(splitFromClientX(e.clientX));
});
els.compare.addEventListener("pointermove", (e) => {
  if (!els.compare.hasPointerCapture(e.pointerId)) return;
  updateCompare(splitFromClientX(e.clientX));
});
els.sliderToggle.addEventListener("change", renderStage);

window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) return;
  if (els.body.classList.contains("show-about")) {
    if (e.key === "ArrowRight") document.getElementById("guideNext")?.click();
    if (e.key === "ArrowLeft") document.getElementById("guidePrev")?.click();
    return;
  }
  if (e.key === "ArrowRight") els.nextBtn.click();
  if (e.key === "ArrowLeft") els.prevBtn.click();
});

function currentPage() {
  const hash = (location.hash || "#studio").replace("#", "");
  if (hash === "about" || hash.startsWith("about/")) return "about";
  return "studio";
}

function aboutStepFromHash() {
  const hash = (location.hash || "").replace("#", "");
  if (!hash.startsWith("about/")) return null;
  return hash.slice("about/".length) || null;
}

function showPage(page) {
  const about = page === "about";
  els.body.classList.toggle("show-about", about);
  els.aboutPage.classList.toggle("hidden", !about);
  els.aboutPage.hidden = !about;
  els.navLinks.forEach((link) => {
    link.classList.toggle("is-active", link.dataset.page === page);
  });
  if (about) {
    els.statusPill.textContent = "About the pipeline";
    const fromHash = aboutStepFromHash();
    if (fromHash && window.guideById(fromHash)) {
      state.guideId = fromHash;
      state.guideGroup = "all";
    }
    renderGuide();
  } else if (state.steps.length) {
    els.statusPill.textContent = STATUS[els.body.classList.contains("running") ? "running" : "ready"];
    if (state.metrics?.elapsed_ms && els.body.classList.contains("ready")) {
      els.statusPill.textContent = `Ready · ${state.metrics.elapsed_ms} ms`;
    }
  } else {
    els.statusPill.textContent = STATUS.idle;
  }
}

function guideList() {
  const all = window.PROCESS_GUIDE || [];
  if (state.guideGroup === "all") return all;
  return all.filter((p) => p.group === state.guideGroup);
}

function renderExplainer() {
  if (!els.explainerBody) return;
  const step = state.steps[state.active];
  const guide = step && window.guideById ? window.guideById(step.id) : null;
  if (!guide) {
    els.explainer.hidden = true;
    return;
  }
  els.explainer.hidden = false;
  els.explainerTabs.querySelectorAll("button").forEach((btn) => {
    const on = btn.dataset.tab === state.explainerTab;
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const tab = state.explainerTab;
  const stats = step.stats;
  if (tab === "params") {
    els.explainerBody.innerHTML = `<ul class="params">${guide.params
      .map((p) => `<li><strong>${p.name}:</strong> ${p.value} <em>(${p.note})</em></li>`)
      .join("")}</ul>`;
  } else if (tab === "how") {
    els.explainerBody.textContent = guide.how;
  } else if (tab === "look") {
    els.explainerBody.textContent = guide.look;
  } else if (tab === "loss" && stats) {
    els.explainerBody.innerHTML = `<p>Adaptive threshold is a 1-bit quantizer. Anything only <strong>C = 2</strong> gray levels darker than its neighborhood becomes black — including CLAHE grain.</p>
      <ul class="params">
        <li><strong>Gray levels:</strong> ${stats.gray_levels_in} → ${stats.gray_levels_out}</li>
        <li><strong>Entropy:</strong> ${stats.entropy_in} → ${stats.entropy_out} bits/px (${stats.entropy_drop_pct}% gone)</li>
        <li><strong>Palm marked vein:</strong> ${stats.dark_pct_palm}%</li>
        <li><strong>Connected islands:</strong> ${Number(stats.components).toLocaleString()} (median ${stats.median_blob_px} px)</li>
        <li><strong>Islands ≥ 500 px:</strong> ${stats.blobs_ge_500}</li>
      </ul>`;
  } else {
    els.explainerBody.textContent = guide.why;
  }
  els.explainerMore.href = `#about/${guide.id}`;
}

function renderGuide() {
  if (!els.guideNav || !els.guideDetail) return;
  const list = guideList();
  if (!list.some((p) => p.id === state.guideId) && list[0]) {
    state.guideId = list[0].id;
  }
  els.guideNav.innerHTML = list
    .map(
      (p) => `
      <button type="button" data-id="${p.id}" class="${p.id === state.guideId ? "is-on" : ""}">
        <small>${GROUPS[p.group]} · ${p.n}</small>
        <b>${p.title}</b>
      </button>`
    )
    .join("");
  els.guideFilters.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("is-on", btn.dataset.group === state.guideGroup);
  });
  const g = window.guideById(state.guideId);
  if (!g) return;
  const idx = list.findIndex((p) => p.id === g.id);
  els.guideDetail.innerHTML = `
    <p class="guide-kicker">${GROUPS[g.group]} · ${g.n} / ${String((window.PROCESS_GUIDE || []).length).padStart(2, "0")}</p>
    <h2>${g.title}</h2>
    <p>${g.summary}</p>
    <h3>Why</h3>
    <p>${g.why}</p>
    <h3>How</h3>
    <p>${g.how}</p>
    <h3>Parameters</h3>
    <table class="param-table">
      <thead><tr><th>Name</th><th>Value</th><th>In code</th></tr></thead>
      <tbody>
        ${g.params.map((p) => `<tr><td>${p.name}</td><td>${p.value}</td><td><code>${p.note}</code></td></tr>`).join("")}
      </tbody>
    </table>
    <h3>What to look for</h3>
    <p>${g.look}</p>
    <p><code>${g.code}</code></p>
    <div class="guide-actions">
      <button type="button" class="ghost" id="guidePrev" ${idx <= 0 ? "disabled" : ""}>← Previous</button>
      <button type="button" class="ghost" id="guideNext" ${idx >= list.length - 1 ? "disabled" : ""}>Next →</button>
      <a class="ghost" href="#studio" style="text-decoration:none;display:inline-flex;align-items:center">Try it in Studio</a>
    </div>
  `;
  document.getElementById("guidePrev")?.addEventListener("click", () => {
    if (idx > 0) selectGuide(list[idx - 1].id, true);
  });
  document.getElementById("guideNext")?.addEventListener("click", () => {
    if (idx < list.length - 1) selectGuide(list[idx + 1].id, true);
  });
  els.guideNav.querySelector(".is-on")?.scrollIntoView({ block: "nearest" });
}

function selectGuide(id, pushHash) {
  state.guideId = id;
  if (pushHash) {
    history.replaceState(null, "", `#about/${id}`);
  }
  renderGuide();
}

function initGuide() {
  els.guideNav?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-id]");
    if (!btn) return;
    selectGuide(btn.dataset.id, true);
  });
  els.guideFilters?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-group]");
    if (!btn) return;
    state.guideGroup = btn.dataset.group;
    renderGuide();
  });
  els.explainerTabs?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    state.explainerTab = btn.dataset.tab;
    renderExplainer();
  });
}

window.addEventListener("hashchange", () => showPage(currentPage()));
initGuide();
showPage(currentPage());
loadSamples();
initPanels();

function initPanels() {
  const panels = loadPanelState();
  applyPanelState(panels);
  document.querySelectorAll("[data-panel]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.panel;
      panels[name] = !panels[name];
      savePanelState(panels);
      applyPanelState(panels);
    });
  });
}

function loadPanelState() {
  try {
    const saved = JSON.parse(localStorage.getItem("vena-panels") || "{}");
    return {
      rail: Boolean(saved.rail),
      facts: Boolean(saved.facts),
      strip: Boolean(saved.strip),
    };
  } catch {
    return { rail: false, facts: false, strip: false };
  }
}

function savePanelState(panels) {
  localStorage.setItem("vena-panels", JSON.stringify(panels));
}

function applyPanelState(panels) {
  els.body.classList.toggle("rail-collapsed", panels.rail);
  els.body.classList.toggle("facts-collapsed", panels.facts);
  els.body.classList.toggle("strip-collapsed", panels.strip);
  document.querySelectorAll(".fold[data-panel]").forEach((btn) => {
    const collapsed = panels[btn.dataset.panel];
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const label = btn.dataset.panel === "rail" ? "source" : btn.dataset.panel === "facts" ? "features" : "pipeline";
    btn.title = collapsed ? `Expand ${label}` : `Collapse ${label}`;
  });
}

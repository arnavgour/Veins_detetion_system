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
  guideId: "original",
  guideGroup: "all",
  analyses: [],
  seeding: false,
  dataView: "table",
  dataSource: "all",
  selectedAnalysisId: null,
  selectedAnalysis: null,
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
  guideNav: document.getElementById("guideNav"),
  guideDetail: document.getElementById("guideDetail"),
  guideFilters: document.getElementById("guideFilters"),
  dataPage: document.getElementById("dataPage"),
  dataViewTabs: document.getElementById("dataViewTabs"),
  dataSourceTabs: document.getElementById("dataSourceTabs"),
  dataCount: document.getElementById("dataCount"),
  dataRefresh: document.getElementById("dataRefresh"),
  dataBanner: document.getElementById("dataBanner"),
  dataTableView: document.getElementById("dataTableView"),
  dataGraphView: document.getElementById("dataGraphView"),
  dataTableBody: document.getElementById("dataTableBody"),
  chartLandmarks: document.getElementById("chartLandmarks"),
  chartPixels: document.getElementById("chartPixels"),
  chartTime: document.getElementById("chartTime"),
  dataDetail: document.getElementById("dataDetail"),
  detailKicker: document.getElementById("detailKicker"),
  detailTitle: document.getElementById("detailTitle"),
  detailClose: document.getElementById("detailClose"),
  detailMetrics: document.getElementById("detailMetrics"),
  detailEnds: document.getElementById("detailEnds"),
  detailBranches: document.getElementById("detailBranches"),
  chartScatter: document.getElementById("chartScatter"),
};

let replayTimer = null;
let toastTimer = null;
let seedPollTimer = null;
let chartTip = null;

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
let comparePointer = null;
els.compare.addEventListener("dragstart", (e) => e.preventDefault());
els.compare.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  e.preventDefault();
  comparePointer = e.pointerId;
  try {
    els.compare.setPointerCapture(e.pointerId);
  } catch {
    /* capture is optional; the flag keeps the drag alive */
  }
  updateCompare(splitFromClientX(e.clientX));
});
els.compare.addEventListener("pointermove", (e) => {
  if (comparePointer !== e.pointerId) return;
  e.preventDefault();
  updateCompare(splitFromClientX(e.clientX));
});
["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
  els.compare.addEventListener(type, (e) => {
    if (comparePointer === e.pointerId) comparePointer = null;
  });
});
els.sliderToggle.addEventListener("change", renderStage);

window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) return;
  if (els.body.classList.contains("show-about")) {
    if (e.key === "ArrowRight") document.getElementById("guideNext")?.click();
    if (e.key === "ArrowLeft") document.getElementById("guidePrev")?.click();
    return;
  }
  if (els.body.classList.contains("show-data")) return;
  if (e.key === "ArrowRight") els.nextBtn.click();
  if (e.key === "ArrowLeft") els.prevBtn.click();
});

function currentPage() {
  const hash = (location.hash || "#studio").replace("#", "");
  if (hash === "about" || hash.startsWith("about/")) return "about";
  if (hash === "data" || hash.startsWith("data/")) return "data";
  return "studio";
}

function aboutStepFromHash() {
  const hash = (location.hash || "").replace("#", "");
  if (!hash.startsWith("about/")) return null;
  return hash.slice("about/".length) || null;
}

function showPage(page) {
  const about = page === "about";
  const data = page === "data";
  els.body.classList.toggle("show-about", about);
  els.body.classList.toggle("show-data", data);
  els.aboutPage.classList.toggle("hidden", !about);
  els.aboutPage.hidden = !about;
  els.dataPage.classList.toggle("hidden", !data);
  els.dataPage.hidden = !data;
  els.navLinks.forEach((link) => {
    link.classList.toggle("is-active", link.dataset.page === page);
  });
  if (data) {
    els.statusPill.textContent = "Feature store";
    loadFeatureData();
  } else {
    clearTimeout(seedPollTimer);
  }
  if (about) {
    els.statusPill.textContent = "About the pipeline";
    const fromHash = aboutStepFromHash();
    if (fromHash && window.guideById(fromHash)) {
      state.guideId = fromHash;
      state.guideGroup = "all";
    }
    renderGuide();
  } else if (data) {
    /* status set above */
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
}

function filteredAnalyses() {
  if (state.dataSource === "all") return state.analyses;
  return state.analyses.filter((row) => row.source === state.dataSource);
}

function fmtInt(value) {
  return Number(value || 0).toLocaleString();
}

function fmtCompact(value) {
  const n = Number(value || 0);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(Math.round(n));
}

function fmtWhen(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function chartLabel(row) {
  const stem = String(row.filename || "image").replace(/\.[^.]+$/, "");
  const short = stem.length > 12 ? `${stem.slice(0, 10)}…` : stem;
  return `${short} #${row.id}`;
}

function svgEl(name, attrs = {}, text) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
  if (text != null) el.textContent = text;
  return el;
}

function hideChartTip() {
  if (chartTip) chartTip.classList.add("hidden");
}

function showChartTip(event, html) {
  if (!chartTip) {
    chartTip = document.createElement("div");
    chartTip.className = "chart-tip hidden";
    document.body.appendChild(chartTip);
  }
  chartTip.innerHTML = html;
  chartTip.classList.remove("hidden");
  chartTip.style.left = `${event.clientX}px`;
  chartTip.style.top = `${event.clientY}px`;
}

function emptyChart(host, message) {
  host.innerHTML = `<p class="chart-empty">${message}</p>`;
}

function renderGroupedBars(host, { labels, series, format = fmtCompact, ids = [] }) {
  host.innerHTML = "";
  if (!labels.length) {
    emptyChart(host, "No stored analyses to plot yet.");
    return;
  }
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  legend.innerHTML = series
    .map((item) => `<span><i class="dot" style="background:${item.color}"></i>${item.name}</span>`)
    .join("");

  const width = Math.max(host.clientWidth || 640, labels.length * 72);
  const height = 260;
  const margin = { top: 16, right: 12, bottom: 58, left: 46 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const maxVal = Math.max(1, ...series.flatMap((item) => item.values));
  const groupW = innerW / labels.length;
  const barW = Math.max(6, (groupW / (series.length + 1.2)) * 0.92);

  const svg = svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`,
    width,
    height,
    role: "img",
  });
  const g = svgEl("g", { transform: `translate(${margin.left},${margin.top})` });
  svg.appendChild(g);

  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const value = (maxVal * i) / ticks;
    const y = innerH - (value / maxVal) * innerH;
    g.appendChild(svgEl("line", { x1: 0, x2: innerW, y1: y, y2: y, stroke: "rgba(25,21,18,0.08)" }));
    g.appendChild(svgEl("text", { x: -8, y: y + 4, "text-anchor": "end", fill: "#746b60", "font-size": 10 }, format(value)));
  }

  labels.forEach((label, index) => {
    const gx = index * groupW;
    series.forEach((item, sIndex) => {
      const value = item.values[index] || 0;
      const h = (value / maxVal) * innerH;
      const x = gx + (sIndex + 0.45) * barW;
      const y = innerH - h;
      const rect = svgEl("rect", {
        x,
        y,
        width: barW,
        height: Math.max(h, value ? 2 : 0),
        rx: 4,
        fill: item.color,
        "data-id": ids[index] || "",
      });
      rect.style.cursor = ids[index] ? "pointer" : "default";
      rect.addEventListener("pointerenter", (event) => {
        showChartTip(event, `<b>${label}</b><br>${item.name}: ${fmtInt(value)}`);
      });
      rect.addEventListener("pointermove", (event) => showChartTip(event, chartTip.innerHTML));
      rect.addEventListener("pointerleave", hideChartTip);
      if (ids[index]) {
        rect.addEventListener("click", () => selectAnalysis(ids[index]));
      }
      g.appendChild(rect);
    });
    const text = svgEl(
      "text",
      {
        x: gx + groupW / 2,
        y: innerH + 16,
        "text-anchor": "end",
        fill: "#746b60",
        "font-size": 10,
        transform: `rotate(-32 ${gx + groupW / 2} ${innerH + 16})`,
      },
      label
    );
    g.appendChild(text);
  });

  host.appendChild(svg);
  host.appendChild(legend);
}

function renderScatter(host, analysis) {
  host.innerHTML = "";
  if (!analysis) {
    emptyChart(host, "Select a row to plot its landmarks.");
    return;
  }
  const ends = analysis.endpoint_points || [];
  const branches = analysis.branch_points || [];
  if (!ends.length && !branches.length) {
    emptyChart(host, "This run has no stored landmarks.");
    return;
  }
  const width = Math.max(host.clientWidth || 480, 360);
  const height = 340;
  const margin = { top: 16, right: 16, bottom: 36, left: 40 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const maxX = Math.max(analysis.width || 1, ...ends.map((p) => p.x), ...branches.map((p) => p.x), 1);
  const maxY = Math.max(analysis.height || 1, ...ends.map((p) => p.y), ...branches.map((p) => p.y), 1);
  const sx = (x) => (x / maxX) * innerW;
  const sy = (y) => (y / maxY) * innerH;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img" });
  const g = svgEl("g", { transform: `translate(${margin.left},${margin.top})` });
  svg.appendChild(g);
  g.appendChild(svgEl("rect", { x: 0, y: 0, width: innerW, height: innerH, fill: "#fffbf4", rx: 10 }));
  g.appendChild(svgEl("text", { x: innerW / 2, y: innerH + 28, "text-anchor": "middle", fill: "#746b60", "font-size": 11 }, `X · ${maxX} px`));
  g.appendChild(svgEl("text", { x: -28, y: innerH / 2, "text-anchor": "middle", fill: "#746b60", "font-size": 11, transform: `rotate(-90 -28 ${innerH / 2})` }, `Y · ${maxY} px`));

  const drawPoints = (points, color, label) => {
    points.forEach((p) => {
      const circle = svgEl("circle", { cx: sx(p.x), cy: sy(p.y), r: 4.2, fill: color, stroke: "#fff", "stroke-width": 1 });
      circle.addEventListener("pointerenter", (event) => {
        showChartTip(event, `${label}<br>${p.x}, ${p.y}`);
      });
      circle.addEventListener("pointerleave", hideChartTip);
      g.appendChild(circle);
    });
  };
  drawPoints(ends, "#1f8a5b", "Endpoint");
  drawPoints(branches, "#c44536", "Bifurcation");
  host.appendChild(svg);
}

function renderDataTable() {
  const rows = filteredAnalyses();
  if (!els.dataTableBody) return;
  if (!rows.length) {
    const message = state.seeding
      ? "Seeding built-in sample features…"
      : state.analyses.length
        ? "No analyses match this filter."
        : "No stored features yet. Upload an image in Studio, or wait for samples to finish seeding.";
    els.dataTableBody.innerHTML = `<tr class="empty-row"><td colspan="12">${message}</td></tr>`;
    return;
  }
  els.dataTableBody.innerHTML = rows
    .map((row) => {
      const selected = row.id === state.selectedAnalysisId ? "is-on" : "";
      return `
        <tr data-id="${row.id}" class="${selected}">
          <td>${row.id}</td>
          <td>${row.filename}</td>
          <td><span class="source-chip ${row.source}">${row.source}</span></td>
          <td>${row.invert ? '<span class="invert-chip">NIR</span>' : "—"}</td>
          <td>${fmtInt(row.endpoints)}</td>
          <td>${fmtInt(row.branches)}</td>
          <td>${fmtInt(row.skeleton_pixels)}</td>
          <td>${fmtInt(row.vein_pixels)}</td>
          <td>${row.width}×${row.height}</td>
          <td>${row.elapsed_ms ?? "—"} ms</td>
          <td>${fmtWhen(row.created_at)}</td>
          <td><button type="button" class="ghost data-del" data-del="${row.id}" aria-label="Delete analysis ${row.id}">Delete</button></td>
        </tr>`;
    })
    .join("");
}

function renderDataCharts() {
  const rows = [...filteredAnalyses()].sort((a, b) => a.id - b.id);
  const labels = rows.map(chartLabel);
  const ids = rows.map((row) => row.id);
  if (els.chartLandmarks) {
    renderGroupedBars(els.chartLandmarks, {
      labels,
      ids,
      series: [
        { name: "Endpoints", values: rows.map((row) => row.endpoints || 0), color: "#1f8a5b" },
        { name: "Bifurcations", values: rows.map((row) => row.branches || 0), color: "#c44536" },
      ],
    });
  }
  if (els.chartPixels) {
    renderGroupedBars(els.chartPixels, {
      labels,
      ids,
      series: [
        { name: "Skeleton px", values: rows.map((row) => row.skeleton_pixels || 0), color: "#215f4a" },
        { name: "Vein px", values: rows.map((row) => row.vein_pixels || 0), color: "#c45c26" },
      ],
    });
  }
  if (els.chartTime) {
    renderGroupedBars(els.chartTime, {
      labels,
      ids,
      format: (n) => `${Math.round(n)}`,
      series: [{ name: "Elapsed ms", values: rows.map((row) => row.elapsed_ms || 0), color: "#2f7a60" }],
    });
  }
  if (state.selectedAnalysis) renderScatter(els.chartScatter, state.selectedAnalysis);
}

function renderDataChrome() {
  const rows = filteredAnalyses();
  if (els.dataCount) {
    els.dataCount.textContent = `${rows.length} ${rows.length === 1 ? "analysis" : "analyses"}`;
  }
  if (els.dataBanner) {
    if (state.seeding) {
      els.dataBanner.hidden = false;
      els.dataBanner.classList.remove("hidden");
      els.dataBanner.textContent = "Built-in samples are being analyzed into SQLite. This page will refresh when they land.";
    } else {
      els.dataBanner.hidden = true;
      els.dataBanner.classList.add("hidden");
    }
  }
  els.dataViewTabs?.querySelectorAll("button").forEach((btn) => {
    const on = btn.dataset.view === state.dataView;
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  els.dataSourceTabs?.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("is-on", btn.dataset.source === state.dataSource);
  });
  if (els.dataTableView) {
    els.dataTableView.hidden = state.dataView !== "table";
    els.dataTableView.classList.toggle("hidden", state.dataView !== "table");
  }
  if (els.dataGraphView) {
    els.dataGraphView.hidden = state.dataView !== "graph";
    els.dataGraphView.classList.toggle("hidden", state.dataView !== "graph");
  }
  if (els.statusPill && currentPage() === "data") {
    els.statusPill.textContent = state.seeding ? "Seeding sample features" : `${state.analyses.length} stored analyses`;
  }
}

function renderDataPage() {
  renderDataChrome();
  renderDataTable();
  if (state.dataView === "graph") {
    requestAnimationFrame(() => renderDataCharts());
  }
  renderDetail();
}

function renderDetail() {
  const row = state.selectedAnalysis;
  if (!els.dataDetail) return;
  if (!row) {
    els.dataDetail.hidden = true;
    els.dataDetail.classList.add("hidden");
    return;
  }
  els.dataDetail.hidden = false;
  els.dataDetail.classList.remove("hidden");
  els.detailKicker.textContent = `${row.source} · ${row.invert ? "NIR invert" : "native"} · ${fmtWhen(row.created_at)}`;
  els.detailTitle.textContent = row.filename;
  const items = [
    [row.endpoints, "Endpoints"],
    [row.branches, "Bifurcations"],
    [row.skeleton_pixels, "Skeleton px"],
    [row.vein_pixels, "Vein pixels"],
    [`${row.width}×${row.height}`, "Working size"],
    [`${row.elapsed_ms ?? "—"} ms`, "Elapsed"],
  ];
  els.detailMetrics.innerHTML = items
    .map(
      ([value, label]) =>
        `<div class="metric"><b>${typeof value === "number" ? fmtInt(value) : value}</b><span>${label}</span></div>`
    )
    .join("");
  const fill = (node, points) => {
    if (!node) return;
    if (!points.length) {
      node.innerHTML = "<li>None stored</li>";
      return;
    }
    node.innerHTML = points.map((p) => `<li>${p.x}, ${p.y}</li>`).join("");
  };
  fill(els.detailEnds, row.endpoint_points || []);
  fill(els.detailBranches, row.branch_points || []);
  requestAnimationFrame(() => renderScatter(els.chartScatter, row));
}

async function loadFeatureData() {
  try {
    const res = await fetch("/api/features");
    if (!res.ok) throw new Error("Could not load stored features.");
    const payload = await res.json();
    state.analyses = payload.analyses || [];
    state.seeding = Boolean(payload.seeding);
    if (state.selectedAnalysisId && !state.analyses.some((row) => row.id === state.selectedAnalysisId)) {
      state.selectedAnalysisId = null;
      state.selectedAnalysis = null;
    }
    renderDataPage();
    clearTimeout(seedPollTimer);
    if (state.seeding && currentPage() === "data") {
      seedPollTimer = setTimeout(loadFeatureData, 2000);
    }
  } catch (err) {
    if (els.dataBanner) {
      els.dataBanner.hidden = false;
      els.dataBanner.classList.remove("hidden");
      els.dataBanner.textContent = err.message || "Could not load the feature store.";
    }
  }
}

async function selectAnalysis(id) {
  const numericId = Number(id);
  if (!numericId) return;
  if (state.selectedAnalysisId === numericId && state.selectedAnalysis) {
    renderDataPage();
    return;
  }
  try {
    const res = await fetch(`/api/features/${numericId}`);
    if (!res.ok) throw new Error("Could not open that analysis.");
    state.selectedAnalysisId = numericId;
    state.selectedAnalysis = await res.json();
    renderDataPage();
    els.dataDetail?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    showToast(err.message || "Could not open that analysis.");
  }
}

async function deleteAnalysis(id) {
  const numericId = Number(id);
  if (!numericId) return;
  if (!window.confirm(`Delete stored features for analysis #${numericId}?`)) return;
  try {
    const res = await fetch(`/api/features/${numericId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Could not delete that analysis.");
    if (state.selectedAnalysisId === numericId) {
      state.selectedAnalysisId = null;
      state.selectedAnalysis = null;
    }
    await loadFeatureData();
    showToast(`Deleted analysis #${numericId}`);
  } catch (err) {
    showToast(err.message || "Could not delete that analysis.");
  }
}

function initDataPage() {
  els.dataViewTabs?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-view]");
    if (!btn) return;
    state.dataView = btn.dataset.view;
    renderDataPage();
  });
  els.dataSourceTabs?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-source]");
    if (!btn) return;
    state.dataSource = btn.dataset.source;
    renderDataPage();
  });
  els.dataRefresh?.addEventListener("click", () => loadFeatureData());
  els.dataTableBody?.addEventListener("click", (e) => {
    const del = e.target.closest("[data-del]");
    if (del) {
      e.preventDefault();
      e.stopPropagation();
      deleteAnalysis(del.dataset.del);
      return;
    }
    const row = e.target.closest("tr[data-id]");
    if (row) selectAnalysis(row.dataset.id);
  });
  els.detailClose?.addEventListener("click", () => {
    state.selectedAnalysisId = null;
    state.selectedAnalysis = null;
    renderDataPage();
  });
  window.addEventListener("resize", () => {
    if (currentPage() === "data" && state.dataView === "graph") {
      renderDataCharts();
    } else if (state.selectedAnalysis) {
      renderScatter(els.chartScatter, state.selectedAnalysis);
    }
  });
}

window.addEventListener("hashchange", () => showPage(currentPage()));
initGuide();
initDataPage();
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

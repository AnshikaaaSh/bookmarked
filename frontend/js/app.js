import { api } from "./api.js";

const $ = (id) => document.getElementById(id);
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STUB_BADGE = `<span class="badge" title="Placeholder response — this feature's backend isn't built yet">demo data</span>`;

function showError(el, message) {
  el.innerHTML = `<div class="errorbox">${escapeHtml(message)}</div>`;
}

/* ---------- Nav with sliding indicator ---------- */
function moveIndicator(btn, animate) {
  const nav = $("tabsNav");
  const ind = $("tabIndicator");
  const navRect = nav.getBoundingClientRect();
  const btnRect = btn.getBoundingClientRect();
  if (!animate) ind.style.transition = "none";
  ind.style.left = `${btnRect.left - navRect.left}px`;
  ind.style.width = `${btnRect.width}px`;
  if (!animate) {
    void ind.offsetWidth;
    ind.style.transition = "";
  }
}

document.querySelectorAll("nav.tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    $(`view-${btn.dataset.view}`).classList.add("active");
    moveIndicator(btn, true);
    if (btn.dataset.view === "graph") initGraphView();
  });
});
window.addEventListener("load", () => moveIndicator(document.querySelector("nav.tabs button.active"), false));
window.addEventListener("resize", () => moveIndicator(document.querySelector("nav.tabs button.active"), false));

/* ---------- Ask ---------- */
async function showLibraryState() {
  const thread = $("askThread");
  try {
    const { sources } = await api.sources();
    if (!sources.length) {
      thread.innerHTML = `<div class="emptystate">
        <strong>Your library is empty.</strong>
        <p>Drop notes in <code>data/books/</code>, a full book in <code>data/texts/</code>,
        or an article in <code>data/articles/</code>, then run
        <code>python -m backend.scripts.ingest</code>. Formats are in the README.</p>
      </div>`;
      return;
    }
    const list = sources
      .map((s) => `<li>${escapeHtml(s.title)}${s.author ? ` · ${escapeHtml(s.author)}` : ""}
        <span class="dim">${s.chunks} chunks${s.max_position ? `, ${s.max_position} chapters` : ""}</span></li>`)
      .join("");
    thread.innerHTML = `<div class="emptystate">
      <strong>${sources.length} source${sources.length === 1 ? "" : "s"} in your library</strong>
      <ul class="sourcelist">${list}</ul>
    </div>`;
  } catch (err) {
    showError(thread, err.message);
  }
}

async function submitAsk() {
  const input = $("askInput");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";

  const thread = $("askThread");
  thread.querySelector(".emptystate")?.remove();

  const entry = document.createElement("div");
  entry.className = "entry";
  entry.innerHTML = `<div class="q">${escapeHtml(question)}</div>`;
  thread.appendChild(entry);

  const typing = document.createElement("div");
  typing.className = "typing";
  typing.innerHTML = "<span></span><span></span><span></span>";
  thread.appendChild(typing);
  typing.scrollIntoView({ behavior: "smooth", block: "end" });

  try {
    const result = await api.ask(question);
    typing.remove();
    const chips = (result.citations || [])
      .map((c) => {
        const web = c.source_type === "web";
        const cls = web ? "chip chip-web" : "chip";
        const label = web ? `🌐 ${c.label}` : c.label;
        const inner = web
          ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`
          : escapeHtml(label);
        return `<span class="${cls}" title="similarity ${c.score}">${inner}</span>`;
      })
      .join("");
    const answer = document.createElement("div");
    answer.className = "entry";
    answer.innerHTML = `<div class="a">${escapeHtml(result.answer).replace(/\n/g, "<br>")}
      ${chips ? `<div class="citations">${chips}</div>` : ""}
      <div class="meta">${result.retrieved} sources${result.used_web ? " (incl. web)" : ""} · ${result.latency_ms} ms</div>
    </div>`;
    thread.appendChild(answer);
    answer.scrollIntoView({ behavior: "smooth", block: "end" });
  } catch (err) {
    typing.remove();
    const box = document.createElement("div");
    box.className = "entry";
    showError(box, err.message);
    thread.appendChild(box);
    box.scrollIntoView({ behavior: "smooth", block: "end" });
  }
}

$("askButton").addEventListener("click", submitAsk);
$("askInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitAsk();
});

/* ---------- Recommend ---------- */
// Deterministic cover art for recommendations the backend doesn't style itself.
const GRADIENTS = [
  "linear-gradient(160deg,#FF8A50,#E14A10)",
  "linear-gradient(160deg,#3C7484,#1D343A)",
  "linear-gradient(160deg,#8462A7,#48334D)",
  "linear-gradient(160deg,#4F8A6B,#224835)",
  "linear-gradient(160deg,#C2557A,#6E2340)",
];
const gradientFor = (title, i) =>
  GRADIENTS[(title.length + i) % GRADIENTS.length];

async function findRecs() {
  const shelf = $("shelf");
  const status = $("recStatus");
  const liked = $("likedInput").value.trim();
  if (!liked) return;

  status.innerHTML = `<p class="dim">Thinking about what pairs with ${escapeHtml(liked)}…</p>`;
  shelf.innerHTML = "";
  $("reasonBox").classList.remove("show");

  let data;
  try {
    data = await api.recommend(liked);
  } catch (err) {
    showError(status, err.message);
    return;
  }

  status.innerHTML = data.stub ? `<p class="dim">${STUB_BADGE} real recommendations arrive in build-order step 3.</p>` : "";

  data.recommendations.forEach((rec, i) => {
    const el = document.createElement("div");
    el.className = "cover";
    el.innerHTML = `
      <div class="art" style="background:${rec.gradient || gradientFor(rec.title, i)}">
        <span>${escapeHtml(rec.title)}</span>
      </div>
      <div class="label">${escapeHtml(rec.author || "")}</div>`;

    const art = el.querySelector(".art");
    art.addEventListener("mousemove", (e) => {
      const rect = art.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      art.style.transform = `perspective(600px) rotateY(${x * 14}deg) rotateX(${-y * 14}deg) scale(1.04)`;
    });
    art.addEventListener("mouseleave", () => {
      art.style.transform = "";
    });

    el.addEventListener("click", () => {
      document.querySelectorAll(".cover").forEach((c) => c.classList.remove("selected"));
      el.classList.add("selected");
      const box = $("reasonBox");
      $("reasonTitle").textContent = rec.title;
      $("reasonText").textContent = rec.reason;
      box.style.display = "block";
      requestAnimationFrame(() => box.classList.add("show"));
    });

    shelf.appendChild(el);
  });
}

$("recButton").addEventListener("click", findRecs);
$("likedInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") findRecs();
});

/* ---------- Write ---------- */
async function draftOutline() {
  const topic = $("topicInput").value.trim();
  if (!topic) return;
  const status = $("writeStatus");
  status.innerHTML = `<p class="dim">Drafting…</p>`;

  let data;
  try {
    data = await api.outline(topic);
  } catch (err) {
    showError(status, err.message);
    return;
  }

  status.innerHTML = data.stub ? `<p class="dim">${STUB_BADGE} real drafting arrives in build-order step 6.</p>` : "";
  $("mTitle").textContent = data.title;

  const outline = $("mOutline");
  outline.innerHTML = "";
  data.outline.forEach((point, i) => {
    const li = document.createElement("li");
    li.textContent = point;
    li.style.animationDelay = `${i * 0.08}s`;
    outline.appendChild(li);
  });

  $("mFootnotes").innerHTML = (data.sources || [])
    .map((s) => `<p>${escapeHtml(s)}</p>`)
    .join("");

  const m = $("manuscript");
  m.style.display = "block";
  m.classList.remove("reveal");
  void m.offsetWidth;
  m.classList.add("reveal");
}

$("outlineButton").addEventListener("click", draftOutline);
$("topicInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") draftOutline();
});

/* ---------- Graph ---------- */
const VIEW_W = 680;
const VIEW_H = 340;
let graphInitialised = false;

/* Nodes arrive without coordinates — the backend stores relationships, not a
   layout. Center the protagonist, ring everyone else around them. Works for any
   number of characters, unlike hardcoded positions. */
function layoutNodes(nodes) {
  const positions = new Map();
  if (!nodes.length) return positions;

  const center = nodes.find((n) => n.main) || nodes[0];
  const others = nodes.filter((n) => n.id !== center.id);
  positions.set(center.id, { x: VIEW_W / 2, y: VIEW_H / 2 });

  const rx = VIEW_W / 2 - 90;
  const ry = VIEW_H / 2 - 52;
  others.forEach((node, i) => {
    const angle = (i / others.length) * Math.PI * 2 - Math.PI / 2;
    positions.set(node.id, {
      x: VIEW_W / 2 + Math.cos(angle) * rx,
      y: VIEW_H / 2 + Math.sin(angle) * ry,
    });
  });
  return positions;
}

function renderGraph(data) {
  const svg = $("graphSvg");
  const positions = layoutNodes(data.nodes);

  if (!data.nodes.length) {
    svg.innerHTML = `<text x="${VIEW_W / 2}" y="${VIEW_H / 2}" text-anchor="middle"
      class="node-label" fill="#8C7A73">No one has been introduced yet.</text>`;
    return;
  }

  let html = "";
  data.edges.forEach((edge) => {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (!from || !to) return;
    html += `<line class="edge-line" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"
      stroke="#F1E2D9" stroke-width="2"/>
      <text class="edge-label edge-text" x="${(from.x + to.x) / 2}" y="${(from.y + to.y) / 2 - 6}"
      text-anchor="middle">${escapeHtml(edge.label || "")}</text>`;
  });

  data.nodes.forEach((node) => {
    const { x, y } = positions.get(node.id);
    const r = node.main ? 46 : 34;
    html += `<g class="node-group">
      <circle class="real-circle" cx="${x}" cy="${y}" r="${r}"
        fill="${node.main ? "#FF5A1F" : "#FFFFFF"}"
        stroke="${node.main ? "#E14A10" : "#3C7484"}" stroke-width="2"/>
      <text class="node-label real-text" x="${x}" y="${y + 4}" text-anchor="middle"
        fill="${node.main ? "#FFFFFF" : "#2B211D"}">${escapeHtml(node.label)}</text>
    </g>`;
  });

  svg.innerHTML = html;
  // One frame later, flip everything to revealed so it fades/scales in.
  requestAnimationFrame(() => {
    svg.querySelectorAll(".node-group, .edge-line, .edge-text").forEach((el) => el.classList.add("revealed"));
  });

  $("hiddenNote").textContent = data.hidden
    ? `${data.hidden} character${data.hidden === 1 ? "" : "s"} still ahead of you — hidden until you reach them.`
    : "";
}

async function loadGraph(sourceId, position) {
  const status = $("graphStatus");
  try {
    const data = await api.graph(sourceId, position);
    status.innerHTML = "";
    $("chapMax").textContent = `Chapter ${data.max_position}`;
    $("progress").max = Math.max(data.max_position, 1);
    renderGraph(data);
  } catch (err) {
    showError(status, err.message);
    $("graphSvg").innerHTML = "";
  }
}

let graphTimer = null;
$("progress").addEventListener("input", () => {
  const position = Number($("progress").value);
  $("chapLabel").textContent = `Chapter ${position}`;
  clearTimeout(graphTimer);
  graphTimer = setTimeout(() => {
    const sourceId = $("graphBook").value;
    if (sourceId) loadGraph(sourceId, position);
  }, 150);
});

$("graphBook").addEventListener("change", () => {
  $("progress").value = 1;
  $("chapLabel").textContent = "Chapter 1";
  loadGraph($("graphBook").value, 1);
});

async function initGraphView() {
  if (graphInitialised) return;
  graphInitialised = true;

  const status = $("graphStatus");
  try {
    const { graphs } = await api.graphs();
    if (!graphs.length) {
      status.innerHTML = `<div class="emptystate">
        <strong>No character graphs yet.</strong>
        <p>Extraction lands in build-order step 4. Until then, seed one by hand in
        <code>data/graphs/&lt;book&gt;.json</code>.</p></div>`;
      $("ribbonWrap").style.display = "none";
      return;
    }
    $("graphBook").innerHTML = graphs
      .map((g) => `<option value="${escapeHtml(g)}">${escapeHtml(g.replace(/-/g, " "))}</option>`)
      .join("");
    loadGraph(graphs[0], 1);
  } catch (err) {
    showError(status, err.message);
  }
}

/* ---------- Boot ---------- */
showLibraryState();

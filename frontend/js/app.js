import { api } from "./api.js";

const $ = (id) => document.getElementById(id);
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function showError(el, message) {
  el.innerHTML = `<div class="errorbox">${escapeHtml(message)}</div>`;
}

// Hand-drawn SVG illustrations for empty states — no external image assets,
// so nothing to fetch, license, or go missing.
const ILLUSTRATION_BOOKS = `<svg class="illustration" viewBox="0 0 64 64" fill="none">
  <rect x="8" y="14" width="20" height="38" rx="2" fill="currentColor" opacity=".18" transform="rotate(-6 8 14)"/>
  <rect x="34" y="12" width="22" height="40" rx="2" fill="currentColor" opacity=".3" transform="rotate(5 34 12)"/>
  <rect x="20" y="10" width="22" height="42" rx="2" fill="currentColor" opacity=".55"/>
  <path d="M24 18h14M24 24h14M24 30h9" stroke="var(--surface)" stroke-width="1.6" stroke-linecap="round"/>
</svg>`;
const ILLUSTRATION_GRAPH = `<svg class="illustration" viewBox="0 0 64 64" fill="none">
  <path d="M20 20 L44 18 M20 20 L32 42 M44 18 L32 42" stroke="currentColor" stroke-width="1.6" opacity=".4"/>
  <circle cx="20" cy="20" r="7" fill="currentColor" opacity=".85"/>
  <circle cx="44" cy="18" r="6" fill="currentColor" opacity=".45"/>
  <circle cx="32" cy="42" r="6" fill="currentColor" opacity=".45"/>
  <circle cx="20" cy="20" r="7" stroke="var(--surface)" stroke-width="1.4"/>
</svg>`;

/* Reading position (FR7) is shared between the Ask and Graph tabs — set it in
   either one and the other picks it up, because it's persisted server-side
   via /api/progress rather than held in a tab's local state. */
const library = { sources: [], progress: {} };

async function loadLibraryState() {
  const [{ sources }, { progress }] = await Promise.all([api.sources(), api.progress()]);
  library.sources = sources;
  library.progress = progress;
}

let progressSaveTimer = null;
function saveProgress(sourceId, position) {
  library.progress[sourceId] = position;
  clearTimeout(progressSaveTimer);
  progressSaveTimer = setTimeout(() => {
    api.setProgress(sourceId, position).catch(() => {
      /* best-effort — a failed save just means the position resets to 1 next visit */
    });
  }, 400);
}

/* ---------- Theme toggle ---------- */
const THEME_KEY = "bookmarked-theme";
function applyTheme(theme) {
  if (theme) document.documentElement.setAttribute("data-theme", theme);
  else document.documentElement.removeAttribute("data-theme"); // follow system
}
try {
  applyTheme(localStorage.getItem(THEME_KEY));
} catch {
  /* private browsing / storage blocked — falls back to system preference */
}
$("themeToggle").addEventListener("click", () => {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark"
    || (!document.documentElement.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const next = isDark ? "light" : "dark";
  applyTheme(next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    /* per-viewer convenience only — fine if it doesn't persist */
  }
});

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
function renderLibraryState() {
  const thread = $("askThread");
  const { sources } = library;
  if (!sources.length) {
    thread.innerHTML = `<div class="emptystate">
      ${ILLUSTRATION_BOOKS}
      <strong>Your library is empty.</strong>
      <p>Drop notes in <code>data/books/</code>, a full book in <code>data/texts/</code>,
      or an article in <code>data/articles/</code>, then run
      <code>python -m backend.scripts.ingest</code>. Formats are in the README.</p>
    </div>`;
    return;
  }
  const list = sources
    .map((s) => `<li>${escapeHtml(s.title)}${s.author ? ` · ${escapeHtml(s.author)}` : ""}
      ${s.max_position ? `<span class="dim">${s.max_position} chapters</span>` : ""}</li>`)
    .join("");
  thread.innerHTML = `<div class="emptystate">
    <strong>${sources.length} source${sources.length === 1 ? "" : "s"} in your library</strong>
    <ul class="sourcelist">${list}</ul>
  </div>`;
}

function populateAskBookPicker() {
  const select = $("askBook");
  const bookSources = library.sources.filter((s) => s.max_position > 0);
  for (const s of bookSources) {
    const option = document.createElement("option");
    option.value = s.source_id;
    option.textContent = s.title;
    select.appendChild(option);
  }
}

function currentAskScope() {
  const sourceId = $("askBook").value || undefined;
  const position = sourceId ? Number($("askPosition").value) : undefined;
  return { source_id: sourceId, position };
}

function onAskBookChange() {
  const sourceId = $("askBook").value;
  const wrap = $("askPositionWrap");
  const note = $("askScopeNote");

  if (!sourceId) {
    wrap.hidden = true;
    note.hidden = true;
    return;
  }
  const source = library.sources.find((s) => s.source_id === sourceId);
  const saved = library.progress[sourceId] || 1;
  $("askPosition").max = source?.max_position || 1;
  $("askPosition").value = saved;
  $("askPositionMax").textContent = `of ${source?.max_position ?? "?"}`;
  wrap.hidden = false;
  note.hidden = false;
}

$("askBook").addEventListener("change", onAskBookChange);
$("askPosition").addEventListener("input", () => {
  const sourceId = $("askBook").value;
  const position = Number($("askPosition").value);
  if (sourceId && position > 0) saveProgress(sourceId, position);
});

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

  const scope = currentAskScope();

  try {
    const result = await api.ask(question, scope);
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
    const scopeNote = scope.source_id
      ? ` · scoped to ch.${scope.position}`
      : "";
    const cachedNote = result.cached ? " · ⚡ cached" : "";
    const answer = document.createElement("div");
    answer.className = "entry";
    answer.innerHTML = `<div class="a">${escapeHtml(result.answer).replace(/\n/g, "<br>")}
      ${chips ? `<div class="citations">${chips}</div>` : ""}
      <div class="meta">${result.retrieved} sources${result.used_web ? " (incl. web)" : ""}${scopeNote}${cachedNote} · ${result.latency_ms} ms</div>
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
  shelf.innerHTML = `<div class="cover skeleton"><div class="art"></div><div class="label-sk"></div></div>
    <div class="cover skeleton" style="animation-delay:.1s"><div class="art"></div><div class="label-sk"></div></div>
    <div class="cover skeleton" style="animation-delay:.2s"><div class="art"></div><div class="label-sk"></div></div>`;
  $("reasonBox").classList.remove("show");

  // This flow makes several LLM round trips (library search, web search,
  // then the structured recommendation itself) — on a slow provider day that
  // compounds into a real wait. Say so after a while instead of leaving a
  // static "Thinking…" up with no sign anything is still happening.
  const slowNotice = setTimeout(() => {
    status.innerHTML = `<p class="dim">Still working — it's checking your library and the web for a few candidates. Free-tier models can be slow to respond some days.</p>`;
  }, 7000);

  let data;
  try {
    data = await api.recommend(liked);
  } catch (err) {
    clearTimeout(slowNotice);
    showError(status, err.message);
    return;
  }
  clearTimeout(slowNotice);

  status.innerHTML = data.cached ? `<p class="dim">⚡ cached — asked this before</p>` : "";
  shelf.innerHTML = ""; // clear the skeleton placeholders before appending real covers

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
// Each category is a full persona, not just a label: it changes the accent
// color, the input placeholder, the lede copy, and — for poetry — the whole
// shape of the response (see write_agent.py's WriteResult.kind). The picker
// is built from this array rather than hardcoded HTML so adding a category
// is a one-line change here, not an HTML+CSS+JS hunt.
const CATEGORIES = [
  {
    id: "general", label: "General", color: "var(--orange)", wash: "var(--orange-wash)",
    placeholder: "Topic for your next post…",
    lede: "Give it a topic — it drafts an outline grounded in your library and current articles, ready for your next post.",
  },
  {
    id: "technical", label: "Technical", color: "var(--cat-tech)", wash: "var(--cat-tech-wash)",
    placeholder: "A concept, system, or pattern to explain…",
    lede: "Precise, mechanism-first outlines for engineering writing — grounded in your library and current sources.",
  },
  {
    id: "business", label: "Business", color: "var(--cat-biz)", wash: "var(--cat-biz-wash)",
    placeholder: "A decision, strategy, or outcome to write about…",
    lede: "Memo-style outlines that lead with the takeaway and tie every point to a concrete outcome.",
  },
  {
    id: "self_help", label: "Self-help", color: "var(--cat-self)", wash: "var(--cat-self-wash)",
    placeholder: "A habit, mindset, or change to write about…",
    lede: "Warm, second-person outlines built around something the reader can act on this week.",
  },
  {
    id: "poetry", label: "Poetry", color: "var(--cat-poem)", wash: "var(--cat-poem-wash)",
    placeholder: "A feeling, image, or moment to write from…",
    lede: "Not an outline — a mood, a form, and a handful of images to build stanzas from.",
  },
];
let activeCategory = CATEGORIES[0];

function categoryById(id) {
  return CATEGORIES.find((c) => c.id === id) || CATEGORIES[0];
}

function buildCategoryBar() {
  const bar = $("categoryBar");
  bar.innerHTML = "";
  CATEGORIES.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = "category-pill" + (cat.id === activeCategory.id ? " active" : "");
    btn.textContent = cat.label;
    btn.style.setProperty("--cat-color", cat.color);
    btn.style.setProperty("--cat-wash", cat.wash);
    btn.addEventListener("click", () => selectCategory(cat.id));
    bar.appendChild(btn);
  });
}

function selectCategory(id) {
  activeCategory = categoryById(id);
  buildCategoryBar();
  $("topicInput").placeholder = activeCategory.placeholder;
  $("writeLede").textContent = activeCategory.lede;
}

// Set once a draft succeeds; both "write the full piece" and every rewrite
// call need to know what topic/category produced what's on screen.
let lastDraft = null; // { topic, category, data }
let lastPiece = null; // the current /api/write/piece response, if any

/* ---------- Rewrite (shared by outline points, poem lines, and the piece) ----------
   An inline control rather than a modal: regenerating one line shouldn't
   cover up the rest of the draft you're comparing it against. */
function attachRewriteControl(container, { getText, getContext, onReplace }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "rewrite-btn";
  btn.title = "Rewrite this";
  btn.textContent = "↻";
  btn.addEventListener("click", () => openRewriteForm(container, btn, { getText, getContext, onReplace }));
  container.appendChild(btn);
  return btn;
}

function openRewriteForm(container, btn, { getText, getContext, onReplace }) {
  if (container.querySelector(".rewrite-form")) return;
  btn.hidden = true;

  const form = document.createElement("div");
  form.className = "rewrite-form";
  form.innerHTML = `
    <input type="text" class="rewrite-feedback" placeholder="What didn't work? (optional)">
    <button type="button" class="rewrite-go">Regenerate</button>
    <button type="button" class="rewrite-cancel">Cancel</button>
  `;
  container.appendChild(form);

  const feedbackInput = form.querySelector(".rewrite-feedback");
  feedbackInput.focus();

  const close = () => {
    form.remove();
    btn.hidden = false;
  };
  form.querySelector(".rewrite-cancel").addEventListener("click", close);

  const go = async () => {
    const feedback = feedbackInput.value.trim() || null;
    form.innerHTML = `<span class="dim">Rewriting…</span>`;
    try {
      const result = await api.rewrite({
        topic: lastDraft.topic,
        category: lastDraft.category,
        text: getText(),
        context: getContext(),
        feedback,
      });
      onReplace(result.text);
      close();
    } catch (err) {
      form.innerHTML = `<span class="rewrite-error">${escapeHtml(err.message)}</span>`;
      setTimeout(close, 3000);
    }
  };
  form.querySelector(".rewrite-go").addEventListener("click", go);
  feedbackInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") go();
  });
}

function outlineContext(title, items, excludeIndex) {
  const rest = items.filter((_, i) => i !== excludeIndex);
  return `Title: ${title}\n` + rest.map((l) => `- ${l}`).join("\n");
}

function renderOutlineManuscript(data) {
  $("mMeta").hidden = true;
  $("mMeta").innerHTML = "";
  const outline = $("mOutline");
  outline.classList.remove("poem-lines");
  outline.innerHTML = "";
  (data.outline || []).forEach((point, i) => {
    const li = document.createElement("li");
    li.className = "point-row";
    li.style.animationDelay = `${i * 0.08}s`;
    const span = document.createElement("span");
    span.className = "point-text";
    span.textContent = point;
    li.appendChild(span);
    attachRewriteControl(li, {
      getText: () => data.outline[i],
      getContext: () => outlineContext(data.title, data.outline, i),
      onReplace: (newText) => {
        data.outline[i] = newText;
        span.textContent = newText;
      },
    });
    outline.appendChild(li);
  });
  $("mFootnotes").innerHTML = (data.sources || [])
    .map((s) => `<p>${escapeHtml(s)}</p>`)
    .join("");
}

function renderPoemManuscript(data) {
  const meta = $("mMeta");
  meta.hidden = false;
  meta.innerHTML = [data.form, data.mood]
    .filter(Boolean)
    .map((label) => `<span class="meta-badge">${escapeHtml(label)}</span>`)
    .join("");

  const outline = $("mOutline");
  outline.classList.add("poem-lines");
  outline.innerHTML = "";
  (data.themes || []).forEach((line, i) => {
    const li = document.createElement("li");
    li.className = "point-row";
    li.style.animationDelay = `${i * 0.08}s`;
    const span = document.createElement("span");
    span.className = "point-text";
    span.textContent = line;
    li.appendChild(span);
    attachRewriteControl(li, {
      getText: () => data.themes[i],
      getContext: () => outlineContext(data.title, data.themes, i),
      onReplace: (newText) => {
        data.themes[i] = newText;
        span.textContent = newText;
      },
    });
    outline.appendChild(li);
  });

  $("mFootnotes").innerHTML = (data.sources || []).length
    ? `<p class="footnote-heading">Echoes</p>` + data.sources.map((s) => `<p>${escapeHtml(s)}</p>`).join("")
    : "";
}

// A new topic is a new draft, not an edit of the old one — clear whatever's
// on screen the moment the request starts, not once the response lands, so
// the old outline/piece never lingers next to a "Drafting…" spinner for a
// completely different topic.
function clearDraft() {
  lastDraft = null;
  lastPiece = null;
  $("manuscript").style.display = "none";
  $("piece").style.display = "none";
  $("writeStatus").innerHTML = "";
}

function clearPiece() {
  lastPiece = null;
  $("piece").style.display = "none";
}

async function draftOutline() {
  const topic = $("topicInput").value.trim();
  if (!topic) return;
  clearDraft();
  const status = $("writeStatus");
  status.innerHTML = `<p class="dim">Drafting…</p>
    <div class="manuscript-sk">
      <div class="sk-line sk-title"></div>
      <div class="sk-line" style="width:88%"></div>
      <div class="sk-line" style="width:95%"></div>
      <div class="sk-line" style="width:70%"></div>
      <div class="sk-line" style="width:82%"></div>
    </div>`;

  let data;
  try {
    data = await api.outline(topic, activeCategory.id);
  } catch (err) {
    showError(status, err.message);
    return;
  }

  status.innerHTML = data.cached ? `<p class="dim">⚡ cached — asked this before</p>` : "";
  $("mTitle").textContent = data.title;
  document.querySelector("#manuscript .rule").style.background = activeCategory.color;

  if (data.kind === "poem") {
    renderPoemManuscript(data);
  } else {
    renderOutlineManuscript(data);
  }

  lastDraft = { topic, category: activeCategory.id, data };

  const m = $("manuscript");
  m.style.display = "block";
  m.classList.remove("reveal");
  void m.offsetWidth;
  m.classList.add("reveal");
}

/* ---------- Full piece ---------- */
function renderPieceBody(text) {
  const body = $("pieceBody");
  body.innerHTML = "";
  text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .forEach((para) => {
      const p = document.createElement("p");
      p.textContent = para;
      body.appendChild(p);
    });
}

function renderPiece(piece) {
  lastPiece = piece;
  $("pieceTitle").textContent = piece.title;
  $("pieceRule").style.background = activeCategory.color;
  renderPieceBody(piece.body);
  $("pieceFootnotes").innerHTML = (piece.sources || [])
    .map((s) => `<p>${escapeHtml(s)}</p>`)
    .join("");

  const el = $("piece");
  el.style.display = "block";
  el.classList.remove("reveal");
  void el.offsetWidth;
  el.classList.add("reveal");
}

async function draftPiece() {
  if (!lastDraft) return;
  const btn = $("pieceButton");
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Writing…";

  const { topic, category, data } = lastDraft;
  try {
    const piece = await api.piece({
      topic,
      category,
      title: data.title,
      outline: data.outline || [],
      sources: data.sources || [],
      themes: data.themes || [],
      mood: data.mood || "",
      form: data.form || "",
    });
    renderPiece(piece);
  } catch (err) {
    showError($("writeStatus"), err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

/* ---------- Download (client-side only — a .md file, no server round trip) ---------- */
function slugify(text) {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "")
      .slice(0, 60) || "untitled"
  );
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function draftToMarkdown({ data }) {
  const lines = [`# ${data.title}`, ""];
  if (data.kind === "poem") {
    const meta = [data.form, data.mood].filter(Boolean).join(" — ");
    if (meta) lines.push(`*${meta}*`, "");
    (data.themes || []).forEach((t) => lines.push(`- ${t}`));
    if ((data.sources || []).length) {
      lines.push("", "**Echoes**");
      data.sources.forEach((s) => lines.push(`- ${s}`));
    }
  } else {
    (data.outline || []).forEach((point, i) => lines.push(`${i + 1}. ${point}`));
    if ((data.sources || []).length) {
      lines.push("", "**Sources**");
      data.sources.forEach((s) => lines.push(`- ${s}`));
    }
  }
  return lines.join("\n") + "\n";
}

function pieceToMarkdown(piece) {
  const lines = [`# ${piece.title}`, "", piece.body.trim()];
  if ((piece.sources || []).length) {
    lines.push("", "**Sources**");
    piece.sources.forEach((s) => lines.push(`- ${s}`));
  }
  return lines.join("\n") + "\n";
}

buildCategoryBar();
$("outlineButton").addEventListener("click", draftOutline);
$("topicInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") draftOutline();
});
$("pieceButton").addEventListener("click", draftPiece);
$("rewritePieceButton").addEventListener("click", () => {
  if (!lastPiece) return;
  openRewriteForm($("piece"), $("rewritePieceButton"), {
    getText: () => lastPiece.body,
    getContext: () => `Title: ${lastPiece.title}`,
    onReplace: (newText) => {
      lastPiece.body = newText;
      renderPieceBody(newText);
    },
  });
});
$("downloadDraftButton").addEventListener("click", () => {
  if (!lastDraft) return;
  const suffix = lastDraft.data.kind === "poem" ? "poem" : "outline";
  downloadText(`${slugify(lastDraft.data.title)}-${suffix}.md`, draftToMarkdown(lastDraft));
});
$("clearDraftButton").addEventListener("click", clearDraft);
$("downloadPieceButton").addEventListener("click", () => {
  if (!lastPiece) return;
  downloadText(`${slugify(lastPiece.title)}.md`, pieceToMarkdown(lastPiece));
});
$("clearPieceButton").addEventListener("click", clearPiece);

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
      class="node-label" fill="var(--ink-dim)">No one has been introduced yet.</text>`;
    return;
  }

  // Colors reference CSS custom properties directly — modern browsers resolve
  // var() inside SVG presentation attributes, so these repaint correctly on
  // a theme switch instead of being frozen at whatever theme was active when
  // the graph last rendered. Non-main nodes use --surface/--ink (white circle
  // + dark text in light mode, dark circle + light text in dark mode) rather
  // than fixed hex values — the fixed-white-circle version of this looked
  // fine in light mode but made dark-mode text nearly invisible on a stark
  // white circle, since the label color came from a CSS class that didn't
  // know which theme was active.
  let html = "";
  data.edges.forEach((edge) => {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (!from || !to) return;
    html += `<line class="edge-line" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"
      stroke="var(--hairline)" stroke-width="2"/>
      <text class="edge-label edge-text" x="${(from.x + to.x) / 2}" y="${(from.y + to.y) / 2 - 6}"
      text-anchor="middle">${escapeHtml(edge.label || "")}</text>`;
  });

  data.nodes.forEach((node) => {
    const { x, y } = positions.get(node.id);
    const r = node.main ? 46 : 34;
    html += `<g class="node-group">
      <circle class="real-circle" cx="${x}" cy="${y}" r="${r}"
        fill="${node.main ? "var(--orange)" : "var(--surface)"}"
        stroke="${node.main ? "var(--orange-dark)" : "var(--teal)"}" stroke-width="2"/>
      <text class="node-label real-text" x="${x}" y="${y + 4}" text-anchor="middle"
        fill="${node.main ? "#FFFFFF" : "var(--ink)"}">${escapeHtml(node.label)}</text>
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
  // Omitting `position` lets the backend resolve it from saved progress —
  // the same value the Ask tab's position picker reads and writes, so the two
  // tabs stay in sync instead of Graph always resetting to chapter 1.
  const status = $("graphStatus");
  try {
    const data = await api.graph(sourceId, position);
    status.innerHTML = "";
    $("chapMax").textContent = `Chapter ${data.max_position}`;
    $("progress").max = Math.max(data.max_position, 1);
    $("progress").value = data.position;
    $("chapLabel").textContent = `Chapter ${data.position}`;
    library.progress[sourceId] = data.position;
    renderGraph(data);
  } catch (err) {
    showError(status, err.message);
    $("graphSvg").innerHTML = "";
  }
}

let graphTimer = null;
$("progress").addEventListener("input", () => {
  const position = Number($("progress").value);
  const sourceId = $("graphBook").value;
  $("chapLabel").textContent = `Chapter ${position}`;
  if (sourceId) saveProgress(sourceId, position);
  clearTimeout(graphTimer);
  graphTimer = setTimeout(() => {
    if (sourceId) loadGraph(sourceId, position);
  }, 150);
});

$("graphBook").addEventListener("change", () => {
  loadGraph($("graphBook").value);
});

async function initGraphView() {
  if (graphInitialised) return;
  graphInitialised = true;

  const status = $("graphStatus");
  try {
    const { graphs } = await api.graphs();
    if (!graphs.length) {
      status.innerHTML = `<div class="emptystate">
        ${ILLUSTRATION_GRAPH}
        <strong>No character graphs yet.</strong>
        <p>Run <code>python -m backend.scripts.extract_graph &lt;source_id&gt;</code>
        for a book you've ingested.</p></div>`;
      $("ribbonWrap").style.display = "none";
      return;
    }
    $("graphBook").innerHTML = graphs
      .map((g) => `<option value="${escapeHtml(g)}">${escapeHtml(g.replace(/-/g, " "))}</option>`)
      .join("");
    loadGraph(graphs[0]);
  } catch (err) {
    showError(status, err.message);
  }
}

/* ---------- Boot ---------- */
// Shown in the composer's right cluster — the real configured provider/model
// (backend/config.py), not a hardcoded label, so it can't drift from .env.
async function loadModelBadge() {
  try {
    const health = await api.health();
    $("modelBadge").textContent = `${health.provider} · ${health.answer_model}`;
  } catch {
    /* best-effort — an empty badge just means the label doesn't show */
  }
}

async function boot() {
  const thread = $("askThread");
  loadModelBadge();
  try {
    await loadLibraryState();
    populateAskBookPicker();
    renderLibraryState();
  } catch (err) {
    showError(thread, err.message);
  }
}
boot();

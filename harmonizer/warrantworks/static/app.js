/* WarrantWorks TN - local workspace (no build step, no external requests). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const app = $("#app");
const state = { meta: null, family: null, cmp: null, rev: null, filter: "undecided", choices: {} };

// ------------------------------------------------------------------ util
function actor() { return ($("#actor").value || "").trim(); }
(function initActor() {
  const a = $("#actor");
  try { a.value = localStorage.getItem("ww.actor") || ""; } catch (_) {}
  a.addEventListener("change", () => { try { localStorage.setItem("ww.actor", a.value.trim()); } catch (_) {} a.classList.toggle("missing", !a.value.trim()); });
  a.classList.toggle("missing", !a.value.trim());
})();

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-Actor": actor() }, opts.headers || {});
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && (data.error || data.detail)) || res.statusText);
  return data;
}
function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = ""), err ? 6000 : 2800);
}
async function guard(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); if (/name/i.test(e.message)) $("#actor").focus(); }
}
function openModal(html) { $("#modal-body").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const fmtTime = (iso) => iso ? new Date(iso).toLocaleString() : "";
const kindBadge = (k) => ({ missing: '<span class="badge bad">Missing in some</span>', extra: '<span class="badge info">Added in some</span>', wording: '<span class="badge warn">Wording differs</span>' }[k] || k);
const statusBadge = (s) => ({ pass: '<span class="badge ok">Pass</span>', attention: '<span class="badge warn">Review</span>', fail: '<span class="badge bad">Fail</span>', draft: '<span class="badge warn">Draft</span>', approved: '<span class="badge ok">Approved</span>', superseded: '<span class="badge">Superseded</span>' }[s] || esc(s));

// ---------------------------------------------------------------- router
window.addEventListener("hashchange", route);
async function route() {
  if (!state.meta) state.meta = await api("/api/meta");
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  if (parts[0] === "f" && parts[1]) return renderFamily(parts[1], parts[2] || "sources");
  return renderHome();
}

// ------------------------------------------------------------------ home
async function renderHome() {
  const fams = await api("/api/families");
  const types = state.meta.form_types;
  app.innerHTML = `
    <h1>Form families</h1>
    <p class="sub">A form family holds every version of one form (for example, each agency's arrest warrant). Compare the versions, decide each difference, and produce one uniform master with a full revision history.</p>
    <div class="grid fams">
      ${fams.map((f) => `
        <div class="card fam" onclick="location.hash='#/f/${f.id}/sources'">
          <div class="row"><h3 style="margin:0">${esc(f.name)}</h3><span class="spacer"></span>
            ${f.latest_revision ? statusBadge(f.latest_revision.status) : ""}</div>
          <div class="small">${esc(f.form_type_label)}</div>
          <p class="small">${f.documents} source document${f.documents === 1 ? "" : "s"}${f.latest_revision ? ` · master rev ${f.latest_revision.number}` : " · no master yet"}</p>
        </div>`).join("") || '<div class="empty">No form families yet. Create the first one below.</div>'}
    </div>
    <div class="card" style="max-width:640px">
      <h2>New form family</h2>
      <label class="f" for="nf-name">Name</label>
      <input type="text" id="nf-name" placeholder="e.g. General Sessions Arrest Warrant - county agencies">
      <label class="f" for="nf-type">Form type</label>
      <select id="nf-type">${Object.entries(types).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
      <label class="f" for="nf-desc">Notes (optional)</label>
      <textarea id="nf-desc" placeholder="Which agencies, which forms, any context for reviewers"></textarea>
      <div class="row" style="margin-top:10px"><button class="btn" id="nf-go">Create family</button></div>
    </div>
    <p class="small">Data folder: <span class="mono">${esc(state.meta.data_dir)}</span> · OCR ${state.meta.ocr_available ? "available" : "not installed"} · LibreOffice ${state.meta.libreoffice_available ? "available" : "not installed"} · audit chain ${state.meta.audit.ok ? `intact (${state.meta.audit.entries} entries)` : "BROKEN"}</p>`;
  $("#nf-go").onclick = () => guard(async () => {
    const f = await api("/api/families", { method: "POST", json: { name: $("#nf-name").value, form_type: $("#nf-type").value, description: $("#nf-desc").value } });
    location.hash = `#/f/${f.id}/sources`;
  });
}

// ---------------------------------------------------------------- family
const TABS = [["sources", "Sources"], ["compare", "Compare"], ["reconcile", "Reconcile"], ["master", "Master"], ["exports", "Exports"], ["history", "History"]];

async function loadFamily(fid) {
  state.family = await api(`/api/families/${fid}`);
  const latest = state.family.comparisons[0];
  if (latest && (!state.cmp || state.cmp.family_id !== fid || !state.family.comparisons.find((c) => c.id === state.cmp.id))) {
    state.cmp = await api(`/api/comparisons/${latest.id}`);
  } else if (!latest) state.cmp = null;
  else if (state.cmp) state.cmp = await api(`/api/comparisons/${state.cmp.id}`);
  const revs = state.family.revisions;
  if (revs.length && (!state.rev || state.rev.family_id !== fid || !revs.find((r) => r.id === state.rev.id))) state.rev = await api(`/api/revisions/${revs[0].id}`);
  else if (!revs.length) state.rev = null;
  else if (state.rev) state.rev = await api(`/api/revisions/${state.rev.id}`);
}

async function renderFamily(fid, tab) {
  await loadFamily(fid);
  const f = state.family;
  const undecided = state.cmp ? state.cmp.undecided : null;
  app.innerHTML = `
    <div class="row"><a href="#">← All families</a></div>
    <div class="row" style="margin-top:8px"><h1>${esc(f.name)}</h1><span class="badge navy">${esc(f.form_type_label)}</span></div>
    ${f.description ? `<p class="sub">${esc(f.description)}</p>` : ""}
    <nav class="tabs">${TABS.map(([k, v], i) => `<button class="tab ${k === tab ? "active" : ""}" onclick="location.hash='#/f/${fid}/${k}'"><span class="n">${i + 1}</span>${v}${k === "reconcile" && undecided ? ` <span class="badge warn">${undecided}</span>` : ""}</button>`).join("")}</nav>
    <section id="tab"></section>`;
  const el = $("#tab");
  ({ sources: tabSources, compare: tabCompare, reconcile: tabReconcile, master: tabMaster, exports: tabExports, history: tabHistory }[tab] || tabSources)(el);
}
const refresh = () => route();

// --------------------------------------------------------------- sources
function tabSources(el) {
  const f = state.family;
  el.innerHTML = `
    <div class="grid two">
      <div class="card">
        <h2>Add source documents</h2>
        <p class="small">PDF (digital or scanned), Word (.docx), plain text, or an image (PNG/JPG/TIFF; read with OCR). Originals are stored unchanged and fingerprinted.</p>
        <div class="row">
          <div style="flex:1;min-width:160px"><label class="f" for="up-role">Role</label>
            <select id="up-role"><option value="version">Version in use (agency copy)</option><option value="approved_master">Approved reference (current official form)</option></select></div>
          <div style="flex:1;min-width:160px"><label class="f" for="up-label">Label (agency or source)</label>
            <input type="text" id="up-label" placeholder="Defaults to the file name"></div>
        </div>
        <div class="drop" id="drop" style="margin-top:12px">Drop files here or <label style="color:var(--navy);cursor:pointer;text-decoration:underline">choose files<input type="file" id="up-file" multiple hidden accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff"></label></div>
        <div id="up-status" class="small" style="margin-top:8px"></div>
      </div>
      <div class="card">
        <h2>Required text</h2>
        <p class="small">Passages the master must contain (for example a statutory notice or a signature block label). Each is checked in the master and again in every exported file. Enter only wording you have verified against a current primary source.</p>
        ${f.requirements.map((r) => `<div class="row" style="border-bottom:1px solid var(--line);padding:6px 0"><div style="flex:1"><div class="anchor-text" style="margin:0">${esc(r.text)}</div>${r.note ? `<div class="small">${esc(r.note)}</div>` : ""}</div><button class="btn ghost small" onclick="delReq('${r.id}')">Remove</button></div>`).join("") || '<div class="empty">None defined.</div>'}
        <label class="f" for="rq-text">Add required passage</label>
        <textarea id="rq-text" placeholder="Exact wording"></textarea>
        <input type="text" id="rq-note" placeholder="Source / note (e.g. where it was verified)" style="margin-top:6px">
        <div class="row" style="margin-top:8px"><button class="btn small" id="rq-go">Add</button></div>
      </div>
    </div>
    <div class="card">
      <h2>Documents in this family</h2>
      <table><thead><tr><th>Label</th><th>Role</th><th>File</th><th>Read as</th><th>Lines</th><th>Uploaded</th><th></th></tr></thead><tbody>
      ${f.documents.map((d) => `<tr>
        <td><b>${esc(d.label)}</b></td>
        <td>${d.role === "approved_master" ? '<span class="badge ok">Approved reference</span>' : '<span class="badge">Version</span>'}</td>
        <td class="mono">${esc(d.filename)}<div class="small">sha256 ${d.sha256.slice(0, 12)}…</div></td>
        <td>${d.kind.toUpperCase()}${d.ocr_used ? ` <span class="badge warn">OCR ${d.ocr_confidence ?? "?"}%</span>` : ""}${d.warnings.length ? `<div class="small" style="color:var(--bad)">${esc(d.warnings.join(" "))}</div>` : ""}</td>
        <td>${d.segments}</td>
        <td class="small">${esc(d.uploaded_by)}<br>${fmtTime(d.created_at)}</td>
        <td class="row"><button class="btn ghost small" onclick="viewDoc('${d.id}')">View</button><a class="btn ghost small" href="/api/documents/${d.id}/file" target="_blank">Original</a><button class="btn ghost small" onclick="removeDoc('${d.id}')">Remove</button></td>
      </tr>`).join("") || '<tr><td colspan="7" class="empty">No documents yet.</td></tr>'}
      </tbody></table>
      ${f.documents.length >= 2 ? `<div class="row" style="margin-top:12px"><span class="spacer"></span><button class="btn gold" onclick="location.hash='#/f/${f.id}/compare'">Next: compare →</button></div>` : ""}
    </div>`;
  const input = $("#up-file"), drop = $("#drop");
  input.onchange = () => uploadFiles([...input.files]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); uploadFiles([...e.dataTransfer.files]); };
  $("#rq-go").onclick = () => guard(async () => {
    await api(`/api/families/${f.id}/requirements`, { method: "POST", json: { text: $("#rq-text").value, note: $("#rq-note").value } });
    toast("Requirement added"); refresh();
  });
}
async function uploadFiles(files) {
  if (!actor()) { toast("Enter your name first; every upload is recorded.", true); $("#actor").focus(); return; }
  const st = $("#up-status");
  for (const file of files) {
    st.textContent = `Reading ${file.name}… (scans take longer: OCR runs locally)`;
    const fd = new FormData();
    fd.append("file", file); fd.append("role", $("#up-role").value);
    fd.append("label", files.length === 1 && $("#up-label").value ? $("#up-label").value : file.name.replace(/\.[^.]+$/, ""));
    const ok = await guard(() => api(`/api/families/${state.family.id}/documents`, { method: "POST", body: fd }));
    if (ok) toast(`${file.name}: ${ok.segments} lines read${ok.ocr_used ? " with OCR" : ""}`);
  }
  st.textContent = "";
  refresh();
}
window.delReq = (id) => guard(async () => { await api(`/api/requirements/${id}`, { method: "DELETE" }); refresh(); });
window.removeDoc = (id) => guard(async () => { if (!confirm("Remove this document from the family? The original file stays in the store and the removal is logged.")) return; await api(`/api/documents/${id}`, { method: "DELETE" }); refresh(); });
window.viewDoc = (id) => guard(async () => {
  const d = await api(`/api/documents/${id}/segments`);
  const doc = state.family.documents.find((x) => x.id === id);
  const pages = doc && doc.has_preview ? (d.pages.length || 1) : 0;
  openModal(`<h2>${esc(d.label)}</h2><p class="small">${d.kind.toUpperCase()} · ${d.segments.length} lines read</p>
    ${pages ? [...Array(pages).keys()].map((p) => `<div class="viewer" style="margin-bottom:10px"><img src="/api/documents/${id}/pages/${p}.png" alt="Page ${p + 1}"></div>`).join("") : ""}
    <h3>Text as read</h3><div class="ctx">${d.segments.map((s) => `<div>${s.conf != null ? `<span class="small">[${s.conf}%]</span> ` : ""}${esc(s.text)}</div>`).join("")}</div>`);
});

// --------------------------------------------------------------- compare
function tabCompare(el) {
  const f = state.family;
  const versions = f.documents.filter((d) => d.role === "version");
  const masters = f.documents.filter((d) => d.role === "approved_master");
  const c = state.cmp;
  el.innerHTML = `
    <div class="card">
      <h2>Set up a comparison</h2>
      <p class="small">Every selected version is aligned line by line to the approved reference if you choose one, otherwise to the visual base. The visual base is the version whose layout the master keeps. A digital PDF or Word version makes the best base; a scan works but its layout is reproduced less precisely.</p>
      <div class="grid two">
        <div><label class="f">Versions to compare</label>
          ${versions.map((d) => `<label class="row" style="padding:3px 0"><input type="checkbox" class="cv" value="${d.id}" ${!c || c.documents.some((x) => x.id === d.id) ? "checked" : ""}> ${esc(d.label)} <span class="small">${d.kind.toUpperCase()}${d.ocr_used ? " · scan" : ""}</span></label>`).join("") || '<div class="empty">Upload versions first.</div>'}
        </div>
        <div>
          <label class="f" for="cm-master">Approved reference</label>
          <select id="cm-master"><option value="">None: produce a proposed consensus draft</option>${masters.map((d) => `<option value="${d.id}" ${(c ? c.mode === "approved_reference" && c.anchor_doc_id === d.id : true) ? "selected" : ""}>${esc(d.label)}</option>`).join("")}</select>
          <label class="f" for="cm-base">Visual base (layout to keep)</label>
          <select id="cm-base">${versions.map((d) => `<option value="${d.id}" ${(c ? c.base_doc_id === d.id : d.id === (versions.find((v) => v.kind === "pdf") || versions[0]).id) ? "selected" : ""}>${esc(d.label)} (${d.kind.toUpperCase()}${d.ocr_used ? ", scan" : ""})</option>`).join("")}</select>
          <div class="row" style="margin-top:14px"><button class="btn" id="cm-go" ${versions.length ? "" : "disabled"}>Run comparison</button></div>
        </div>
      </div>
    </div>
    ${c ? compareResult(c) : '<div class="card empty">No comparison yet.</div>'}`;
  $("#cm-go") && ($("#cm-go").onclick = () => guard(async () => {
    const ids = [...document.querySelectorAll(".cv:checked")].map((x) => x.value);
    const btn = $("#cm-go"); btn.disabled = true; btn.textContent = "Comparing…";
    try {
      state.cmp = await api(`/api/families/${f.id}/comparisons`, { method: "POST", json: { version_ids: ids, base_id: $("#cm-base").value, master_id: $("#cm-master").value || null } });
      toast(`${state.cmp.stats.items} differences found`); refresh();
    } finally { btn.disabled = false; btn.textContent = "Run comparison"; }
  }));
}
function compareResult(c) {
  const docs = c.documents;
  const itemsByRow = Object.fromEntries(c.items.map((i) => [i.row, i]));
  return `<div class="card">
    <div class="row"><h2 style="margin:0">Comparison</h2><span class="badge ${c.mode === "approved_reference" ? "ok" : "warn"}">${esc(c.mode_label)}</span><span class="spacer"></span><span class="small">Run by ${esc(c.created_by)} · ${fmtTime(c.created_at)}</span></div>
    <div style="margin:12px 0">
      <span class="stat"><b>${c.stats.rows}</b><span>lines in the form</span></span>
      <span class="stat"><b>${c.stats.unanimous_rows}</b><span>identical everywhere</span></span>
      <span class="stat"><b>${c.stats.items}</b><span>differences to decide</span></span>
      <span class="stat"><b>${c.stats.by_kind.missing}</b><span>missing in some</span></span>
      <span class="stat"><b>${c.stats.by_kind.extra}</b><span>added in some</span></span>
      <span class="stat"><b>${c.stats.by_kind.wording}</b><span>wording differs</span></span>
      <span class="stat"><b>${c.stats.ocr_only}</b><span>only in OCR readings</span></span>
    </div>
    <div class="row" style="margin-bottom:10px"><span class="small"><span class="st same"></span>same <span class="st modified"></span>worded differently <span class="st missing"></span>absent <span class="st extra"></span>added <span class="st merged"></span>joined with line above</span><span class="spacer"></span><button class="btn gold" onclick="location.hash='#/f/${c.family_id}/reconcile'">Next: reconcile ${c.undecided} →</button></div>
    <div style="overflow:auto;max-height:640px">
    <table class="matrix"><thead><tr><th>#</th>${docs.map((d) => `<th>${esc(d.label)}${d.is_anchor ? " ★" : ""}${d.is_base ? " ▣" : ""}</th>`).join("")}</tr></thead><tbody>
    ${c.rows.map((r, n) => {
      const it = itemsByRow[r.id];
      return `<tr class="${it ? "diff" : ""}"><td class="small">${n + 1}${it ? `<br><a href="#/f/${c.family_id}/reconcile" onclick="state.filter='all'">${it.id}</a>` : ""}</td>${docs.map((d) => {
        const cell = r.cells[d.id] || { status: "missing" };
        const txt = cell.text ? esc(cell.text) : "";
        return `<td class="cell">${cell.segs && cell.segs.length ? `<a href="javascript:void(0)" onclick="showSource('${d.id}','${cell.segs.join(",")}')"><span class="st ${cell.status}"></span></a>` : `<span class="st ${cell.status}"></span>`}${txt}${cell.moved ? ' <span class="small">(moved)</span>' : ""}</td>`;
      }).join("")}</tr>`;
    }).join("")}
    </tbody></table></div>
    <p class="small">★ alignment anchor (${c.mode === "approved_reference" ? "approved reference" : "visual base"}) · ▣ visual base. Click a colored marker to see that line in its source document.</p>
    ${c.notes.length ? `<details><summary class="small">${c.notes.length} layout-only notes (same wording, different position)</summary><ul class="small">${c.notes.map((n) => `<li>${esc(n.text)}: ${esc(n.detail)}</li>`).join("")}</ul></details>` : ""}
  </div>`;
}
window.showSource = (did, segs) => guard(async () => {
  const h = await api(`/api/documents/${did}/highlight?segs=${segs}`);
  const pg = h.segments.find((s) => s.page !== undefined);
  let viewer = "";
  if (h.has_preview && pg) {
    viewer = `<div class="viewer"><img src="/api/documents/${did}/pages/${pg.page}.png" alt="Source page">${h.segments.filter((s) => s.rect && s.page === pg.page).map((s) => `<div class="hl" style="left:${s.rect[0] * 100}%;top:${s.rect[1] * 100}%;width:${(s.rect[2] - s.rect[0]) * 100}%;height:${(s.rect[3] - s.rect[1]) * 100}%"></div>`).join("")}</div>`;
  }
  const loc = h.segments.map((s) => {
    const l = s.loc;
    if (l.page !== undefined) return `page ${l.page + 1}`;
    if (l.kind) return l.kind === "p" ? `paragraph ${l.body + 1}` : `table ${esc(l.row)} column ${l.col + 1}`;
    if (l.line !== undefined) return `line ${l.line + 1}, column ${l.col + 1}`;
    return "";
  });
  openModal(`<h2>${esc(h.label)}</h2><p class="small">${h.kind.toUpperCase()} · ${esc([...new Set(loc)].join("; "))}${h.segments.some((s) => s.conf != null) ? ` · OCR confidence ${h.segments.map((s) => s.conf).join(", ")}%` : ""}</p>
    ${viewer}<h3 style="margin-top:12px">Text around this line</h3><div class="ctx">${h.context.map((c) => `<div class="${c.hit ? "hit" : ""}">${esc(c.text)}</div>`).join("")}</div>`);
});

// ------------------------------------------------------------- reconcile
function tabReconcile(el) {
  const c = state.cmp;
  if (!c) { el.innerHTML = '<div class="card empty">Run a comparison first.</div>'; return; }
  const all = c.items;
  const flt = state.filter;
  const shown = all.filter((i) => flt === "all" || (flt === "undecided" && !i.decision) || (flt === "decided" && i.decision) || (flt === "minor" && i.minor) || (flt === "ocr" && i.ocr_only));
  const pct = all.length ? Math.round((c.decided / all.length) * 100) : 100;
  el.innerHTML = `
    <div class="card">
      <div class="row"><h2 style="margin:0">Decide each difference</h2><span class="badge ${c.mode === "approved_reference" ? "ok" : "warn"}">${esc(c.mode_label)}</span></div>
      <p class="small">Each proposal is marked: in reference mode it is the approved reference's wording, in consensus mode the wording most versions use. Nothing reaches the master until a named person chooses. Departing from a proposal needs a reason, which is kept in the record.</p>
      <div class="row"><div style="flex:1"><div class="progress"><div style="width:${pct}%"></div></div></div><b>${c.decided} of ${all.length} decided</b></div>
      <div class="row" style="margin-top:12px">
        <div class="filters">${[["undecided", "Undecided"], ["all", "All"], ["decided", "Decided"], ["minor", "Minor"], ["ocr", "Only in OCR readings"]].map(([k, v]) => `<button class="btn ghost small ${flt === k ? "on" : ""}" onclick="state.filter='${k}';refresh()">${v}</button>`).join("")}</div>
        <span class="spacer"></span>
        <button class="btn ghost small" onclick="bulk('minor')" title="Accept the proposal on every undecided minor difference (punctuation, OCR noise, blank-line differences). Each is recorded under your name.">Accept proposals: minor</button>
        <button class="btn ghost small" onclick="bulk('all')" title="Accept the proposal on every remaining difference. Each is recorded under your name.">Accept all remaining proposals</button>
        ${c.undecided === 0 ? `<button class="btn gold" onclick="location.hash='#/f/${c.family_id}/master'">Next: generate master →</button>` : ""}
      </div>
    </div>
    ${shown.map(itemCard).join("") || '<div class="card empty">Nothing in this view.</div>'}`;
}
function itemCard(it) {
  const c = state.cmp;
  const dec = it.decision;
  const prop = it.proposal;
  const curChoice = state.choices[it.id] ?? (dec ? dec.choice : prop.choice);
  const vhtml = it.variants.map((v, k) => {
    const choice = v.absent ? "omit" : `variant:${k}`;
    const isProp = prop.choice === choice;
    const chosen = curChoice === choice;
    const diff = v.diff_vs_anchor && v.diff_vs_anchor.some((d) => d.op !== "equal") ? v.diff_vs_anchor.map((d) => d.op === "equal" ? esc(d.text) : d.op === "delete" ? `<del>${esc(d.text)}</del>` : `<ins>${esc(d.text)}</ins>`).join(" ") : esc(v.text);
    return `<div class="variant ${chosen ? "chosen" : ""}" onclick="pick('${it.id}','${choice}')">
      <input type="radio" name="ch-${it.id}" ${chosen ? "checked" : ""} aria-label="Choose this wording">
      <div><div class="txt">${v.absent ? '<span class="absent">Leave this line out (absent in these sources)</span>' : diff}${isProp ? '<span class="proposed">PROPOSED</span>' : ""}</div>
      <div class="chips">${v.sources.map((s) => `<span class="chip ${s.role === "approved_master" ? "ref" : ""}" ${s.segs.length ? `onclick="event.stopPropagation();showSource('${s.doc}','${s.segs.join(",")}')"` : ""} title="${s.segs.length ? "Show in source" : "Not present in this source"}">${esc(s.label)}${s.ocr ? " (OCR)" : ""}${s.moved ? " ↕" : ""}</span>`).join("")}</div></div></div>`;
  }).join("");
  const custom = curChoice === "custom";
  const needReason = curChoice !== prop.choice;
  return `<div class="item ${dec ? "decided" : ""}" id="it-${it.id}">
    <div class="head"><b>${it.id}</b>${kindBadge(it.kind)}${it.minor ? '<span class="badge">minor</span>' : ""}${it.ocr_only ? '<span class="badge warn">only in OCR readings</span>' : ""}
      <span class="spacer"></span>${dec ? `<span class="small">Decided by ${esc(dec.decided_by)} · ${fmtTime(dec.decided_at)}${dec.follows_proposal ? "" : " · departed from proposal"}</span> <button class="btn ghost small" onclick="decHistory('${it.id}')">History</button>` : '<span class="badge warn">Needs decision</span>'}</div>
    ${it.anchor_text ? `<div class="small">${c.mode === "approved_reference" ? "Approved reference reads" : "Visual base reads"}:</div><div class="anchor-text">${esc(it.anchor_text)}</div>` : `<div class="small">Not in the ${c.mode === "approved_reference" ? "approved reference" : "visual base"}.</div>`}
    <div class="small">Proposal basis: ${esc(prop.basis)}</div>
    ${vhtml}
    <div class="variant ${custom ? "chosen" : ""}" onclick="pick('${it.id}','custom')"><input type="radio" name="ch-${it.id}" ${custom ? "checked" : ""} aria-label="Custom wording"><div><div class="txt">Use custom wording…</div>
      ${custom ? `<textarea id="cu-${it.id}" onclick="event.stopPropagation()">${esc(dec && dec.choice === "custom" ? dec.text : (it.anchor_text || it.variants.find((v) => !v.absent)?.text || ""))}</textarea>` : ""}</div></div>
    <div class="row" style="margin-top:8px">
      <input type="text" id="rs-${it.id}" placeholder="${needReason ? "Reason for departing from the proposal (required)" : "Note (optional)"}" value="${esc(dec && dec.choice === curChoice ? dec.reason : "")}" style="flex:1">
      <button class="btn small" onclick="saveDecision('${it.id}')">${dec ? "Update decision" : "Record decision"}</button>
    </div>
  </div>`;
}
window.pick = (id, choice) => { state.choices[id] = choice; const it = state.cmp.items.find((i) => i.id === id); $(`#it-${id}`).outerHTML = itemCard(it); };
window.saveDecision = (id) => guard(async () => {
  const it = state.cmp.items.find((i) => i.id === id);
  const choice = state.choices[id] ?? (it.decision ? it.decision.choice : it.proposal.choice);
  const text = choice === "custom" ? ($(`#cu-${id}`) || {}).value : null;
  await api(`/api/comparisons/${state.cmp.id}/decisions`, { method: "POST", json: { item_id: id, choice, text, reason: $(`#rs-${id}`).value } });
  delete state.choices[id];
  toast(`${id} recorded`);
  refresh();
});
window.bulk = (scope) => guard(async () => {
  if (scope === "all" && !confirm("Accept the proposal for every remaining difference? Each acceptance is recorded under your name and can be changed until a master is generated.")) return;
  const r = await api(`/api/comparisons/${state.cmp.id}/accept`, { method: "POST", json: { scope } });
  toast(`${r.accepted} proposals accepted`); refresh();
});
window.decHistory = (id) => guard(async () => {
  const h = await api(`/api/comparisons/${state.cmp.id}/items/${id}/history`);
  openModal(`<h2>Decision history: ${id}</h2><table><thead><tr><th>When</th><th>Who</th><th>Choice</th><th>Wording</th><th>Reason</th></tr></thead><tbody>${h.map((d) => `<tr><td class="small">${fmtTime(d.decided_at)}</td><td>${esc(d.decided_by)}</td><td>${esc(d.choice)}${d.superseded_by ? ' <span class="badge">replaced</span>' : ' <span class="badge ok">current</span>'}</td><td>${esc(d.text) || "<i>omitted</i>"}</td><td>${esc(d.reason)}</td></tr>`).join("")}</tbody></table>`);
});

// ---------------------------------------------------------------- master
function tabMaster(el) {
  const c = state.cmp, f = state.family, r = state.rev;
  el.innerHTML = `
    <div class="card">
      <div class="row"><h2 style="margin:0">Generate a master revision</h2><span class="spacer"></span></div>
      ${c ? `<p class="small">From the current comparison (${esc(c.mode_label)}). ${c.undecided ? `<b>${c.undecided} difference(s) still need a decision.</b>` : "All differences are decided."}</p>
      <div class="row"><input type="text" id="gen-note" placeholder="Revision note (what changed and why)" style="flex:1"><button class="btn" id="gen-go" ${c.undecided ? "disabled" : ""}>Generate revision</button></div>` : '<p class="empty">Run a comparison first.</p>'}
    </div>
    <div class="grid two">
      <div class="card"><h2>Revisions</h2>
        ${f.revisions.map((x) => `<div class="row" style="padding:6px 0;border-bottom:1px solid var(--line);cursor:pointer" onclick="selectRev('${x.id}')">
          <b>Rev ${x.number}</b>${statusBadge(x.status)}<span class="small">${x.lines} lines · by ${esc(x.created_by)} · ${fmtTime(x.created_at)}</span><span class="spacer"></span>${r && r.id === x.id ? '<span class="badge navy">viewing</span>' : ""}</div>`).join("") || '<div class="empty">No revisions yet.</div>'}
      </div>
      ${r ? `<div class="card"><h2>Rev ${r.number} ${statusBadge(r.status)}</h2>
        <p class="small">${esc(r.note || "")}</p>
        <p class="small">Content fingerprint <span class="mono">${r.content_sha256.slice(0, 16)}…</span>${r.approved_by ? ` · approved by ${esc(r.approved_by)} ${fmtTime(r.approved_at)}` : ""}</p>
        ${r.status === "draft" ? `<label class="f" for="ap-text">Approval statement</label><textarea id="ap-text" placeholder="What you reviewed (for example: compared against the current official form dated …)"></textarea><div class="row" style="margin-top:8px"><button class="btn gold" id="ap-go" ${r.checklist_summary.fail ? "disabled" : ""}>Approve revision ${r.number}</button>${r.checklist_summary.fail ? '<span class="small" style="color:var(--bad)">Resolve failing checks first.</span>' : ""}</div>` : ""}
        ${r.parent_id ? `<div class="row" style="margin-top:10px"><button class="btn ghost small" onclick="showDiff('${r.parent_id}','${r.id}')">Compare with previous revision</button></div>` : ""}
      </div>` : ""}
    </div>
    ${r ? `<div class="card"><h2>Review checklist</h2><p class="small">Each check cites its evidence. This is a record of what was verified, not a legal-compliance score.</p>
      ${r.checklist.map((x) => `<div class="check"><div>${statusBadge(x.status)}</div><div><b>${esc(x.label)}</b><div class="small">${esc(x.evidence)}</div>${x.detail && x.detail.length ? `<details><summary class="small">Details</summary><pre class="mono" style="white-space:pre-wrap">${esc(JSON.stringify(x.detail, null, 1))}</pre></details>` : ""}</div></div>`).join("")}
    </div>
    <div class="card"><div class="row"><h2 style="margin:0">Master text, line by line</h2><span class="spacer"></span><button class="btn gold" onclick="location.hash='#/f/${f.id}/exports'">Next: export →</button></div>
      <p class="small">Shaded lines came from a decision; the rest were identical in every source.</p>
      ${r.final.map((l) => `<div class="final-line ${l.basis !== "unanimous" ? "dec" : ""}"><span class="small">${l.n}</span><span class="t">${esc(l.text)}</span><span class="small b">${l.basis === "unanimous" ? "same in all sources" : `${esc(l.basis)} ${l.item || ""}`}</span></div>`).join("")}
      ${r.omitted.length ? `<h3 style="margin-top:14px">Left out by decision</h3>${r.omitted.map((o) => `<div class="final-line"><span class="small">${o.item}</span><span class="t"><del>${esc(o.anchor_text || "(line not in anchor)")}</del></span><span class="small b">${esc(o.reason || "")}</span></div>`).join("")}` : ""}
    </div>` : ""}`;
  $("#gen-go") && ($("#gen-go").onclick = () => guard(async () => {
    state.rev = await api(`/api/comparisons/${c.id}/revisions`, { method: "POST", json: { note: $("#gen-note").value } });
    toast(`Revision ${state.rev.number} generated`); refresh();
  }));
  $("#ap-go") && ($("#ap-go").onclick = () => guard(async () => {
    state.rev = await api(`/api/revisions/${r.id}/approve`, { method: "POST", json: { attestation: $("#ap-text").value } });
    toast(`Revision ${state.rev.number} approved`); refresh();
  }));
}
window.selectRev = (id) => guard(async () => { state.rev = await api(`/api/revisions/${id}`); refresh(); });
window.showDiff = (a, b) => guard(async () => {
  const d = await api(`/api/revisions/${a}/diff/${b}`);
  openModal(`<h2>Changes between revisions</h2>${d.changes.map((c) => `<div class="card"><span class="badge">${c.op}</span> <span class="small">lines ${c.from_lines.join("-")} → ${c.to_lines.join("-")}</span>
    ${c.words.length ? `<div class="anchor-text">${c.words.map((w) => w.op === "equal" ? esc(w.text) : w.op === "delete" ? `<del>${esc(w.text)}</del>` : `<ins>${esc(w.text)}</ins>`).join(" ")}</div>` : `${c.from.map((t) => `<div class="anchor-text"><del>${esc(t)}</del></div>`).join("")}${c.to.map((t) => `<div class="anchor-text"><ins>${esc(t)}</ins></div>`).join("")}`}</div>`).join("") || '<p class="empty">No wording changes.</p>'}`);
});

// --------------------------------------------------------------- exports
function tabExports(el) {
  const r = state.rev;
  if (!r) { el.innerHTML = '<div class="card empty">Generate a master revision first.</div>'; return; }
  el.innerHTML = `
    <div class="card">
      <div class="row"><h2 style="margin:0">Export revision ${r.number}</h2>${statusBadge(r.status)}</div>
      <p class="small">Exports start from the visual base and keep its layout. After writing, each file is opened again and checked line by line: every master line present, required text present, removed wording gone, and for PDFs unchanged lines still in their original position.</p>
      <div class="row"><button class="btn" onclick="doExport('pdf')">PDF</button><button class="btn" onclick="doExport('docx')">Word (.docx)</button><button class="btn" onclick="doExport('txt')">Plain text</button>
        <label class="row small"><input type="checkbox" id="ex-footer"> Add a small revision footer to PDF pages</label></div>
      ${r.status === "draft" ? '<p class="small" style="color:var(--warn)">This revision is a draft. Exports are labeled with its status.</p>' : ""}
    </div>
    <div class="card"><h2>Files for this revision</h2>
      ${r.exports.length ? `<table><thead><tr><th>File</th><th>Format</th><th>Verification</th><th>Created</th><th></th></tr></thead><tbody>
        ${r.exports.slice().reverse().map((e) => `<tr><td class="mono">${esc(e.filename)}<div class="small">sha256 ${e.sha256.slice(0, 12)}… · ${(e.size / 1024).toFixed(1)} KB</div></td><td>${e.format.toUpperCase()}</td>
        <td>${e.passed ? '<span class="badge ok">Re-read: passed</span>' : '<span class="badge bad">Re-read: problems</span>'}</td><td class="small">${esc(e.created_by)}<br>${fmtTime(e.created_at)}</td>
        <td class="row"><button class="btn ghost small" onclick="showExport('${e.id}')">Report</button><a class="btn small" href="/api/exports/${e.id}/file">Download</a></td></tr>`).join("")}</tbody></table>` : '<div class="empty">No exports yet.</div>'}
    </div>`;
}
window.doExport = (fmt) => guard(async () => {
  toast(`Building ${fmt.toUpperCase()}…`);
  const e = await api(`/api/revisions/${state.rev.id}/exports`, { method: "POST", json: { format: fmt, footer: !!($("#ex-footer") || {}).checked } });
  toast(`${e.filename}: ${e.verification.passed ? "verified" : "check the report"}`);
  await refresh(); showExport(e.id);
});
window.showExport = (id) => guard(async () => {
  const e = await api(`/api/exports/${id}`);
  const v = e.verification;
  const lay = v.layout;
  openModal(`<h2>${esc(e.filename)}</h2>
    <p>${v.passed ? '<span class="badge ok">All checks passed</span>' : '<span class="badge bad">Some checks failed</span>'} <span class="small">Re-opened with the ${esc(v.extractor)} reader; ${v.segments_read} lines read back.</span></p>
    <table><tbody>
      <tr><td>Master lines found in file</td><td><b>${v.master_lines_found} of ${v.master_lines}</b>${v.missing_lines.length ? `<div class="small" style="color:var(--bad)">${v.missing_lines.map((m) => `${m.n}: ${esc(m.text)}`).join("<br>")}</div>` : ""}</td></tr>
      <tr><td>Required passages</td><td>${v.required.length ? v.required.map((q) => `${q.present ? "✓" : "✗"} ${esc(q.text)}`).join("<br>") : '<span class="small">none defined</span>'}</td></tr>
      <tr><td>Removed wording still present</td><td>${v.removed_wording_still_present.length ? `<span style="color:var(--bad)">${v.removed_wording_still_present.map(esc).join("<br>")}</span>` : "none"}</td></tr>
      ${lay && lay.rendered !== undefined ? `<tr><td>Layout (Word file rendered)</td><td>${lay.rendered ? `${lay.lines_in_position} of ${lay.lines} lines within ${lay.tolerance_pt} pt of their position in the master PDF` : esc(lay.reason)}</td></tr>` : ""}
      ${lay && lay.unchanged_lines !== undefined ? `<tr><td>Layout</td><td>${lay.unchanged_lines_in_original_position} of ${lay.unchanged_lines} unchanged lines in their original position · page size ${lay.page_size_matches_base ? "matches" : "differs from"} the base · vector rules/boxes: base ${lay.base_vector_paths}, export ${lay.export_vector_paths}</td></tr>` : ""}
      ${v.ocr_reread ? `<tr><td>OCR re-read of page images</td><td>${v.ocr_reread.legible_words} of ${v.ocr_reread.master_words} master words legible (${Math.round(v.ocr_reread.recall * 100)}%)</td></tr>` : ""}
      ${v.build && v.build.pdf_edit ? `<tr><td>Edits to the base</td><td>${plural(v.build.pdf_edit.replaced, "line")} reworded in place, ${v.build.pdf_edit.inserted} added, ${v.build.pdf_edit.removed} removed${v.build.pdf_edit.warnings.length ? `<div class="small" style="color:var(--warn)">${v.build.pdf_edit.warnings.map(esc).join("<br>")}</div>` : ""}</td></tr>` : ""}
      ${v.build && v.build.docx_edit ? `<tr><td>Edits to the base</td><td>${v.build.docx_edit.replaced} reworded, ${v.build.docx_edit.inserted} added, ${v.build.docx_edit.removed} removed</td></tr>` : ""}
      ${v.build && v.build.docx && v.build.docx.note ? `<tr><td>Note</td><td>${esc(v.build.docx.note)}</td></tr>` : ""}
    </tbody></table>
    ${e.format === "pdf" ? [...Array(v.pages || 1).keys()].map((p) => `<div class="viewer" style="margin-top:12px"><img src="/api/exports/${id}/pages/${p}.png" alt="Exported page ${p + 1}"></div>`).join("") : ""}
    <div class="row" style="margin-top:12px"><a class="btn" href="/api/exports/${id}/file">Download</a></div>`);
});

// --------------------------------------------------------------- history
async function tabHistory(el) {
  const [rows, chain] = await Promise.all([api(`/api/families/${state.family.id}/history`), api("/api/audit/verify")]);
  el.innerHTML = `<div class="card"><div class="row"><h2 style="margin:0">Activity record</h2><span class="spacer"></span>${chain.ok ? `<span class="badge ok">Hash chain intact · ${chain.entries} entries</span>` : `<span class="badge bad">Hash chain broken at entry ${chain.broken_at}</span>`}</div>
    <p class="small">Every upload, comparison, decision, revision, approval and export, in order. Each entry is chained to the one before it by SHA-256, so an edited entry is detectable.</p>
    <table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td class="small">${fmtTime(r.ts)}</td><td>${esc(r.actor)}</td><td><span class="badge">${esc(r.action)}</span></td><td class="small">${esc(summarize(r))}</td></tr>`).join("")}
    </tbody></table></div>`;
}
function summarize(r) {
  const d = r.details;
  switch (r.action) {
    case "document.uploaded": return `${d.filename} as ${d.role} (${d.kind}, ${d.segments} lines${d.ocr_used ? ", OCR" : ""}) sha256 ${d.sha256.slice(0, 12)}`;
    case "comparison.run": return `${d.mode}; ${d.stats.items} differences across ${d.documents.length} documents`;
    case "decision.recorded": return `${d.item_id}: ${d.choice}${d.text ? ` "${d.text}"` : ""}${d.reason ? ` - ${d.reason}` : ""}${d.supersedes ? " (replaces earlier decision)" : ""}`;
    case "revision.generated": return `rev ${d.number}: ${d.lines} lines, ${d.omitted} omitted, content ${d.content_sha256.slice(0, 12)}`;
    case "revision.approved": return `rev ${d.number} approved: ${d.attestation}`;
    case "export.created": return `rev ${d.number} ${d.format.toUpperCase()} sha256 ${d.sha256.slice(0, 12)}; re-read ${d.verification_passed ? "passed" : "FAILED"}`;
    default: return JSON.stringify(d);
  }
}

route().catch((e) => { app.innerHTML = `<div class="card">Could not start: ${esc(e.message)}</div>`; });

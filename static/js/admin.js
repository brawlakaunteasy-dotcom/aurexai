/* AurexAi admin panel — simplified.
 * OpenRouter doimiy ulangan; admin faqat kalit + model qo'shadi.
 */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  return r.json();
}

// Tabs ----------------------------------------------------------------------
$$(".admin-tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".admin-tabs button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $$(".admin-panel").forEach((p) => (p.hidden = p.id !== "tab-" + b.dataset.tab));
    if (b.dataset.tab === "users") loadUsers();
    if (b.dataset.tab === "keys") loadKeys();
    if (b.dataset.tab === "models") loadModels();
  }),
);

// Settings ------------------------------------------------------------------
async function loadSettings() {
  const j = await api("/admin/api/settings");
  $("#siteName").value = j.settings.site_name || "";
  $("#siteLogo").value = j.settings.site_logo || "";
  $("#adminTg").value = j.settings.admin_telegram || "";
}
$("#saveSettings").addEventListener("click", async () => {
  const btn = $("#saveSettings");
  btn.disabled = true;
  await api("/admin/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      site_name: $("#siteName").value.trim(),
      site_logo: $("#siteLogo").value.trim(),
      admin_telegram: $("#adminTg").value.trim(),
    }),
  });
  btn.disabled = false;
  toast("Saqlandi");
});

// Users ---------------------------------------------------------------------
async function loadUsers() {
  const t = $("#usersTable");
  t.innerHTML = "Yuklanmoqda...";
  const j = await api("/admin/api/users");
  let html = `<table><tr><th>ID</th><th>Username</th><th>Email</th><th>Tarif</th><th>Tugaydi</th><th>Xotira</th><th>Amallar</th></tr>`;
  for (const u of j.users) {
    html += `<tr>
      <td>${u.id}</td>
      <td>${escapeHtml(u.username)}${u.is_admin ? " 👑" : ""}</td>
      <td>${escapeHtml(u.email)}</td>
      <td><select data-uid="${u.id}" class="setplan">
        <option ${u.plan === "ODDIY" ? "selected" : ""}>ODDIY</option>
        <option ${u.plan === "PRO" ? "selected" : ""}>PRO</option>
        <option ${u.plan === "PLUS" ? "selected" : ""}>PLUS</option>
      </select></td>
      <td>${u.plan_expires_at ? new Date(u.plan_expires_at).toLocaleDateString() : "—"}</td>
      <td>${(u.memory_used / 1024 / 1024).toFixed(1)} MB</td>
      <td>
        <button class="neon-btn small grant" data-uid="${u.id}">30 kun beruv</button>
        <button class="neon-btn small wipe" data-uid="${u.id}">Tozalash</button>
      </td>
    </tr>`;
  }
  html += `</table>`;
  t.innerHTML = html;
  t.querySelectorAll(".grant").forEach((b) =>
    b.addEventListener("click", async () => {
      const uid = b.dataset.uid;
      const sel = t.querySelector(`select[data-uid="${uid}"]`);
      await api(`/admin/api/users/${uid}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: sel.value, days: 30 }),
      });
      toast("Tarif berildi");
      loadUsers();
    }),
  );
  t.querySelectorAll(".wipe").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Foydalanuvchining barcha chatlari tozalansinmi?")) return;
      await api(`/admin/api/users/${b.dataset.uid}/wipe`, { method: "POST" });
      toast("Tozalandi");
      loadUsers();
    }),
  );
}

// OpenRouter keys -----------------------------------------------------------
async function loadKeys() {
  const j = await api("/admin/api/openrouter/keys");
  const list = $("#keysList");
  if (!j.keys.length) {
    list.innerHTML = `<div class="muted" style="padding:12px 0">Hali kalit qo'shilmagan.</div>`;
    return;
  }
  list.innerHTML = j.keys
    .map(
      (k) => `
    <div class="item">
      <div>
        <b>${escapeHtml(k.label || "key")}</b>
        <code>${k.secret_masked}</code>
        <span class="muted">${k.failures ? "· xatolar: " + k.failures : ""}${k.last_used_at ? " · oxirgi: " + new Date(k.last_used_at).toLocaleString() : ""}</span>
      </div>
      <div><button class="neon-btn small del" data-id="${k.id}">O'chirish</button></div>
    </div>`,
    )
    .join("");
  list.querySelectorAll(".del").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Kalit o'chirilsinmi?")) return;
      await api(`/admin/api/keys/${b.dataset.id}`, { method: "DELETE" });
      loadKeys();
    }),
  );
}
$("#addKey").addEventListener("click", async () => {
  const label = $("#keyLabel").value.trim() || "key";
  const secret = $("#keySecret").value.trim();
  if (!secret) return toast("Kalit bo'sh bo'lmasin");
  const r = await api("/admin/api/openrouter/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, secret }),
  });
  if (!r.ok) return toast(r.error || "Xato");
  $("#keyLabel").value = "";
  $("#keySecret").value = "";
  toast("Kalit qo'shildi");
  loadKeys();
});

// Models --------------------------------------------------------------------
async function loadModels() {
  const j = await api("/admin/api/models");
  const list = $("#modelsList");
  if (!j.models.length) {
    list.innerHTML = `<div class="muted" style="padding:12px 0">Hali model qo'shilmagan.</div>`;
    return;
  }
  list.innerHTML = j.models
    .map(
      (m) => `
    <div class="item">
      <div>
        <b>${escapeHtml(m.display_name)}</b> · <code>${escapeHtml(m.model_id)}</code><br>
        <span class="muted">${m.service || "OpenRouter"} · min: ${m.min_plan}${m.is_codex ? " · CODEX" : ""}${m.enabled ? "" : " · o'chirilgan"}</span>
      </div>
      <div><button class="neon-btn small del" data-id="${m.id}">O'chirish</button></div>
    </div>`,
    )
    .join("");
  list.querySelectorAll(".del").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Model o'chirilsinmi?")) return;
      await api(`/admin/api/models/${b.dataset.id}`, { method: "DELETE" });
      loadModels();
    }),
  );
}
$("#addModel").addEventListener("click", async () => {
  const display_name = $("#mdlName").value.trim();
  const model_id = $("#mdlId").value.trim();
  if (!display_name || !model_id) return toast("Nom va model_id kerak");
  const r = await api("/admin/api/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name,
      model_id,
      min_plan: $("#mdlPlan").value,
      is_codex: $("#mdlCodex").checked,
    }),
  });
  if (!r.ok) return toast(r.error || "Xato");
  $("#mdlName").value = "";
  $("#mdlId").value = "";
  $("#mdlCodex").checked = false;
  toast("Model qo'shildi");
  loadModels();
});

// Helpers -------------------------------------------------------------------
function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
let toastTimer;
function toast(msg) {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), 1800);
}

loadSettings();

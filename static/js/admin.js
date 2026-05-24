/* AurexAi admin panel — settings, users, payments, keys, models. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  return r.json();
}

// Tabs ----------------------------------------------------------------------
$$(".admin-tabs button[data-tab]").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".admin-tabs button[data-tab]").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $$(".admin-panel").forEach((p) => (p.hidden = p.id !== "tab-" + b.dataset.tab));
    if (b.dataset.tab === "users")    loadUsers();
    if (b.dataset.tab === "payments") loadPayments();
    if (b.dataset.tab === "keys")     loadKeys();
    if (b.dataset.tab === "models")   loadModels();
  }),
);

// Settings ------------------------------------------------------------------
async function loadSettings() {
  const j = await api("/admin/api/settings");
  $("#siteName").value = j.settings.site_name || "";
  $("#siteLogo").value = j.settings.site_logo || "";
  $("#adminTg").value = j.settings.admin_telegram || "";
  $("#payCard").value = j.settings.payment_card || "";
  $("#payHolder").value = j.settings.payment_card_holder || "";
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
      payment_card: $("#payCard").value.trim(),
      payment_card_holder: $("#payHolder").value.trim(),
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
  let html = `<table><tr><th>ID</th><th>Username</th><th>Email</th><th>Tarif</th><th>Tugaydi</th><th>Xotira</th><th>Kredit</th><th>Amallar</th></tr>`;
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
      <td>${u.credits_used_today || 0}</td>
      <td>
        <button class="neon-btn small grant" data-uid="${u.id}">30 kun</button>
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
        method: "POST", headers: { "Content-Type": "application/json" },
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

// Payments ------------------------------------------------------------------
let paymentsFilter = "pending";

$$(".filter-btn").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".filter-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    paymentsFilter = b.dataset.filter;
    loadPayments();
  }),
);

async function loadPayments() {
  const list = $("#paymentsList");
  list.innerHTML = "Yuklanmoqda...";
  const url = paymentsFilter === "all"
    ? "/admin/api/payments"
    : `/admin/api/payments?status=${paymentsFilter}`;
  const j = await api(url);
  if (!j.ok) {
    list.innerHTML = `<div class="muted">Xato</div>`;
    return;
  }

  // Update badge for pending
  if (paymentsFilter === "pending") {
    const badge = $("#payBadge");
    badge.textContent = j.payments.length;
    badge.hidden = j.payments.length === 0;
  }

  if (!j.payments.length) {
    list.innerHTML = `<div class="muted">Hech narsa yo'q</div>`;
    return;
  }
  list.innerHTML = j.payments.map((p) => `
    <div class="payment-row status-${p.status}">
      <div class="payment-info">
        <b>#${p.id} · ${p.plan}</b> · ${(p.amount).toLocaleString()} so'm
        <span class="status-pill status-${p.status}">${({pending:'⏳',approved:'✅',rejected:'❌'})[p.status]} ${p.status}</span>
        <div class="muted">👤 ${escapeHtml(p.username || '?')} · ${escapeHtml(p.email || '?')}</div>
        <div class="muted">${new Date(p.created_at).toLocaleString()}</div>
        ${p.note ? `<div class="muted">📝 ${escapeHtml(p.note)}</div>` : ""}
        ${p.reject_reason ? `<div class="reject-reason">Sabab: ${escapeHtml(p.reject_reason)}</div>` : ""}
      </div>
      ${p.receipt_url ? `<a href="${p.receipt_url}" target="_blank"><img src="${p.receipt_url}" class="payment-thumb"></a>` : ""}
      ${p.status === "pending" ? `
        <div class="payment-actions">
          <button class="neon-btn small approve" data-id="${p.id}">✅ Tasdiqlash (30 kun)</button>
          <button class="neon-btn small reject" data-id="${p.id}">❌ Rad etish</button>
        </div>` : ""}
    </div>`).join("");

  list.querySelectorAll(".approve").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("To'lov tasdiqlansinmi? Foydalanuvchiga 30 kunlik tarif beriladi.")) return;
    const r = await api(`/admin/api/payments/${b.dataset.id}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: 30 }),
    });
    if (!r.ok) return alert("❌ " + (r.error || "Xato"));
    toast("Tasdiqlandi");
    loadPayments();
  }));
  list.querySelectorAll(".reject").forEach((b) => b.addEventListener("click", async () => {
    const reason = prompt("Rad etish sababini yozing (foydalanuvchiga ko'rinadi):");
    if (!reason || !reason.trim()) return;
    const r = await api(`/admin/api/payments/${b.dataset.id}/reject`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason.trim() }),
    });
    if (!r.ok) return alert("❌ " + (r.error || "Xato"));
    toast("Rad etildi");
    loadPayments();
  }));
}

// OpenRouter quick keys ------------------------------------------------------
async function loadKeys() {
  const j = await api("/admin/api/openrouter/keys");
  const list = $("#keysList");
  if (!j.keys || !j.keys.length) {
    list.innerHTML = `<div class="muted" style="padding:12px 0">Hali kalit qo'shilmagan.</div>`;
    return;
  }
  list.innerHTML = j.keys.map((k) => `
    <div class="item">
      <div>
        <b>${escapeHtml(k.label || "key")}</b>
        <code>${k.secret_masked}</code>
        <span class="muted">${k.failures ? "· xatolar: " + k.failures : ""}${k.last_used_at ? " · oxirgi: " + new Date(k.last_used_at).toLocaleString() : ""}</span>
      </div>
      <div><button class="neon-btn small del" data-id="${k.id}">O'chirish</button></div>
    </div>`).join("");
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
    method: "POST", headers: { "Content-Type": "application/json" },
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
  // Refresh folder dropdown
  const f = await api("/admin/api/folders");
  const sel = $("#mdlFolder");
  sel.innerHTML = `<option value="">Standart (OpenRouter)</option>` +
    (f.folders || []).map(fo =>
      `<option value="${fo.id}">${escapeHtml(fo.service || '?')} · ${escapeHtml(fo.name)} (${fo.key_count} kalit)</option>`,
    ).join("");

  const j = await api("/admin/api/models");
  const list = $("#modelsList");
  if (!j.models.length) {
    list.innerHTML = `<div class="muted" style="padding:12px 0">Hali model qo'shilmagan.</div>`;
    return;
  }
  list.innerHTML = j.models.map((m) => `
    <div class="item">
      <div>
        <b>${escapeHtml(m.display_name)}</b> · <code>${escapeHtml(m.model_id)}</code><br>
        <span class="muted">📁 ${escapeHtml(m.service || "OpenRouter")} / ${escapeHtml(m.folder_name || "default")}
          · min: ${m.min_plan}${m.is_codex ? " · 🚀 CODEX" : ""}${m.is_image_gen ? " · 🖼 IMAGE" : ""}${m.enabled ? "" : " · ❌ o'chirilgan"}</span>
      </div>
      <div><button class="neon-btn small del" data-id="${m.id}">O'chirish</button></div>
    </div>`).join("");
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
  const folder_id = $("#mdlFolder").value || null;
  const r = await api("/admin/api/models", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name, model_id,
      folder_id: folder_id ? parseInt(folder_id) : null,
      min_plan: $("#mdlPlan").value,
      is_codex: $("#mdlCodex").checked,
      is_image_gen: $("#mdlImage").checked,
    }),
  });
  if (!r.ok) return toast(r.error || "Xato");
  $("#mdlName").value = "";
  $("#mdlId").value = "";
  $("#mdlCodex").checked = false;
  $("#mdlImage").checked = false;
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

// Init pending payments badge on load
async function initPendingBadge() {
  const j = await api("/admin/api/payments?status=pending");
  if (j.ok) {
    const badge = $("#payBadge");
    badge.textContent = j.payments.length;
    badge.hidden = j.payments.length === 0;
  }
}

loadSettings();
initPendingBadge();

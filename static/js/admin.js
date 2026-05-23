/* Admin panel front-end */
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

async function api(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

// Tabs
$$(".admin-tabs button").forEach(b => b.addEventListener("click", () => {
  $$(".admin-tabs button").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  $$(".admin-panel").forEach(p => p.hidden = (p.id !== "tab-" + b.dataset.tab));
  if (b.dataset.tab === "users")    loadUsers();
  if (b.dataset.tab === "services") loadServices();
  if (b.dataset.tab === "keys")     loadKeysTab();
  if (b.dataset.tab === "models")   loadModelsTab();
}));

// Settings ------------------------------------------------------------------
async function loadSettings() {
  const j = await api("/admin/api/settings");
  $("#siteName").value = j.settings.site_name || "";
  $("#siteLogo").value = j.settings.site_logo || "";
  $("#adminTg").value  = j.settings.admin_telegram || "";
}
$("#saveSettings").addEventListener("click", async () => {
  await api("/admin/api/settings", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      site_name: $("#siteName").value,
      site_logo: $("#siteLogo").value,
      admin_telegram: $("#adminTg").value,
    })
  });
  alert("Saqlandi");
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
      <td>${u.username}${u.is_admin?" 👑":""}</td>
      <td>${u.email}</td>
      <td><select data-uid="${u.id}" class="setplan">
        <option ${u.plan==="ODDIY"?"selected":""}>ODDIY</option>
        <option ${u.plan==="PRO"  ?"selected":""}>PRO</option>
        <option ${u.plan==="PLUS" ?"selected":""}>PLUS</option>
      </select></td>
      <td>${u.plan_expires_at ? new Date(u.plan_expires_at).toLocaleDateString() : "—"}</td>
      <td>${(u.memory_used/1024/1024).toFixed(1)} MB</td>
      <td>
        <button class="neon-btn small grant" data-uid="${u.id}">30 kun beruv</button>
        <button class="neon-btn small wipe"  data-uid="${u.id}">Tozalash</button>
      </td>
    </tr>`;
  }
  html += `</table>`;
  t.innerHTML = html;
  t.querySelectorAll(".grant").forEach(b => b.addEventListener("click", async () => {
    const uid = b.dataset.uid;
    const sel = t.querySelector(`select[data-uid="${uid}"]`);
    await api(`/admin/api/users/${uid}/plan`, { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ plan: sel.value, days: 30 }) });
    loadUsers();
  }));
  t.querySelectorAll(".wipe").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("Foydalanuvchining barcha chatlari tozalansinmi?")) return;
    await api(`/admin/api/users/${b.dataset.uid}/wipe`, { method:"POST" });
    loadUsers();
  }));
}

// Services ------------------------------------------------------------------
async function loadServices() {
  const j = await api("/admin/api/services");
  const list = $("#servicesList");
  list.innerHTML = (j.services||[]).map(s => `
    <div class="item">
      <div>
        <b>${s.name}</b> <span class="muted">(${s.request_format})</span><br>
        <span class="muted">${s.base_url}</span><br>
        <span class="muted">Papkalar: ${s.folders.length}, kalitlar: ${s.folders.reduce((a,f)=>a+f.key_count,0)}</span>
      </div>
      <div>
        <button class="neon-btn small addFolder" data-id="${s.id}">+ Papka</button>
        <button class="neon-btn small del" data-id="${s.id}">O'chirish</button>
      </div>
    </div>`).join("") || "<i>Bo'sh</i>";
  list.querySelectorAll(".del").forEach(b => b.onclick = async () => {
    if (!confirm("O'chirilsinmi?")) return;
    await api(`/admin/api/services/${b.dataset.id}`, {method:"DELETE"});
    loadServices();
  });
  list.querySelectorAll(".addFolder").forEach(b => b.onclick = async () => {
    const name = prompt("Papka nomi:", "default");
    if (!name) return;
    await api(`/admin/api/services/${b.dataset.id}/folders`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ name }) });
    loadServices();
  });
}
$("#addSvc").addEventListener("click", async () => {
  const name = $("#svcName").value.trim();
  const base_url = $("#svcUrl").value.trim();
  if (!name || !base_url) return alert("Nom va URL kiriting");
  await api("/admin/api/services", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ name, base_url, request_format: $("#svcFmt").value })});
  $("#svcName").value = ""; $("#svcUrl").value = "";
  loadServices();
});

// Keys tab ------------------------------------------------------------------
async function loadKeysTab() {
  const j = await api("/admin/api/services");
  let html = "";
  for (const s of (j.services||[])) {
    html += `<div class="item"><div><b>${s.name}</b></div></div>`;
    for (const f of s.folders) {
      html += `<div class="item">
        <div>📁 <b>${f.name}</b> <span class="muted">(${f.key_count} kalit)</span></div>
        <div>
          <button class="neon-btn small viewKeys" data-id="${f.id}">Ko'rish</button>
          <button class="neon-btn small addKey"   data-id="${f.id}">+ Kalit</button>
          <button class="neon-btn small delF"     data-id="${f.id}">O'chirish</button>
        </div>
      </div>
      <div id="keys-${f.id}"></div>`;
    }
  }
  $("#keysPanel").innerHTML = html || "Avval API xizmat va papka qo'shing.";
  $("#keysPanel").querySelectorAll(".addKey").forEach(b => b.onclick = async () => {
    const secret = prompt("API kalit:");
    if (!secret) return;
    const label = prompt("Yorliq (ixtiyoriy):", "key") || "key";
    await api(`/admin/api/folders/${b.dataset.id}/keys`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ secret, label })});
    loadKeysTab();
  });
  $("#keysPanel").querySelectorAll(".delF").forEach(b => b.onclick = async () => {
    if (!confirm("Papka va ichidagi barcha kalitlar o'chirilsinmi?")) return;
    await api(`/admin/api/folders/${b.dataset.id}`, {method:"DELETE"});
    loadKeysTab();
  });
  $("#keysPanel").querySelectorAll(".viewKeys").forEach(b => b.onclick = async () => {
    const j = await api(`/admin/api/folders/${b.dataset.id}/keys`);
    const target = $("#keys-" + b.dataset.id);
    target.innerHTML = j.keys.map(k => `
      <div class="item">
        <div><b>${k.label}</b> · <code>${k.secret_masked}</code> <span class="muted">(xato: ${k.failures})</span></div>
        <div><button class="neon-btn small delK" data-id="${k.id}">O'chirish</button></div>
      </div>`).join("");
    target.querySelectorAll(".delK").forEach(x => x.onclick = async () => {
      await api(`/admin/api/keys/${x.dataset.id}`, {method:"DELETE"});
      loadKeysTab();
    });
  });
}

// Models tab ----------------------------------------------------------------
async function loadModelsTab() {
  const svcs = (await api("/admin/api/services")).services || [];
  $("#mdlSvc").innerHTML = svcs.map(s => `<option value="${s.id}">${s.name}</option>`).join("");
  refreshFolderSelect();
  $("#mdlSvc").onchange = refreshFolderSelect;

  function refreshFolderSelect() {
    const svc = svcs.find(s => s.id == $("#mdlSvc").value);
    $("#mdlFolder").innerHTML = (svc?.folders||[]).map(f => `<option value="${f.id}">${f.name}</option>`).join("");
  }

  const j = await api("/admin/api/models");
  $("#modelsList").innerHTML = (j.models||[]).map(m => `
    <div class="item">
      <div>
        <b>${m.display_name}</b> · <code>${m.model_id}</code><br>
        <span class="muted">${m.service} · min: ${m.min_plan}${m.is_codex?" · CODEX":""}${m.enabled?"":" · o'chirilgan"}</span>
      </div>
      <div><button class="neon-btn small del" data-id="${m.id}">O'chirish</button></div>
    </div>`).join("") || "<i>Bo'sh</i>";
  $("#modelsList").querySelectorAll(".del").forEach(b => b.onclick = async () => {
    if (!confirm("Model o'chirilsinmi?")) return;
    await api(`/admin/api/models/${b.dataset.id}`, {method:"DELETE"});
    loadModelsTab();
  });
}
$("#addModel").addEventListener("click", async () => {
  await api("/admin/api/models", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({
      display_name: $("#mdlName").value.trim(),
      model_id: $("#mdlId").value.trim(),
      service_id: parseInt($("#mdlSvc").value),
      folder_id: parseInt($("#mdlFolder").value),
      min_plan: $("#mdlPlan").value,
      is_codex: $("#mdlCodex").checked,
    }),
  });
  $("#mdlName").value = ""; $("#mdlId").value = "";
  loadModelsTab();
});

// Init ----------------------------------------------------------------------
loadSettings();

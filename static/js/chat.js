/* AurexAi main chat — per-chat model locking + 429-aware streaming UI. */
(function () {
  let me = null;
  let currentChat = null;     // {id, model_id, model_name, ...} or null
  let models = [];
  let plan = "ODDIY";

  const $ = (s) => document.querySelector(s);
  const messagesEl = $("#messages");
  const composer = $("#composer");
  const input = $("#composerInput");
  const modelSel = $("#modelSelect");
  const chatList = $("#chatList");
  const memFill = $("#memoryFill");
  const memText = $("#memoryText");

  // -------- bootstrap ------------------------------------------------------
  async function loadMe() {
    const r = await fetch("/api/auth/me").then((x) => x.json());
    me = r.authenticated ? r.user : null;
    if (me) {
      plan = me.plan;
      if (me.is_admin) document.getElementById("adminBtn").style.display = "inline-flex";
      await loadModels();
      await loadChats();
      updateMemoryBar();
      applyModelLock();
    } else {
      modelSel.innerHTML = `<option value="">Kirish kerak</option>`;
    }
  }

  async function loadChats() {
    const j = await fetch("/api/chat/list").then((r) => r.json());
    if (!j.ok) return;
    chatList.innerHTML = "";
    j.chats.forEach((c) => {
      const div = document.createElement("div");
      div.className = "chat-item" + (currentChat && c.id === currentChat.id ? " active" : "");
      div.dataset.id = c.id;
      div.dataset.modelId = c.model_id || "";
      const lockIcon = c.model_id
        ? `<span class="chat-lock" title="${escapeHtml(c.model_name || "")}">&#128274;</span>`
        : "";
      div.innerHTML = `<span class="chat-title">${lockIcon}${escapeHtml(c.title || "Suhbat")}</span><span class="x" title="O'chirish">&times;</span>`;
      div.addEventListener("click", (e) => {
        if (e.target.classList.contains("x")) {
          if (!confirm("Ushbu suhbat o'chirilsinmi?")) return;
          fetch(`/api/chat/${c.id}`, { method: "DELETE" }).then(() => {
            if (currentChat && currentChat.id === c.id) {
              currentChat = null;
              renderHero();
              applyModelLock();
            }
            loadChats();
          });
        } else openChat(c.id);
      });
      chatList.appendChild(div);
    });
  }

  async function loadModels() {
    const j = await fetch("/api/chat/models").then((r) => r.json());
    models = j.models || [];
    plan = j.plan || "ODDIY";
    renderModelOptions();
  }

  function renderModelOptions() {
    if (!models.length) {
      modelSel.innerHTML = `<option>Hech model yo'q (admin qo'shsin)</option>`;
      return;
    }
    modelSel.innerHTML = models
      .map(
        (m) =>
          `<option value="${m.id}" ${m.allowed ? "" : "disabled"}>${escapeHtml(m.display_name)} · ${m.min_plan}${m.allowed ? "" : " · qulflangan"}</option>`,
      )
      .join("");
    const firstAllowed = models.find((m) => m.allowed);
    if (firstAllowed) modelSel.value = firstAllowed.id;
  }

  function applyModelLock() {
    if (currentChat && currentChat.model_id) {
      modelSel.value = currentChat.model_id;
      modelSel.disabled = true;
      modelSel.title = "Bu suhbat shu modelga bog'langan";
    } else {
      modelSel.disabled = false;
      modelSel.title = "Suhbat uchun model tanlang";
    }
  }

  function updateMemoryBar() {
    if (!me) return;
    const limits = { ODDIY: 100 * 1024 * 1024, PRO: 500 * 1024 * 1024, PLUS: 1024 * 1024 * 1024 };
    const limit = limits[plan] || limits.ODDIY;
    const used = me.memory_used || 0;
    const pct = Math.min(100, Math.round((used / limit) * 100));
    memFill.style.width = pct + "%";
    memText.textContent = `${(used / 1024 / 1024).toFixed(1)} / ${(limit / 1024 / 1024).toFixed(0)} MB · ${plan}`;
  }

  // -------- auth modal -----------------------------------------------------
  function openAuthModal(mode = "login") {
    const modal = $("#authModal");
    const frame = $("#authFrame");
    frame.src = "/" + mode;
    modal.style.display = "grid";
  }
  function closeAuthModal() {
    $("#authModal").style.display = "none";
    $("#authFrame").src = "";
  }
  window.addEventListener("message", async (e) => {
    if (e.data && e.data.type === "aurex-auth-ok") {
      closeAuthModal();
      await loadMe();
    }
  });

  // -------- chat rendering -------------------------------------------------
  function renderHero() {
    messagesEl.innerHTML = `<div class="hero">
      <h2>Salom, men <span class="grad">${escapeHtml(window.AUREX.siteName)}</span></h2>
      <p>Modelni tanlang va savol bering. Tanlangan model ushbu suhbatga bog'lanadi.</p>
    </div>`;
  }

  function appendMessage(role, content) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "assistant");
    wrap.innerHTML = `<div class="avatar"></div><div class="bubble"></div>`;
    wrap.querySelector(".bubble").textContent = content;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap.querySelector(".bubble");
  }

  function appendStatus(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg-status";
    wrap.textContent = text;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }

  async function openChat(id) {
    const j = await fetch(`/api/chat/${id}`).then((r) => r.json());
    if (!j.ok) return;
    currentChat = j.chat;
    document.querySelectorAll(".chat-item").forEach((el) =>
      el.classList.toggle("active", parseInt(el.dataset.id) === id),
    );
    messagesEl.innerHTML = "";
    j.messages.forEach((m) => appendMessage(m.role, m.content));
    if (!j.messages.length) renderHero();
    applyModelLock();
  }

  async function ensureChat() {
    if (currentChat && currentChat.id) return currentChat;
    const j = await fetch("/api/chat/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: parseInt(modelSel.value) || null }),
    }).then((r) => r.json());
    currentChat = j.chat;
    await loadChats();
    applyModelLock();
    return currentChat;
  }

  // -------- send + stream --------------------------------------------------
  async function streamSend(text, modelId) {
    const chat = await ensureChat();
    appendMessage("user", text);
    const bubble = appendMessage("assistant", "");
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    bubble.appendChild(cursor);

    let statusEl = null;
    function showStatus(msg) {
      if (!statusEl) statusEl = appendStatus(msg);
      else statusEl.textContent = msg;
    }
    function clearStatus() {
      if (statusEl) {
        statusEl.remove();
        statusEl = null;
      }
    }

    const r = await fetch(`/api/chat/${chat.id}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model_id: modelId }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      bubble.textContent = "Xato: " + (j.error || r.statusText);
      cursor.remove();
      return;
    }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let typed = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.replace(/^data:\s*/, "").trim();
        if (!line) continue;
        try {
          const obj = JSON.parse(line);
          if (obj.token) {
            clearStatus();
            typed += obj.token;
            bubble.textContent = typed;
            bubble.appendChild(cursor);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          } else if (obj.status) {
            showStatus("⏳ " + obj.status);
          } else if (obj.error) {
            clearStatus();
            bubble.textContent = "Xato: " + obj.error;
          } else if (obj.done) {
            clearStatus();
            cursor.remove();
          }
        } catch (_) {}
      }
    }
    cursor.remove();
    clearStatus();
    await loadChats();
    await loadMe();
  }

  // -------- events ---------------------------------------------------------
  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (!me) {
      openAuthModal("login");
      return;
    }
    input.value = "";
    autosize();
    streamSend(text, parseInt(modelSel.value) || null);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composer.requestSubmit();
    }
  });
  input.addEventListener("input", autosize);
  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(200, input.scrollHeight) + "px";
  }

  modelSel.addEventListener("focus", () => {
    if (!me) {
      openAuthModal("login");
      modelSel.blur();
    }
  });

  $("#newChatBtn")?.addEventListener("click", () => {
    if (!me) return openAuthModal("login");
    currentChat = null;
    document.querySelectorAll(".chat-item").forEach((el) => el.classList.remove("active"));
    renderHero();
    applyModelLock();
  });

  // dropdown menu
  $("#menuBtn").addEventListener("click", () => $("#dropMenu").classList.toggle("open"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#menuBtn") && !e.target.closest("#dropMenu"))
      $("#dropMenu").classList.remove("open");
  });
  $("#wipeAllBtn")?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!me) return openAuthModal("login");
    if (!confirm("Barcha (codex bo'lmagan) suhbatlar o'chirilsinmi?")) return;
    await fetch("/api/chat/wipe", { method: "POST" });
    currentChat = null;
    renderHero();
    applyModelLock();
    await Promise.all([loadChats(), loadMe()]);
  });
  $("#logoutBtn")?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (me) {
      await fetch("/api/auth/logout", { method: "POST" });
    }
    location.reload();
  });

  $("#authModal").addEventListener("click", (e) => {
    if (e.target.id === "authModal") closeAuthModal();
  });

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  loadMe();
})();

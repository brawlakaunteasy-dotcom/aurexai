/* Main chat page logic:
   - Auth guard (open modal on first send / model select if logged out)
   - Chat list, new/delete/rename
   - Send message with SSE streaming + animated typing
   - Memory bar / model selector / dropdown menu                        */
(function () {
  let me = null;
  let currentChatId = null;
  let models = [];
  let plan = "ODDIY";

  const $ = (s) => document.querySelector(s);
  const messagesEl = $("#messages");
  const composer   = $("#composer");
  const input      = $("#composerInput");
  const modelSel   = $("#modelSelect");
  const chatList   = $("#chatList");
  const memFill    = $("#memoryFill");
  const memText    = $("#memoryText");

  // -------- bootstrap ------------------------------------------------------
  async function loadMe() {
    const r = await fetch("/api/auth/me").then(x => x.json());
    me = r.authenticated ? r.user : null;
    if (me) {
      plan = me.plan;
      if (me.is_admin) document.getElementById("adminBtn").style.display = "inline-flex";
      await Promise.all([loadChats(), loadModels()]);
      updateMemoryBar();
    } else {
      await loadModels(true);  // public listing falls back to dummy
    }
  }

  async function loadChats() {
    const j = await fetch("/api/chat/list").then(r => r.json());
    if (!j.ok) return;
    chatList.innerHTML = "";
    j.chats.forEach((c) => {
      const div = document.createElement("div");
      div.className = "chat-item" + (c.id === currentChatId ? " active" : "");
      div.dataset.id = c.id;
      div.innerHTML = `<span>${escapeHtml(c.title || "Suhbat")}</span><span class="x" title="O'chirish">&times;</span>`;
      div.addEventListener("click", (e) => {
        if (e.target.classList.contains("x")) {
          if (!confirm("Ushbu suhbat o'chirilsinmi?")) return;
          fetch(`/api/chat/${c.id}`, { method: "DELETE" }).then(loadChats);
          if (currentChatId === c.id) { currentChatId = null; renderHero(); }
        } else openChat(c.id);
      });
      chatList.appendChild(div);
    });
  }

  async function loadModels() {
    if (!me) {
      modelSel.innerHTML = `<option>Kirish kerak</option>`;
      return;
    }
    const j = await fetch("/api/chat/models").then(r => r.json());
    models = j.models || [];
    plan = j.plan || "ODDIY";
    modelSel.innerHTML = models.map(m =>
      `<option value="${m.id}" ${m.allowed ? "" : "disabled"}>${escapeHtml(m.display_name)} · ${m.min_plan}${m.allowed ? "" : " · qulflangan"}</option>`
    ).join("");
  }

  function updateMemoryBar() {
    if (!me) return;
    const limits = { ODDIY: 100*1024*1024, PRO: 500*1024*1024, PLUS: 1024*1024*1024 };
    const limit = limits[plan] || limits.ODDIY;
    const pct = Math.min(100, Math.round((me.memory_used / limit) * 100));
    memFill.style.width = pct + "%";
    memText.textContent = `${(me.memory_used/1024/1024).toFixed(1)} / ${(limit/1024/1024).toFixed(0)} MB · ${plan}`;
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
      <p>Sun'iy intellekt bilan ishlang. Modelni tanlang va savol bering.</p>
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

  async function openChat(id) {
    currentChatId = id;
    document.querySelectorAll(".chat-item").forEach(el =>
      el.classList.toggle("active", parseInt(el.dataset.id) === id));
    const j = await fetch(`/api/chat/${id}`).then(r => r.json());
    messagesEl.innerHTML = "";
    j.messages.forEach((m) => appendMessage(m.role, m.content));
    if (!j.messages.length) renderHero();
  }

  async function ensureChat() {
    if (currentChatId) return currentChatId;
    const j = await fetch("/api/chat/new", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    }).then(r => r.json());
    currentChatId = j.chat.id;
    await loadChats();
    return currentChatId;
  }

  // -------- send + stream --------------------------------------------------
  async function streamSend(text, modelId) {
    const cid = await ensureChat();
    appendMessage("user", text);
    const bubble = appendMessage("assistant", "");
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    bubble.appendChild(cursor);

    const r = await fetch(`/api/chat/${cid}/send`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model_id: modelId }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      bubble.textContent = "Xato: " + (j.error || r.statusText);
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
            typed += obj.token;
            bubble.textContent = typed;
            bubble.appendChild(cursor);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          } else if (obj.error) {
            bubble.textContent = "Xato: " + obj.error;
          } else if (obj.done) {
            cursor.remove();
          }
        } catch (_) {}
      }
    }
    cursor.remove();
    await loadChats();
    await loadMe();
  }

  // -------- events ---------------------------------------------------------
  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (!me) { openAuthModal("login"); return; }
    input.value = ""; autosize();
    streamSend(text, modelSel.value);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); composer.requestSubmit(); }
  });
  input.addEventListener("input", autosize);
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(200, input.scrollHeight) + "px"; }

  modelSel.addEventListener("focus", () => { if (!me) { openAuthModal("login"); modelSel.blur(); } });

  $("#newChatBtn")?.addEventListener("click", async () => {
    if (!me) { openAuthModal("login"); return; }
    currentChatId = null; renderHero();
  });

  // dropdown menu
  $("#menuBtn").addEventListener("click", () => $("#dropMenu").classList.toggle("open"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#menuBtn") && !e.target.closest("#dropMenu")) $("#dropMenu").classList.remove("open");
  });
  $("#wipeAllBtn")?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!me) return openAuthModal("login");
    if (!confirm("Barcha (codex bo'lmagan) suhbatlar o'chirilsinmi?")) return;
    await fetch("/api/chat/wipe", { method: "POST" });
    currentChatId = null; renderHero();
    await Promise.all([loadChats(), loadMe()]);
  });
  $("#logoutBtn")?.addEventListener("click", async (e) => {
    e.preventDefault();
    if (me) { await fetch("/api/auth/logout", { method: "POST" }); }
    location.reload();
  });

  // close auth modal on backdrop click
  $("#authModal").addEventListener("click", (e) => { if (e.target.id === "authModal") closeAuthModal(); });

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
  }

  loadMe();
})();

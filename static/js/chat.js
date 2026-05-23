/* AurexAi main chat:
   - Per-chat model lock
   - Collab mode (PLUS): two-stage A → B pipeline
   - "AI thinking..." animation while waiting for first token
   - Animated emoji-stickers (CSS bounce on each emoji)
   - 429-aware status messages
   - Mobile drawer for sidebar
   - Memory bar with adaptive units (B/KB/MB/GB) + ∞ for admin
*/
(function () {
  let me = null;
  let currentChat = null;
  let models = [];
  let plan = "ODDIY";
  let collabPending = null; // {a, b} when user clicks "Suhbat boshlash" in collab modal

  const $ = (s) => document.querySelector(s);
  const messagesEl = $("#messages");
  const composer = $("#composer");
  const input = $("#composerInput");
  const modelSel = $("#modelSelect");
  const collabBadge = $("#collabBadge");
  const chatList = $("#chatList");
  const memFill = $("#memoryFill");
  const memText = $("#memoryText");
  const sidebar = $("#sidebar");
  const drawerBackdrop = $("#drawerBackdrop");

  const EMOJI_RE = /(\p{Extended_Pictographic}\p{Emoji_Modifier}?\u{FE0F}?(?:\u{200D}\p{Extended_Pictographic}\u{FE0F}?)*)/gu;

  // -------- helpers --------------------------------------------------------
  function fmtBytes(b) {
    b = b || 0;
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
    if (b < 1024 * 1024 * 1024) return (b / 1024 / 1024).toFixed(2) + " MB";
    return (b / 1024 / 1024 / 1024).toFixed(2) + " GB";
  }
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  /** Render text with emojis wrapped in animated sticker spans. Safe: only
   *  emoji segments use innerHTML. Text segments use textContent.            */
  function renderWithStickers(node, text) {
    node.innerHTML = "";
    let last = 0;
    const matches = [...text.matchAll(EMOJI_RE)];
    for (const m of matches) {
      if (m.index > last) node.appendChild(document.createTextNode(text.slice(last, m.index)));
      const span = document.createElement("span");
      span.className = "sticker";
      span.textContent = m[0];
      node.appendChild(span);
      last = m.index + m[0].length;
    }
    if (last < text.length) node.appendChild(document.createTextNode(text.slice(last)));
  }

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
      const lockIcon = c.is_collab
        ? `<span class="chat-lock collab-icon" title="Collab: ${escapeHtml(c.model_name || "")} → ${escapeHtml(c.collab_model_b_name || "")}">🔮</span>`
        : c.model_id
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
        } else {
          openChat(c.id);
          closeDrawer();
        }
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
    if (currentChat && currentChat.is_collab) {
      collabBadge.hidden = false;
      collabBadge.textContent = `🔮 ${currentChat.model_name} → ${currentChat.collab_model_b_name}`;
      modelSel.disabled = true;
      modelSel.style.display = "none";
    } else if (currentChat && currentChat.model_id) {
      collabBadge.hidden = true;
      modelSel.style.display = "";
      modelSel.value = currentChat.model_id;
      modelSel.disabled = true;
      modelSel.title = "Bu suhbat shu modelga bog'langan";
    } else {
      collabBadge.hidden = true;
      modelSel.style.display = "";
      modelSel.disabled = false;
      modelSel.title = "Suhbat uchun model tanlang";
    }
  }

  function updateMemoryBar() {
    if (!me) return;
    const used = me.memory_used || 0;
    if (me.is_admin) {
      memFill.style.width = "0%";
      memText.textContent = `${fmtBytes(used)} / ∞ · admin`;
      return;
    }
    const limits = { ODDIY: 100 * 1024 * 1024, PRO: 500 * 1024 * 1024, PLUS: 1024 * 1024 * 1024 };
    const limit = limits[plan] || limits.ODDIY;
    const pct = Math.min(100, Math.round((used / limit) * 100));
    memFill.style.width = pct + "%";
    memText.textContent = `${fmtBytes(used)} / ${fmtBytes(limit)} · ${plan}`;
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

  function appendMessage(role, content, opts = {}) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "assistant");
    if (opts.author) wrap.dataset.author = opts.author;
    wrap.innerHTML =
      `<div class="avatar"></div>` +
      (opts.label ? `<div class="msg-label">${escapeHtml(opts.label)}</div>` : "") +
      `<div class="bubble"></div>`;
    const bubble = wrap.querySelector(".bubble");
    if (role === "assistant") renderWithStickers(bubble, content);
    else bubble.textContent = content;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
  }

  function appendThinking(label = "AurexAi o'ylayapti") {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-thinking-wrap";
    wrap.innerHTML = `
      <div class="avatar"></div>
      <div class="msg-thinking">
        <span class="thinking-text">🤖 ${escapeHtml(label)}</span>
        <span class="dots"><span></span><span></span><span></span></span>
      </div>`;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
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
    let body = { model_id: parseInt(modelSel.value) || null };
    if (collabPending) {
      body = {
        is_collab: true,
        model_id: collabPending.a,
        model_b_id: collabPending.b,
      };
      collabPending = null;
    }
    const j = await fetch("/api/chat/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json());
    if (!j.ok) {
      alert(j.error || "Suhbat yaratib bo'lmadi");
      throw new Error(j.error);
    }
    currentChat = j.chat;
    await loadChats();
    applyModelLock();
    return currentChat;
  }

  // -------- send + stream --------------------------------------------------
  async function streamSend(text, modelId) {
    let chat;
    try {
      chat = await ensureChat();
    } catch (_) {
      return;
    }
    appendMessage("user", text);

    // "thinking" placeholder (replaced by first bubble when tokens arrive)
    let thinkingEl = appendThinking();

    let bubbleA = null;
    let bubbleB = null;
    let typedA = "";
    let typedB = "";
    let statusEl = null;

    function curBubble(author) {
      if (chat.is_collab) {
        if (author === "B") {
          if (!bubbleB) {
            bubbleB = appendMessage("assistant", "", {
              author: "B",
              label: `🅱 ${chat.collab_model_b_name || "Yakuniy javob"}`,
            });
          }
          return bubbleB;
        }
        if (!bubbleA) {
          bubbleA = appendMessage("assistant", "", {
            author: "A",
            label: `🅰 ${chat.model_name || "Birinchi tahlil"}`,
          });
        }
        return bubbleA;
      }
      if (!bubbleA) bubbleA = appendMessage("assistant", "");
      return bubbleA;
    }

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
    function clearThinking() {
      if (thinkingEl) {
        thinkingEl.remove();
        thinkingEl = null;
      }
    }

    const r = await fetch(`/api/chat/${chat.id}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model_id: modelId }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      clearThinking();
      const b = appendMessage("assistant", "❌ Xato: " + (j.error || r.statusText));
      return;
    }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
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
            clearThinking();
            const author = obj.author || "A";
            const bubble = curBubble(author);
            if (author === "B") {
              typedB += obj.token;
              renderWithStickers(bubble, typedB);
            } else {
              typedA += obj.token;
              renderWithStickers(bubble, typedA);
            }
            messagesEl.scrollTop = messagesEl.scrollHeight;
          } else if (obj.status) {
            showStatus("⏳ " + obj.status);
          } else if (obj.author && !obj.token) {
            // explicit handoff marker — pre-create bubble label
            curBubble(obj.author);
          } else if (obj.error) {
            clearStatus();
            clearThinking();
            const bubble = curBubble("A");
            bubble.textContent = "❌ Xato: " + obj.error;
          } else if (obj.done) {
            clearStatus();
            clearThinking();
          }
        } catch (_) {}
      }
    }
    clearThinking();
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
    closeDrawer();
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

  // -------- collab modal --------------------------------------------------
  $("#collabModeBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    if (!me) return openAuthModal("login");
    if (plan !== "PLUS" && !me.is_admin) {
      alert("Collab mode faqat PLUS tarifida mavjud.");
      return;
    }
    const a = $("#collabA");
    const b = $("#collabB");
    const allowed = models.filter((m) => m.allowed);
    if (allowed.length < 2) {
      alert("Collab uchun kamida 2 ta ruxsat etilgan model kerak.");
      return;
    }
    a.innerHTML = b.innerHTML = allowed
      .map((m) => `<option value="${m.id}">${escapeHtml(m.display_name)} · ${m.min_plan}</option>`)
      .join("");
    a.value = allowed[0].id;
    b.value = allowed[1].id;
    $("#collabModal").style.display = "grid";
    $("#dropMenu").classList.remove("open");
  });
  $("#collabCancel")?.addEventListener("click", () => ($("#collabModal").style.display = "none"));
  $("#collabModal")?.addEventListener("click", (e) => {
    if (e.target.id === "collabModal") $("#collabModal").style.display = "none";
  });
  $("#collabStart")?.addEventListener("click", async () => {
    const a = parseInt($("#collabA").value);
    const b = parseInt($("#collabB").value);
    if (!a || !b || a === b) return alert("Ikki farqli model tanlang");
    collabPending = { a, b };
    $("#collabModal").style.display = "none";
    currentChat = null;
    renderHero();
    applyModelLock();
    input.focus();
    appendStatus(`🔮 Collab tayyor: ${models.find((m) => m.id === a)?.display_name} → ${models.find((m) => m.id === b)?.display_name}. Birinchi xabarni yozing.`);
  });

  // -------- mobile drawer -------------------------------------------------
  function openDrawer() {
    sidebar.classList.add("open");
    drawerBackdrop.classList.add("open");
  }
  function closeDrawer() {
    sidebar.classList.remove("open");
    drawerBackdrop.classList.remove("open");
  }
  $("#drawerBtn")?.addEventListener("click", () =>
    sidebar.classList.contains("open") ? closeDrawer() : openDrawer(),
  );
  drawerBackdrop?.addEventListener("click", closeDrawer);

  loadMe();
})();

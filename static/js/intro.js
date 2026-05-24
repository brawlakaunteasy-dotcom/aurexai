/* Cinematic intro:
   - Shown ONLY for users who just registered (intro_seen=false on user)
   - Once dismissed -> intro_seen=true on server, never shown again.
*/
(function () {
  async function shouldShow() {
    try {
      const r = await fetch("/api/auth/me").then((x) => x.json());
      if (!r.authenticated) return false;
      // Only when server says intro hasn't been marked yet.
      return r.user && r.user.intro_seen === false;
    } catch (_) {
      return false;
    }
  }

  function dismiss() {
    fetch("/api/chat/intro-seen", { method: "POST" }).catch(() => {});
    const el = document.getElementById("introOverlay");
    if (!el) return;
    el.classList.add("closing");
    setTimeout(() => el.remove(), 600);
  }

  function animateNumber(el, target, dur = 1400) {
    const start = performance.now();
    function step(t) {
      const p = Math.min(1, (t - start) / dur);
      const ease = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * ease).toLocaleString();
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  async function run() {
    const overlay = document.getElementById("introOverlay");
    if (!overlay) return;
    if (!(await shouldShow())) return;

    // Wait for the loader overlay to finish
    await new Promise((res) => {
      const t = setInterval(() => {
        if (!document.getElementById("loader")) {
          clearInterval(t);
          res();
        }
      }, 200);
      setTimeout(() => {
        clearInterval(t);
        res();
      }, 8000);
    });

    overlay.hidden = false;

    // Fetch live stats
    const stats = await fetch("/api/site/stats")
      .then((r) => r.json())
      .catch(() => ({ users_total: 0, models_total: 0 }));

    const frames = overlay.querySelectorAll(".intro-frame");
    const dotsRoot = document.getElementById("introDots");
    dotsRoot.innerHTML = "";
    frames.forEach((_, i) => {
      const d = document.createElement("button");
      d.className = "intro-dot";
      d.dataset.idx = i;
      dotsRoot.appendChild(d);
    });

    const startBtn = document.getElementById("introStart");
    const skipBtn = document.getElementById("introSkip");
    let idx = 0;
    let timer = null;

    function show(i) {
      idx = (i + frames.length) % frames.length;
      frames.forEach((f, n) => f.classList.toggle("active", n === idx));
      dotsRoot.querySelectorAll(".intro-dot").forEach((d, n) =>
        d.classList.toggle("active", n === idx),
      );
      // Counters
      if (idx === 1) animateNumber(document.getElementById("introUsers"), stats.users_total || 1);
      if (idx === 2) animateNumber(document.getElementById("introModels"), stats.models_total || 1);
      // Show "Boshlash" prominent on last frame
      startBtn.classList.toggle("ready", idx === frames.length - 1);
    }
    show(0);

    function autoplay() {
      clearInterval(timer);
      timer = setInterval(() => {
        if (idx < frames.length - 1) show(idx + 1);
        else clearInterval(timer);
      }, 3600);
    }
    autoplay();

    dotsRoot.addEventListener("click", (e) => {
      const t = e.target.closest(".intro-dot");
      if (!t) return;
      show(parseInt(t.dataset.idx));
      autoplay();
    });
    overlay.addEventListener("click", (e) => {
      if (e.target.closest(".intro-dot, .intro-skip, .intro-start")) return;
      if (idx < frames.length - 1) show(idx + 1);
      else dismiss();
      autoplay();
    });
    skipBtn.addEventListener("click", dismiss);
    startBtn.addEventListener("click", dismiss);
  }

  run();
})();

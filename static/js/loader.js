/* 4-stage loader:
   1) Internet speed test
   2) Site asset preload
   3) Device detection (PC / Mobile)
   4) Final reveal animation                                            */
(function () {
  const overlay  = document.getElementById("loader");
  const fill     = document.getElementById("loaderFill");
  const percent  = document.getElementById("loaderPercent");
  const stage    = document.getElementById("loaderStage");
  if (!overlay) return;

  function setProgress(p, label) {
    p = Math.min(100, Math.max(0, Math.round(p)));
    fill.style.width    = p + "%";
    percent.textContent = p + "%";
    if (label) {
      stage.textContent = label;
      stage.style.animation = "none"; void stage.offsetWidth;
      stage.style.animation = "stageFade .4s ease";
    }
  }

  async function stageSpeedTest() {
    setProgress(2, "1-bosqich: Internet tezligi tekshirilmoqda...");
    const start = performance.now();
    try {
      // small static asset
      await fetch("/static/img/logo.svg?nc=" + Date.now(), { cache: "no-store" });
    } catch (_) {}
    const ms = performance.now() - start;
    const mbps = Math.max(1, Math.round(800 / Math.max(20, ms)));
    for (let i = 2; i <= 25; i++) {
      await sleep(20);
      setProgress(i);
    }
    setProgress(25, `1-bosqich: tezlik ~${mbps} Mbps`);
    await sleep(250);
  }

  async function stageAssets() {
    setProgress(28, "2-bosqich: Sayt yuklanmoqda...");
    // wait for DOM ready + a few frames
    if (document.readyState !== "complete") {
      await new Promise((r) => window.addEventListener("load", r, { once: true }));
    }
    for (let i = 28; i <= 65; i++) {
      await sleep(15);
      setProgress(i);
    }
  }

  async function stageDevice() {
    const isMobile =
      /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
      window.matchMedia("(max-width: 800px)").matches;
    setProgress(70, `3-bosqich: Qurilma aniqlandi · ${isMobile ? "Telefon" : "Kompyuter"}`);
    document.documentElement.dataset.device = isMobile ? "mobile" : "desktop";
    for (let i = 70; i <= 88; i++) { await sleep(15); setProgress(i); }
  }

  async function stageReveal() {
    setProgress(92, "4-bosqich: Animatsiya tayyorlanmoqda...");
    for (let i = 92; i <= 100; i++) { await sleep(20); setProgress(i); }
    setProgress(100, "Tayyor!");
    await sleep(300);
    overlay.classList.add("done");
    setTimeout(() => overlay.remove(), 600);
  }

  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  (async () => {
    await stageSpeedTest();
    await stageAssets();
    await stageDevice();
    await stageReveal();
  })();
})();

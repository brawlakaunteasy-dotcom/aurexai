/* Theme: light/dark/auto (follows OS by default).
   - Toggle button cycles: auto -> light -> dark -> auto
   - Default = auto (matches OS via prefers-color-scheme)               */
(function () {
  const KEY = "aurex-theme";
  const html = document.documentElement;

  function apply(mode) {
    if (mode === "auto") {
      const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      html.dataset.theme = dark ? "dark" : "light";
      html.dataset.themeMode = "auto";
    } else {
      html.dataset.theme = mode;
      html.dataset.themeMode = mode;
    }
  }

  const saved = localStorage.getItem(KEY) || "auto";
  apply(saved);

  // React to OS changes when in auto
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((localStorage.getItem(KEY) || "auto") === "auto") apply("auto");
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#themeToggle");
    if (!btn) return;
    const order = ["auto", "light", "dark"];
    const cur = localStorage.getItem(KEY) || "auto";
    const next = order[(order.indexOf(cur) + 1) % order.length];
    localStorage.setItem(KEY, next);
    apply(next);
  });
})();

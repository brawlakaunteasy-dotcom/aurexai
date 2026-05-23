/* Login + Register handlers (used on /login and /register) */
async function postJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(loginForm);
    const j = await postJSON("/api/auth/login", {
      identifier: fd.get("identifier"),
      password:   fd.get("password"),
      remember:   fd.get("remember") === "on",
    });
    if (j.ok) {
      // If embedded in modal, notify parent
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "aurex-auth-ok", user: j.user }, "*");
      } else {
        location.href = "/";
      }
    } else {
      document.getElementById("loginErr").textContent = j.error || "Xatolik";
    }
  });
}

const regForm = document.getElementById("registerForm");
if (regForm) {
  regForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(regForm);
    const j = await postJSON("/api/auth/register", {
      first_name: fd.get("first_name"),
      last_name:  fd.get("last_name"),
      username:   fd.get("username"),
      email:      fd.get("email"),
      password:   fd.get("password"),
      password2:  fd.get("password2"),
    });
    if (j.ok) {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "aurex-auth-ok", user: j.user }, "*");
      } else {
        location.href = "/";
      }
    } else {
      document.getElementById("regErr").textContent = j.error || "Xatolik";
    }
  });
}

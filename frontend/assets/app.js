(() => {
  const $ = (id) => document.getElementById(id);

  const state = {
    source: "url",
    role: "admin",
    authenticated: false,
    userRole: null,
  };

  const appShell = $("app-shell");
  const authOverlay = $("auth-overlay");
  const loginPassword = $("login-password");
  const loginError = $("login-error");
  const loginSubmit = $("login-submit");
  const guestRoleBtn = $("guest-role-btn");
  const roleBadge = $("role-badge");
  const docsLink = $("docs-link");
  const historyPanel = $("history-panel");

  const urlField = $("url-field");
  const textField = $("text-field");
  const errorEl = $("error");
  const loader = $("loader");
  const postEl = $("post");
  const lengthEl = $("length");
  const copyBtn = $("copy");
  const generateBtn = $("generate");
  const historyBody = $("history-body");
  const historyList = $("history-list");
  const historyEmpty = $("history-empty");
  const historyToggle = $("history-toggle");

  document.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".toggle-btn").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      state.source = btn.dataset.source;
      urlField.classList.toggle("hidden", state.source !== "url");
      textField.classList.toggle("hidden", state.source !== "text");
    });
  });

  document.querySelectorAll(".role-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.classList.contains("hidden")) return;
      document.querySelectorAll(".role-btn").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      state.role = btn.dataset.role;
      loginPassword.focus();
    });
  });

  $("toggle-password").addEventListener("click", () => {
    const isPassword = loginPassword.type === "password";
    loginPassword.type = isPassword ? "text" : "password";
    $("toggle-password").setAttribute("aria-label", isPassword ? "Скрыть пароль" : "Показать пароль");
  });

  loginSubmit.addEventListener("click", onLogin);
  loginPassword.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onLogin();
  });

  authOverlay.addEventListener("keydown", (e) => {
    if (e.key === "Escape") e.preventDefault();
  });

  $("logout").addEventListener("click", onLogout);

  historyToggle.addEventListener("click", () => {
    const open = historyBody.classList.toggle("hidden") === false;
    historyToggle.setAttribute("aria-expanded", String(open));
    if (open) loadHistory();
  });

  copyBtn.addEventListener("click", async () => {
    const text = postEl.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "Скопировано";
      setTimeout(() => {
        copyBtn.textContent = "Копировать";
      }, 1200);
    } catch {
      copyBtn.textContent = "Не удалось скопировать";
    }
  });

  generateBtn.addEventListener("click", onGenerate);

  boot();

  async function boot() {
    try {
      const me = await api("/auth/me");
      if (!me.guest_enabled) {
        guestRoleBtn.classList.add("hidden");
        state.role = "admin";
      }
      if (me.authenticated) {
        await enterApp(me, { animate: false });
      } else {
        showLogin();
      }
    } catch {
      showLogin();
    } finally {
      document.body.classList.remove("boot-locked");
    }
  }

  function showLogin(message) {
    state.authenticated = false;
    appShell.classList.add("is-locked");
    appShell.classList.remove("is-ready", "is-unlocking");
    appShell.setAttribute("aria-hidden", "true");
    authOverlay.classList.remove("is-hidden", "is-leaving");
    if (message) showLoginError(message);
    setTimeout(() => loginPassword.focus(), 50);
  }

  async function enterApp(me, { animate }) {
    state.authenticated = true;
    state.userRole = me.role;
    roleBadge.textContent = me.role === "admin" ? "ADMIN" : "GOST";
    docsLink.classList.toggle("hidden", me.role !== "admin");
    historyPanel.classList.toggle("hidden", false);

    if (animate) {
      authOverlay.classList.add("is-leaving");
      appShell.classList.remove("is-locked");
      appShell.classList.add("is-unlocking");
      setTimeout(() => {
        authOverlay.classList.add("is-hidden");
        authOverlay.classList.remove("is-leaving");
        appShell.classList.remove("is-unlocking");
        appShell.classList.add("is-ready");
        appShell.setAttribute("aria-hidden", "false");
      }, 1300);
    } else {
      authOverlay.classList.add("is-hidden");
      appShell.classList.remove("is-locked");
      appShell.classList.add("is-ready");
      appShell.setAttribute("aria-hidden", "false");
    }
  }

  async function onLogin() {
    clearLoginError();
    const password = (loginPassword.value || "").trim();
    if (!password) {
      showLoginError("Неверные данные для входа");
      shakePassword();
      return;
    }
    loginSubmit.disabled = true;
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ role: state.role, password }),
      });
      loginPassword.value = "";
      await enterApp(data, { animate: true });
    } catch (err) {
      showLoginError(err.message || "Неверные данные для входа");
      shakePassword();
    } finally {
      loginSubmit.disabled = false;
    }
  }

  async function onLogout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    showLogin();
  }

  async function onGenerate() {
    if (!state.authenticated) return showLogin("Сессия завершена. Войдите снова.");
    clearError();
    const payload = {
      platform: $("platform").value,
      style: $("style").value,
      goal: $("goal").value,
      max_length: Number($("max_length").value || 800),
      cta: $("cta").checked,
      hashtags: $("hashtags").checked,
      url: null,
      text: null,
    };

    if (state.source === "url") {
      payload.url = ($("url").value || "").trim();
      if (!payload.url) return showError("Укажите URL");
    } else {
      payload.text = ($("text").value || "").trim();
      if (!payload.text) return showError("Укажите текст");
    }

    setLoading(true);
    try {
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      postEl.textContent = data.post || "";
      postEl.classList.remove("is-fresh");
      void postEl.offsetWidth;
      postEl.classList.add("is-fresh");
      lengthEl.textContent = `${data.length || 0} символов`;
      copyBtn.disabled = !data.post;
      if (!historyBody.classList.contains("hidden")) loadHistory();
    } catch (err) {
      if (err.status === 401) {
        showLogin("Сессия завершена. Войдите снова.");
      } else {
        showError(err.message || "Ошибка запроса");
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory() {
    try {
      const items = await api("/api/history?limit=20");
      historyList.innerHTML = "";
      if (!items.length) {
        historyEmpty.classList.remove("hidden");
        historyEmpty.textContent = "История пока пуста.";
        return;
      }
      historyEmpty.classList.add("hidden");
      items.forEach((item) => {
        const li = document.createElement("li");
        const top = document.createElement("div");
        top.className = "top";
        top.innerHTML = `<span>${item.platform} · ${item.style} · ${item.goal}</span><span>${item.length} симв.</span>`;
        const snippet = document.createElement("div");
        snippet.className = "snippet";
        snippet.textContent = item.post;
        li.appendChild(top);
        li.appendChild(snippet);
        historyList.appendChild(li);
      });
    } catch (err) {
      if (err.status === 401) {
        showLogin("Сессия завершена. Войдите снова.");
        return;
      }
      historyEmpty.textContent = "Не удалось загрузить историю.";
      historyEmpty.classList.remove("hidden");
    }
  }

  async function api(url, options = {}) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(formatDetail(data.detail) || "Ошибка запроса");
      error.status = res.status;
      throw error;
    }
    return data;
  }

  function setLoading(isLoading) {
    generateBtn.disabled = isLoading;
    loader.classList.toggle("hidden", !isLoading);
  }

  function formatDetail(detail) {
    if (!detail) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item === "string" ? item : item.msg || JSON.stringify(item)))
        .join("; ");
    }
    return String(detail);
  }

  function showError(message) {
    errorEl.textContent = formatDetail(message) || "Ошибка запроса";
    errorEl.classList.remove("hidden");
  }

  function clearError() {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }

  function showLoginError(message) {
    loginError.textContent = message;
    loginError.classList.remove("hidden");
  }

  function clearLoginError() {
    loginError.textContent = "";
    loginError.classList.add("hidden");
  }

  function shakePassword() {
    loginPassword.classList.remove("shake");
    void loginPassword.offsetWidth;
    loginPassword.classList.add("shake");
  }
})();

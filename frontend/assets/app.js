(() => {
  const $ = (id) => document.getElementById(id);

  const state = { source: "url" };

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

  async function onGenerate() {
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
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatDetail(data.detail) || "Не удалось сгенерировать пост");
      }
      postEl.textContent = data.post || "";
      lengthEl.textContent = `${data.length || 0} символов`;
      copyBtn.disabled = !data.post;
      if (!historyBody.classList.contains("hidden")) loadHistory();
    } catch (err) {
      showError(err.message || "Ошибка запроса");
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory() {
    try {
      const res = await fetch("/api/history?limit=20");
      if (!res.ok) throw new Error("history");
      const items = await res.json();
      historyList.innerHTML = "";
      if (!items.length) {
        historyEmpty.classList.remove("hidden");
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
    } catch {
      historyEmpty.textContent = "Не удалось загрузить историю.";
      historyEmpty.classList.remove("hidden");
    }
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
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && item.msg) return item.msg;
          return JSON.stringify(item);
        })
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
})();

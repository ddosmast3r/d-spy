const DEFAULTS = { ollamaHost: "http://192.168.0.112:11434", ollamaModel: "gemma4:12b", orgTitle: "Чё? Шашлык" };
const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(DEFAULTS).then((cfg) => {
  $("ollamaHost").value = cfg.ollamaHost;
  $("ollamaModel").value = cfg.ollamaModel;
  $("orgTitle").value = cfg.orgTitle;
});

$("save").addEventListener("click", async () => {
  await chrome.storage.sync.set({
    ollamaHost: $("ollamaHost").value.trim(),
    ollamaModel: $("ollamaModel").value.trim(),
    orgTitle: $("orgTitle").value.trim(),
  });
  show("Сохранено", "ok");
});

$("test").addEventListener("click", async () => {
  show("Проверяю…", "");
  await chrome.storage.sync.set({
    ollamaHost: $("ollamaHost").value.trim(),
    ollamaModel: $("ollamaModel").value.trim(),
  });
  const res = await chrome.runtime.sendMessage({ type: "PING" });
  if (res.ok && res.hasModel) show("Связь есть, модель на месте", "ok");
  else if (res.ok) show("Ollama на связи, но модели нет. Доступны: " + res.models.join(", "), "err");
  else show("Нет связи: " + res.error, "err");
});

function show(text, cls) { const m = $("msg"); m.textContent = text; m.className = cls; }

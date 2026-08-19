// Фоновый воркер: единственный, кто ходит в Ollama.
// Контент-скрипт не может звать http:// с https-страницы (mixed content), а воркер может.

import { SYSTEM, buildPrompt, cleanDraft } from "./style.js";
import { EXAMPLES } from "./examples.js";

const DEFAULTS = {
  ollamaHost: "http://192.168.0.112:11434",
  ollamaModel: "gemma4:12b",
  orgTitle: "Чё? Шашлык",
};

async function config() {
  const saved = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...saved };
}

async function generate({ review, author, rating }) {
  const cfg = await config();
  const host = cfg.ollamaHost.replace(/\/+$/, "");
  const prompt = buildPrompt(review, author, rating, cfg.orgTitle, EXAMPLES);

  const res = await fetch(`${host}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: cfg.ollamaModel,
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: prompt },
      ],
      stream: false,
      think: false,                       // gemma4 reasoning: иначе бюджет уходит в thinking
      options: { temperature: 0.7, num_predict: 1200 },
    }),
  });
  if (!res.ok) throw new Error(`Ollama ответила ${res.status}`);
  const data = await res.json();
  const raw = (data.message && data.message.content) || "";
  return cleanDraft(raw, author);
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "DRAFT") {
    generate(msg.payload)
      .then(text => sendResponse({ ok: true, text }))
      .catch(err => sendResponse({ ok: false, error: String(err.message || err) }));
    return true; // ответ асинхронный
  }
  if (msg.type === "PING") {
    config().then(async cfg => {
      try {
        const host = cfg.ollamaHost.replace(/\/+$/, "");
        const r = await fetch(`${host}/api/tags`, { signal: AbortSignal.timeout(8000) });
        const models = (await r.json()).models.map(m => m.name);
        sendResponse({ ok: true, hasModel: models.includes(cfg.ollamaModel), models, cfg });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e), cfg });
      }
    });
    return true;
  }
});

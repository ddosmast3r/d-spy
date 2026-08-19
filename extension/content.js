// Контент-скрипт для Яндекс Бизнеса. DOM там React и меняется,
// поэтому не завязываемся на конкретные классы, а работаем эвристикой.

let lastEditable = null;

// запоминаем последнее поле ответа, куда пользователь ставил курсор
document.addEventListener("focusin", (e) => {
  const el = e.target;
  if (isEditable(el)) lastEditable = el;
}, true);

function isEditable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "TEXTAREA" ||
    (tag === "INPUT" && /text|search/i.test(el.type || "")) ||
    el.isContentEditable;
}

// текст отзыва рядом с полем ответа: поднимаемся по предкам, берём самый длинный
// текстовый блок, который не является самим полем и не служебная мелочь
function extractReview(editable) {
  let node = editable;
  for (let depth = 0; depth < 8 && node; depth++) {
    node = node.parentElement;
    if (!node) break;
    const candidates = [];
    node.querySelectorAll("p, div, span").forEach((c) => {
      if (c.contains(editable)) return;
      if (isEditable(c)) return;
      const t = (c.innerText || "").trim();
      if (t.length >= 40 && t.length < 2000) candidates.push(t);
    });
    if (candidates.length) {
      candidates.sort((a, b) => b.length - a.length);
      const review = candidates[0];
      return { review, author: findAuthor(node, review), rating: findRating(node) };
    }
  }
  return null;
}

function findAuthor(container, reviewText) {
  // имя обычно короткая строка над отзывом, из 1-3 слов с заглавной
  const bits = [];
  container.querySelectorAll("a, span, div, h1, h2, h3").forEach((c) => {
    const t = (c.innerText || "").trim();
    if (t && t.length < 40 && /^[А-ЯЁA-Z][а-яёa-z]+(\s[А-ЯЁA-Z][а-яёa-z.]+)?$/.test(t) &&
        !reviewText.includes(t)) bits.push(t);
  });
  return bits[0] || null;
}

function findRating(container) {
  // ищем aria-label вида "Оценка 4" или "4 звезды"
  const el = container.querySelector('[aria-label*="Оценка"], [aria-label*="звезд"], [aria-label*="star"]');
  if (el) {
    const m = (el.getAttribute("aria-label") || "").match(/([1-5])/);
    if (m) return Number(m[1]);
  }
  return null;
}

// вставка в React-поле: нативный сеттер + событие input
function insertText(el, text) {
  el.focus();
  if (el.isContentEditable) {
    const sel = window.getSelection();
    sel.selectAllChildren(el);
    document.execCommand("insertText", false, text);
    el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    return;
  }
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, text);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

// плавающая кнопка
const fab = document.createElement("div");
fab.id = "draft-fab";
fab.innerHTML = `<button id="draft-btn" title="Черновик ответа">🤖 Черновик</button><div id="draft-status"></div>`;
document.documentElement.appendChild(fab);

const btn = fab.querySelector("#draft-btn");
const status = fab.querySelector("#draft-status");

function setStatus(text, kind) {
  status.textContent = text || "";
  status.className = kind || "";
}

btn.addEventListener("click", async () => {
  const target = lastEditable || document.querySelector("textarea");
  if (!target) {
    setStatus("Кликните в поле ответа, потом сюда", "err");
    return;
  }
  const found = extractReview(target);
  if (!found) {
    setStatus("Не нашёл текст отзыва рядом", "err");
    return;
  }
  setStatus("Пишу черновик…", "wait");
  btn.disabled = true;
  try {
    const res = await chrome.runtime.sendMessage({ type: "DRAFT", payload: found });
    if (!res || !res.ok) throw new Error(res ? res.error : "нет ответа");
    insertText(target, res.text);
    setStatus("Готово, проверьте и отправьте", "ok");
  } catch (e) {
    setStatus("Ошибка: " + (e.message || e), "err");
  } finally {
    btn.disabled = false;
  }
});

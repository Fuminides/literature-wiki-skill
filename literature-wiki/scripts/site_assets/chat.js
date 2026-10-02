// Chat panel injected by .tools/serve_site.py. The conversation lives in sessionStorage, so it
// follows the reader from page to page within a tab; the server resumes the Claude session.
(function () {
  const wikiName = (document.querySelector(".brand") || {}).textContent || "";
  const KEY = "wikichat:" + wikiName.trim();
  const pageTitle = document.title.split(" · ")[0];
  let state = { session: null, open: false, messages: [] };
  try { state = { ...state, ...JSON.parse(sessionStorage.getItem(KEY)) }; } catch (e) {}
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  document.body.insertAdjacentHTML("beforeend", `
<button class="wc-launch" title="Ask Claude about this page">Ask Claude</button>
<section class="wc-panel" hidden aria-label="Ask Claude">
  <header class="wc-head">
    <div><strong>Ask Claude</strong><span class="wc-page">about ${esc(pageTitle)}</span></div>
    <button class="wc-new" title="Start a new conversation">New</button>
    <button class="wc-close" aria-label="Close">×</button>
  </header>
  <div class="wc-log"></div>
  <form class="wc-form">
    <div class="wc-quote" hidden><span></span><button type="button" aria-label="Drop the highlighted passage">×</button></div>
    <textarea rows="2" placeholder="Ask about this page… (highlight text to ask about it)"></textarea>
    <button class="wc-send" type="submit">Send</button>
  </form>
</section>`);

  const panel = document.querySelector(".wc-panel");
  const launch = document.querySelector(".wc-launch");
  const log = panel.querySelector(".wc-log");
  const form = panel.querySelector(".wc-form");
  const input = form.querySelector("textarea");
  const send = form.querySelector(".wc-send");
  const quoteBox = form.querySelector(".wc-quote");
  let quote = "";
  let busy = false;

  // ---- math, rendered with the site's own KaTeX (loaded on demand on pages without math)
  let katexReady = null;
  function renderMath(el) {
    if (!el.querySelector(".math")) return;
    katexReady = katexReady || (window.katex ? Promise.resolve() : new Promise((resolve) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "/assets/katex/katex.min.css";
      const js = document.createElement("script");
      js.src = "/assets/katex/katex.min.js"; js.onload = resolve;
      document.head.append(css, js);
    }));
    katexReady.then(() => el.querySelectorAll(".math").forEach((e) => {
      try { katex.render(e.textContent, e, { displayMode: e.classList.contains("block"), throwOnError: false }); } catch (x) {}
    }));
  }

  function addMessage(m) {
    const div = document.createElement("div");
    div.className = "wc-msg wc-" + m.role + (m.error ? " wc-error" : "");
    if (m.role === "user") {
      div.innerHTML = `<div class="wc-on">on ${esc(m.page)}</div>` +
        (m.quote ? `<blockquote>${esc(m.quote)}</blockquote>` : "") + `<div>${esc(m.text)}</div>`;
    } else {
      div.innerHTML = m.html;
      renderMath(div);
    }
    log.append(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  function setOpen(open) {
    state.open = open;
    panel.hidden = !open;
    launch.hidden = open;
    save();
    if (open) { log.scrollTop = log.scrollHeight; input.focus(); }
  }

  function setQuote(text) {
    quote = text;
    quoteBox.hidden = !text;
    quoteBox.querySelector("span").textContent = text.length > 160 ? text.slice(0, 160) + "…" : text;
  }

  state.messages.forEach(addMessage);
  setOpen(state.open);

  launch.addEventListener("click", () => setOpen(true));
  panel.querySelector(".wc-close").addEventListener("click", () => setOpen(false));
  panel.querySelector(".wc-new").addEventListener("click", () => {
    if (busy) return;
    state.session = null; state.messages = []; log.innerHTML = ""; save(); input.focus();
  });
  quoteBox.querySelector("button").addEventListener("click", () => setQuote(""));

  // A passage highlighted in the article becomes context for the next question.
  document.addEventListener("selectionchange", () => {
    const sel = document.getSelection();
    const text = sel.toString().trim();
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    if (text && node && node.closest("main")) setQuote(text);
  });

  // Keep typing here away from the site's own shortcuts ("/" focuses search).
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    if (e.key === "Escape") setOpen(false);
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question || busy) return;
    input.value = "";
    ask(question, question, quote);
    setQuote("");
  });

  // Other scripts on the page (the exams) post questions here; the log shows `label` instead.
  window.wikiChat = { ask: (question, label) => { setOpen(true); ask(question, label, ""); } };

  async function ask(question, label, quoted) {
    if (busy) return;
    const user = { role: "user", text: label, quote: quoted, page: pageTitle };
    state.messages.push(user); save();
    addMessage(user);
    busy = true; send.disabled = true;

    const bubble = addMessage({ role: "assistant", html: '<div class="wc-status">Thinking…</div><div class="wc-live"></div>' });
    bubble.classList.add("wc-pending");
    const status = bubble.querySelector(".wc-status");
    const live = bubble.querySelector(".wc-live");
    let result = null;

    const handle = (ev) => {
      if (ev.session) { state.session = ev.session; save(); }
      if (ev.tool) { status.textContent = ev.tool + "…"; live.textContent = ""; }
      if (ev.text) { status.textContent = ""; live.textContent += ev.text; log.scrollTop = log.scrollHeight; }
      if (ev.done) result = { role: "assistant", html: ev.html };
      if (ev.error) result = { role: "assistant", html: "<p>" + esc(ev.error) + "</p>", error: true };
      if (ev.reset) state.session = null;
    };

    try {
      const res = await fetch("/__chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question, selection: quoted, session: state.session,
          page: location.pathname, title: pageTitle,
        }),
      });
      if (!res.ok) throw new Error("The chat server answered " + res.status + ".");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        lines.filter(Boolean).forEach((l) => handle(JSON.parse(l)));
      }
    } catch (err) {
      result = { role: "assistant", html: "<p>" + esc(String(err.message || err)) + "</p>", error: true };
    }

    result = result || { role: "assistant", html: "<p>The answer was cut off.</p>", error: true };
    bubble.remove();
    state.messages.push(result); save();
    addMessage(result);
    busy = false; send.disabled = false;
    input.focus();
  }
})();

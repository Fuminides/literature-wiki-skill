// Exams: each attempt draws a random subset of the bank, multiple choice is graded here,
// and when the site is served by .tools/serve_site.py Claude grades the written answers
// and explains mistakes in the chat panel. The attempt lives in sessionStorage, so it
// survives following a "Review" link and coming back. When served, the server also counts
// how often each question was answered: attempts draw the least-answered questions first,
// and the server has Claude write new questions once every question has been practised enough.
document.addEventListener("DOMContentLoaded", async () => {
  const exam = document.querySelector(".exam");
  if (!exam) return;
  const KEY = "exam:" + location.pathname;
  const all = [...exam.querySelectorAll(".q")];
  const byId = Object.fromEntries(all.map((q) => [q.dataset.id, q]));
  const list = exam.querySelector(".exam-questions");
  const result = exam.querySelector(".exam-result");
  const submit = exam.querySelector(".exam-submit");
  const chat = window.wikiChat;  // present only when served with the chat panel
  const statusLine = document.querySelector(".exam-status");
  const level = exam.dataset.level;
  const options = (q) => [...q.querySelectorAll(".q-options > li")];
  all.forEach((q) => options(q).forEach((li, i) => (li.dataset.i = i)));
  const shuffle = (a) => {
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  };

  let state = null;  // {ids, order: {id: [option i]}, answers: {id: option i | text}, submitted, grades: {id: {verdict, html}}}
  try { state = JSON.parse(sessionStorage.getItem(KEY)); } catch (e) {}
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };

  // ---- practice counts kept by the server: {threshold, least, counts: {id: {answered, correct}}, exhausted, job}
  let status = null;
  let polling = false;
  async function api(path, body) {
    const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    if (!res.ok) throw new Error(res.status);
    return res.json();
  }
  async function refresh() {
    try { status = await api(`/__chat/exam-status?level=${level}`); } catch (e) { return; }
    showStatus();
  }
  function showStatus() {
    if (!status) return;
    const total = Object.keys(status.counts).length;
    // A finished job is news only to a page rendered before it; a page with the full bank has its result.
    const job = status.job && !(status.job.state === "done" && total === all.length) ? status.job : null;
    const times = (n) => `${n} time${n === 1 ? "" : "s"}`;
    const unseen = Object.values(status.counts).filter((c) => !c.answered).length;
    let text = "";
    if (job) text = job.message;
    else if (status.exhausted) text = document.querySelector(".exam-note") ? "" : `No new questions will be added: ${status.exhausted}`;
    else if (status.threshold > 0)
      text = (unseen ? `${unseen} of ${total} questions here ${unseen === 1 ? "has" : "have"} not been answered yet.`
        : `Every question here has been answered at least ${times(status.least)}.`) +
        ` Once each has been answered ${times(status.threshold)}, Claude writes new questions for this exam.`;
    statusLine.textContent = text;
    statusLine.hidden = !text;
    if (job && job.state === "done" && job.added) {
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "Reload with the new questions";
      b.addEventListener("click", () => location.reload());
      statusLine.append(" ", b);
    }
    if (job && job.state === "running" && !polling) {
      polling = true;
      setTimeout(() => { polling = false; refresh(); }, 15000);
    }
    if (state && state.submitted) showCounts();
  }
  function showCounts() {
    for (const id of state.ids) {
      const c = status.counts[id];
      const q = byId[id];
      if (!c || !q) continue;
      const el = q.querySelector(".q-count") || q.querySelector(".q-review").insertAdjacentElement("afterend", document.createElement("div"));
      el.className = "q-count";
      el.textContent = `Answered ${c.answered} time${c.answered === 1 ? "" : "s"}, right ${c.correct}.`;
    }
  }

  function draw() {
    const n = +exam.dataset.perAttempt;
    // Least-answered questions first, random among equals (sort is stable), so new questions
    // come up at once and practice spreads evenly. Without the server, plain random order.
    const answered = (q) => (status && status.counts[q.dataset.id] ? status.counts[q.dataset.id].answered : 0);
    const pick = (qs) => shuffle(qs).sort((a, b) => answered(a) - answered(b));
    const choice = pick(all.filter((q) => q.dataset.kind === "choice"));
    const written = pick(all.filter((q) => q.dataset.kind === "written"));
    // Keep the bank's share of written questions in every attempt.
    const nw = Math.min(written.length, Math.round((n * written.length) / all.length));
    const ids = [...choice.slice(0, n - nw), ...written.slice(0, nw)].map((q) => q.dataset.id);
    const order = {};
    for (const id of ids) order[id] = shuffle(options(byId[id]).map((li) => +li.dataset.i));
    state = { ids, order, answers: {}, submitted: false, grades: {} };
    save();
  }

  function show() {
    all.forEach((q) => (q.hidden = true));
    for (const id of state.ids) {
      const q = byId[id];
      if (!q) { draw(); return show(); }  // the bank changed since this attempt was saved
      list.append(q);
      q.hidden = false;
      q.className = "q";
      const ul = q.querySelector(".q-options");
      if (ul) {
        const lis = options(q);
        state.order[id].forEach((i) => ul.append(lis.find((li) => +li.dataset.i === i)));
        lis.forEach((li) => {
          const input = li.querySelector("input");
          input.checked = state.answers[id] === +li.dataset.i;
          input.disabled = state.submitted;
          li.className = "";
          li.querySelector(".why").hidden = true;
        });
      } else {
        const ta = q.querySelector("textarea");
        ta.value = state.answers[id] || "";
        ta.readOnly = state.submitted;
      }
      q.querySelector(".q-review").hidden = true;
      q.querySelectorAll(".model-answer, .q-grade").forEach((e) => (e.hidden = true));
      q.querySelectorAll(".q-explain, .q-count").forEach((e) => e.remove());
    }
    submit.hidden = state.submitted;
    result.hidden = true;
    if (state.submitted) grade();
  }

  // ---- grading

  function verdictOf(id) {
    const q = byId[id];
    if (q.dataset.kind === "choice") {
      const chosen = state.answers[id];
      return chosen === undefined ? "unanswered" : q.querySelector(`[data-i="${chosen}"]`).hasAttribute("data-correct") ? "correct" : "incorrect";
    }
    if (!(state.answers[id] || "").trim()) return "unanswered";
    return state.grades[id] ? state.grades[id].verdict : "pending";
  }

  function grade() {
    for (const id of state.ids) {
      const q = byId[id];
      if (q.dataset.kind === "choice") {
        for (const li of options(q)) {
          const chosen = state.answers[id] === +li.dataset.i;
          const correct = li.hasAttribute("data-correct");
          li.classList.toggle("chosen", chosen);
          li.classList.toggle("correct", correct);
          li.querySelector(".why").hidden = !(chosen || correct);
        }
      } else {
        q.querySelector(".model-answer").hidden = false;
        const box = q.querySelector(".q-grade");
        const g = state.grades[id];
        box.hidden = false;
        if (g) box.innerHTML = `<div class="verdict">${{ correct: "Correct", partial: "Partly correct", incorrect: "Not correct" }[g.verdict]}</div>${g.html}`;
        else if (!(state.answers[id] || "").trim()) box.innerHTML = '<div class="verdict">No answer</div>';
        else if (chat) { box.innerHTML = '<div class="verdict">Claude is grading this answer…</div>'; requestGrade(id); }
        else box.innerHTML = '<div class="verdict">Compare your answer with the full answer below.</div>' +
          "<p>Serve the site with <code>python3 .tools/serve_site.py</code> to have Claude grade it.</p>";
      }
      const v = verdictOf(id);
      q.className = "q " + v;
      q.querySelector(".q-review").hidden = v === "correct";
      if (chat && v !== "correct" && v !== "pending" && !q.querySelector(".q-explain")) {
        const b = document.createElement("button");
        b.className = "btn q-explain";
        b.textContent = "Ask Claude to explain";
        b.addEventListener("click", () => explain(id));
        q.querySelector(".q-review").before(b);
      }
    }
    summary();
  }

  const pending = new Set();
  async function requestGrade(id) {
    if (pending.has(id)) return;
    pending.add(id);
    let g;
    try {
      const res = await fetch("/__chat/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: exam.dataset.level, id, response: state.answers[id] }),
      });
      g = await res.json();
    } catch (err) { g = { error: String(err.message || err) }; }
    pending.delete(id);
    if (g.error) {
      byId[id].querySelector(".q-grade").innerHTML = `<div class="verdict">Grading failed</div><p>${g.error.replace(/</g, "&lt;")}</p>`;
      return;
    }
    state.grades[id] = g;
    save();
    grade();
    if (chat) refresh();  // the server counted a correct written answer
  }

  function summary() {
    const v = state.ids.map(verdictOf);
    const points = v.reduce((s, x) => s + (x === "correct" ? 1 : x === "partial" ? 0.5 : 0), 0);
    const scored = v.filter((x) => x !== "pending").length;
    const waiting = v.filter((x) => x === "pending").length;
    const review = new Map();
    state.ids.forEach((id, i) => {
      if (v[i] !== "correct") byId[id].querySelectorAll(".q-review a").forEach((a) => review.set(a.getAttribute("href"), a.outerHTML));
    });
    result.hidden = false;
    result.innerHTML =
      `<div class="score"><b>${points}</b> / ${scored}</div>` +
      `<div><p>${waiting ? (chat ? `Claude is still grading ${waiting} written answer${waiting > 1 ? "s" : ""}.` : `${waiting} written answer${waiting > 1 ? "s are" : " is"} not scored; compare them with the full answers.`) :
        points === scored ? "Everything right." : "Each question below explains the right answer and why the others are wrong."}</p>` +
      (review.size ? `<p class="review-pages">Pages to review: ${[...review.values()].join(" · ")}</p>` : "") +
      `<p><button class="btn primary exam-again">New attempt</button></p></div>`;
    result.querySelector(".exam-again").addEventListener("click", () => { draw(); show(); scrollTo(0, 0); });
  }

  // ---- Claude explains a mistake in the chat panel

  function explain(id) {
    const q = byId[id];
    const text = (el) => (el ? el.innerText.trim() : "");
    const question = text(q.querySelector(".q-text"));
    let prompt;
    if (q.dataset.kind === "choice") {
      const chosen = q.querySelector(`[data-i="${state.answers[id]}"] label`);
      prompt = `In the ${exam.dataset.level} exam I got question ${id} wrong.\n\nQuestion: ${question}\n\n` +
        "Options:\n" + options(q).map((li) => "- " + text(li.querySelector("label"))).join("\n") +
        `\n\nMy answer: ${chosen ? text(chosen) : "(none)"}\nCorrect answer: ${text(q.querySelector("[data-correct] label"))}\n\n` +
        "Explain why my answer is wrong and walk me through the reasoning that leads to the correct one.";
    } else {
      prompt = `In the ${exam.dataset.level} exam, question ${id} asked me to write an answer.\n\nQuestion: ${question}\n\n` +
        `My answer: ${state.answers[id] || "(none)"}\n\nGrade: ${text(q.querySelector(".q-grade"))}\n\n` +
        "Help me understand what I missed or got wrong, and how to reason about it.";
    }
    chat.ask(prompt, `Explain my mistake: “${question.length > 90 ? question.slice(0, 90) + "…" : question}”`);
  }

  // ---- events

  list.addEventListener("change", (e) => {
    const q = e.target.closest(".q");
    if (state.submitted || !q || e.target.type !== "radio") return;
    state.answers[q.dataset.id] = +e.target.closest("li").dataset.i;
    save();
  });
  list.addEventListener("input", (e) => {
    if (state.submitted || e.target.tagName !== "TEXTAREA") return;
    state.answers[e.target.closest(".q").dataset.id] = e.target.value;
    save();
  });
  // After grading, a click on another option shows why it is wrong.
  list.addEventListener("click", (e) => {
    const li = e.target.closest(".q-options > li");
    if (state.submitted && li && !e.target.closest("a")) li.querySelector(".why").hidden = false;
  });
  // Keep typing in an answer away from the site's "/" search shortcut.
  list.addEventListener("keydown", (e) => { if (e.target.tagName === "TEXTAREA") e.stopPropagation(); });

  submit.addEventListener("click", () => {
    const open = state.ids.filter((id) => verdictOf(id) === "unanswered").length;
    if (open && !confirm(`${open} question${open > 1 ? "s are" : " is"} unanswered. Submit anyway?`)) return;
    state.submitted = true;
    save();
    show();
    result.scrollIntoView({ behavior: "smooth" });
    if (chat) {
      // Count this attempt once; written answers are counted as right when Claude grades them.
      const answered = state.ids.filter((id) => verdictOf(id) !== "unanswered");
      const correct = state.ids.filter((id) => byId[id].dataset.kind === "choice" && verdictOf(id) === "correct");
      api("/__chat/attempt", { level, answered, correct }).then((s) => { status = s; showStatus(); }).catch(() => {});
    }
  });
  exam.querySelector(".exam-new").addEventListener("click", () => {
    if (!state.submitted && Object.keys(state.answers).length && !confirm("Discard your answers and draw new questions?")) return;
    draw();
    show();
  });

  if (chat) await refresh();
  if (!state || !Array.isArray(state.ids)) draw();
  show();
  if (status && state.submitted) showCounts();
});

(function () {
  const prefix = document.body.dataset.prefix || "";

  // ---- theme toggle
  document.querySelector(".theme-btn").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
  });

  // ---- mobile nav
  document.querySelector(".menu-btn").addEventListener("click", () => document.body.classList.toggle("nav-open"));
  const current = document.querySelector(".sidebar a.on");
  const sidebar = document.querySelector(".sidebar");
  if (current) sidebar.scrollTop = current.offsetTop - sidebar.clientHeight / 2;

  // ---- search
  const docs = (window.SEARCH_DOCS || []).map((d) => ({
    ...d, tl: d.t.toLowerCase(), kl: d.k.toLowerCase(), xl: d.x.toLowerCase(),
  }));
  const input = document.getElementById("q");
  const box = document.getElementById("search-results");
  let sel = -1;
  const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const highlight = (s, terms) => {
    let out = escapeHtml(s);
    for (const t of terms) out = out.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi"), "<mark>$1</mark>");
    return out;
  };

  function search(q) {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    const hits = [];
    for (const d of docs) {
      let score = 0;
      let ok = true;
      for (const t of terms) {
        const inT = d.tl.includes(t), inK = d.kl.includes(t);
        const n = d.xl.split(t).length - 1;
        if (!inT && !inK && !n) { ok = false; break; }
        score += (inT ? 20 : 0) + (inK ? 12 : 0) + Math.min(n, 10);
      }
      if (ok) hits.push({ d, score });
    }
    hits.sort((a, b) => b.score - a.score);
    return hits.slice(0, 12).map(({ d }) => {
      const i = d.xl.indexOf(terms[0]);
      const start = Math.max(0, i - 60);
      const snip = i < 0 ? d.x.slice(0, 140) : (start ? "…" : "") + d.x.slice(start, i + 100) + "…";
      return { d, snip, terms };
    });
  }

  function render() {
    const q = input.value.trim();
    if (!q) { box.hidden = true; return; }
    const res = search(q);
    sel = -1;
    box.innerHTML = res.length
      ? res.map(({ d, snip, terms }) =>
          `<a href="${prefix}${d.h}"><span class="r-type">${d.y}</span><span class="r-title">${highlight(d.t, terms)}</span>` +
          `<span class="r-snip">${highlight(snip, terms)}</span></a>`).join("")
      : '<div class="r-empty">No matches.</div>';
    box.hidden = false;
  }

  input.addEventListener("input", render);
  input.addEventListener("focus", render);
  input.addEventListener("keydown", (e) => {
    const items = box.querySelectorAll("a");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = Math.max(0, Math.min(items.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)));
      items.forEach((a, i) => a.classList.toggle("sel", i === sel));
      if (items[sel]) items[sel].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && items.length) {
      location.href = items[Math.max(sel, 0)].href;
    } else if (e.key === "Escape") {
      box.hidden = true; input.blur();
    }
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) box.hidden = true; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); input.focus(); }
  });

  // ---- home: paper filters
  const cards = document.querySelectorAll(".card");
  if (cards.length) {
    let cat = "";
    const filterInput = document.getElementById("paper-filter");
    const apply = () => {
      const t = filterInput.value.trim().toLowerCase();
      cards.forEach((c) => {
        c.hidden = (cat && c.dataset.cat !== cat) || (t && !c.dataset.text.includes(t) && c.dataset.year !== t);
      });
    };
    document.querySelectorAll(".filter").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(".filter").forEach((x) => x.classList.toggle("on", x === b));
      cat = b.dataset.cat;
      apply();
    }));
    filterInput.addEventListener("input", apply);
  }

  // ---- table of contents: highlight the section in view
  const tocLinks = document.querySelectorAll(".toc a");
  if (tocLinks.length && "IntersectionObserver" in window) {
    const byId = {};
    tocLinks.forEach((a) => (byId[a.getAttribute("href").slice(1)] = a));
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) {
        tocLinks.forEach((a) => a.classList.remove("on"));
        const a = byId[e.target.id];
        if (a) a.classList.add("on");
      }
    }, { rootMargin: "-70px 0px -70% 0px" });
    document.querySelectorAll(".prose h2[id]").forEach((h) => obs.observe(h));
  }
})();

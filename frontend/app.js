/* Encontramed — PWA. Dados externos são inseridos sempre via textContent (nunca innerHTML). */
(() => {
  "use strict";
  const API = (window.ENCONTRAMED_API || "").replace(/\/$/, "");
  const $ = (s, el = document) => el.querySelector(s);
  const RECENT_KEY = "encontramed.recent";
  const STATUS_RANK = { ESTOQUE_CONFIRMADO: 0, DISPONIBILIDADE_INFORMADA: 1, CONSULTAR_FARMACIA: 2, INDISPONIVEL: 3 };
  let current = null;
  let sortMode = "relevancia";

  const brl = (v) => v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const when = (iso) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  const el = (tag, props = {}, text) => {
    const e = document.createElement(tag);
    Object.assign(e, props);
    if (text != null) e.textContent = text;
    return e;
  };
  const safeUrl = (u) => {
    try { const x = new URL(u); return ["https:", "http:", "tel:"].includes(x.protocol) ? x.href : null; }
    catch { return null; }
  };

  // ---------- recentes (lista de medicamentos pesquisados) ----------
  const loadRecent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; } };
  const saveRecent = (m, l) => {
    try {
      const list = loadRecent().filter((r) => !(r.m === m && r.l === l));
      list.unshift({ m, l });
      localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 8)));
    } catch { /* storage indisponível */ }
  };
  function renderRecent() {
    const box = $("#recent"); const list = loadRecent();
    box.replaceChildren();
    if (!list.length) { box.hidden = true; return; }
    box.hidden = false;
    box.append(el("span", {}, "Recentes:"));
    list.forEach((r) => {
      const b = el("button", { type: "button" }, r.l ? `${r.m} · ${r.l}` : r.m);
      b.onclick = () => { $("#medicine").value = r.m; $("#location").value = r.l || ""; search(); };
      box.append(b);
    });
  }

  // ---------- ordenação (espelha engine/search.py) ----------
  const big = 1e9;
  const price = (o) => o.total_price ?? o.price ?? big;
  const dist = (o) => o.store.distance_km ?? big;
  const days = (o) => o.channel === "retirada" ? (o.shipping_days ?? 0) : (o.shipping_days ?? big);
  const cmp = (...ks) => (a, b) => { for (const k of ks) { const d = k(a) - k(b); if (d) return d; } return 0; };
  const rank = (o) => STATUS_RANK[o.status];
  const unavailable = (o) => o.status === "INDISPONIVEL" ? 1 : 0;
  const SORTERS = {
    relevancia: cmp(rank, (o) => o.channel === "retirada" ? 0 : 1, price, dist, days),
    proximos: cmp(dist, rank, price),
    preco: cmp(unavailable, price, rank),
    entrega: cmp(unavailable, days, rank, price),
    confirmado: cmp(rank, dist, price),
  };
  const sorted = (list) => [...list].sort(SORTERS[sortMode]);

  // ---------- cartões ----------
  function fact(dl, label, value, cls) {
    if (value == null || value === "") return;
    const d = el("div", { className: cls || "" });
    d.append(el("dt", {}, label), el("dd", {}, value));
    dl.append(d);
  }
  function link(actions, label, href, primary) {
    const u = safeUrl(href); if (!u) return;
    const a = el("a", { href: u, className: primary ? "primary" : "" }, label);
    if (!u.startsWith("tel:")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    actions.append(a);
  }
  function card(o, { compact = false } = {}) {
    const node = $("#offer-tpl").content.firstElementChild.cloneNode(true);
    const s = o.store;
    $(".store", node).textContent = s.name;
    $(".product", node).textContent = o.product ? o.product.name : [s.address, s.city].filter(Boolean).join(" · ");
    const badge = $(".badge", node);
    badge.textContent = o.status_label; badge.classList.add(`s-${o.status}`);
    const dl = $(".facts", node);
    if (o.channel === "retirada") {
      if (o.product) fact(dl, "Endereço", [s.address, s.city].filter(Boolean).join(", "));
      fact(dl, "Distância", s.distance_km != null ? `${s.distance_km.toFixed(1).replace(".", ",")} km` : null);
      fact(dl, "Telefone", s.phone);
      fact(dl, "Horário", s.opening_hours);
      fact(dl, "Preço", o.price != null ? brl(o.price) : null, "total");
      fact(dl, "Retirada", o.shipping_label);
    } else {
      fact(dl, "Preço", brl(o.price));
      fact(dl, "Frete", o.shipping_price != null ? (o.shipping_price === 0 ? "Grátis" : brl(o.shipping_price)) : "não calculado");
      fact(dl, "Prazo", o.shipping_label);
      fact(dl, "Total", o.total_price != null ? brl(o.total_price) : null, "total");
    }
    if (o.product && o.product.pack_quantity) fact(dl, "Embalagem", `${o.product.pack_quantity} un.`);
    const ul = $(".warnings", node);
    (o.warnings || []).forEach((w) => ul.append(el("li", {}, w)));
    if (o.match && o.match.confidence < 0.9) (o.match.reasons || []).slice(1).forEach((r) => ul.append(el("li", {}, r)));

    const actions = $(".actions", node);
    if (s.phone) link(actions, "Ligar", `tel:${s.phone.replace(/[^\d+]/g, "")}`, o.status === "CONSULTAR_FARMACIA");
    if (s.directions_url) link(actions, "Como chegar", s.directions_url, o.channel === "retirada" && o.status !== "CONSULTAR_FARMACIA");
    if (o.product_url) link(actions, o.purchase_allowed_online ? "Comprar na loja" : "Ver na loja", o.product_url, o.channel === "entrega" && o.purchase_allowed_online);

    const ev = $(".evidence", node);
    const e0 = (o.evidence || [])[0];
    if (e0) {
      ev.append(`Fonte: ${e0.source_name} · consultado em ${when(e0.checked_at)}`);
      if (e0.notes && e0.notes[0]) ev.append(el("br"), e0.notes[0]);
    }
    if (compact) node.querySelector(".card-body").classList.add("compact");
    return node;
  }
  function fill(id, list, emptyText, opts) {
    const box = $(id); box.replaceChildren();
    if (!list.length) { box.append(el("div", { className: "empty" }, emptyText)); return; }
    sorted(list).forEach((o) => box.append(card(o, opts)));
  }

  // ---------- render ----------
  function render() {
    const r = current; if (!r) return;
    const q = r.query; const loc = r.location;
    const qi = $("#query-info"); qi.replaceChildren();
    qi.append("Buscando ", el("b", {}, [q.brands.join(", "), q.active_ingredients.join(", ")].filter(Boolean).join(" · ") || q.raw_text));
    if (q.dose_value) qi.append(" ", el("b", {}, `${q.dose_value} ${q.dose_unit}`));
    if (loc) qi.append(" em ", el("b", {}, [loc.city, loc.state].filter(Boolean).join("-") || loc.raw_text), loc.postal_code ? ` (CEP ${loc.postal_code})` : "");
    qi.append(` · ${when(r.created_at)}`);

    const alerts = $("#alerts"); alerts.replaceChildren();
    if (q.controlled) {
      const a = el("div", { className: "alert legal" });
      a.append(el("strong", {}, `Medicamento controlado (lista ${q.controlled.list_code}) — ${q.controlled.prescription}`));
      const ul = el("ul"); q.controlled.legal_notes.slice(2).forEach((n) => ul.append(el("li", {}, n)));
      a.append(ul); alerts.append(a);
    }
    const others = r.warnings.filter((w) => !(q.controlled && q.controlled.legal_notes.includes(w)));
    if (others.length) {
      const a = el("div", { className: "alert info" }); const ul = el("ul");
      others.forEach((w) => ul.append(el("li", {}, w))); a.append(ul); alerts.append(a);
    }

    $("#city-label").textContent = loc && loc.city ? `em ${loc.city}` : "";
    fill("#local-list", r.local_offers, "Nenhuma loja integrada informou estoque para retirada na cidade. Veja abaixo as farmácias para consultar por telefone.");
    $("#pharm-count").textContent = `(${r.local_pharmacies_without_data.length})`;
    $("#pharmacies-box").open = !r.local_offers.length && r.local_pharmacies_without_data.length > 0;
    fill("#pharm-list", r.local_pharmacies_without_data, "Nenhuma farmácia localizada no mapa para esta cidade.", { compact: true });
    $("#expansion").textContent = r.expansion_reason || "";
    fill("#online-list", r.online_offers, "Nenhuma loja online integrada retornou este medicamento.");
    $("#related-stage").hidden = !r.related_offers.length;
    fill("#related-list", r.related_offers, "");

    const ml = $("#manual-list"); ml.replaceChildren();
    $("#manual-stage").hidden = !r.manual_checks.length;
    r.manual_checks.forEach((m) => {
      const c = el("article", { className: "card" });
      c.append(el("h3", { className: "store" }, m.name), el("p", { className: "product" }, m.reason));
      const act = el("div", { className: "actions" }); link(act, "Abrir busca no site", m.url, true); c.append(act);
      ml.append(c);
    });

    const sl = $("#sources-list"); sl.replaceChildren();
    r.source_runs.forEach((s) => {
      const row = el("div", { className: "src" });
      row.append(el("span", {}, `${s.source_name} — ${s.offers} resultado(s) · ${s.duration_ms ?? 0} ms`),
        el("span", { className: `st st-${s.status}` }, s.status.replace("_", " ")));
      if (s.message) row.append(el("span", { className: "msg" }, s.message));
      sl.append(row);
    });
    $("#sources-box").open = r.summary.sources_failed > 0 && !r.local_offers.length && !r.online_offers.length;
  }

  function setStatus(content, spinning) {
    const s = $("#status"); s.hidden = !content; s.replaceChildren();
    if (spinning) s.append(el("span", { className: "spinner" }));
    if (content) s.append(content);
  }

  async function search(ev) {
    if (ev) ev.preventDefault();
    const medicine = $("#medicine").value.trim();
    const location = $("#location").value.trim();
    if (medicine.length < 2) return;
    const btn = $("#go"); btn.disabled = true;
    $("#results").hidden = true;
    setStatus("Consultando farmácias e lojas online… isso pode levar alguns segundos.", true);
    const params = new URLSearchParams({ m: medicine }); if (location) params.set("l", location);
    history.replaceState(null, "", `?${params}`);
    try {
      const res = await fetch(`${API}/api/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ medicine, location: location || null }),
      });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      current = await res.json();
      saveRecent(medicine, location); renderRecent();
      setStatus(null); render(); $("#results").hidden = false;
    } catch (e) {
      setStatus(`Não foi possível concluir a busca (${e.message}). Verifique a conexão e tente novamente.`);
    } finally { btn.disabled = false; }
  }

  document.querySelectorAll(".sorts button").forEach((b) => b.addEventListener("click", () => {
    sortMode = b.dataset.sort;
    document.querySelectorAll(".sorts button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    render();
  }));
  $("#search").addEventListener("submit", search);
  renderRecent();
  const p = new URLSearchParams(location.search);
  if (p.get("m")) { $("#medicine").value = p.get("m"); $("#location").value = p.get("l") || ""; search(); }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();

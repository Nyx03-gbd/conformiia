/* ConformiIA - Tableau de bord : emojis, accès rapides, dernière analyse */
(function () {
    "use strict";
    if (window.__cfDashFix) { return; }
    window.__cfDashFix = true;

    const API = () => window.API_BASE || "http://127.0.0.1:8001";
    const PICTO = /^\s*(?:\p{Extended_Pictographic}[\uFE0F\u200D]*)+\s*/u;
    const _svg = (pp) => '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + pp + "</svg>";
    const ICONS = {
        organisation: _svg('<path d="M3 21h18"></path><path d="M5 21V7l8-4v18"></path><path d="M19 21V11l-6-4"></path>'),
        formulaires: _svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline>'),
        registre: _svg('<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1"></rect>'),
        incidents: _svg('<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>'),
        conformite: _svg('<line x1="12" y1="20" x2="12" y2="10"></line><line x1="18" y1="20" x2="18" y2="4"></line><line x1="6" y1="20" x2="6" y2="16"></line>'),
        risques: _svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>'),
        documents: _svg('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>'),
        profil: _svg('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle>'),
        dashboard: _svg('<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline>'),
    };
    const DOT = _svg('<circle cx="12" cy="12" r="2.5"></circle>');
    const _fetch = window.fetch.bind(window);

    const st = document.createElement("style");
    st.textContent = `
html body .quick-card > span:first-child { display:flex !important; align-items:center; justify-content:center;
    font-size:0 !important; line-height:1 !important; opacity:1 !important; visibility:visible !important; text-indent:0 !important; }
html body .quick-card strong { white-space:normal !important; overflow:visible !important; text-overflow:clip !important; line-height:1.25 !important; }
html body .quick-card small { white-space:normal !important; overflow:visible !important; text-overflow:clip !important; }`;
    document.head.appendChild(st);

    /* ---------- Accès rapides ---------- */
    function fixQuickCards() {
        document.querySelectorAll(".quick-card").forEach((card) => {
            const m = /navigate\(\s*['"]([\w-]+)['"]/.exec(card.getAttribute("onclick") || "");
            const strong = card.querySelector("strong");
            const icon = card.querySelector(":scope > span");
            const fromTitle = strong && PICTO.exec(strong.textContent || "");
            const svg = (m && ICONS[m[1]]) || DOT;
            if (icon) { icon.innerHTML = svg; }
            if (strong && PICTO.test(strong.textContent || "")) {
                strong.textContent = strong.textContent.replace(PICTO, "");
            }
        });
    }

    /* ---------- Cartes Analyse / Scoring ---------- */
    function labelOf(text) {
        return Array.from(document.querySelectorAll("span")).find((s) =>
            s.textContent.replace(PICTO, "").trim().toLowerCase() === text);
    }
    function valueEl(id, labelText) {
        let v = document.getElementById(id);
        if (v) { return v; }
        const l = labelOf(labelText);
        if (!l) { return null; }
        v = l.parentElement.querySelector("strong");
        if (!v) {
            v = document.createElement("strong");
            l.insertAdjacentElement("afterend", v);
        }
        return v;
    }
    function decorate(valueNode, labelText, emoji) {
        const l = (valueNode && valueNode.parentElement && Array.from(valueNode.parentElement.querySelectorAll("span"))
            .find((s) => s.textContent.replace(PICTO, "").trim().toLowerCase() === labelText)) || labelOf(labelText);
        if (l && !PICTO.test(l.textContent)) { l.textContent = emoji + " " + l.textContent.trim(); }
    }
    const fmt = (n) => Number(n).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
    const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    function levelColor(n) {
        const k = norm(n);
        if (k.startsWith("faible") || k.startsWith("bas")) { return "#067647"; }
        if (k.startsWith("moyen") || k.startsWith("modere")) { return "#b54708"; }
        return "#b42318";
    }
    function setText(el, txt, color) {
        if (!el) { return; }
        if (el.textContent !== txt) { el.textContent = txt; }
        if (color && el.style.color !== color) { el.style.color = color; }
    }

    let cache = null, refreshing = false, lastEl = null;

    function apply() {
        const conf = valueEl("dashboard-score-conformite", "score de conformité");
        const risk = valueEl("dashboard-score-risque", "score de risque");
        const lvl = valueEl("dashboard-niveau-risque", "niveau de risque");
        const trt = valueEl("dashboard-traitement-evalue", "traitement évalué");
        if (!cache) { return; }
        const { t, lc, lr, when } = cache;
        const date = new Date(when);
        const quand = isNaN(date) ? "" : date.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
        if (lc) { setText(conf, fmt(lc.score_global) + " %"); }
        if (lr) {
            setText(risk, fmt(lr.score_global));
            const n = String(lr.niveau || "");
            setText(lvl, n.charAt(0).toUpperCase() + n.slice(1), levelColor(n));
        }
        const id = t.id || t.traitement_id || "";
        const nom = t.nom_traitement || t.nom || t.name || ("Traitement #" + String(id).slice(0, 8));
        setText(trt, nom);
        if (trt) { trt.title = nom; }
        const sm = (el) => el && el.parentElement && el.parentElement.querySelector("small");
        const s1 = sm(conf), s2 = sm(risk), s4 = sm(trt);
        if (s1) { setText(s1, "Dernière évaluation" + (quand ? " : " + quand : "")); }
        if (s2) { setText(s2, "Dernière évaluation" + (quand ? " : " + quand : "")); }
        if (s4) { setText(s4, "Dernier traitement analysé"); }
    }

    async function refresh() {
        if (refreshing) { return; }
        refreshing = true;
        try {
            const raw = await (await _fetch(API() + "/traitements")).json();
            const list = Array.isArray(raw) ? raw : (raw.items || raw.data || raw.traitements || []);
            let best = null;
            await Promise.all(list.map(async (t) => {
                const id = t.id || t.traitement_id;
                if (!id) { return; }
                try {
                    const [c, r] = await Promise.all([
                        _fetch(API() + "/traitements/" + id + "/scores/conformite").then((x) => (x.ok ? x.json() : [])),
                        _fetch(API() + "/traitements/" + id + "/scores/risque").then((x) => (x.ok ? x.json() : []))
                    ]);
                    const last = (a) => (Array.isArray(a) ? a : [a]).filter(Boolean)
                        .sort((x, y) => String(y.date_calcul).localeCompare(String(x.date_calcul)))[0];
                    const lc = last(c), lr = last(r);
                    const when = [lc && lc.date_calcul, lr && lr.date_calcul].filter(Boolean).sort().pop();
                    if (when && (!best || when > best.when)) { best = { t, lc, lr, when }; }
                } catch (_) {}
            }));
            if (best) { cache = best; }
        } catch (e) {
            console.warn("[ConformiIA] Dernière analyse indisponible :", e);
        }
        refreshing = false;
        apply();
    }

    /* Rafraîchit après chaque calcul de score */
    window.fetch = function (input, init) {
        const p = _fetch(input, init);
        try {
            const url = typeof input === "string" ? input : ((input && input.url) || "");
            const method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
            if (method === "POST" && /\/scores\/calculer/.test(url)) {
                p.then((r) => { if (r.ok) { setTimeout(refresh, 800); } }).catch(() => {});
            }
        } catch (_) {}
        return p;
    };

    let timer = null;
    function tick() {
        fixQuickCards();
        apply();
        const el = document.getElementById("dashboard-score-conformite");
        if (el && el !== lastEl) { lastEl = el; refresh(); }
    }
    new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(tick, 120); })
        .observe(document.body, { childList: true, subtree: true, characterData: true });
    tick();
})();

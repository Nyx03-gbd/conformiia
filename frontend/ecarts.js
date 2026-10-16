/* ConformiIA - Analyse des écarts APDP + plan d'action (bloc 2) */
(function () {
    "use strict";
    if (window.__cfEcartsInstalled) { return; }
    window.__cfEcartsInstalled = true;

    const API = () => window.API_BASE || "http://127.0.0.1:8001";
    const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    const STATUTS = {
        conforme: { label: "Conforme", bg: "#ecfdf3", fg: "#067647", bd: "#abefc6" },
        partiellement_conforme: { label: "Partiellement conforme", bg: "#fffaeb", fg: "#b54708", bd: "#fedf89" },
        non_conforme: { label: "Non conforme", bg: "#fef3f2", fg: "#b42318", bd: "#fecdca" },
        non_evalue: { label: "Non évalué", bg: "#f2f4f7", fg: "#475467", bd: "#e4e7ec" },
        non_applicable: { label: "Non applicable", bg: "#f8f9fc", fg: "#98a2b3", bd: "#eaecf0" },
    };
    const PRIORITES = { faible: "Faible", moyenne: "Moyenne", elevee: "Élevée", critique: "Critique" };
    const ACT_STATUTS = { a_faire: "À faire", en_cours: "En cours", realisee: "Réalisée", validee: "Validée" };

    const state = { orgId: null, traitementId: null, evals: [], synth: null, orgs: [], traitements: [] };

    async function jget(path) {
        const r = await fetch(API() + path, { headers: authHeaders() });
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
    }
    function authHeaders() {
        const h = { "Content-Type": "application/json" };
        try { const t = localStorage.getItem("conformiia_access_token"); if (t) { h["Authorization"] = "Bearer " + t; } } catch (_) { /* ignore */ }
        return h;
    }
    async function jsend(method, path, body) {
        const r = await fetch(API() + path, {
            method,
            headers: authHeaders(),
            body: body == null ? undefined : JSON.stringify(body),
        });
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.status === 204 ? null : r.json();
    }

    function sel(name, options, value, extra) {
        const opts = Object.entries(options).map(([k, v]) =>
            '<option value="' + k + '"' + (k === value ? " selected" : "") + ">" + esc(v) + "</option>").join("");
        return '<select data-field="' + name + '" ' + (extra || "") + ' style="padding:6px 8px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;background:#fff;">' + opts + "</select>";
    }

    // ---------- data ----------
    async function loadScope() {
        state.orgs = await jget("/organisations").then((d) => Array.isArray(d) ? d : (d.items || d.data || []));
        if (!state.orgId && state.orgs[0]) {
            const ctx = window.conformiiaContext;
            state.orgId = (ctx && ctx.organisationId) || state.orgs[0].id;
        }
        if (state.orgId) {
            try {
                const t = await jget("/traitements?organisation_id=" + encodeURIComponent(state.orgId));
                state.traitements = Array.isArray(t) ? t : (t.items || t.data || []);
            } catch (_) { state.traitements = []; }
        }
    }

    function scopeQuery() {
        return "?organisation_id=" + encodeURIComponent(state.orgId) +
            (state.traitementId ? "&traitement_id=" + encodeURIComponent(state.traitementId) : "");
    }

    async function loadData() {
        const q = scopeQuery();
        [state.evals, state.synth] = await Promise.all([
            jget("/analyse-ecarts" + q),
            jget("/analyse-ecarts/synthese" + q),
        ]);
    }

    async function refreshSynth() {
        try {
            state.synth = await jget("/analyse-ecarts/synthese" + scopeQuery());
            const el = document.getElementById("cf-ec-synth");
            if (el) { el.innerHTML = synthHtml(state.synth); }
        } catch (_) { /* silencieux */ }
    }

    // ---------- render ----------
    function synthHtml(s) {
        if (!s) { return ""; }
        const cell = (n, lbl, color) =>
            '<div style="flex:1;min-width:120px;background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:12px 14px;">'
            + '<div style="font-size:24px;font-weight:700;color:' + (color || "#101828") + ';">' + n + "</div>"
            + '<div style="font-size:12px;color:#667085;">' + esc(lbl) + "</div></div>";
        const p = s.par_statut;
        return '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px;">'
            + cell(s.taux_conformite + " %", "Taux de conformité évaluée", "#067647")
            + cell(p.conforme, "Conformes", STATUTS.conforme.fg)
            + cell(p.partiellement_conforme, "Partiellement", STATUTS.partiellement_conforme.fg)
            + cell(p.non_conforme, "Non conformes", STATUTS.non_conforme.fg)
            + cell(p.non_evalue, "Non évaluées", STATUTS.non_evalue.fg)
            + cell(s.actions_en_retard, "Actions en retard", s.actions_en_retard ? "#b42318" : "#101828")
            + "</div>";
    }

    function actionHtml(a) {
        return '<div class="cf-ec-action" data-act="' + a.id + '" style="border:1px solid #eaecf0;border-radius:9px;padding:10px 12px;margin-top:8px;background:#fcfcfd;">'
            + '<div style="display:flex;gap:8px;align-items:flex-start;">'
            + '<textarea data-field="action" rows="1" style="flex:1;padding:7px 9px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;resize:vertical;">' + esc(a.action) + "</textarea>"
            + '<button data-act-del="1" title="Supprimer" style="border:1px solid #fecdca;background:#fef3f2;color:#b42318;border-radius:7px;padding:6px 9px;cursor:pointer;font-size:13px;">✕</button></div>'
            + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center;">'
            + '<input data-field="responsable" placeholder="Responsable" value="' + esc(a.responsable || "") + '" style="flex:1;min-width:130px;padding:6px 9px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;">'
            + '<input data-field="echeance" type="date" value="' + esc((a.echeance || "").slice(0, 10)) + '" style="padding:6px 9px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;">'
            + sel("priorite", PRIORITES, a.priorite) + sel("statut", ACT_STATUTS, a.statut) + "</div></div>";
    }

    function rowHtml(ev) {
        const st = STATUTS[ev.statut] || STATUTS.non_evalue;
        const ex = ev.exigence;
        const nbAct = (ev.actions || []).length;
        return '<div class="cf-ec-row" data-eval="' + ev.id + '" style="border:1px solid #e4e7ec;border-radius:12px;margin-bottom:10px;background:#fff;overflow:hidden;">'
            + '<div class="cf-ec-head" style="display:flex;gap:12px;align-items:center;padding:12px 14px;cursor:pointer;">'
            + '<span style="font-family:monospace;font-size:12px;color:#667085;min-width:54px;">' + esc(ex.code) + "</span>"
            + '<span style="flex:1;font-size:14px;color:#172033;">' + esc(ex.intitule) + "</span>"
            + '<span data-pill style="font-size:12px;font-weight:600;color:' + st.fg + ';background:' + st.bg + ';border:1px solid ' + st.bd + ';padding:3px 9px;border-radius:999px;white-space:nowrap;">' + esc(st.label) + "</span>"
            + '<span style="font-size:12px;color:#667085;white-space:nowrap;">' + (nbAct ? nbAct + " action" + (nbAct > 1 ? "s" : "") : "") + "</span>"
            + '<span class="cf-ec-caret" style="color:#98a2b3;font-size:12px;">▾</span></div>'
            + '<div class="cf-ec-body" style="display:none;padding:0 14px 14px;border-top:1px solid #f2f4f7;">'
            + '<div style="display:flex;gap:16px;flex-wrap:wrap;margin:12px 0 6px;">'
            + '<div><div style="font-size:12px;color:#667085;margin-bottom:3px;">Statut de conformité</div>' + sel("statut", Object.fromEntries(Object.entries(STATUTS).map(([k, v]) => [k, v.label])), ev.statut, 'data-eval-statut="1"') + "</div>"
            + '<div style="flex:1;min-width:200px;"><div style="font-size:12px;color:#667085;margin-bottom:3px;">Référence réglementaire</div>'
            + '<input data-field="reference_reglementaire" value="' + esc(ev.reference_reglementaire || ex.reference_reglementaire || "") + '" style="width:100%;padding:7px 9px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;box-sizing:border-box;"></div></div>'
            + (ex.description ? '<p style="font-size:12px;color:#98a2b3;margin:4px 0 8px;">' + esc(ex.description) + "</p>" : "")
            + fld("constat", "Constat", ev.constat)
            + fld("justification", "Justification", ev.justification)
            + fld("preuve", "Preuve (référence / lien du document)", ev.preuve)
            + '<div style="margin-top:14px;display:flex;justify-content:space-between;align-items:center;">'
            + '<strong style="font-size:13px;color:#344054;">Plan d\'action</strong>'
            + '<button data-add-action="1" style="border:1px solid #b2ddff;background:#eff8ff;color:#175cd3;border-radius:7px;padding:6px 12px;cursor:pointer;font-size:13px;">+ Action corrective</button></div>'
            + '<div class="cf-ec-actions">' + (ev.actions || []).map(actionHtml).join("") + "</div>"
            + "</div></div>";
    }

    function fld(name, lbl, value) {
        return '<div style="margin-top:8px;"><div style="font-size:12px;color:#667085;margin-bottom:3px;">' + esc(lbl) + "</div>"
            + '<textarea data-field="' + name + '" rows="2" style="width:100%;padding:8px 10px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;box-sizing:border-box;resize:vertical;">' + esc(value || "") + "</textarea></div>";
    }

    function gridHtml() {
        if (!state.evals.length) { return '<p style="color:#667085;">Aucune exigence. Vérifiez que le référentiel est chargé.</p>'; }
        const groups = {};
        state.evals.forEach((e) => { (groups[e.exigence.domaine] = groups[e.exigence.domaine] || []).push(e); });
        return Object.entries(groups).map(([dom, list]) =>
            '<div style="margin:18px 0 6px;font-size:13px;font-weight:700;color:#475467;text-transform:uppercase;letter-spacing:.03em;">' + esc(dom) + "</div>"
            + list.map(rowHtml).join("")).join("");
    }

    function scopeBar() {
        const orgOpts = state.orgs.map((o) => '<option value="' + o.id + '"' + (o.id === state.orgId ? " selected" : "") + ">" + esc(o.nom) + "</option>").join("");
        const trOpts = '<option value="">- Toute l\'organisation -</option>' + state.traitements.map((t) =>
            '<option value="' + t.id + '"' + (t.id === state.traitementId ? " selected" : "") + ">" + esc(t.nom) + "</option>").join("");
        return '<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px;">'
            + '<div><div style="font-size:12px;color:#667085;margin-bottom:3px;">Organisation</div>'
            + '<select id="cf-ec-org" style="padding:8px 10px;border:1px solid #d0d5dd;border-radius:8px;font:inherit;min-width:220px;">' + orgOpts + "</select></div>"
            + '<div><div style="font-size:12px;color:#667085;margin-bottom:3px;">Portée</div>'
            + '<select id="cf-ec-tr" style="padding:8px 10px;border:1px solid #d0d5dd;border-radius:8px;font:inherit;min-width:240px;">' + trOpts + "</select></div></div>";
    }

    function render() {
        const root = document.getElementById("cf-ecarts-root");
        if (!root) { return; }
        root.innerHTML = '<div style="text-align:left;">' + scopeBar()
            + '<div id="cf-ec-synth">' + synthHtml(state.synth) + "</div>"
            + '<div id="cf-ec-grid">' + gridHtml() + "</div></div>";
        wire(root);
    }

    async function reloadAndRender(full) {
        const root = document.getElementById("cf-ecarts-root");
        try {
            if (full) { await loadScope(); }
            await loadData();
            render();
        } catch (e) {
            if (root) { root.innerHTML = '<p style="color:#b42318;padding:20px;">Impossible de charger l\'analyse des écarts : ' + esc(e.message) + ". Vérifiez qu'une organisation existe (page Organisation).</p>"; }
        }
    }

    // ---------- events ----------
    function wire(root) {
        root.querySelector("#cf-ec-org").onchange = (e) => { state.orgId = e.target.value; state.traitementId = null; reloadAndRender(true); };
        root.querySelector("#cf-ec-tr").onchange = (e) => { state.traitementId = e.target.value || null; reloadAndRender(false); };

        // expand/collapse
        root.querySelectorAll(".cf-ec-head").forEach((h) => {
            h.addEventListener("click", (e) => {
                if (e.target.closest("select,input,textarea,button")) { return; }
                const body = h.parentElement.querySelector(".cf-ec-body");
                const open = body.style.display !== "none";
                body.style.display = open ? "none" : "block";
                h.querySelector(".cf-ec-caret").textContent = open ? "▾" : "▴";
            });
        });

        // evaluation statut (header pill select in body)
        root.querySelectorAll('[data-eval-statut]').forEach((s) => {
            s.addEventListener("change", async (e) => {
                const row = e.target.closest(".cf-ec-row");
                await saveEval(row, { statut: e.target.value });
                const st = STATUTS[e.target.value];
                const pill = row.querySelector("[data-pill]");
                pill.textContent = st.label; pill.style.color = st.fg; pill.style.background = st.bg; pill.style.borderColor = st.bd;
                refreshSynth();
            });
        });

        // evaluation text fields (constat/justification/preuve/reference) on blur
        root.querySelectorAll(".cf-ec-body > div > textarea[data-field], .cf-ec-body input[data-field='reference_reglementaire']").forEach((el) => {
            el.addEventListener("change", (e) => {
                const row = e.target.closest(".cf-ec-row");
                saveEval(row, { [e.target.dataset.field]: e.target.value });
            });
        });
        // the fld() textareas live deeper; bind all body textareas that are eval fields
        root.querySelectorAll(".cf-ec-body textarea[data-field]").forEach((el) => {
            if (["constat", "justification", "preuve"].includes(el.dataset.field)) {
                el.addEventListener("change", (e) => saveEval(e.target.closest(".cf-ec-row"), { [el.dataset.field]: e.target.value }));
            }
        });

        // add action
        root.querySelectorAll('[data-add-action]').forEach((b) => {
            b.addEventListener("click", async (e) => {
                const row = e.target.closest(".cf-ec-row");
                const evalId = row.dataset.eval;
                try {
                    const a = await jsend("POST", "/analyse-ecarts/evaluations/" + evalId + "/actions", { action: "Nouvelle action corrective" });
                    const box = row.querySelector(".cf-ec-actions");
                    box.insertAdjacentHTML("beforeend", actionHtml(a));
                    wireAction(box.lastElementChild);
                    updateActionBadge(row);
                    refreshSynth();
                } catch (err) { alert("Erreur : " + err.message); }
            });
        });

        root.querySelectorAll(".cf-ec-action").forEach(wireAction);
    }

    function updateActionBadge(row) {
        const n = row.querySelectorAll(".cf-ec-action").length;
        const badge = row.querySelector(".cf-ec-head > span:nth-last-child(2)");
        if (badge) { badge.textContent = n ? n + " action" + (n > 1 ? "s" : "") : ""; }
    }

    function wireAction(el) {
        const id = el.dataset.act;
        const save = (patch) => jsend("PATCH", "/analyse-ecarts/actions/" + id, patch)
            .then(() => { if ("echeance" in patch || "statut" in patch) { refreshSynth(); } })
            .catch((e) => alert("Erreur : " + e.message));
        el.querySelectorAll("[data-field]").forEach((f) => {
            f.addEventListener("change", () => {
                let v = f.value;
                if (f.dataset.field === "echeance") { v = v ? v + "T00:00:00" : null; }
                save({ [f.dataset.field]: v });
            });
        });
        el.querySelector("[data-act-del]").addEventListener("click", async () => {
            if (!confirm("Supprimer cette action ?")) { return; }
            const row = el.closest(".cf-ec-row");
            try { await jsend("DELETE", "/analyse-ecarts/actions/" + id); el.remove(); updateActionBadge(row); refreshSynth(); }
            catch (e) { alert("Erreur : " + e.message); }
        });
    }

    async function saveEval(row, patch) {
        try { await jsend("PATCH", "/analyse-ecarts/evaluations/" + row.dataset.eval, patch); }
        catch (e) { alert("Impossible d'enregistrer : " + e.message); }
    }

    // ---------- show when page active ----------
    let shownFor = null;
    function maybeShow() {
        const root = document.getElementById("cf-ecarts-root");
        if (!root) { shownFor = null; return; }
        if (shownFor === root) { return; }   // already rendered into this instance
        shownFor = root;
        reloadAndRender(true);
    }
    new MutationObserver(maybeShow).observe(document.body, { childList: true, subtree: true });
    maybeShow();
})();

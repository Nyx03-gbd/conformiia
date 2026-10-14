/* ConformiIA — Incidents : déclaration + liste avec délai de 72 h */
(function () {
    "use strict";
    if (window.__cfIncidentsInstalled) { return; }
    window.__cfIncidentsInstalled = true;

    const API = () => window.API_BASE || "http://127.0.0.1:8001";
    const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    function authHeaders() {
        const h = { "Content-Type": "application/json" };
        try { const t = localStorage.getItem("conformiia_access_token"); if (t) { h["Authorization"] = "Bearer " + t; } } catch (_) { /* ignore */ }
        return h;
    }

    const label = (v) => { const t = String(v || "").replace(/_/g, " ").trim(); return t.charAt(0).toUpperCase() + t.slice(1); };
    const DEF_VIOL = ["Accès non autorisé", "Perte ou vol de données", "Vol ou perte de matériel",
        "Divulgation accidentelle", "Rançongiciel / malware", "Altération des données"];
    const DEF_CONS = ["Usurpation d'identité", "Perte financière", "Atteinte à la réputation",
        "Discrimination", "Indisponibilité du service"];

    async function getOptions() {
        const out = { viol: DEF_VIOL, cons: DEF_CONS };
        try {
            const d = await (await fetch(API() + "/openapi.json")).json();
            const p = d.components.schemas.IncidentCreate.properties;
            const en = (prop) => {
                let it = prop && prop.items;
                if (it && it.$ref) { it = d.components.schemas[it.$ref.split("/").pop()]; }
                return it && it.enum;
            };
            out.viol = en(p.types_violation) || out.viol;
            out.cons = en(p.consequences_potentielles) || out.cons;
        } catch (_) {}
        return out;
    }

    async function getOrganisationId() {
        const ctx = window.conformiiaContext;
        if (ctx && ctx.organisationId) { return ctx.organisationId; }
        const data = await (await fetch(API() + "/organisations")).json();
        const arr = Array.isArray(data) ? data : (data.items || data.data || []);
        return arr[0] && arr[0].id;
    }

    function deadline(iso) {
        const t = new Date(iso);
        if (isNaN(t)) { return { txt: "—", color: "#667085" }; }
        const left = t.getTime() + 72 * 3600e3 - Date.now();
        const a = Math.abs(left), h = Math.floor(a / 3600e3), m = Math.floor((a % 3600e3) / 60e3);
        if (left < 0) { return { txt: "Délai de 72 h dépassé de " + h + " h " + m + " min", color: "#b42318" }; }
        return { txt: "Reste " + h + " h " + m + " min sur 72 h", color: left < 24 * 3600e3 ? "#b54708" : "#067647" };
    }

    const STATUT_INCIDENT = {
        nouveau: "Nouveau", analyse: "En analyse",
        notification_preparee: "Notification préparée", notifie: "Notifié à l'APDP", cloture: "Clôturé",
    };
    const NIVEAU = {
        retard: { bg: "#fef3f2", fg: "#b42318", bd: "#fecdca", txt: "En retard" },
        urgent: { bg: "#fffaeb", fg: "#b54708", bd: "#fedf89", txt: "Échéance proche" },
        a_suivre: { bg: "#eff8ff", fg: "#175cd3", bd: "#b2ddff", txt: "À suivre" },
        notifie: { bg: "#ecfdf3", fg: "#067647", bd: "#abefc6", txt: "Notifié" },
    };

    function banner(s) {
        if (!s) { return ""; }
        const c = (n, lbl, col) => '<div style="flex:1;min-width:110px;background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:10px 13px;">'
            + '<div style="font-size:22px;font-weight:700;color:' + col + ';">' + n + "</div>"
            + '<div style="font-size:12px;color:#667085;">' + esc(lbl) + "</div></div>";
        return '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">'
            + c(s.en_retard, "En retard (72 h dépassées)", s.en_retard ? "#b42318" : "#101828")
            + c(s.urgents, "Échéance proche (< 24 h)", s.urgents ? "#b54708" : "#101828")
            + c(s.a_suivre, "À suivre", "#175cd3")
            + c(s.notifies, "Notifiés / clôturés", "#067647") + "</div>";
    }

    async function loadList(notice) {
        const box = document.getElementById("cf-incidents-list");
        if (!box) { return; }
        try {
            const [res, resAl] = await Promise.all([
                fetch(API() + "/incidents"),
                fetch(API() + "/incidents/alertes"),
            ]);
            if (!res.ok) { throw new Error("HTTP " + res.status); }
            const data = await res.json();
            const alertes = resAl.ok ? await resAl.json() : { incidents: [] };
            const alMap = {};
            (alertes.incidents || []).forEach((a) => { alMap[a.id] = a; });
            const items = (Array.isArray(data) ? data : (data.items || data.data || []))
                .sort((x, y) => String(y.date_heure_constatation).localeCompare(String(x.date_heure_constatation)));
            const head = notice ? '<div style="background:#ecfdf3;color:#067647;padding:10px 14px;border-radius:10px;margin-bottom:12px;">' + esc(notice) + "</div>" : "";
            if (!items.length) {
                box.innerHTML = head + banner(alertes) + '<p style="color:#667085;">Aucun incident déclaré pour le moment.</p>';
                return;
            }
            box.innerHTML = head + banner(alertes) + items.map((i) => {
                const d = deadline(i.date_heure_constatation);
                const types = (i.types_violation || []).map(label).join(", ") || "Incident de sécurité";
                const a = alMap[i.id];
                const niv = a ? NIVEAU[a.niveau] : null;
                const statut = i.statut || "nouveau";
                const badge = niv ? '<span style="font-size:12px;font-weight:600;color:' + niv.fg + ';background:' + niv.bg + ';border:1px solid ' + niv.bd + ';padding:3px 9px;border-radius:999px;white-space:nowrap;">' + niv.txt + "</span>" : "";
                const statutSel = '<select data-inc-statut="' + i.id + '" style="padding:5px 8px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;">'
                    + Object.entries(STATUT_INCIDENT).map(([k, v]) => '<option value="' + k + '"' + (k === statut ? " selected" : "") + ">" + esc(v) + "</option>").join("") + "</select>";
                return '<div class="cf-inc-card" data-inc="' + i.id + '" style="border:1px solid #e4e7ec;border-radius:12px;padding:14px 16px;margin-bottom:10px;background:#fff;text-align:left;">'
                    + '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;">'
                    + '<strong style="font-size:16px;line-height:1.3;flex:1;">' + esc(types) + "</strong>"
                    + badge + '<span style="font-size:13px;font-weight:600;color:' + d.color + ';">' + esc(d.txt) + "</span></div>"
                    + '<div style="color:#667085;font-size:13px;margin-top:4px;">Constaté le '
                    + esc(new Date(i.date_heure_constatation).toLocaleString("fr-FR"))
                    + (i.lieu_violation ? " · " + esc(i.lieu_violation) : "") + "</div>"
                    + (i.resume_incident ? '<p style="margin:8px 0 0;font-size:14px;line-height:1.5;color:#344054;">' + esc(i.resume_incident) + "</p>" : "")
                    + '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px;">'
                    + '<span style="font-size:13px;color:#667085;">Statut :</span>' + statutSel
                    + '<button data-inc-steps="' + i.id + '" style="border:1px solid #d0d5dd;background:#fff;border-radius:7px;padding:5px 11px;cursor:pointer;font-size:13px;">Étapes</button></div>'
                    + '<div class="cf-inc-steps" data-steps="' + i.id + '" style="display:none;margin-top:10px;border-top:1px solid #f2f4f7;padding-top:10px;"></div>'
                    + "</div>";
            }).join("");
            wireCards(box);
        } catch (e) {
            box.innerHTML = '<p style="color:#b42318;">Impossible de charger les incidents : ' + esc(e.message) + "</p>";
        }
    }

    function wireCards(box) {
        box.querySelectorAll("[data-inc-statut]").forEach((sel) => {
            sel.addEventListener("change", async (e) => {
                const id = e.target.dataset.incStatut;
                try {
                    await fetch(API() + "/incidents/" + id, {
                        method: "PATCH", headers: authHeaders(),
                        body: JSON.stringify({ statut: e.target.value }),
                    });
                    loadList();
                } catch (err) { alert("Erreur : " + err.message); }
            });
        });
        box.querySelectorAll("[data-inc-steps]").forEach((b) => {
            b.addEventListener("click", async (e) => {
                const id = e.target.dataset.incSteps;
                const pane = box.querySelector('.cf-inc-steps[data-steps="' + id + '"]');
                if (pane.style.display === "block") { pane.style.display = "none"; return; }
                pane.style.display = "block";
                pane.innerHTML = '<p style="color:#667085;font-size:13px;">Chargement…</p>';
                try {
                    const steps = await (await fetch(API() + "/incidents/" + id + "/etapes")).json();
                    pane.innerHTML = (steps.length ? steps.map((s) =>
                        '<div style="display:flex;gap:10px;font-size:13px;margin-bottom:6px;">'
                        + '<span style="color:#98a2b3;white-space:nowrap;">' + esc(new Date(s.date_etape).toLocaleString("fr-FR")) + "</span>"
                        + '<span style="color:#344054;">' + esc(s.description || s.etape) + "</span></div>").join("")
                        : '<p style="color:#667085;font-size:13px;">Aucune étape.</p>')
                        + '<div style="display:flex;gap:8px;margin-top:8px;">'
                        + '<input data-note="' + id + '" placeholder="Ajouter une note de suivi…" style="flex:1;padding:7px 10px;border:1px solid #d0d5dd;border-radius:7px;font:inherit;font-size:13px;">'
                        + '<button data-add-note="' + id + '" style="border:0;background:#2563eb;color:#fff;border-radius:7px;padding:7px 12px;cursor:pointer;font-size:13px;">Ajouter</button></div>';
                    pane.querySelector("[data-add-note]").addEventListener("click", async () => {
                        const input = pane.querySelector('input[data-note="' + id + '"]');
                        const txt = (input.value || "").trim();
                        if (!txt) { return; }
                        await fetch(API() + "/incidents/" + id + "/etapes", {
                            method: "POST", headers: authHeaders(),
                            body: JSON.stringify({ etape: "note", description: txt }),
                        });
                        b.click(); b.click();  // recharge le panneau
                    });
                } catch (err) { pane.innerHTML = '<p style="color:#b42318;font-size:13px;">Erreur : ' + esc(err.message) + "</p>"; }
            });
        });
    }

    function checks(name, list) {
        return list.map((v) => '<label style="display:inline-flex;gap:6px;align-items:center;font-size:14px;margin:3px 14px 3px 0;">'
            + '<input type="checkbox" name="' + name + '" value="' + esc(v) + '"> ' + esc(label(v)) + "</label>").join("");
    }

    const INPUT = 'style="width:100%;padding:9px 11px;border:1px solid #d0d5dd;border-radius:8px;box-sizing:border-box;font:inherit;font-size:14px;"';
    const LABEL = 'style="display:block;font-weight:600;font-size:14px;margin:12px 0 4px;"';

    async function openForm() {
        if (document.getElementById("cf-incident-modal")) { return; }
        const opt = await getOptions();
        const ov = document.createElement("div");
        ov.id = "cf-incident-modal";
        ov.style.cssText = "position:fixed;inset:0;background:rgba(16,24,40,.55);z-index:10000;display:flex;align-items:center;justify-content:center;padding:16px;";
        ov.innerHTML = '<form id="cf-incident-form" style="background:#fff;color:#172033;border-radius:14px;max-width:660px;width:100%;max-height:90vh;overflow:auto;padding:22px 24px;">'
            + '<h2 style="margin:0 0 4px;font-size:20px;">Déclarer un incident</h2>'
            + '<p style="margin:0;font-size:14px;color:#667085;">Le délai de notification de 72 h démarre à la constatation.</p>'
            + "<label " + LABEL + ">Date et heure de constatation *</label><input " + INPUT + ' type="datetime-local" name="constat" required>'
            + "<label " + LABEL + ">Date et heure de la violation (si connue)</label><input " + INPUT + ' type="datetime-local" name="violation">'
            + "<label " + LABEL + ">Lieu</label><input " + INPUT + ' name="lieu" placeholder="Ex. Siège, serveur de fichiers">'
            + "<label " + LABEL + ">Type de violation</label><div>" + checks("types", opt.viol) + "</div>"
            + "<label " + LABEL + ">Autre type (préciser)</label><input " + INPUT + ' name="autre">'
            + "<label " + LABEL + ">Résumé de l'incident</label><textarea " + INPUT + ' name="resume" rows="3"></textarea>'
            + "<label " + LABEL + ">Données personnelles concernées</label><textarea " + INPUT + ' name="donnees" rows="2"></textarea>'
            + "<label " + LABEL + ">Conséquences potentielles</label><div>" + checks("conseq", opt.cons) + "</div>"
            + "<label " + LABEL + ">Observations techniques</label><textarea " + INPUT + ' name="obs" rows="2"></textarea>'
            + "<label " + LABEL + ">Déclarant (facultatif)</label>"
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">'
            + "<input " + INPUT + ' name="nom" placeholder="Nom"><input ' + INPUT + ' name="prenoms" placeholder="Prénoms">'
            + "<input " + INPUT + ' name="tel" placeholder="Téléphone"><input ' + INPUT + ' name="email" type="email" placeholder="E-mail"></div>'
            + '<div id="cf-incident-msg" style="margin-top:12px;color:#b42318;"></div>'
            + '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:16px;">'
            + '<button type="button" id="cf-incident-cancel" style="padding:9px 16px;font-size:14px;border:1px solid #d0d5dd;border-radius:8px;background:#fff;cursor:pointer;">Annuler</button>'
            + '<button type="submit" class="btn-primary" style="padding:9px 18px;font-size:14px;border:0;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer;">Enregistrer l\'incident</button></div></form>';
        document.body.appendChild(ov);

        const close = () => ov.remove();
        ov.querySelector("#cf-incident-cancel").onclick = close;
        ov.addEventListener("mousedown", (e) => { if (e.target === ov) { close(); } });
        document.addEventListener("keydown", function esc1(e) {
            if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc1); }
        });

        const form = ov.querySelector("#cf-incident-form");
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const msg = ov.querySelector("#cf-incident-msg");
            const g = (n) => (form.elements[n].value || "").trim() || null;
            const picked = (n) => Array.from(form.querySelectorAll('input[name="' + n + '"]:checked')).map((i) => i.value);
            const dt = (v) => (v ? (v.length === 16 ? v + ":00" : v) : null);
            msg.style.color = "#667085";
            msg.textContent = "Enregistrement…";
            try {
                const organisation_id = await getOrganisationId();
                if (!organisation_id) { throw new Error("Aucune organisation : créez-la d'abord dans la page Organisation."); }
                const res = await fetch(API() + "/incidents", {
                    method: "POST",
                    headers: authHeaders(),
                    body: JSON.stringify({
                        organisation_id: organisation_id,
                        date_heure_constatation: dt(form.elements.constat.value),
                        date_heure_violation: dt(form.elements.violation.value),
                        lieu_violation: g("lieu"),
                        types_violation: picked("types"),
                        violation_autre: g("autre"),
                        resume_incident: g("resume"),
                        donnees_personnelles_concernees: g("donnees"),
                        consequences_potentielles: picked("conseq"),
                        observations_techniques: g("obs"),
                        nom_famille: g("nom"),
                        prenoms: g("prenoms"),
                        telephone_portable: g("tel"),
                        adresse_electronique: g("email"),
                        pieces: []
                    })
                });
                if (!res.ok) {
                    let d = "";
                    try {
                        const j = await res.json();
                        d = typeof j.detail === "string" ? j.detail
                            : (j.detail || []).map((x) => (x.loc || []).slice(1).join(".") + " : " + x.msg).join(" | ");
                    } catch (_) {}
                    throw new Error(d || "Erreur HTTP " + res.status);
                }
                close();
                loadList("Incident enregistré. Le délai de 72 h court depuis la constatation.");
            } catch (err) {
                msg.style.color = "#b42318";
                msg.textContent = err.message;
            }
        });
    }
    window.cfOpenIncidentForm = openForm;

    /* Clic sur « + Nouvel incident » (le bouton d'origine n'avait aucune action). */
    document.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (b && /nouvel incident/i.test(b.textContent || "")) {
            e.preventDefault();
            openForm();
        }
    }, true);

    /* Remplace le texte provisoire par la liste dès que la page Incidents s'affiche. */
    let timer = null;
    function inject() {
        if (document.getElementById("cf-incidents-list")) { return; }
        const marker = Array.from(document.querySelectorAll("h1,h2,h3,h4,strong"))
            .find((n) => /^gestion des incidents$/i.test((n.textContent || "").trim()));
        if (!marker) { return; }
        const box = marker.closest(".empty-state") || marker.parentElement;
        box.style.cssText += ";border:0;background:transparent;padding:0;text-align:left;";
        box.innerHTML = '<div id="cf-incidents-list"><p style="color:#667085;">Chargement…</p></div>';
        loadList();
    }
    new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(inject, 120); })
        .observe(document.body, { childList: true, subtree: true });
    inject();
})();

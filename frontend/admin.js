/* ConformiIA — Administration : liste des comptes (admin uniquement) */
(function () {
    "use strict";
    if (window.__cfAdminInstalled) { return; }
    window.__cfAdminInstalled = true;

    const API = () => window.API_BASE || "http://127.0.0.1:8001";
    const TOKEN_KEY = "conformiia_access_token";
    const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const token = () => { try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; } };
    const isAdmin = () => window.currentUser && window.currentUser.role === "admin";

    const ROLE_LABEL = { admin: "Administrateur", dpo: "RSSI / DPO", direction: "Direction", metier: "Responsable de traitement" };
    const ROLE_COLOR = { admin: "#6941c6", dpo: "#175cd3", direction: "#b54708", metier: "#475467" };

    // ---- visibilité du menu admin ----
    function updateNavVisibility() {
        const show = isAdmin();
        document.querySelectorAll(".cf-admin-only").forEach((el) => {
            el.style.display = show ? "" : "none";
        });
    }

    // ---- rendu de la page ----
    async function loadUsers() {
        const root = document.getElementById("cf-users-root");
        if (!root) { return; }
        if (!isAdmin()) {
            root.innerHTML = '<p style="color:#b42318;padding:20px;">Accès réservé aux administrateurs.</p>';
            return;
        }
        try {
            const res = await fetch(API() + "/auth/utilisateurs", {
                headers: { "Authorization": "Bearer " + (token() || "") },
            });
            if (!res.ok) { throw new Error("HTTP " + res.status); }
            const users = await res.json();
            render(root, Array.isArray(users) ? users : []);
        } catch (e) {
            root.innerHTML = '<p style="color:#b42318;padding:20px;">Impossible de charger les comptes : ' + esc(e.message) + "</p>";
        }
    }

    function render(root, users) {
        const nbAdmin = users.filter((u) => u.role === "admin").length;
        const nbVerif = users.filter((u) => u.email_verifie).length;
        const stat = (n, l) => '<div style="flex:1;min-width:120px;background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:12px 14px;">'
            + '<div style="font-size:24px;font-weight:700;color:#101828;">' + n + "</div>"
            + '<div style="font-size:12px;color:#667085;">' + esc(l) + "</div></div>";

        const rows = users.map((u) => {
            const rc = ROLE_COLOR[u.role] || "#475467";
            const nom = [u.nom, u.prenoms].filter(Boolean).join(" ");
            const d = u.date_creation ? new Date(u.date_creation).toLocaleDateString("fr-FR") : "—";
            return "<tr style='border-top:1px solid #f2f4f7;'>"
                + "<td style='padding:11px 10px;font-size:14px;color:#172033;'>" + esc(nom || "—") + "</td>"
                + "<td style='padding:11px 10px;font-size:14px;color:#475467;'>" + esc(u.email) + "</td>"
                + "<td style='padding:11px 10px;'><span style='font-size:12px;font-weight:600;color:" + rc + ";background:" + rc + "14;padding:3px 9px;border-radius:999px;'>" + esc(ROLE_LABEL[u.role] || u.role) + "</span></td>"
                + "<td style='padding:11px 10px;font-size:13px;color:#667085;'>" + esc(u.fonction || "—") + "</td>"
                + "<td style='padding:11px 10px;font-size:13px;'>" + (u.email_verifie
                    ? "<span style='color:#067647;'>✓ Vérifié</span>"
                    : "<span style='color:#b54708;'>En attente</span>") + "</td>"
                + "<td style='padding:11px 10px;font-size:13px;color:#667085;'>" + esc(d) + "</td></tr>";
        }).join("");

        root.innerHTML = '<div style="text-align:left;">'
            + '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px;">'
            + stat(users.length, "Comptes au total") + stat(nbAdmin, "Administrateurs") + stat(nbVerif, "Comptes vérifiés") + "</div>"
            + '<div style="background:#fff;border:1px solid #e4e7ec;border-radius:14px;overflow:hidden;">'
            + "<table style='width:100%;border-collapse:collapse;'>"
            + "<thead><tr style='background:#f9fafb;text-align:left;'>"
            + ["Nom", "E-mail", "Rôle", "Fonction", "Statut", "Créé le"].map((h) =>
                "<th style='padding:10px;font-size:12px;color:#667085;font-weight:600;text-transform:uppercase;letter-spacing:.03em;'>" + h + "</th>").join("")
            + "</tr></thead><tbody>" + (rows || "<tr><td colspan='6' style='padding:20px;color:#667085;'>Aucun compte.</td></tr>") + "</tbody></table></div></div>";
    }

    // ---- journal d'audit ----
    const ACTION = {
        creation: { l: "Création", c: "#067647" }, modification: { l: "Modification", c: "#175cd3" },
        suppression: { l: "Suppression", c: "#b42318" }, validation: { l: "Validation", c: "#6941c6" },
        calcul: { l: "Calcul", c: "#b54708" },
    };
    const ENTITE = { traitement: "Traitement", score: "Score", ecart: "Écart", action: "Action", incident: "Incident" };

    async function loadAudit() {
        const root = document.getElementById("cf-audit-root");
        if (!root) { return; }
        if (!isAdmin()) { root.innerHTML = '<p style="color:#b42318;padding:20px;">Accès réservé aux administrateurs.</p>'; return; }
        try {
            const res = await fetch(API() + "/auth/audit?limite=300", { headers: { "Authorization": "Bearer " + (token() || "") } });
            if (!res.ok) { throw new Error("HTTP " + res.status); }
            const rows = await res.json();
            renderAudit(root, Array.isArray(rows) ? rows : []);
        } catch (e) {
            root.innerHTML = '<p style="color:#b42318;padding:20px;">Impossible de charger le journal : ' + esc(e.message) + "</p>";
        }
    }

    function renderAudit(root, rows) {
        const body = rows.map((r) => {
            const a = ACTION[r.action] || { l: r.action, c: "#475467" };
            const d = r.date_action ? new Date(r.date_action).toLocaleString("fr-FR") : "—";
            return "<tr style='border-top:1px solid #f2f4f7;'>"
                + "<td style='padding:10px;font-size:13px;color:#667085;white-space:nowrap;'>" + esc(d) + "</td>"
                + "<td style='padding:10px;font-size:13px;color:#172033;'>" + esc(r.utilisateur_email || "anonyme") + "</td>"
                + "<td style='padding:10px;'><span style='font-size:12px;font-weight:600;color:" + a.c + ";background:" + a.c + "14;padding:3px 9px;border-radius:999px;'>" + esc(a.l) + "</span></td>"
                + "<td style='padding:10px;font-size:13px;color:#475467;'>" + esc(ENTITE[r.entite] || r.entite) + "</td>"
                + "<td style='padding:10px;font-size:13px;color:#344054;'>" + esc(r.description || "") + "</td></tr>";
        }).join("");
        root.innerHTML = '<div style="text-align:left;">'
            + '<p style="color:#667085;font-size:13px;margin:0 0 14px;">Les ' + rows.length + " dernières actions sur les traitements, écarts, actions correctives et incidents.</p>"
            + '<div style="background:#fff;border:1px solid #e4e7ec;border-radius:14px;overflow:hidden;"><table style="width:100%;border-collapse:collapse;">'
            + "<thead><tr style='background:#f9fafb;text-align:left;'>"
            + ["Date", "Utilisateur", "Action", "Objet", "Description"].map((h) =>
                "<th style='padding:10px;font-size:12px;color:#667085;font-weight:600;text-transform:uppercase;letter-spacing:.03em;'>" + h + "</th>").join("")
            + "</tr></thead><tbody>" + (body || "<tr><td colspan='5' style='padding:20px;color:#667085;'>Aucune action enregistrée.</td></tr>") + "</tbody></table></div></div>";
    }

    // ---- déclencheurs ----
    let lastUsers = null, lastAudit = null;
    function tick() {
        updateNavVisibility();
        const ru = document.getElementById("cf-users-root");
        if (ru && ru !== lastUsers) { lastUsers = ru; loadUsers(); }
        if (!ru) { lastUsers = null; }
        const ra = document.getElementById("cf-audit-root");
        if (ra && ra !== lastAudit) { lastAudit = ra; loadAudit(); }
        if (!ra) { lastAudit = null; }
    }
    new MutationObserver(tick).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    setInterval(updateNavVisibility, 1000);
    tick();
})();

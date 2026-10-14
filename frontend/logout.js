/* ============================================================
   CONFORMIIA — DÉCONNEXION UNIQUE (page Sécurité)
   Un seul bouton : #cf-dedicated-logout
   Une seule fonction : cfLogout()
   ============================================================ */
(function () {
    "use strict";

    if (window.__cfLogoutUnique) {
        return;
    }
    window.__cfLogoutUnique = true;

    /* Laisser vide si le frontend et l'API ont la même origine. */
    const API_BASE = window.CONFORMIIA_API_BASE || "http://127.0.0.1:8001";

    const SESSION_KEYS = [
        "conformiia_access_token",
        "conformiia_token",
        "conformiia_session",
        "conformiia_session_started_at",
        "conformiia_auth",
        "conformiia_authenticated_user",
        "conformiia_current_user",
        "conformiia_user",
        "conformiia_user_profile",
        "access_token",
        "auth_token",
        "token",
        "currentUser",
        "currentUserProfile"
    ];

    const TOKEN_KEYS = [
        "conformiia_access_token",
        "conformiia_token",
        "access_token"
    ];

    let running = false;

    function getToken() {
        for (const store of [localStorage, sessionStorage]) {
            for (const key of TOKEN_KEYS) {
                const value = store.getItem(key);
                if (value) {
                    return value;
                }
            }
        }
        return "";
    }

    function clearSession() {
        SESSION_KEYS.forEach(function (key) {
            localStorage.removeItem(key);
            sessionStorage.removeItem(key);
        });
        sessionStorage.clear();

        window.currentUser = null;
        window.currentUserProfile = null;
        window.conformiiaUser = null;
        window.userProfile = null;
    }

    function showLogin() {

        function afficher() {
            if (typeof window.conformiiaShowLogin === "function") {
                window.conformiiaShowLogin();
            } else {
                console.error("[ConformiIA] conformiiaShowLogin indisponible.");
            }
        }

        afficher();

        /* Si un autre code referme la connexion, on la réaffiche. */
        [50, 200, 600].forEach(function (delai) {
            setTimeout(function () {
                if (!document.body.classList.contains("cf-auth-locked")) {
                    afficher();
                }
            }, delai);
        });
    }

    async function cfLogout() {
        if (running) {
            return;
        }
        running = true;

        try {
            const token = getToken();

            if (token) {
                const controller = new AbortController();
                const timer = setTimeout(function () {
                    controller.abort();
                }, 4000);

                try {
                    await fetch(API_BASE + "/auth/logout", {
                        method: "POST",
                        headers: { "Authorization": "Bearer " + token },
                        signal: controller.signal
                    });
                } catch (error) {
                    console.warn("[ConformiIA] Logout serveur :", error);
                } finally {
                    clearTimeout(timer);
                }
            }
        } finally {
            /* Même si l'API échoue, la session locale est supprimée. */
            clearSession();
            showLogin();
            running = false;
        }
    }

    window.conformiiaLogout = cfLogout;
    window.conformiiaLogoutDefinitif = cfLogout;

    /* Seul clic géré : le bouton de la page Sécurité. */
    document.addEventListener("click", function (event) {
        const button = event.target.closest("#cf-dedicated-logout");
        if (!button) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        button.disabled = true;
        cfLogout().finally(function () {
            button.disabled = false;
        });
    }, true);

    /* Retirer d'éventuels anciens boutons recréés par du vieux code. */
    function purgeLegacyButtons() {
        document
            .querySelectorAll("#user-logout-button, #cf-settings-logout")
            .forEach(function (el) { el.remove(); });
    }

    new MutationObserver(purgeLegacyButtons)
        .observe(document.body, { childList: true, subtree: true });

    purgeLegacyButtons();
})();

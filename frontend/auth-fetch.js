/* ConformiIA - injecte le jeton d'authentification sur TOUS les appels API.
   Chargé en premier : les modules suivants (qui appellent fetch) sont ainsi
   authentifiés automatiquement, sans modifier chaque appel. */
(function () {
    "use strict";
    if (window.__cfAuthFetch) { return; }
    window.__cfAuthFetch = true;

    const TOKEN_KEY = "conformiia_access_token";
    const _fetch = window.fetch.bind(window);

    function token() {
        try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; }
    }
    function isApiUrl(url) {
        const base = window.API_BASE || "http://127.0.0.1:8001";
        return url.indexOf(base) === 0 || url.indexOf("api.conformiia") !== -1 ||
            url.indexOf("http://127.0.0.1:8001") === 0;
    }

    /* Anti mixed-content : sur page HTTPS, réécrit les appels http://127.0.0.1:8001
       vers l'API HTTPS ; sur page HTTP, l'inverse. */
    function normalizeUrl(url) {
        try {
            const httpsApi = "https://api.conformiia";
            const legacyHttpsApi = "https://api.conformiia.test";
            const httpApi = "http://127.0.0.1:8001";
            if (location.protocol === "https:") {
                if (url.indexOf(httpApi) === 0) { return httpsApi + url.slice(httpApi.length); }
                if (url.indexOf(legacyHttpsApi) === 0) { return httpsApi + url.slice(legacyHttpsApi.length); }
            }
            if (location.protocol !== "https:" && url.indexOf(httpsApi) === 0) {
                return httpApi + url.slice(httpsApi.length);
            }
        } catch (_) { /* ignore */ }
        return url;
    }

    window.fetch = function (input, init) {
        try {
            if (typeof input === "string") {
                const fixed = normalizeUrl(input);
                if (fixed !== input) { input = fixed; }
            }
            const url = typeof input === "string" ? input : ((input && input.url) || "");
            const tok = token();
            if (tok && isApiUrl(url)) {
                const opts = init ? Object.assign({}, init) : {};
                const headers = new Headers(
                    (init && init.headers) ||
                    (typeof input !== "string" && input && input.headers) ||
                    {}
                );
                if (!headers.has("Authorization")) {
                    headers.set("Authorization", "Bearer " + tok);
                }
                opts.headers = headers;
                return _fetch(input, opts);
            }
        } catch (_) { /* en cas de souci, on laisse passer l'appel d'origine */ }
        return _fetch(input, init);
    };
})();

/* ConformiIA - émoticônes noir & blanc sur toute la plateforme.
   Enveloppe chaque emoji dans un span.cf-emoji-bw (filtre grayscale),
   y compris le contenu rendu dynamiquement via navigate(). */
(function () {
    "use strict";
    if (window.__cfEmojiBW) { return; }
    window.__cfEmojiBW = true;

    var EMOJI_RE = /([\u{1F000}-\u{1FAFF}\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+)/u;

    function wrapEmojis(root) {
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
        var nodes = [];
        while (walker.nextNode()) { nodes.push(walker.currentNode); }
        nodes.forEach(function (node) {
            var text = node.nodeValue;
            if (!text || !EMOJI_RE.test(text)) { return; }
            if (node.parentNode && node.parentNode.classList &&
                node.parentNode.classList.contains("cf-emoji-bw")) { return; }
            var frag = document.createDocumentFragment();
            var last = 0;
            var re = new RegExp(EMOJI_RE.source, "gu");
            var m;
            while ((m = re.exec(text)) !== null) {
                if (m.index > last) {
                    frag.appendChild(document.createTextNode(text.slice(last, m.index)));
                }
                var s = document.createElement("span");
                s.className = "cf-emoji-bw";
                s.textContent = m[0];
                frag.appendChild(s);
                last = m.index + m[0].length;
            }
            if (last < text.length) {
                frag.appendChild(document.createTextNode(text.slice(last)));
            }
            node.parentNode.replaceChild(frag, node);
        });
    }

    function scan() {
        try {
            if (document.body) { wrapEmojis(document.body); }
        } catch (_) { /* ignore */ }
    }

    document.addEventListener("DOMContentLoaded", scan);
    window.addEventListener("load", scan);
    // navigate() réécrit .main-content : observer les mutations
    if (window.MutationObserver) {
        var t = null;
        var obs = new MutationObserver(function () {
            if (t) { clearTimeout(t); }
            t = setTimeout(scan, 60);
        });
        document.addEventListener("DOMContentLoaded", function () {
            try { obs.observe(document.body, { childList: true, subtree: true }); }
            catch (_) { /* ignore */ }
        });
    }
})();

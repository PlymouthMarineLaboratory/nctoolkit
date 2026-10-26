(function () {
  "use strict";

  /* ---------- header scroll + mobile nav ---------- */
  var header = document.querySelector(".site-header");
  var navToggle = document.querySelector(".nav-toggle");
  var navLinks = document.querySelector(".nav-links");

  function onScroll() {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      var open = navLinks.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) {
        document.querySelectorAll(".nav-dropdown.is-open").forEach(function (d) {
          d.classList.remove("is-open");
        });
      }
    });
    navLinks.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        navLinks.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  /* ---------- nav dropdowns (click-to-open, closes on outside click) ---------- */
  var dropdowns = document.querySelectorAll(".nav-dropdown");
  dropdowns.forEach(function (dd) {
    var toggle = dd.querySelector(".nav-dropdown-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      var willOpen = !dd.classList.contains("is-open");
      dropdowns.forEach(function (d) { d.classList.remove("is-open"); });
      if (willOpen) dd.classList.add("is-open");
      toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
    });
  });
  document.addEventListener("click", function () {
    dropdowns.forEach(function (d) {
      d.classList.remove("is-open");
      var t = d.querySelector(".nav-dropdown-toggle");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  });

  /* ---------- mark active nav link (plain links + dropdown menus) ---------- */
  var here = (location.pathname.split("/").pop() || "index.html");
  document.querySelectorAll(".nav-links a[data-page]").forEach(function (a) {
    if (a.getAttribute("data-page") === here) {
      a.classList.add("active");
      var parentDropdown = a.closest(".nav-dropdown");
      if (parentDropdown) {
        var toggle = parentDropdown.querySelector(".nav-dropdown-toggle");
        if (toggle) toggle.classList.add("active");
      }
    }
  });

  /* ---------- copy-to-clipboard for code cards ---------- */
  document.querySelectorAll("[data-copy-target]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.querySelector(btn.getAttribute("data-copy-target"));
      if (!target) return;
      var text = target.innerText;
      navigator.clipboard.writeText(text).then(function () {
        var label = btn.querySelector(".copy-label");
        var original = label ? label.textContent : null;
        if (label) label.textContent = "Copied!";
        setTimeout(function () {
          if (label && original !== null) label.textContent = original;
        }, 1600);
      });
    });
  });

  /* ---------- FAQ accordion ---------- */
  document.querySelectorAll(".faq-item").forEach(function (item) {
    var q = item.querySelector(".faq-question");
    if (!q) return;
    q.addEventListener("click", function () {
      var isOpen = item.classList.contains("is-open");
      item.classList.toggle("is-open", !isOpen);
      var answer = item.querySelector(".faq-answer");
      if (answer) {
        answer.style.maxHeight = !isOpen ? answer.scrollHeight + 40 + "px" : "";
      }
    });
  });

  /* ---------- reference/recipe tables: search + filter + expand ---------- */
  var recipeSearch = document.querySelector("#recipe-search");
  var recipeRows = document.querySelectorAll("tr.recipe-row");
  var filterPills = document.querySelectorAll(".filter-pill");
  var activeRegion = "all";

  function applyRecipeFilters() {
    var term = (recipeSearch && recipeSearch.value || "").trim().toLowerCase();
    recipeRows.forEach(function (row) {
      var text = row.textContent.toLowerCase();
      var region = row.getAttribute("data-region");
      var matchesTerm = !term || text.indexOf(term) !== -1;
      var matchesRegion = activeRegion === "all" || region === activeRegion;
      var show = matchesTerm && matchesRegion;
      row.classList.toggle("hidden-row", !show);
      var detail = row.nextElementSibling;
      if (detail && detail.classList.contains("recipe-detail")) {
        detail.classList.toggle("hidden-row", !show && true);
        if (!show) detail.classList.remove("is-open");
      }
    });
  }

  if (recipeSearch) recipeSearch.addEventListener("input", applyRecipeFilters);
  filterPills.forEach(function (pill) {
    pill.addEventListener("click", function () {
      filterPills.forEach(function (p) { p.classList.remove("active"); });
      pill.classList.add("active");
      activeRegion = pill.getAttribute("data-region");
      applyRecipeFilters();
    });
  });

  recipeRows.forEach(function (row) {
    row.addEventListener("click", function () {
      var detail = row.nextElementSibling;
      if (!detail || !detail.classList.contains("recipe-detail")) return;
      var willOpen = !detail.classList.contains("is-open");
      document.querySelectorAll(".recipe-detail.is-open").forEach(function (d) {
        d.classList.remove("is-open");
      });
      if (willOpen) detail.classList.add("is-open");
    });
  });

  /* ---------- docs scrollspy ---------- */
  var tocLinks = document.querySelectorAll(".docs-toc a");
  if (tocLinks.length) {
    var targets = [];
    tocLinks.forEach(function (link) {
      var id = link.getAttribute("href").replace("#", "");
      var el = document.getElementById(id);
      if (el) targets.push({ link: link, el: el });
    });

    function updateToc() {
      var pos = window.scrollY + 120;
      var current = null;
      targets.forEach(function (t) {
        if (t.el.offsetTop <= pos) current = t;
      });
      tocLinks.forEach(function (l) { l.classList.remove("active"); });
      if (current) current.link.classList.add("active");
    }
    updateToc();
    window.addEventListener("scroll", updateToc, { passive: true });
  }

  /* ---------- docs version (latest PyPI release) ---------- */
  var versionEls = document.querySelectorAll("#nctoolkit-docs-version");
  if (versionEls.length) {
    fetch("https://pypi.org/pypi/nctoolkit/json")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var version = data && data.info && data.info.version;
        if (!version) return;
        versionEls.forEach(function (el) {
          el.textContent = "v" + version;
          el.title = "nctoolkit v" + version + " (latest PyPI release)";
        });
      })
      .catch(function () {
        /* PyPI unreachable (offline, blocked, rate-limited): leave the
           static fallback text in the HTML in place rather than showing
           an error or a stale version number. */
      });
  }

  /* ---------- version history empty-state ---------- */
  var versionHistoryList = document.querySelector(".version-history-list");
  var versionHistoryEmpty = document.querySelector("#version-history-empty");
  if (versionHistoryList && versionHistoryEmpty) {
    versionHistoryEmpty.hidden = versionHistoryList.children.length > 0;
  }

  /* ---------- site search (Pagefind) ----------
     The index is built in CI (see .github/workflows/pages.yml) and is not
     committed, so the button only appears once pagefind/ is actually being
     served. Archived snapshots under /archive/ have no index of their own. */
  var navActions = document.querySelector(".nav-actions");
  var mainScript = document.querySelector('script[src$="assets/js/main.js"]');
  if (navActions && mainScript && location.pathname.indexOf("/archive/") === -1) {
    var pagefindBase = new URL("../../pagefind/", mainScript.src).href;
    var searchDialog = null;
    var searchReady = false;

    var searchBtn = document.createElement("button");
    searchBtn.type = "button";
    searchBtn.className = "icon-btn search-btn";
    searchBtn.hidden = true;
    searchBtn.setAttribute("aria-label", "Search the docs");
    searchBtn.title = "Search (press /)";
    searchBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
    navActions.insertBefore(searchBtn, navActions.firstChild);

    var loadPagefindUI = function () {
      return new Promise(function (resolve, reject) {
        var css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = pagefindBase + "pagefind-ui.css";
        document.head.appendChild(css);
        var js = document.createElement("script");
        js.src = pagefindBase + "pagefind-ui.js";
        js.onload = resolve;
        js.onerror = reject;
        document.head.appendChild(js);
      });
    };

    var buildDialog = function () {
      if (!searchDialog) {
        searchDialog = document.createElement("dialog");
        searchDialog.className = "search-dialog";
        searchDialog.innerHTML = '<div id="search-ui"></div>';
        document.body.appendChild(searchDialog);
        searchDialog.addEventListener("click", function (e) {
          if (e.target === searchDialog) searchDialog.close();
        });
        new PagefindUI({
          element: "#search-ui",
          showImages: false,
          showSubResults: true,
          resetStyles: false,
          pageSize: 8
        });
      }
    };

    var openSearch = function () {
      var ready = window.PagefindUI ? Promise.resolve() : loadPagefindUI();
      ready.then(function () {
        buildDialog();
        searchDialog.showModal();
        var input = searchDialog.querySelector("input");
        if (input) input.focus();
      });
    };

    searchBtn.addEventListener("click", function () {
      if (searchReady) openSearch();
    });

    document.addEventListener("keydown", function (e) {
      var tag = (e.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;
      var wantsSearch = (e.key === "/" && !typing) ||
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k");
      if (wantsSearch && searchReady) {
        e.preventDefault();
        openSearch();
      }
    });

    fetch(pagefindBase + "pagefind-entry.json", { method: "HEAD" })
      .then(function (res) {
        if (!res.ok) throw new Error("no search index");
        searchReady = true;
        searchBtn.hidden = false;
      })
      .catch(function () { /* no index (e.g. local preview): leave search off */ });
  }

  /* ---------- back to top ---------- */
  var backToTop = document.querySelector(".back-to-top");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      backToTop.classList.toggle("is-visible", window.scrollY > 600);
    }, { passive: true });
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
})();

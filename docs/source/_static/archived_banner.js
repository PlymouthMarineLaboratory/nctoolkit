// This documentation site is archived - NCToolkit's docs have moved to
// https://plymouthmarinelaboratory.github.io/nctoolkit/. Inserted via html_js_files
// (see conf.py) rather than a theme template override, so it shows on
// every page regardless of whether it was built from a .rst file or a
// notebook (nbsphinx pages don't go through the same reST pipeline that
// rst_prolog hooks into).
(function () {
  function insertBanner() {
    var banner = document.createElement("div");
    banner.setAttribute(
      "style",
      "margin: 0 0 24px; padding: 14px 18px; border: 1px solid #f5c26b;" +
        "border-left: 4px solid #e8a33d; border-radius: 4px;" +
        "background: #fdf6e8; color: #5c4a1e; font-size: 0.95em;" +
        "font-family: inherit;"
    );
    banner.innerHTML =
      "This site is archived and no longer updated &mdash; NCToolkit's docs have moved. " +
      'See <a href="https://plymouthmarinelaboratory.github.io/nctoolkit/" style="font-weight: 600;">' +
      "plymouthmarinelaboratory.github.io/nctoolkit</a> for the current quickstart, user guide and API reference.";

    var target =
      document.querySelector("[itemprop='articleBody']") ||
      document.querySelector(".document") ||
      document.querySelector(".body") ||
      document.body;
    target.insertBefore(banner, target.firstChild);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", insertBanner);
  } else {
    insertBanner();
  }
})();

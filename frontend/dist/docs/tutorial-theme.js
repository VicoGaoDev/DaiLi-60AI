(function () {
  var STORAGE_KEY = "banana-web-theme";
  var THEMES = { warm: true, jade: true, iris: true, cyan: true, mauve: true, alum: true, mist: true, dark: true, midnight: true };

  function applyTheme(theme) {
    var name = THEMES[theme] ? theme : "warm";
    document.documentElement.setAttribute("data-theme", name);
    document.documentElement.style.colorScheme = name === "midnight" ? "dark" : "light";
  }

  function readTheme() {
    try {
      if (window.parent !== window) {
        var fromParent = window.parent.document.documentElement.getAttribute("data-theme");
        if (THEMES[fromParent]) return fromParent;
      }
    } catch (error) {
      /* ignore cross-origin */
    }
    try {
      return localStorage.getItem(STORAGE_KEY) || "warm";
    } catch (error) {
      return "warm";
    }
  }

  applyTheme(readTheme());

  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    if (event.data && event.data.type === "banana-tutorial-theme") {
      applyTheme(event.data.theme);
    }
  });

  try {
    if (window.parent !== window) {
      new MutationObserver(function () {
        applyTheme(readTheme());
      }).observe(window.parent.document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    }
  } catch (error) {
    /* standalone open */
  }
})();

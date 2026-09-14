(function () {
  const origin = window.location.origin;

  function postToParent(payload) {
    if (window.parent === window) return;
    window.parent.postMessage(payload, origin);
  }

  let pinnedSectionId = "";
  let pinTimer = 0;

  function pinSection(id) {
    pinnedSectionId = id;
    window.clearTimeout(pinTimer);
    pinTimer = window.setTimeout(() => {
      pinnedSectionId = "";
    }, 1000);
  }

  function postActiveSection(id) {
    if (!id) return;
    if (pinnedSectionId && id !== pinnedSectionId) return;
    postToParent({ type: "banana-tutorial-section", id });
  }

  function postHash(id) {
    if (!id) return;
    postToParent({ type: "banana-tutorial-hash", id });
  }

  function headingTargetId(heading) {
    if (heading.id) return heading.id;
    return heading.closest("section[id]")?.id || "";
  }

  function isNumberedHeading(heading) {
    return /^\s*\d+\./.test(heading.textContent || "");
  }

  function enhanceHeadings() {
    document.querySelectorAll(".doc h2").forEach((heading) => {
      if (!isNumberedHeading(heading)) return;
      const id = headingTargetId(heading);
      if (!id || heading.querySelector(".heading-anchor")) return;
      const link = document.createElement("a");
      link.className = "heading-anchor";
      link.href = `#${id}`;
      link.setAttribute("aria-label", `定位到「${(heading.textContent || "").trim()}」`);
      link.textContent = "#";
      heading.append(link);
    });
  }

  function hydrateSectionImages(section) {
    if (!section) return;
    section.querySelectorAll("img[loading='lazy']").forEach((img) => {
      img.loading = "eager";
    });
    const next = section.nextElementSibling;
    if (next && next.matches("section[id]")) {
      next.querySelectorAll("img[loading='lazy']").forEach((img) => {
        img.loading = "eager";
      });
    }
  }

  function scrollToId(id, behavior) {
    if (!id) return false;
    const target = document.getElementById(id);
    if (!target) return false;
    hydrateSectionImages(target);
    pinSection(target.id);
    target.scrollIntoView({ behavior: behavior || "smooth", block: "start" });
    postActiveSection(target.id);
    return true;
  }

  function currentHashId() {
    return decodeURIComponent(window.location.hash.replace(/^#/, ""));
  }

  enhanceHeadings();

  window.addEventListener("message", (event) => {
    if (event.origin !== origin) return;
    if (event.data?.type === "banana-tutorial-scroll") {
      scrollToId(event.data.id);
      return;
    }
    if (event.data?.type === "banana-tutorial-scroll-top") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      const firstSection = document.querySelector("section[id]");
      if (firstSection?.id) {
        pinSection(firstSection.id);
        postActiveSection(firstSection.id);
      }
    }
  });

  window.addEventListener("hashchange", () => {
    scrollToId(currentHashId());
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".heading-anchor");
    if (!link) return;
    const id = decodeURIComponent((link.getAttribute("href") || "").replace(/^#/, ""));
    if (!id) return;
    event.preventDefault();
    scrollToId(id);
    if (window.parent === window) {
      history.replaceState(null, "", `#${id}`);
    } else {
      postHash(id);
    }
  });

  const anchors = Array.from(document.querySelectorAll("section[id]"));
  if (anchors.length) {
    function sectionAtSpyLine() {
      const line = window.innerHeight * 0.22;
      let current = anchors[0];
      for (const el of anchors) {
        if (el.getBoundingClientRect().top - line <= 2) current = el;
        else break;
      }
      return current?.id || "";
    }

    function syncActiveSection() {
      postActiveSection(sectionAtSpyLine());
    }

    window.addEventListener("scroll", syncActiveSection, { passive: true });
    const initialId = currentHashId();
    if (!scrollToId(initialId, "auto")) {
      postActiveSection(anchors[0].id);
    }
  }

  function createLightbox() {
    const overlay = document.createElement("div");
    overlay.className = "shot-lightbox";
    overlay.innerHTML =
      '<button type="button" class="shot-lightbox-close" aria-label="关闭预览"></button>' +
      '<figure class="shot-lightbox-figure">' +
      '<img class="shot-lightbox-image" alt="" />' +
      '<figcaption class="shot-lightbox-caption"></figcaption>' +
      "</figure>";
    document.body.append(overlay);
    return overlay;
  }

  const lightbox = createLightbox();
  const lightboxImage = lightbox.querySelector(".shot-lightbox-image");
  const lightboxCaption = lightbox.querySelector(".shot-lightbox-caption");

  function closeLightbox() {
    lightbox.classList.remove("is-open");
    lightboxImage.removeAttribute("src");
    lightboxImage.alt = "";
    lightboxCaption.textContent = "";
    document.body.classList.remove("shot-lightbox-open");
  }

  function openLightbox(img) {
    const src = img.currentSrc || img.src || "";
    if (!src || !img.naturalWidth) return;
    const caption = img.closest("figure")?.querySelector("figcaption")?.textContent || img.alt || "";
    const alt = img.alt || caption;
    if (window.parent !== window) {
      postToParent({ type: "banana-tutorial-preview", src, alt, caption });
      return;
    }
    lightboxImage.src = src;
    lightboxImage.alt = alt;
    lightboxCaption.textContent = caption;
    lightboxCaption.hidden = !caption;
    lightbox.classList.add("is-open");
    document.body.classList.add("shot-lightbox-open");
  }

  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox || event.target.closest(".shot-lightbox-close")) {
      closeLightbox();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && lightbox.classList.contains("is-open")) closeLightbox();
  });

  document.querySelectorAll("figure img").forEach((img) => {
    const figure = img.closest("figure");
    if (!figure) return;

    img.addEventListener("error", () => {
      figure.hidden = true;
    });

    figure.classList.add("is-zoomable");
    figure.setAttribute("role", "button");
    figure.setAttribute("tabindex", "0");
    figure.setAttribute("aria-label", (img.alt || "教程截图") + "，点击放大预览");
    figure.addEventListener("click", (event) => {
      if (event.target.closest(".heading-anchor")) return;
      openLightbox(img);
    });
    figure.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openLightbox(img);
      }
    });
  });

  function postScrollState() {
    const top = window.scrollY || document.documentElement.scrollTop;
    postToParent({ type: "banana-tutorial-scroll-state", visible: top > 240 });
  }

  window.addEventListener("scroll", postScrollState, { passive: true });
  postScrollState();
})();

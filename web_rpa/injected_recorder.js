(function installWebRpaRecorder() {
  if (window.__webRpaRecorderInstalled) return;
  window.__webRpaRecorderInstalled = true;

  const INTERACTIVE_SELECTOR = [
    "button",
    "a[href]",
    "input",
    "textarea",
    "select",
    "option",
    "[contenteditable='true']",
    "[role='button']",
    "[role='link']",
    "[role='textbox']",
    "[role='combobox']",
    "[role='option']",
    "[tabindex]"
  ].join(",");

  function closestInteractive(node) {
    let current = node && node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    for (let depth = 0; current && depth < 8; depth += 1) {
      if (current.matches && current.matches(INTERACTIVE_SELECTOR)) return current;
      current = current.parentElement;
    }
    return node && node.nodeType === Node.ELEMENT_NODE ? node : null;
  }

  function textOf(element) {
    return (element.innerText || element.textContent || "").replace(/\s+/g, " ").trim();
  }

  function cssPath(element) {
    if (!element || !element.tagName) return "";
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      const tag = current.tagName.toLowerCase();
      if (current.id) {
        parts.unshift(`${tag}#${CSS.escape(current.id)}`);
        break;
      }
      let selector = tag;
      if (current.name) selector += `[name="${cssEscapeAttr(current.name)}"]`;
      else if (current.type) selector += `[type="${cssEscapeAttr(current.type)}"]`;
      else {
        const parent = current.parentElement;
        if (parent) {
          const siblings = Array.from(parent.children).filter((item) => item.tagName === current.tagName);
          if (siblings.length > 1) selector += `:nth-child(${Array.from(parent.children).indexOf(current) + 1})`;
        }
      }
      parts.unshift(selector);
      current = current.parentElement;
    }
    return parts.join(" > ");
  }

  function cssEscapeAttr(value) {
    return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function labelsFor(element) {
    const labels = [];
    if (element.labels) {
      for (const label of element.labels) labels.push(textOf(label));
    }
    if (element.id) {
      const explicit = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
      if (explicit) labels.push(textOf(explicit));
    }
    return Array.from(new Set(labels.filter(Boolean)));
  }

  function descriptor(element) {
    const rect = element.getBoundingClientRect();
    return {
      tag: element.tagName ? element.tagName.toLowerCase() : "",
      text: textOf(element),
      id: element.id || null,
      name: element.getAttribute("name"),
      type: element.getAttribute("type"),
      role: element.getAttribute("role"),
      ariaLabel: element.getAttribute("aria-label"),
      ariaLabelledby: element.getAttribute("aria-labelledby"),
      placeholder: element.getAttribute("placeholder"),
      title: element.getAttribute("title"),
      alt: element.getAttribute("alt"),
      href: element.getAttribute("href"),
      testId: element.getAttribute("data-testid"),
      dataTest: element.getAttribute("data-test"),
      dataQa: element.getAttribute("data-qa"),
      dataCy: element.getAttribute("data-cy"),
      labels: labelsFor(element),
      cssPath: cssPath(element),
      bbox: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
    };
  }

  function emit(type, element, extra = {}) {
    if (!element || typeof window.__rpa_record !== "function") return;
    window.__rpa_record({
      type,
      ts: Date.now() / 1000,
      url: location.href,
      descriptor: descriptor(element),
      ...extra
    });
  }

  document.addEventListener("click", (event) => {
    const target = closestInteractive(event.target);
    if (target) emit("click", target);
  }, true);

  document.addEventListener("input", (event) => {
    const target = closestInteractive(event.target);
    if (!target) return;
    emit("fill", target, { value: target.value || target.textContent || "" });
  }, true);

  document.addEventListener("change", (event) => {
    const target = closestInteractive(event.target);
    if (!target) return;
    const type = target.tagName && target.tagName.toLowerCase() === "select" ? "select" : "change";
    emit(type, target, { value: target.value || "" });
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const target = closestInteractive(event.target);
    if (target) emit("press", target, { key: "Enter" });
  }, true);

  document.addEventListener("submit", (event) => {
    const target = closestInteractive(event.submitter || event.target);
    if (target) emit("click", target);
  }, true);
})();

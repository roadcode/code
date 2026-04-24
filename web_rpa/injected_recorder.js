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
    const data = {
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
    data.selectorCounts = selectorCounts(element, data);
    return data;
  }

  function selectorCounts(element, data) {
    const counts = {};
    const add = (key, count) => {
      if (key && Number.isFinite(count)) counts[key] = count;
    };
    const role = data.role || impliedRole(data);
    const name = accessibleName(data);
    if (data.testId) add(`test_id:${data.testId}`, countCss(`[data-testid="${cssEscapeAttr(data.testId)}"]`));
    if (data.dataTest) add(`test_id:${data.dataTest}`, countCss(`[data-test="${cssEscapeAttr(data.dataTest)}"]`));
    if (data.dataQa) add(`test_id:${data.dataQa}`, countCss(`[data-qa="${cssEscapeAttr(data.dataQa)}"]`));
    if (data.dataCy) add(`test_id:${data.dataCy}`, countCss(`[data-cy="${cssEscapeAttr(data.dataCy)}"]`));
    if (role && name) add(`role:${role}:${name}`, countByRoleAndName(role, name));
    for (const label of data.labels || []) add(`label:${label}`, countByLabel(label));
    for (const [field, kind] of [["placeholder", "placeholder"], ["title", "title"], ["alt", "alt"]]) {
      if (data[field]) add(`${kind}:${data[field]}`, countCss(`[${kind}="${cssEscapeAttr(data[field])}"]`));
    }
    if (data.text && data.text.length <= 80) add(`text:${data.text}`, countByText(data.text));
    for (const css of stableCssCandidates(data)) add(`css:${css}`, countCss(css));
    if (data.cssPath) add(`css:${data.cssPath}`, countCss(data.cssPath));
    return counts;
  }

  function countCss(selector) {
    try {
      return document.querySelectorAll(selector).length;
    } catch (_error) {
      return Number.NaN;
    }
  }

  function countByText(text) {
    return Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR)).filter((item) => textOf(item) === text).length;
  }

  function countByRoleAndName(role, name) {
    return Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR)).filter((item) => {
      const itemData = {
        tag: item.tagName ? item.tagName.toLowerCase() : "",
        text: textOf(item),
        type: item.getAttribute("type"),
        role: item.getAttribute("role"),
        ariaLabel: item.getAttribute("aria-label"),
        title: item.getAttribute("title"),
        alt: item.getAttribute("alt"),
        labels: labelsFor(item),
        value: item.value
      };
      return (itemData.role || impliedRole(itemData)) === role && accessibleName(itemData) === name;
    }).length;
  }

  function countByLabel(label) {
    return Array.from(document.querySelectorAll("input, textarea, select")).filter((item) => labelsFor(item).includes(label)).length;
  }

  function accessibleName(data) {
    return normalizeSpace(data.ariaLabel || (data.labels || []).join(" ") || data.title || data.alt || data.text || data.value || "");
  }

  function normalizeSpace(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function impliedRole(data) {
    const tag = (data.tag || "").toLowerCase();
    const type = (data.type || "").toLowerCase();
    if (tag === "button" || ["button", "submit", "reset"].includes(type)) return "button";
    if (tag === "a" && data.href) return "link";
    if (["input", "textarea"].includes(tag) && !["checkbox", "radio"].includes(type)) return "textbox";
    if (tag === "select") return "combobox";
    if (tag === "option") return "option";
    return null;
  }

  function stableCssCandidates(data) {
    const tag = data.tag || "*";
    const attrs = [];
    for (const [field, attr] of [
      ["id", "id"],
      ["name", "name"],
      ["type", "type"],
      ["href", "href"],
      ["ariaLabel", "aria-label"],
      ["ariaLabelledby", "aria-labelledby"],
      ["testId", "data-testid"],
      ["dataTest", "data-test"],
      ["dataQa", "data-qa"],
      ["dataCy", "data-cy"]
    ]) {
      if (data[field]) attrs.push(`${tag}[${attr}="${cssEscapeAttr(data[field])}"]`);
    }
    return attrs;
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

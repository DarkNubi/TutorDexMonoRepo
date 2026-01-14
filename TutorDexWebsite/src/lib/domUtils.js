/**
 * DOM utilities for assignments page.
 * 
 * Handles DOM element access and manipulation.
 */

// Element cache to avoid repeated DOM queries
const _elCache = new Map();

/**
 * Get element by ID with caching.
 * @param {string} id - Element ID
 * @returns {HTMLElement|null} Element or null
 */
export function $id(id) {
  if (_elCache.has(id)) return _elCache.get(id);
  const el = document.getElementById(id);
  if (el) _elCache.set(id, el);
  return el;
}

/**
 * Clear element cache.
 * Call this if elements are dynamically added/removed.
 */
export function clearElementCache() {
  _elCache.clear();
}

/**
 * Set element visibility.
 * @param {HTMLElement} el - Element
 * @param {boolean} visible - Whether to show element
 */
export function setVisible(el, visible) {
  if (!el) return;
  el.style.display = visible ? "" : "none";
}

/**
 * Set element text content safely.
 * @param {HTMLElement} el - Element
 * @param {string} text - Text to set
 */
export function setText(el, text) {
  if (!el) return;
  el.textContent = String(text || "");
}

/**
 * Add CSS class to element.
 * @param {HTMLElement} el - Element
 * @param {string} className - Class name
 */
export function addClass(el, className) {
  if (!el || !className) return;
  el.classList.add(className);
}

/**
 * Remove CSS class from element.
 * @param {HTMLElement} el - Element
 * @param {string} className - Class name
 */
export function removeClass(el, className) {
  if (!el || !className) return;
  el.classList.remove(className);
}

/**
 * Toggle CSS class on element.
 * @param {HTMLElement} el - Element
 * @param {string} className - Class name
 * @param {boolean} force - Force add/remove
 */
export function toggleClass(el, className, force) {
  if (!el || !className) return;
  el.classList.toggle(className, force);
}

/**
 * Clear all children from element.
 * @param {HTMLElement} el - Element
 */
export function clearChildren(el) {
  if (!el) return;
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

/**
 * Create element with attributes.
 * @param {string} tag - Tag name
 * @param {Object} attrs - Attributes object
 * @param {string|HTMLElement} content - Content (text or element)
 * @returns {HTMLElement} Created element
 */
export function createElement(tag, attrs = {}, content = null) {
  const el = document.createElement(tag);
  
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "className" || key === "class") {
      el.className = value;
    } else if (key === "dataset") {
      for (const [dataKey, dataValue] of Object.entries(value)) {
        el.dataset[dataKey] = dataValue;
      }
    } else {
      el.setAttribute(key, value);
    }
  }
  
  if (content) {
    if (typeof content === "string") {
      el.textContent = content;
    } else if (content instanceof HTMLElement) {
      el.appendChild(content);
    }
  }
  
  return el;
}

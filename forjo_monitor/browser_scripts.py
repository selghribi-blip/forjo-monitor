"""JavaScript probes injected into the audited page.

The probes only *read* the document: they measure timing, enumerate ad
resources and read the geometry of elements already on the page. No click, no
form fill, no synthetic interaction of any kind.
"""

from __future__ import annotations

INIT_METRICS_PROBE = """
window.__forjo = { lcp: 0, cls: 0 };
try {
  new PerformanceObserver(function (list) {
    list.getEntries().forEach(function (entry) { window.__forjo.lcp = entry.startTime; });
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (error) { /* probe unsupported */ }
try {
  new PerformanceObserver(function (list) {
    list.getEntries().forEach(function (entry) {
      if (!entry.hadRecentInput) { window.__forjo.cls += entry.value; }
    });
  }).observe({ type: 'layout-shift', buffered: true });
} catch (error) { /* probe unsupported */ }
"""

NAVIGATION_TIMING_PROBE = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const resources = performance.getEntriesByType('resource') || [];
  const probe = window.__forjo || { lcp: 0, cls: 0 };
  let transferBytes = 0;
  for (const entry of resources) { transferBytes += (entry.transferSize || 0); }
  if (nav) { transferBytes += (nav.transferSize || 0); }
  return {
    ttfb: nav ? nav.responseStart : null,
    domContentLoaded: nav ? nav.domContentLoadedEventEnd : null,
    load: nav ? nav.loadEventEnd : null,
    lcp: probe.lcp,
    cls: probe.cls,
    requestCount: resources.length,
    transferBytes: transferBytes
  };
}
"""

AD_ELEMENT_PROBE = """
(domains) => {
  const matchDomain = (value) => {
    if (!value) { return null; }
    let host;
    try { host = new URL(value, location.href).hostname.toLowerCase(); }
    catch (error) { return null; }
    for (const domain of domains) {
      if (host === domain || host.endsWith('.' + domain)) { return domain; }
    }
    return null;
  };

  const viewportWidth = window.innerWidth || 1;
  const viewportHeight = window.innerHeight || 1;
  const rows = [];
  const seen = new Set();

  const selector = 'iframe[src], img[src], script[src], link[href]';
  for (const element of document.querySelectorAll(selector)) {
    const url = element.getAttribute('src') || element.getAttribute('href') || '';
    const network = matchDomain(url);
    if (!network) { continue; }
    const key = network + '|' + url;
    if (seen.has(key)) { continue; }
    seen.add(key);
    const rect = element.getBoundingClientRect();
    rows.push({
      network: network,
      url: url,
      tag: element.tagName.toLowerCase(),
      width: rect.width,
      height: rect.height,
      top: rect.top,
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight
    });
  }
  return rows;
}
"""

AD_RESOURCE_PROBE = """
(domains) => {
  const entries = performance.getEntriesByType('resource') || [];
  const rows = [];
  for (const entry of entries) {
    let host;
    try { host = new URL(entry.name).hostname.toLowerCase(); }
    catch (error) { continue; }
    for (const domain of domains) {
      if (host === domain || host.endsWith('.' + domain)) {
        rows.push({ network: domain, url: entry.name, kind: entry.initiatorType || 'other' });
        break;
      }
    }
  }
  return rows;
}
"""

/*
 * P0 #250 F2.4 — browser HTTP probe (read-only).
 *
 * Paste in Chrome DevTools while authenticated, then change the month/class once
 * to force a reload. The probe observes GET XHRs only; it never issues requests,
 * changes request data, or records ids/content/PII.
 *
 * Export: copy(JSON.stringify(window.__P0_250_F24__.events, null, 2))
 * Remove: window.__P0_250_F24__.restore()
 */
(() => {
  if (window.__P0_250_F24__?.restore) window.__P0_250_F24__.restore();

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  const events = [];

  const routeType = (url) => {
    const value = String(url || '');
    if (value.includes('/professor/diarios')) return 'PROFESSOR_DIARIES';
    if (value.includes('/content-entries')) return 'CONTENT_ENTRIES';
    if (value.includes('/learning-objects')) return 'LEARNING_OBJECTS';
    return null;
  };

  const safeParams = (url) => {
    try {
      const parsed = new URL(url, window.location.origin);
      return {
        has_class_id: parsed.searchParams.has('class_id'),
        has_course_id: parsed.searchParams.has('course_id') || parsed.searchParams.has('component_id'),
        has_assignment_id: parsed.searchParams.has('assignment_id'),
        academic_year: parsed.searchParams.get('academic_year') || null,
        month: parsed.searchParams.get('month') || null,
      };
    } catch {
      return {};
    }
  };

  const summarizePayload = (route, payload) => {
    const rows = Array.isArray(payload)
      ? payload
      : (Array.isArray(payload?.items) ? payload.items : []);
    const dates = [...new Set(rows.map((row) => String(row?.date || '').slice(0, 10)).filter(Boolean))]
      .sort()
      .reverse();
    const componentCount = new Set(
      rows.map((row) => row?.component_id || row?.course_id).filter(Boolean)
    ).size;
    const result = {
      response_count: rows.length,
      unique_date_count: dates.length,
      dates,
      component_count: componentCount,
    };
    if (route === 'PROFESSOR_DIARIES') {
      result.blocked_total = Number(payload?.blocked_total || 0);
      result.content_enabled_count = rows.filter((row) => row?.capabilities?.content_enabled === true).length;
    }
    return result;
  };

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__p0f24 = {
      method: String(method || '').toUpperCase(),
      url: String(url || ''),
      route: routeType(url),
      started_at: new Date().toISOString(),
    };
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const meta = this.__p0f24;
    if (meta?.route && meta.method === 'GET') {
      this.addEventListener('loadend', () => {
        let payload = null;
        try { payload = JSON.parse(this.responseText || 'null'); } catch { /* non-JSON */ }
        const event = {
          seq: events.length + 1,
          route: meta.route,
          method: 'GET',
          status: this.status,
          started_at: meta.started_at,
          finished_at: new Date().toISOString(),
          params: safeParams(meta.url),
          ...summarizePayload(meta.route, payload),
        };
        events.push(event);
        console.info('[P0-250-F2.4]', JSON.stringify(event));
      }, { once: true });
    }
    return originalSend.call(this, body);
  };

  window.__P0_250_F24__ = {
    events,
    restore() {
      XMLHttpRequest.prototype.open = originalOpen;
      XMLHttpRequest.prototype.send = originalSend;
      console.info('[P0-250-F2.4] probe removed');
    },
  };
  console.info('[P0-250-F2.4] probe active; change month/class once to trigger GETs');
})();

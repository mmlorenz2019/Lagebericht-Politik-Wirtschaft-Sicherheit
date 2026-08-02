'use strict';

(function exposeFreshnessModel(root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.FreshnessModel = model;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createFreshnessModel() {
  function berlinDateKey(now) {
    const parts = new Intl.DateTimeFormat('de-DE', {
      timeZone: 'Europe/Berlin',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(now);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function displayDate(value) {
    const [year, month, day] = String(value || '').split('-');
    return year && month && day ? `${day}.${month}.${year}` : 'unbekannt';
  }

  function dailyNotice(index, now) {
    const today = berlinDateKey(now);
    const latest = index && typeof index.latestDaily === 'string' ? index.latestDaily : '';
    if (latest >= today) return '';
    if (!latest) return `Der heutige Bericht vom ${displayDate(today)} ist noch nicht verfügbar.`;
    return `Der heutige Bericht vom ${displayDate(today)} ist noch nicht verfügbar. Angezeigt wird der Stand vom ${displayDate(latest)}.`;
  }

  return { berlinDateKey, dailyNotice };
}));

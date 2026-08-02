'use strict';

(function exposePeriodModel(root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.PeriodModel = model;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createPeriodModel() {
  function dayNumber(value) {
    const [year, month, day] = String(value || '').split('-').map(Number);
    return Date.UTC(year, month - 1, day) / 86400000;
  }

  function coverage(report) {
    const total = dayNumber(report.periodEnd) - dayNumber(report.periodStart) + 1;
    const available = new Set(report.sourceReportDates || []).size;
    const snapshot = available === 1;
    const partial = available < total;
    const suffix = snapshot ? 'Momentaufnahme' : partial ? 'Teilüberblick' : 'Vollständig';
    return {
      available,
      total,
      partial,
      snapshot,
      label: `Datenbasis: ${available} von ${total} Tagen · ${suffix}`,
    };
  }

  return { coverage };
}));

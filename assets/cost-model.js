'use strict';

(function exposeCostModel(root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.CostModel = model;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createCostModel() {
  const TICK_LABELS = Object.freeze(['0 €', '1,25 €', '2,50 €', '3,75 €', '5 €']);
  const MONTH_PATTERN = /^[0-9]{4}-(0[1-9]|1[0-2])$/;
  const COST_PATH_PATTERN = /^data\/costs\/[0-9]{4}-(0[1-9]|1[0-2])\.json$/;
  const percentFormat = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const euroFormat = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function unavailable() {
    return {
      available: false,
      monthLabel: '',
      percentLabel: '',
      widthPercent: null,
      tone: 'unavailable',
      accessibleLabel: 'Kosten derzeit nicht verfügbar',
      estimateNote: 'Kosten derzeit nicht verfügbar',
      tickLabels: TICK_LABELS.slice(),
    };
  }

  function berlinMonth(moment) {
    if (!(moment instanceof Date) || !Number.isFinite(moment.getTime())) return null;
    const parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      timeZone: 'Europe/Berlin',
    }).formatToParts(moment);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return values.year && values.month ? `${values.year}-${values.month}` : null;
  }

  function monthLabel(month) {
    const date = new Date(`${month}-15T12:00:00Z`);
    return new Intl.DateTimeFormat('de-DE', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(date);
  }

  function validNonnegativeNumber(value) {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0;
  }

  function roundedBudgetPercent(estimatedCostEur) {
    const scaled = estimatedCostEur * 200;
    const lower = Math.floor(scaled);
    const fraction = scaled - lower;
    const tolerance = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 8;
    const rounded = Math.abs(fraction - 0.5) <= tolerance
      ? (lower % 2 === 0 ? lower : lower + 1)
      : Math.floor(scaled + 0.5);
    return rounded / 10;
  }

  function validReport(report, moment) {
    return report !== null
      && typeof report === 'object'
      && !Array.isArray(report)
      && report.schemaVersion === 1
      && typeof report.month === 'string'
      && MONTH_PATTERN.test(report.month)
      && report.month === berlinMonth(moment)
      && report.budgetEur === 5
      && validNonnegativeNumber(report.estimatedCostEur)
      && validNonnegativeNumber(report.budgetPercent)
      && Math.abs(report.budgetPercent - roundedBudgetPercent(report.estimatedCostEur)) <= 1e-9
      && Number.isInteger(report.unmeasuredCalls)
      && report.unmeasuredCalls >= 0
      && typeof report.collectionStartedAt === 'string'
      && Number.isFinite(Date.parse(report.collectionStartedAt));
  }

  function collectionDateLabel(value) {
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      timeZone: 'Europe/Berlin',
    }).format(new Date(value));
  }

  function presentation(report, now) {
    const moment = now instanceof Date ? now : new Date(now);
    if (!validReport(report, moment)) return unavailable();

    const percent = report.budgetPercent;
    const tone = percent >= 100 ? 'over' : percent >= 75 ? 'warning' : 'normal';
    const label = monthLabel(report.month);
    const percentLabel = `${percentFormat.format(percent)} %`;
    const costLabel = `${euroFormat.format(report.estimatedCostEur)} €`;
    const budgetLabel = `${euroFormat.format(report.budgetEur)} €`;
    const minimum = report.unmeasuredCalls > 0
      ? `Die Schätzung umfasst mindestens die messbaren Aufrufe; ${report.unmeasuredCalls} ${report.unmeasuredCalls === 1 ? 'Aufruf war' : 'Aufrufe waren'} nicht messbar.`
      : `Erfassung seit ${collectionDateLabel(report.collectionStartedAt)}. Tokenbasierte Schätzung, keine Rechnung.`;

    return {
      available: true,
      monthLabel: label,
      percentLabel,
      widthPercent: Math.min(percent, 100),
      tone,
      accessibleLabel: `Geschätzte API-Kosten im ${label}: ${costLabel} von ${budgetLabel}, ${percentLabel} des Monatsbudgets.`,
      estimateNote: minimum,
      tickLabels: TICK_LABELS.slice(),
    };
  }

  function isAllowedCostPath(path) {
    return typeof path === 'string' && COST_PATH_PATTERN.test(path);
  }

  return Object.freeze({ presentation, isAllowedCostPath });
}));

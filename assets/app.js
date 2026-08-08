'use strict';

const ALLOWED_HOSTS = new Set([
  'npr.org', 'www.npr.org', 'nytimes.com', 'www.nytimes.com', 'cnbc.com', 'www.cnbc.com',
  'pbs.org', 'www.pbs.org', 'caixinglobal.com', 'www.caixinglobal.com', 'scmp.com', 'www.scmp.com',
  'chinadaily.com.cn', 'www.chinadaily.com.cn', 'vijesti.me', 'www.vijesti.me', 'pobjeda.me', 'www.pobjeda.me',
  'politico.eu', 'www.politico.eu', 'politico.com', 'www.politico.com', 'euobserver.com', 'www.euobserver.com',
  'ec.europa.eu'
]);
const CATEGORY_LABELS = {
  politics_society: 'Politik & Gesellschaft',
  economy_technology: 'Wirtschaft & Technologie',
  foreign_security: 'Außenpolitik & Sicherheit'
};
const COUNTRY_LABELS = { usa: 'USA', china: 'China', montenegro: 'Montenegro', eu: 'EU' };
const state = {
  index: null, archiveType: 'daily', country: 'usa', report: null,
  costs: null, freshnessNotice: '', reportNotice: ''
};

const elements = {
  updated: document.getElementById('updated'), notice: document.getElementById('notice'),
  select: document.getElementById('period-select'), overall: document.getElementById('overall'),
  overallCopy: document.getElementById('overall-copy'), report: document.getElementById('report'),
  kicker: document.getElementById('report-kicker'), countryTitle: document.getElementById('country-title'),
  completeness: document.getElementById('completeness'), stories: document.getElementById('stories'),
  costMeter: document.getElementById('cost-meter'), costMonth: document.getElementById('cost-month'),
  costPercent: document.getElementById('cost-percent'), costTrack: document.getElementById('cost-track'),
  costFill: document.getElementById('cost-fill'), costTicks: document.getElementById('cost-ticks'),
  costNote: document.getElementById('cost-note'), themeToggle: document.getElementById('theme-toggle')
};

const THEME_STORAGE_KEY = 'lagebericht-theme';
const THEME_ORDER = ['system', 'light', 'dark'];
const THEME_LABELS = { system: 'Farbschema: System', light: 'Farbschema: Hell', dark: 'Farbschema: Dunkel' };

function readStoredTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_STORAGE_KEY); } catch (_) { stored = null; }
  return THEME_ORDER.includes(stored) ? stored : 'system';
}

function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.setAttribute('data-theme', theme);
  else document.documentElement.removeAttribute('data-theme');
  elements.themeToggle.textContent = THEME_LABELS[theme];
}

function cycleTheme() {
  const next = THEME_ORDER[(THEME_ORDER.indexOf(readStoredTheme()) + 1) % THEME_ORDER.length];
  try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch (_) { /* storage unavailable, theme just won't persist */ }
  applyTheme(next);
}

applyTheme(readStoredTheme());
elements.themeToggle.addEventListener('click', cycleTheme);

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined && text !== null) value.textContent = text;
  if (className) value.className = className;
  return value;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

function leafIcon(filled, color) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('class', 'leaf');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', 'M8 1 C13 3 14 9 8 15 C2 9 3 3 8 1 Z');
  path.setAttribute('fill', filled ? color : 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', '1.3');
  svg.append(path);
  return svg;
}

function leafRow(score, color) {
  const wrap = node('span', null, 'leaf-row');
  wrap.setAttribute('role', 'img');
  wrap.setAttribute('aria-label', `${score} von 3`);
  for (let i = 0; i < 3; i += 1) wrap.append(leafIcon(i < score, color));
  return wrap;
}

function renderNotice() {
  const message = [state.freshnessNotice, state.reportNotice].filter(Boolean).join(' ');
  elements.notice.textContent = message;
  elements.notice.hidden = !message;
}

function showNotice(message) {
  state.reportNotice = message;
  renderNotice();
}

function renderCosts(report) {
  const value = CostModel.presentation(report, new Date());
  elements.costMeter.hidden = false;
  elements.costNote.textContent = value.estimateNote;
  if (!value.available) {
    elements.costMonth.textContent = '';
    elements.costPercent.textContent = '';
    elements.costTrack.hidden = true;
    elements.costTicks.hidden = true;
    elements.costTrack.removeAttribute('aria-valuenow');
    elements.costTrack.setAttribute('aria-label', value.accessibleLabel);
    elements.costFill.className = 'cost-fill';
    elements.costFill.style.width = '0%';
    return;
  }

  elements.costMonth.textContent = value.monthLabel;
  elements.costPercent.textContent = value.percentLabel;
  elements.costTrack.hidden = false;
  elements.costTicks.hidden = false;
  elements.costTrack.setAttribute('aria-valuenow', String(value.widthPercent));
  elements.costTrack.setAttribute('aria-label', value.accessibleLabel);
  elements.costFill.className = `cost-fill cost-${value.tone}`;
  elements.costFill.style.width = `${value.widthPercent}%`;
  elements.costTicks.replaceChildren(...value.tickLabels.map((label) => node('span', label)));
}

async function loadCurrentCosts() {
  const reference = state.index && state.index.currentCosts;
  const path = reference && reference.path;
  if (!CostModel.isAllowedCostPath(path)) {
    state.costs = null;
    renderCosts(null);
    return;
  }
  try {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.costs = await response.json();
    renderCosts(state.costs);
  } catch (_) {
    state.costs = null;
    renderCosts(null);
  }
}

function safeSourceLink(source) {
  try {
    const url = new URL(source.url);
    if (url.protocol !== 'https:' || !ALLOWED_HOSTS.has(url.hostname.toLowerCase())) return null;
    const link = node('a', source.name);
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.referrerPolicy = 'no-referrer';
    return link;
  } catch (_) {
    return null;
  }
}

function archiveEntries() {
  return state.index ? state.index[state.archiveType] || [] : [];
}

function entryLabel(entry) {
  if (state.archiveType === 'daily') return new Intl.DateTimeFormat('de-DE', { dateStyle: 'full', timeZone: 'UTC' }).format(new Date(`${entry.date}T12:00:00Z`));
  return state.archiveType === 'weekly' ? `Kalenderwoche ${entry.period.slice(-2)} · ${entry.period.slice(0, 4)}` : new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${entry.period}-15T12:00:00Z`));
}

function fillPeriodSelect() {
  elements.select.replaceChildren();
  archiveEntries().forEach((entry) => {
    const option = node('option', entryLabel(entry));
    option.value = entry.path;
    elements.select.append(option);
  });
}

function renderSources(item, article) {
  if (!item.sources || !item.sources.length) return;
  const details = node('details', null, 'sources');
  details.append(node('summary', `${item.sources.length} Originalquelle${item.sources.length === 1 ? '' : 'n'} anzeigen`));
  const list = node('ul');
  item.sources.forEach((source) => {
    const row = node('li');
    const link = safeSourceLink(source);
    row.append(link || node('span', `${source.name} · Link nicht freigegeben`));
    row.append(node('span', `${source.type} · ${source.titleOriginal}`, 'source-type'));
    list.append(row);
  });
  details.append(list);
  article.append(details);
}

function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', 'Bedeutungsbewertung');
  ratings.forEach((rating) => {
    const details = node('details', null, `rating rating-${rating.key}`);
    const summary = document.createElement('summary');
    if (rating.legacy) {
      summary.append(node('span', rating.label, 'rating-label'), node('span', 'alter Datenstand', 'rating-legacy-note'));
    } else {
      summary.append(leafRow(rating.score, 'currentColor'), node('span', rating.label, 'rating-label'));
    }
    details.append(summary);
    details.append(node('p', rating.reasonDe, 'rating-reason'));
    group.append(details);
  });
  article.append(group);
}

function renderStory(item, index) {
  const article = node('article', null, 'story');
  const label = CATEGORY_LABELS[item.id] || item.id;
  const chip = node('div', null, 'story-num');
  chip.append(leafIcon(true, 'currentColor'), document.createTextNode(` No. ${String(index + 1).padStart(3, '0')} — ${label}`));
  article.append(chip);
  const top = node('div', null, 'story-top');
  top.append(node('span', RatingModel.badgeForItem(item), 'badge'));
  article.append(top);
  if (item.status === 'no_major_development') {
    article.append(node('h3', 'Keine neue Meldung in den geprüften Quellen'));
    article.append(node('p', 'Für diesen Bereich wurde im Berichtsfenster keine technisch geeignete neue Meldung gefunden.', 'empty'));
    return article;
  }
  if (item.status === 'unavailable') {
    article.append(node('h3', 'Heute technisch nicht vollständig prüfbar'));
    article.append(node('p', 'Mindestens eine benötigte Quelle oder Verarbeitung war nicht verfügbar.', 'empty'));
    return article;
  }
  article.append(node('h3', item.headlineDe));
  const summary = node('div', null, 'summary');
  (item.summaryDe || []).forEach((sentence) => summary.append(node('p', sentence)));
  article.append(summary);
  const contextSentences = item.contextDe || [];
  if (contextSentences.length) {
    const context = node('section', null, 'context');
    context.append(node('h4', 'Einordnung'));
    contextSentences.forEach((sentence) => context.append(node('p', sentence)));
    article.append(context);
  }
  renderRatings(item, article);
  if (item.additionalImportant) article.append(node('p', `Außerdem wichtig: ${item.additionalImportant}`, 'additional'));
  renderSources(item, article);
  return article;
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  const isDaily = Object.hasOwn(report, 'reportDate');
  const countries = report.countries || [];
  const country = countries.find((item) => item.id === state.country) || countries[0];
  if (!country) throw new Error('Bericht enthält keine Länderansicht.');
  state.country = country.id;
  document.querySelectorAll('[data-country]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.country === state.country)));
  elements.countryTitle.textContent = country.label || COUNTRY_LABELS[country.id];
  elements.kicker.textContent = isDaily ? 'Tagesbericht' : report.periodType === 'week' ? 'Wochenbericht' : 'Monatsbericht';
  if (isDaily) {
    elements.completeness.className = 'muted';
    elements.completeness.textContent = report.status === 'complete' ? 'Vollständig' : 'Teilbericht · Einschränkungen sichtbar';
  } else {
    const coverage = PeriodModel.coverage(report);
    elements.completeness.className = 'muted period-coverage';
    elements.completeness.textContent = coverage.label;
  }
  elements.updated.textContent = isDaily ? `Bericht vom ${report.reportDate} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}` : `${report.periodStart} bis ${report.periodEnd} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}`;
  elements.stories.replaceChildren(...(country.categories || country.sections || []).map((item, index) => renderStory(item, index)));
  elements.overall.hidden = isDaily;
  elements.overallCopy.replaceChildren();
  if (!isDaily) (report.overallSummary || []).forEach((sentence) => elements.overallCopy.append(node('p', sentence)));
  const missing = report.missingReportDates || [];
  showNotice(missing.length ? `Für diesen Rückblick fehlen ${missing.length} Tagesberichte: ${missing.join(', ')}.` : '');
  elements.report.setAttribute('aria-busy', 'false');
}

async function loadSelectedReport() {
  const path = elements.select.value;
  if (!path) {
    showNotice('Für diese Archivart ist noch kein Bericht vorhanden.');
    return;
  }
  elements.report.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(path, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.report = await response.json();
    renderReport();
  } catch (error) {
    elements.report.setAttribute('aria-busy', 'false');
    showNotice(`Bericht konnte nicht geladen werden. Ein zuvor gelesener Bericht ist offline möglicherweise weiterhin verfügbar. (${error.message})`);
  }
}

async function start() {
  await refreshIndex({ preferLatest: true });
}

async function refreshIndex({ preferLatest = false } = {}) {
  const previousPath = elements.select.value;
  const previousLatest = state.index && state.index.latestDaily;
  try {
    const response = await fetch('data/index.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.index = await response.json();
    void loadCurrentCosts();
    state.freshnessNotice = FreshnessModel.dailyNotice(state.index, new Date());
    renderNotice();
    fillPeriodSelect();
    const entries = archiveEntries();
    if (!entries.length) {
      showNotice('Für diese Archivart ist noch kein Bericht vorhanden.');
      return;
    }
    const hasPreviousPath = entries.some((entry) => entry.path === previousPath);
    const hasNewDaily = state.archiveType === 'daily' && state.index.latestDaily !== previousLatest;
    if (!preferLatest && !hasNewDaily && hasPreviousPath) elements.select.value = previousPath;
    await loadSelectedReport();
  } catch (error) {
    renderCosts(null);
    showNotice(`Das Archiv konnte nicht geladen werden. (${error.message})`);
    elements.report.setAttribute('aria-busy', 'false');
  }
}

document.querySelectorAll('[data-archive-type]').forEach((button) => button.addEventListener('click', async () => {
  state.archiveType = button.dataset.archiveType;
  document.querySelectorAll('[data-archive-type]').forEach((peer) => peer.setAttribute('aria-pressed', String(peer === button)));
  fillPeriodSelect();
  await loadSelectedReport();
}));
document.querySelectorAll('[data-country]').forEach((button) => button.addEventListener('click', () => {
  state.country = button.dataset.country;
  renderReport();
}));
elements.select.addEventListener('change', loadSelectedReport);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refreshIndex({ preferLatest: state.archiveType === 'daily' });
});

if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('service-worker.js?v=12', { updateViaCache: 'none' }));
start();

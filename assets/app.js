'use strict';

const ALLOWED_HOSTS = new Set([
  'npr.org', 'www.npr.org', 'nytimes.com', 'www.nytimes.com', 'cnbc.com', 'www.cnbc.com',
  'pbs.org', 'www.pbs.org', 'caixinglobal.com', 'www.caixinglobal.com', 'scmp.com', 'www.scmp.com',
  'chinadaily.com.cn', 'www.chinadaily.com.cn', 'vijesti.me', 'www.vijesti.me', 'pobjeda.me', 'www.pobjeda.me',
  'politico.eu', 'www.politico.eu', 'politico.com', 'www.politico.com', 'euobserver.com', 'www.euobserver.com',
  'ec.europa.eu'
]);
const COUNTRY_LABELS = { usa: 'USA', china: 'China', montenegro: 'Montenegro', eu: 'EU' };
const STRINGS = {
  de: {
    skipLink: 'Zum Bericht springen',
    archive: { daily: 'Tage', weekly: 'Wochen', monthly: 'Monate' },
    periodLabel: 'Zeitraum', periodSelectAriaLabel: 'Zeitraum auswählen',
    countryNavAriaLabel: 'Land oder Region auswählen',
    overallEyebrow: 'Gesamtlage', overallTitle: 'Der Zeitraum im Überblick',
    kicker: { daily: 'Tagesbericht', week: 'Wochenbericht', month: 'Monatsbericht' },
    completeness: { complete: 'Vollständig', partial: 'Teilbericht · Einschränkungen sichtbar' },
    noMajorDevelopment: {
      title: 'Keine neue Meldung in den geprüften Quellen',
      body: 'Für diesen Bereich wurde im Berichtsfenster keine technisch geeignete neue Meldung gefunden.'
    },
    unavailable: {
      title: 'Heute technisch nicht vollständig prüfbar',
      body: 'Mindestens eine benötigte Quelle oder Verarbeitung war nicht verfügbar.'
    },
    additionalImportantPrefix: 'Außerdem wichtig: ',
    contextHeading: 'Einordnung',
    sourcesSummary: (count) => `${count} Originalquelle${count === 1 ? '' : 'n'} anzeigen`,
    sourceLinkBlocked: (name) => `${name} · Link nicht freigegeben`,
    footerNote: 'Keine Anmeldung, kein Tracking und keine Werbung. Originalquellen öffnen sich online in einem neuen Tab.',
    costEyebrow: 'Transparenz', costHeading: 'Geschätzte API-Kosten',
    noArchiveNotice: 'Für diese Archivart ist noch kein Bericht vorhanden.',
    reportLoadError: (message) => `Bericht konnte nicht geladen werden. Ein zuvor gelesener Bericht ist offline möglicherweise weiterhin verfügbar. (${message})`,
    archiveLoadError: (message) => `Das Archiv konnte nicht geladen werden. (${message})`,
    missingReportsNotice: (count, list) => `Für diesen Rückblick fehlen ${count} Tagesberichte: ${list}.`,
    categoryLabels: {
      politics_society: 'Politik & Gesellschaft',
      economy_technology: 'Wirtschaft & Technologie',
      foreign_security: 'Außenpolitik & Sicherheit'
    },
    ratingsAriaLabel: 'Bedeutungsbewertung',
    legacyNote: 'alter Datenstand',
    languageToggleLabel: 'Sprache: Deutsch'
  },
  en: {
    skipLink: 'Skip to report',
    archive: { daily: 'Days', weekly: 'Weeks', monthly: 'Months' },
    periodLabel: 'Period', periodSelectAriaLabel: 'Select period',
    countryNavAriaLabel: 'Select country or region',
    overallEyebrow: 'Overview', overallTitle: 'The period at a glance',
    kicker: { daily: 'Daily report', week: 'Weekly report', month: 'Monthly report' },
    completeness: { complete: 'Complete', partial: 'Partial report · limitations shown' },
    noMajorDevelopment: {
      title: 'No new story in the reviewed sources',
      body: 'No technically suitable new story was found for this section in the reporting window.'
    },
    unavailable: {
      title: 'Not fully checkable today',
      body: 'At least one required source or processing step was unavailable.'
    },
    additionalImportantPrefix: 'Also notable: ',
    contextHeading: 'Context',
    sourcesSummary: (count) => `Show ${count} original source${count === 1 ? '' : 's'}`,
    sourceLinkBlocked: (name) => `${name} · link not approved`,
    footerNote: 'No login, no tracking and no ads. Original sources open online in a new tab.',
    costEyebrow: 'Transparency', costHeading: 'Estimated API costs',
    noArchiveNotice: 'No report is available yet for this archive type.',
    reportLoadError: (message) => `The report could not be loaded. A previously read report may still be available offline. (${message})`,
    archiveLoadError: (message) => `The archive could not be loaded. (${message})`,
    missingReportsNotice: (count, list) => `This review is missing ${count} daily reports: ${list}.`,
    categoryLabels: {
      politics_society: 'Politics & Society',
      economy_technology: 'Economy & Technology',
      foreign_security: 'Foreign Affairs & Security'
    },
    ratingsAriaLabel: 'Significance rating',
    legacyNote: 'legacy data',
    languageToggleLabel: 'Language: English'
  }
};
const state = {
  index: null, archiveType: 'daily', country: 'usa', report: null,
  costs: null, freshnessNotice: '', reportNotice: '', language: 'de'
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
  costNote: document.getElementById('cost-note'), themeToggle: document.getElementById('theme-toggle'),
  languageToggle: document.getElementById('language-toggle'), skipLink: document.getElementById('skip-link'),
  periodLabel: document.getElementById('period-label'), overallEyebrow: document.getElementById('overall-eyebrow'),
  costEyebrow: document.getElementById('cost-eyebrow'), footerNote: document.getElementById('footer-note'),
  countryNav: document.querySelector('.country-nav'), overallTitle: document.getElementById('overall-title'),
  costTitle: document.getElementById('cost-title')
};

const LANGUAGE_STORAGE_KEY = 'lagebericht-language';

function readStoredLanguage() {
  let stored = null;
  try { stored = localStorage.getItem(LANGUAGE_STORAGE_KEY); } catch (_) { stored = null; }
  return stored === 'en' ? 'en' : 'de';
}

function strings() {
  return STRINGS[state.language];
}

function dataRoot() {
  return state.language === 'en' ? 'data/en' : 'data';
}

function applyLanguage(language) {
  state.language = language;
  const s = strings();
  document.documentElement.lang = language;
  elements.skipLink.textContent = s.skipLink;
  elements.languageToggle.textContent = s.languageToggleLabel;
  document.querySelectorAll('[data-archive-type]').forEach((button) => {
    button.textContent = s.archive[button.dataset.archiveType];
  });
  elements.periodLabel.textContent = s.periodLabel;
  elements.select.setAttribute('aria-label', s.periodSelectAriaLabel);
  elements.countryNav.setAttribute('aria-label', s.countryNavAriaLabel);
  elements.overallEyebrow.textContent = s.overallEyebrow;
  elements.overallTitle.textContent = s.overallTitle;
  elements.costEyebrow.textContent = s.costEyebrow;
  elements.costTitle.textContent = s.costHeading;
  elements.footerNote.textContent = s.footerNote;
}

function cycleLanguage() {
  const next = state.language === 'de' ? 'en' : 'de';
  try { localStorage.setItem(LANGUAGE_STORAGE_KEY, next); } catch (_) { /* storage unavailable, language just won't persist */ }
  applyLanguage(next);
  refreshIndex({ preferLatest: state.archiveType === 'daily' });
}

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
applyLanguage(readStoredLanguage());
elements.languageToggle.addEventListener('click', cycleLanguage);

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
  try {
    const indexResponse = await fetch('data/index.json', { cache: 'no-store' });
    if (!indexResponse.ok) throw new Error(`HTTP ${indexResponse.status}`);
    const germanIndex = await indexResponse.json();
    const reference = germanIndex.currentCosts;
    const path = reference && reference.path;
    if (!CostModel.isAllowedCostPath(path)) {
      state.costs = null;
      renderCosts(null);
      return;
    }
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
  const s = strings();
  const details = node('details', null, 'sources');
  details.append(node('summary', s.sourcesSummary(item.sources.length)));
  const list = node('ul');
  item.sources.forEach((source) => {
    const row = node('li');
    const link = safeSourceLink(source);
    row.append(link || node('span', s.sourceLinkBlocked(source.name)));
    row.append(node('span', `${source.type} · ${source.titleOriginal}`, 'source-type'));
    list.append(row);
  });
  details.append(list);
  article.append(details);
}

function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const s = strings();
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', s.ratingsAriaLabel);
  ratings.forEach((rating) => {
    const details = node('details', null, `rating rating-${rating.key}`);
    const summary = document.createElement('summary');
    if (rating.legacy) {
      summary.append(node('span', rating.label, 'rating-label'), node('span', s.legacyNote, 'rating-legacy-note'));
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
  const s = strings();
  const article = node('article', null, 'story');
  const label = s.categoryLabels[item.id] || item.id;
  const chip = node('div', null, 'story-num');
  chip.append(leafIcon(true, 'currentColor'), document.createTextNode(` No. ${String(index + 1).padStart(3, '0')} — ${label}`));
  article.append(chip);
  const top = node('div', null, 'story-top');
  top.append(node('span', RatingModel.badgeForItem(item), 'badge'));
  article.append(top);
  if (item.status === 'no_major_development') {
    article.append(node('h3', s.noMajorDevelopment.title));
    article.append(node('p', s.noMajorDevelopment.body, 'empty'));
    return article;
  }
  if (item.status === 'unavailable') {
    article.append(node('h3', s.unavailable.title));
    article.append(node('p', s.unavailable.body, 'empty'));
    return article;
  }
  article.append(node('h3', item.headlineDe));
  const summary = node('div', null, 'summary');
  (item.summaryDe || []).forEach((sentence) => summary.append(node('p', sentence)));
  article.append(summary);
  const contextSentences = item.contextDe || [];
  if (contextSentences.length) {
    const context = node('section', null, 'context');
    context.append(node('h4', s.contextHeading));
    contextSentences.forEach((sentence) => context.append(node('p', sentence)));
    article.append(context);
  }
  renderRatings(item, article);
  if (item.additionalImportant) article.append(node('p', `${s.additionalImportantPrefix}${item.additionalImportant}`, 'additional'));
  renderSources(item, article);
  return article;
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  const s = strings();
  const isDaily = Object.hasOwn(report, 'reportDate');
  const countries = report.countries || [];
  const country = countries.find((item) => item.id === state.country) || countries[0];
  if (!country) throw new Error('Bericht enthält keine Länderansicht.');
  state.country = country.id;
  document.querySelectorAll('[data-country]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.country === state.country)));
  elements.countryTitle.textContent = country.label || COUNTRY_LABELS[country.id];
  elements.kicker.textContent = isDaily ? s.kicker.daily : s.kicker[report.periodType];
  if (isDaily) {
    elements.completeness.className = 'muted';
    elements.completeness.textContent = report.status === 'complete' ? s.completeness.complete : s.completeness.partial;
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
  showNotice(missing.length ? s.missingReportsNotice(missing.length, missing.join(', ')) : '');
  elements.report.setAttribute('aria-busy', 'false');
}

async function loadSelectedReport() {
  const path = elements.select.value;
  if (!path) {
    showNotice(strings().noArchiveNotice);
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
    showNotice(strings().reportLoadError(error.message));
  }
}

async function start() {
  await refreshIndex({ preferLatest: true });
}

async function refreshIndex({ preferLatest = false } = {}) {
  const previousPath = elements.select.value;
  const previousLatest = state.index && state.index.latestDaily;
  void loadCurrentCosts();
  try {
    const response = await fetch(`${dataRoot()}/index.json`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.index = await response.json();
    state.freshnessNotice = FreshnessModel.dailyNotice(state.index, new Date());
    renderNotice();
    fillPeriodSelect();
    const entries = archiveEntries();
    if (!entries.length) {
      showNotice(strings().noArchiveNotice);
      return;
    }
    const hasPreviousPath = entries.some((entry) => entry.path === previousPath);
    const hasNewDaily = state.archiveType === 'daily' && state.index.latestDaily !== previousLatest;
    if (!preferLatest && !hasNewDaily && hasPreviousPath) elements.select.value = previousPath;
    await loadSelectedReport();
  } catch (error) {
    showNotice(strings().archiveLoadError(error.message));
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

if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('service-worker.js?v=13', { updateViaCache: 'none' }));
start();

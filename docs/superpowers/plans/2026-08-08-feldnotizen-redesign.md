# Feldnotizen-Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live app's visual design (navy/blue SaaS-dashboard look) with the approved "Feldnotizen/Sammlungskatalog" direction — Steinkatalog color palette, Etikett card treatment (rotated dark label chip, no card box), Museumsetikett typography (Baskerville/Palatino serif throughout) — while preserving every existing behavior, accessibility feature, and security constraint.

**Architecture:** Pure presentation-layer change. `assets/rating-model.js`, `assets/cost-model.js`, `assets/freshness-model.js`, `assets/period-model.js` (the business-logic layer) are **not touched**. Only `assets/app.css` (full rewrite), `assets/app.js` (DOM-building functions only — `CATEGORY_LABELS`, `renderStory`, `renderRatings`), `index.html` (meta theme-color + cache-busting version strings), `service-worker.js` (cache-busting version strings), and `manifest.webmanifest` (theme colors) change. The existing `<details>/<summary>` native disclosure pattern for ratings/sources is kept (already accessible, already shows the `reasonDe` justification text — this is not new functionality, only restyled).

**Tech Stack:** Vanilla JS (no framework, no build step), vanilla CSS custom properties, native `<details>`, inline SVG built via `document.createElementNS` (no `innerHTML`).

## Global Constraints

- No `.innerHTML =` assignment anywhere in `assets/app.js` (tested: `test_frontend_has_no_external_resources_or_dynamic_inner_html`, `test_cost_card_has_semantic_meter_and_safe_independent_rendering_contract`, `test_period_model_and_context_are_loaded_and_rendered_safely`).
- No `document.write` (same tests).
- No external resources: no `src=`/`href=` starting with `http://`/`https://` in `index.html` (tested). No `@font-face`/`@import` from a CDN in `assets/app.css` — system font stacks only (the page's CSP is `style-src 'self'`).
- Exactly 3 elements with `class="country-code"` in `index.html` (tested: `test_country_symbols_do_not_depend_on_emoji_flag_fonts`). No `🇺🇸`-style flag emoji anywhere in `index.html`.
- `data-archive-type="daily"`, `data-archive-type="weekly"`, `data-archive-type="monthly"` must remain in `index.html` (tested).
- `index.html` must never contain the string `"Beispieldaten"` (tested).
- Script tag order in `index.html` must stay: `rating-model.js` → `app.js`; `cost-model.js` → `app.js`; `period-model.js` → `app.js`; `freshness-model.js` → `app.js` (all tested via `html.index(...)` comparisons).
- `assets/app.js` must still call `RatingModel.badgeForItem`, `RatingModel.ratingsForItem`, `CostModel.isAllowedCostPath`, `CostModel.presentation` (via `loadCurrentCosts`), `PeriodModel.coverage`, `FreshnessModel.dailyNotice` — and must still contain the literal substrings `"CostModel.isAllowedCostPath"`, `"loadCurrentCosts"`, `"PeriodModel.coverage(report)"`, `"Einordnung"`, `"item.contextDe || []"`, `"FreshnessModel.dailyNotice"`, `"visibilitychange"`, `"document.visibilityState === 'visible'"`, `"new URL(source.url)"`, `"Keine neue Meldung in den geprüften Quellen"` (all tested — these are exact-substring assertions, not just behavioral).
- `assets/app.js` must **not** contain the string `"belanglose Meldung"` (tested).
- `<section id="cost-meter">` must keep `aria-labelledby="cost-title"` immediately in its opening tag; `<div id="cost-track">` must keep `role="meter" aria-valuemin="0" aria-valuemax="100"` in that attribute order (tested via regex matching the literal HTML).
- `manifest.webmanifest` structural fields (`display: "standalone"`, `start_url: "./"`, icon sizes 192x192/512x512, no `http`-prefixed icon `src`) must stay unchanged (tested: `test_manifest_is_installable_and_local_only`) — only `background_color`/`theme_color` values change.
- Every task ends with `PYTHONPATH=src python -m unittest discover -s tests -v` reported green before moving to the next task.

---

### Task 1: Bump cache-busting version from v9 to v10

**Why first:** shipping new CSS/JS without a fresh cache-bust version means a returning installed-PWA user can stay stuck on the old cached shell (`service-worker.js` uses a cache-first strategy for the app shell). This is a real, user-visible bug if skipped, not cosmetic housekeeping — do it before any visual change lands so every later task ships under the new version.

**Files:**
- Modify: `index.html:14-18` (five `<script src="assets/*.js?v=9" defer>` tags)
- Modify: `assets/app.js:287` (service worker registration URL)
- Modify: `service-worker.js:1,3` (`SHELL_CACHE` constant and `SHELL` array)
- Modify: `tests/test_frontend_contract.py` (every hardcoded `v=9`/`v9`/`lagebericht-shell-v9` string)

**Interfaces:** None — pure string rename, no new functions.

- [ ] **Step 1: Update the test file's expectations to v10 first (red)**

In `tests/test_frontend_contract.py`, replace every occurrence of `v=9` with `v=10`, `v9` with `v10`, and `lagebericht-shell-v9` with `lagebericht-shell-v10`. Concretely, these lines change (line numbers from the current file):

- Line 217: `self.assertLess(html.index("assets/period-model.js?v=9"), html.index("assets/app.js?v=9"))` → `...v=10"...v=10"...`
- Line 218: `self.assertLess(html.index("assets/cost-model.js?v=9"), html.index("assets/app.js?v=9"))` → `v=10`
- Line 223: `self.assertIn("lagebericht-shell-v9", worker)` → `"lagebericht-shell-v10"`
- Line 224: `self.assertIn("./assets/period-model.js?v=9", worker)` → `v=10`
- Line 225: `self.assertIn("./assets/cost-model.js?v=9", worker)` → `v=10`
- Line 304: `self.assertLess(html.index("assets/freshness-model.js?v=9"), html.index("assets/app.js?v=9"))` → `v=10`
- Line 308: `self.assertIn("lagebericht-shell-v9", worker)` → `v10`
- Line 309: `self.assertIn("./assets/freshness-model.js?v=9", worker)` → `v=10`
- Line 344: `self.assertIn("lagebericht-shell-v9", worker)` → `v10`
- Line 345: `self.assertIn("./assets/rating-model.js", worker)` — no version suffix here, leave unchanged
- Line 346: `self.assertIn('assets/rating-model.js?v=9', html)` → `v=10`
- Line 347: `self.assertIn('assets/app.js?v=9', html)` → `v=10`
- Line 348: `self.assertIn("service-worker.js?v=9", app)` → `v=10`

- [ ] **Step 2: Run the suite to confirm these specific tests now fail**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_frontend_contract -v`
Expected: `test_period_model_and_context_are_loaded_and_rendered_safely`, `test_app_refreshes_index_when_pwa_becomes_visible`, `test_service_worker_does_not_cache_cross_origin_requests` FAIL (source still says v9, test now expects v10).

- [ ] **Step 3: Bump the version in the source files**

In `index.html`, replace the five script tags (lines 14-18):
```html
  <script src="assets/freshness-model.js?v=9" defer></script>
  <script src="assets/rating-model.js?v=9" defer></script>
  <script src="assets/period-model.js?v=9" defer></script>
  <script src="assets/cost-model.js?v=9" defer></script>
  <script src="assets/app.js?v=9" defer></script>
```
with:
```html
  <script src="assets/freshness-model.js?v=10" defer></script>
  <script src="assets/rating-model.js?v=10" defer></script>
  <script src="assets/period-model.js?v=10" defer></script>
  <script src="assets/cost-model.js?v=10" defer></script>
  <script src="assets/app.js?v=10" defer></script>
```

In `assets/app.js` line 287, replace:
```js
if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('service-worker.js?v=9', { updateViaCache: 'none' }));
```
with:
```js
if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('service-worker.js?v=10', { updateViaCache: 'none' }));
```

In `service-worker.js` lines 1 and 3, replace:
```js
const SHELL_CACHE = 'lagebericht-shell-v9';
const DATA_CACHE = 'lagebericht-data-v1';
const SHELL = ['./', './index.html', './offline.html', './manifest.webmanifest', './assets/app.css', './assets/freshness-model.js?v=9', './assets/rating-model.js?v=9', './assets/period-model.js?v=9', './assets/cost-model.js?v=9', './assets/app.js?v=9', './assets/icons/icon.svg', './assets/icons/icon-192.png', './assets/icons/icon-512.png'];
```
with:
```js
const SHELL_CACHE = 'lagebericht-shell-v10';
const DATA_CACHE = 'lagebericht-data-v1';
const SHELL = ['./', './index.html', './offline.html', './manifest.webmanifest', './assets/app.css', './assets/freshness-model.js?v=10', './assets/rating-model.js?v=10', './assets/period-model.js?v=10', './assets/cost-model.js?v=10', './assets/app.js?v=10', './assets/icons/icon.svg', './assets/icons/icon-192.png', './assets/icons/icon-512.png'];
```
(`DATA_CACHE` stays `v1` — it caches report JSON, unrelated to the shell redesign.)

- [ ] **Step 4: Run the full suite to confirm green**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all 181 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add index.html assets/app.js service-worker.js tests/test_frontend_contract.py
git commit -m "chore: bump PWA shell cache version to v10 ahead of redesign"
```

---

### Task 2: Rewrite `assets/app.css` — Steinkatalog / Museumsetikett / Etikett

**Files:**
- Modify: `assets/app.css` (complete rewrite)

**Interfaces:**
- Consumes: every class name currently emitted by `assets/app.js` and `index.html` (unchanged in this task — Task 3 changes `app.js`'s DOM output, so this CSS must already define rules for the *new* classes `.story-num`, `.leaf`, `.leaf-row`, `.rating-label`, `.rating-legacy-note` that Task 3 will introduce, even though Task 3 hasn't run yet).
- Produces: nothing consumed by JS (CSS has no JS-visible interface) — but drops the now-dead `.story-icon` / `.timeline::before` rules since Task 3 stops emitting a `.story-icon` element and the timeline line no longer fits the flat Etikett layout.

- [ ] **Step 1: Replace the full contents of `assets/app.css`**

```css
:root {
  color-scheme: light dark;
  --paper: #e6e8e6;
  --card: #eef0ee;
  --ink: #20242a;
  --muted: #5c6266;
  --line: #cbd0cd;
  --rust: #a8542e;
  --brass: #4a6b6a;
  --warn-ink: #7a4a12;
  --warn-bg: #f1e6d2;
  --cost-normal: #4a6b6a;
  --cost-warning: #a8542e;
  --cost-over: #8a2f2f;
  --cost-track: #d9dcd6;
  font-family: "Palatino Linotype", "Book Antiqua", Palatino, serif;
}

* { box-sizing: border-box; }
html { background: var(--paper); color: var(--ink); }
body { margin: 0; min-width: 320px; line-height: 1.6; }
button, select { font: inherit; }
button, select, a { outline-offset: 3px; }
a { color: var(--rust); }
h1, h2, h3, h4 { font-family: "Baskerville", "Palatino Linotype", Georgia, serif; font-weight: 700; }

.skip-link { position: absolute; left: 1rem; top: -5rem; background: var(--card); padding: .7rem 1rem; z-index: 10; }
.skip-link:focus { top: 1rem; }

.site-header, main, footer { width: min(760px, calc(100% - 2rem)); margin-inline: auto; }
.site-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 2.2rem 0 1.4rem; border-bottom: 1px solid var(--line); }
h1 { margin: .15rem 0 .4rem; font-size: clamp(1.6rem, 5vw, 2.3rem); letter-spacing: -.01em; }
h2 { margin: .2rem 0; font-size: clamp(1.25rem, 4vw, 1.7rem); }
h3 { margin: .5rem 0 .6rem; font-size: 1.18rem; line-height: 1.32; }
h4 { margin: 0 0 .35rem; font-size: .95rem; }
p { line-height: 1.6; }
.eyebrow { margin: 0; color: var(--muted); font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.muted { color: var(--muted); }
.sample-badge, .badge { display: inline-flex; align-items: center; border: 1px solid var(--line); padding: .3rem .6rem; font-size: .74rem; letter-spacing: .03em; }
.sample-badge { background: var(--warn-bg); color: var(--warn-ink); border-color: var(--warn-ink); }
.badge { background: none; color: var(--muted); }

.toolbar { display: grid; grid-template-columns: auto auto minmax(10rem, 1fr); gap: .8rem; align-items: center; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: .75rem 0; }
.toolbar label { font-size: .8rem; color: var(--muted); }
.toolbar select { width: 100%; min-height: 42px; border: 1px solid var(--line); background: var(--card); color: var(--ink); padding: .5rem .7rem; font-style: italic; }
.segmented { display: flex; gap: .4rem; }
.segmented button, .country-nav button {
  border: 1px solid var(--line); border-radius: 0; background: none; color: var(--ink); cursor: pointer;
  min-height: 42px; padding: .5rem .9rem; font-style: italic; letter-spacing: .02em;
}
.segmented button[aria-pressed="true"], .country-nav button[aria-pressed="true"] { background: var(--ink); color: var(--paper); border-color: var(--ink); font-style: normal; font-weight: 700; }

.notice { margin-top: 1rem; border-left: 3px solid var(--warn-ink); background: var(--warn-bg); color: var(--warn-ink); padding: .8rem 1rem; }
.country-nav { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin: 1.1rem 0; }
.country-code { display: inline-grid; place-items: center; min-width: 1.6rem; min-height: 1.6rem; margin-right: .3rem; border: 1px solid currentColor; font-size: .64rem; letter-spacing: .04em; }
.overall { margin: 1rem 0 1.4rem; border-top: 2px solid var(--ink); padding: 1.1rem 0 .2rem; }
.overall .eyebrow { color: var(--brass); }
.overall p:last-child { margin-bottom: 0; }

#report { position: relative; padding: 0; }
.report-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; border-bottom: 1px solid var(--line); padding-bottom: .9rem; }
.timeline { position: relative; margin-top: 0; }
.story { position: relative; padding: 1.5rem 0; border-bottom: 1px solid var(--line); }
.story:last-child { border-bottom: 0; padding-bottom: .4rem; }
.story-num {
  display: inline-flex; align-items: center; gap: 6px; background: var(--ink); color: var(--paper);
  font-size: .72rem; letter-spacing: .05em; font-variant: small-caps; font-weight: 400;
  padding: .3rem .65rem; transform: rotate(-1.2deg); box-shadow: 1px 2px 3px rgba(0, 0, 0, .2); margin-bottom: .8rem;
}
.leaf { width: 11px; height: 11px; flex: none; }
.leaf-row { display: inline-flex; gap: 2px; }
.story-top { display: flex; flex-wrap: wrap; justify-content: flex-start; align-items: center; gap: .5rem; margin-bottom: .3rem; }
.summary p { margin: .45rem 0; }
.context { margin-top: .9rem; border-left: 2px solid var(--brass); background: var(--card); padding: .7rem .9rem; }
.context p { margin: .35rem 0; font-size: .92rem; }
.period-coverage { max-width: 25rem; text-align: right; font-style: italic; }
.additional { border-left: 2px solid var(--rust); padding-left: .8rem; font-style: italic; }
.ratings { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: .9rem; }
.rating { min-width: min(100%, 15rem); border: 1px solid var(--line); background: var(--card); }
.rating summary { cursor: pointer; display: flex; align-items: center; gap: .5rem; padding: .5rem .7rem; font-size: .82rem; }
.rating-label { font-style: italic; }
.rating-legacy-note { color: var(--muted); font-size: .78rem; }
.rating-reason { margin: 0; padding: 0 .7rem .65rem; font-size: .82rem; line-height: 1.5; color: var(--ink); border-top: 1px dotted var(--line); padding-top: .5rem; }
.sources { margin-top: .9rem; }
.sources summary { cursor: pointer; color: var(--muted); font-size: .86rem; font-style: italic; }
.sources ul { padding-left: 1.2rem; }
.sources li { margin: .55rem 0; line-height: 1.45; }
.source-type { display: block; color: var(--muted); font-size: .76rem; }
.empty { color: var(--muted); font-style: italic; }

footer { color: var(--muted); font-size: .8rem; padding: 1.6rem 0 2.4rem; }
.cost-meter { margin-bottom: 1.2rem; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: .9rem 0; }
.cost-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; margin-bottom: .7rem; }
.cost-heading h2 { font-size: 1.02rem; }
.cost-value { display: grid; justify-items: end; gap: .08rem; }
.cost-value strong { color: var(--ink); font-size: 1.15rem; font-variant-numeric: tabular-nums; }
.cost-track { position: relative; height: 6px; overflow: hidden; background: var(--cost-track); }
.cost-fill { position: absolute; inset: 0 auto 0 0; width: 0; background: var(--cost-normal); }
.cost-fill.cost-normal { background: var(--cost-normal); }
.cost-fill.cost-warning { background: var(--cost-warning); }
.cost-fill.cost-over { background: var(--cost-over); }
.cost-mark { position: absolute; z-index: 1; top: 0; bottom: 0; width: 1px; background: var(--paper); }
.cost-mark.mark-25 { left: 25%; }
.cost-mark.mark-50 { left: 50%; }
.cost-mark.mark-75 { left: 75%; }
.cost-ticks { display: grid; grid-template-columns: repeat(5, 1fr); margin-top: .35rem; color: var(--muted); font-size: .7rem; font-variant-numeric: tabular-nums; }
.cost-ticks span { text-align: center; }
.cost-ticks span:first-child { text-align: left; }
.cost-ticks span:last-child { text-align: right; }
.cost-note { margin: .65rem 0 0; color: var(--muted); font-size: .76rem; line-height: 1.5; }
.offline { padding-top: 15vh; max-width: 42rem; }

@media (max-width: 440px) {
  .cost-heading { align-items: flex-start; }
  .cost-value { justify-items: end; }
  .cost-ticks span:nth-child(2), .cost-ticks span:nth-child(4) { visibility: hidden; }
}

@media (max-width: 640px) {
  .site-header { padding-top: 1.4rem; }
  .toolbar { grid-template-columns: 1fr; }
  .toolbar label { margin-bottom: -.5rem; }
  .segmented button { flex: 1; }
  .country-nav { gap: .3rem; }
  .country-nav button { padding-inline: .3rem; }
  .report-heading { align-items: flex-start; flex-direction: column; }
  .period-coverage { text-align: left; }
}

@media (prefers-color-scheme: dark) {
  :root {
    --paper: #1b1d1f;
    --card: #232628;
    --ink: #eceeec;
    --muted: #9aa0a3;
    --line: #3a3d3f;
    --rust: #c97a52;
    --brass: #6f9291;
    --warn-ink: #e8c98f;
    --warn-bg: #3a2c14;
    --cost-normal: #6f9291;
    --cost-warning: #c97a52;
    --cost-over: #d97a7a;
    --cost-track: #34383a;
  }
}
```

- [ ] **Step 2: Run the full test suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all 181 tests PASS (CSS has no test assertions on its content, but this confirms nothing else broke).

- [ ] **Step 3: Commit**

```bash
git add assets/app.css
git commit -m "style: rewrite app.css to Steinkatalog/Museumsetikett/Etikett design"
```

---

### Task 3: Update `assets/app.js` rendering functions

**Files:**
- Modify: `assets/app.js:8-13` (`CATEGORY_LABELS`)
- Modify: `assets/app.js:144-192` (`renderRatings`, `renderStory`)
- Modify: `assets/app.js:214` (the `.map(renderStory)` call site)

**Interfaces:**
- Consumes: `RatingModel.ratingsForItem(item)` → array of `{key, label, icon, score, reasonDe, className, legacy}` (unchanged, from `assets/rating-model.js`); `RatingModel.badgeForItem(item)` → string (unchanged).
- Produces: `leafIcon(filled, color)` → SVG element; `leafRow(score, color)` → `<span class="leaf-row">` wrapping three `leafIcon` calls. Both are new local functions in `assets/app.js`, not exported — no other file consumes them.

- [ ] **Step 1: Replace `CATEGORY_LABELS`**

Replace (lines 8-12):
```js
const CATEGORY_LABELS = {
  politics_society: ['Politik & Gesellschaft', '🏛️'],
  economy_technology: ['Wirtschaft & Technologie', '⚙️'],
  foreign_security: ['Außenpolitik & Sicherheit', '🛡️']
};
```
with:
```js
const CATEGORY_LABELS = {
  politics_society: 'Politik & Gesellschaft',
  economy_technology: 'Wirtschaft & Technologie',
  foreign_security: 'Außenpolitik & Sicherheit'
};
```

- [ ] **Step 2: Add `leafIcon` and `leafRow` helpers**

Insert directly after the existing `node()` function (after line 36, before `function renderNotice()`):
```js
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
  for (let i = 0; i < 3; i += 1) wrap.append(leafIcon(i < score, color));
  return wrap;
}
```

- [ ] **Step 3: Replace `renderRatings`**

Replace the existing function (lines 144-157):
```js
function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', 'Bedeutungsbewertung');
  ratings.forEach((rating) => {
    const details = node('details', null, `rating ${rating.className}`);
    const value = rating.legacy ? 'alter Datenstand' : `${rating.score} von 3`;
    details.append(node('summary', `${rating.icon} ${rating.label}: ${value}`));
    details.append(node('p', rating.reasonDe, 'rating-reason'));
    group.append(details);
  });
  article.append(group);
}
```
with:
```js
function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', 'Bedeutungsbewertung');
  ratings.forEach((rating) => {
    const details = node('details', null, `rating ${rating.className}`);
    const summary = document.createElement('summary');
    if (rating.legacy) {
      summary.append(node('span', rating.label, 'rating-label'), node('span', 'alter Datenstand', 'rating-legacy-note'));
    } else {
      const color = rating.key === 'germany' ? 'var(--brass)' : 'var(--rust)';
      summary.append(leafRow(rating.score, color), node('span', rating.label, 'rating-label'));
    }
    details.append(summary);
    details.append(node('p', rating.reasonDe, 'rating-reason'));
    group.append(details);
  });
  article.append(group);
}
```

- [ ] **Step 4: Replace `renderStory`**

Replace the existing function (lines 159-192):
```js
function renderStory(item) {
  const article = node('article', null, 'story');
  const [label, icon] = CATEGORY_LABELS[item.id] || [item.id, '•'];
  article.append(node('div', icon, 'story-icon'));
  const top = node('div', null, 'story-top');
  top.append(node('p', label, 'eyebrow'));
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
```
with:
```js
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
```

Note: `article.append(chip)` is called before `.story-top` unconditionally, including for `no_major_development`/`unavailable` states — this is intentional, the catalog number should appear on every card including empty-state ones (matches the approved mockup, which numbered every slot).

- [ ] **Step 5: Update the call site to pass the index**

In `renderReport()`, replace (line 214):
```js
  elements.stories.replaceChildren(...(country.categories || country.sections || []).map(renderStory));
```
with:
```js
  elements.stories.replaceChildren(...(country.categories || country.sections || []).map((item, index) => renderStory(item, index)));
```

- [ ] **Step 6: Run the full test suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all 181 tests PASS. Pay particular attention to `test_frontend_has_no_external_resources_or_dynamic_inner_html`, `test_empty_categories_do_not_claim_multiple_verification`, `test_country_symbols_do_not_depend_on_emoji_flag_fonts`, `test_html_registers_manifest_and_has_archive_controls` — these are the ones most likely to catch a mistake in this task.

- [ ] **Step 7: Commit**

```bash
git add assets/app.js
git commit -m "feat: restyle story/rating rendering for Feldnotizen design, drop emoji category icons"
```

---

### Task 4: Update `manifest.webmanifest` and `index.html` theme color

**Files:**
- Modify: `manifest.webmanifest:10-11` (`background_color`, `theme_color`)
- Modify: `index.html:6` (`<meta name="theme-color">`)

**Interfaces:** None.

- [ ] **Step 1: Update manifest colors**

In `manifest.webmanifest`, replace:
```json
  "background_color": "#f8fafc",
  "theme_color": "#172554",
```
with:
```json
  "background_color": "#e6e8e6",
  "theme_color": "#20242a",
```

- [ ] **Step 2: Update the HTML meta tag to match**

In `index.html` line 6, replace:
```html
  <meta name="theme-color" content="#172554">
```
with:
```html
  <meta name="theme-color" content="#20242a">
```

- [ ] **Step 3: Run the full test suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all 181 tests PASS (`test_manifest_is_installable_and_local_only` only checks structural fields, not these two color values).

- [ ] **Step 4: Commit**

```bash
git add manifest.webmanifest index.html
git commit -m "style: match PWA theme color to Steinkatalog palette"
```

---

### Task 5: Manual verification against real data

**Files:** none modified — verification only.

- [ ] **Step 1: Start a local static server from the project root**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && python -m http.server 8899`

- [ ] **Step 2: Load the app in the Browser pane and check the console**

Navigate to `http://localhost:8899/`. Confirm no console errors.

- [ ] **Step 3: Walk through every interactive path**

- Switch all three countries (USA/China/Montenegro) — catalog numbers restart at "No. 001" each time, headlines/summaries update.
- Switch archive type to Wochen and Monate — period view renders (`.overall` summary box, `.period-coverage` label), catalog numbers still present.
- Expand at least one rating `<details>` — leaf icons match the score, `reasonDe` text appears below.
- Expand the sources `<details>` on a story — links open only for allow-listed hosts.
- Confirm the cost meter renders with the new thin-bar styling and correct percentage.
- Resize to 375px width (`resize_window` preset mobile) — confirm no horizontal scroll, toolbar stacks to one column.
- Switch OS color scheme to dark (`resize_window` `colorScheme: "dark"` or `prefers-color-scheme` emulation) — confirm text stays legible, the story-num chip still reads clearly (light chip / dark text in dark mode).

- [ ] **Step 4: Stop the local server**

Run: `mcp__Claude_Browser__preview_stop` on the server started in Step 1 (or kill the background Bash process).

---

### Task 6: Final push

- [ ] **Step 1: Confirm the full suite is green one more time after all tasks**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all 181 tests PASS.

- [ ] **Step 2: Ask the user before pushing**

Pushing to `main` triggers the live Tests/Pages workflows and updates the public site. Per this project's established pattern, ask for explicit confirmation before `git push origin main`, even though every commit up to here was already made locally.

'use strict';

(function exposeRatingModel(root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.RatingModel = model;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createRatingModel() {
  const limitationLabels = {
    single_source: 'Nur eine Quelle',
    paywall: 'Bezahlschranke',
    feed_only: 'Nur Feed-Informationen',
    source_disagreement: 'Quellen widersprechen sich',
    technical_failure: 'Technisch unvollständig',
  };

  function validRating(value) {
    return value && Number.isInteger(value.score) && value.score >= 0 && value.score <= 3
      && typeof value.reasonDe === 'string' && value.reasonDe.trim();
  }

  function entry(key, label, icon, value) {
    return {
      key,
      label,
      icon,
      score: value.score,
      reasonDe: value.reasonDe,
      className: `rating-${value.score}`,
      legacy: false,
    };
  }

  function ratingsForItem(item) {
    const ratings = [];
    if (validRating(item && item.germanyRelevance)) {
      ratings.push(entry('germany', 'Deutschland-Bezug', 'DE', item.germanyRelevance));
    } else if (item && item.germanyRelevance === true) {
      ratings.push({
        key: 'germany',
        label: 'Deutschland-Bezug',
        icon: 'DE',
        score: null,
        reasonDe: 'Alter Datenstand ohne Punktbewertung.',
        className: 'rating-legacy',
        legacy: true,
      });
    }
    if (validRating(item && item.overallSignificance)) {
      ratings.push(entry('overall', 'Allgemeine Tragweite', '⚡', item.overallSignificance));
    }
    return ratings;
  }

  function badgeForItem(item) {
    if (item.status === 'no_major_development') return 'Keine neue Meldung';
    const limitationText = (item.limitations || [])
      .map((value) => limitationLabels[value])
      .filter(Boolean)
      .join(' · ');
    if (item.status === 'unavailable') return limitationText || 'Technisch unvollständig';
    return limitationText || (item.sourceBasis === 'multiple' ? 'Mehrfach geprüft' : 'Meldung');
  }

  return { badgeForItem, ratingsForItem };
}));

'use strict';

(function exposeRatingModel(root, factory) {
  const model = factory();
  if (typeof module === 'object' && module.exports) module.exports = model;
  else root.RatingModel = model;
}(typeof globalThis !== 'undefined' ? globalThis : this, function createRatingModel() {
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

  return { ratingsForItem };
}));

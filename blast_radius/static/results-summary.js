const loadResultsBase = loadResults;

loadResults = async function loadResultsWithMeasuredSummary() {
  await loadResultsBase();
  const scores = document.querySelector('#result-tests').textContent.split('→');
  if (scores.length === 2) {
    document.querySelector('#result-summary-line').textContent =
      `Pre ${scores[0].trim()} → post ${scores[1].trim()}`;
  }
};

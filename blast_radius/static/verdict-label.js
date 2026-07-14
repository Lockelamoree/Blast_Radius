const renderVerdictBase = renderVerdict;

renderVerdict = function renderVerdictWithHonestLabel(grade, remaining) {
  renderVerdictBase(grade, remaining);
  const grader = String(grade.graded_by || 'deterministic');
  const label = grader.startsWith('gpt-5.6')
    ? 'GPT-5.6 CRITIC · sol'
    : 'DETERMINISTIC CHECK';
  const receipts = Array.isArray(grade.receipts) && grade.receipts.length
    ? ' / RECEIPTS ATTACHED'
    : '';
  document.querySelector('#verdict-kicker').textContent = `${label}${receipts}`;
};

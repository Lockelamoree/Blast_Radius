let integrityCase = 'tell';

document.querySelector('#gate-catch').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const result = document.querySelector('#gate-catch-result');
  const selectedCase = integrityCase;
  integrityCase = integrityCase === 'tell' ? 'citation' : 'tell';
  button.disabled = true;
  result.className = '';
  result.textContent = 'Running the correctness gate…';
  try {
    const review = await api(`/api/demo/gate-catch?case=${selectedCase}`);
    if (review.passed) {
      result.className = 'gate-failed-open';
      result.textContent = 'Unexpected pass. Do not use this scenario.';
      window.announceStatus(result.textContent);
      return;
    }
    result.className = 'gate-blocked';
    result.textContent = `BLOCKED BEFORE DISPLAY · PLANTED HALLUCINATION: ${review.planted_claim} · FAILED INVARIANT: ${review.reasons.join(' · ')}`;
    window.announceStatus(result.textContent);
  } catch (error) {
    result.className = 'gate-failed-open';
    result.textContent = error.message;
    window.announceStatus(`Integrity check failed: ${result.textContent}`);
  } finally {
    button.disabled = false;
  }
});

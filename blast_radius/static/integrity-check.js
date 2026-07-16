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
    result.replaceChildren();
    const caught = document.createElement('strong');
    caught.textContent = `BLOCKED BEFORE DISPLAY · PLANTED HALLUCINATION: ${review.planted_claim}`;
    const invariant = document.createElement('span');
    invariant.className = 'invariant';
    const reason = review.reasons.join(' · ').replace(`: ${review.planted_claim}`, '');
    invariant.textContent = `FAILED INVARIANT: ${reason}`;
    const hint = document.createElement('span');
    hint.className = 'invariant';
    hint.textContent = `Run again — next plant: ${integrityCase === 'tell' ? 'fabricated exploit tell' : 'fabricated citation'}.`;
    result.append(caught, invariant, hint);
    window.announceStatus(`${caught.textContent}. ${invariant.textContent}`);
  } catch (error) {
    result.className = 'gate-failed-open';
    result.textContent = error.message;
    window.announceStatus(`Integrity check failed: ${result.textContent}`);
  } finally {
    button.disabled = false;
  }
});

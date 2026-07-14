document.querySelector('#gate-catch').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const result = document.querySelector('#gate-catch-result');
  button.disabled = true;
  result.className = '';
  result.textContent = 'Running the correctness gate…';
  try {
    const review = await api('/api/demo/gate-catch');
    if (review.passed) {
      result.className = 'gate-failed-open';
      result.textContent = 'Unexpected pass. Do not use this scenario.';
      return;
    }
    result.className = 'gate-blocked';
    result.textContent = `BLOCKED · ${review.reasons.join(' · ')}`;
  } catch (error) {
    result.className = 'gate-failed-open';
    result.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

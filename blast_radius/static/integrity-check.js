// Landing-page "integrity check": we deliberately plant a hallucinated scenario
// and show the deterministic correctness gate blocking it BEFORE any learner sees
// it. The story must read as a win ("you can trust this tool"), not an error.
let integrityCase = 'tell';

const PLANT_COPY = {
  tell: {
    setup: 'a threat the code never actually shows',
    lesson:
      'A hallucinating model can invent a danger that is not really there. The gate checked the claim against the real artifact, found nothing supporting it, and refused to serve it.',
    next: 'a fabricated citation',
  },
  citation: {
    setup: 'a source link that is not on the approved receipt list',
    lesson:
      'Every scenario must cite a pre-approved, verified source. This link was invented, so the gate blocked it before it could pose as evidence.',
    next: 'a fabricated vulnerability',
  },
};

document.querySelector('#gate-catch').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const result = document.querySelector('#gate-catch-result');
  const selectedCase = integrityCase;
  integrityCase = integrityCase === 'tell' ? 'citation' : 'tell';
  button.disabled = true;
  result.className = 'gate-running';
  result.textContent = 'Feeding a planted fake through the correctness gate…';
  try {
    const review = await api(`/api/demo/gate-catch?case=${selectedCase}`);
    if (review.passed) {
      result.className = 'gate-failed-open';
      result.textContent =
        'Unexpected pass — this scenario would be withheld. Please report it.';
      window.announceStatus(result.textContent);
      return;
    }
    result.className = 'gate-blocked';
    result.replaceChildren();

    const verdict = document.createElement('strong');
    verdict.className = 'gate-verdict';
    verdict.textContent = 'BLOCKED BEFORE DISPLAY — you never saw the fake.';

    const planted = document.createElement('span');
    planted.className = 'gate-line';
    planted.textContent = 'WE PLANTED: ';
    const plantedClaim = document.createElement('em');
    plantedClaim.textContent = `“${review.planted_claim}” — ${PLANT_COPY[selectedCase].setup}`;
    planted.append(plantedClaim);

    const reason = review.reasons.join(' · ').replace(`: ${review.planted_claim}`, '');
    const caught = document.createElement('span');
    caught.className = 'gate-line';
    caught.textContent = `GATE CAUGHT IT: ${reason}`;

    const why = document.createElement('span');
    why.className = 'gate-why';
    why.textContent = PLANT_COPY[selectedCase].lesson;

    const hint = document.createElement('span');
    hint.className = 'gate-line hint';
    hint.textContent = `Run again — next plant: ${PLANT_COPY[selectedCase].next}.`;

    result.append(verdict, planted, caught, why, hint);
    window.announceStatus(`${verdict.textContent} ${caught.textContent}`);
  } catch (error) {
    result.className = 'gate-failed-open';
    result.textContent = error.message;
    window.announceStatus(`Integrity check failed: ${result.textContent}`);
  } finally {
    button.disabled = false;
  }
});

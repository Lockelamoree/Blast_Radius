// Landing-page "integrity check": we deliberately plant a hallucinated scenario
// and show the deterministic correctness gate blocking it BEFORE any learner sees
// it. The story must read as a win ("you can trust this tool"), not an error.
//
// The panel renders three beats so the "plant" is visible, not abstract:
//   1 — the real scenario the learner would have seen,
//   2 — the lie we injected on top of it (highlighted as danger),
//   3 — the deterministic gate catching it, in plain language + the raw gate log.
// Then a loud acid verdict. The endpoint returns {case, planted_claim, passed,
// reasons}; the per-case artifact + humanized copy live here.
let integrityCase = 'tell';

const VERDICT_SUB =
  'Every real scenario passes this exact gate. That is why you can trust what you do see.';

const PLANT_COPY = {
  tell: {
    artifact: {
      title: 'Install proposal · what you would be shown',
      lines: [
        '$ pip install reqeusts==2.32.0',
        'Approved lockfile entry: requests==2.32.0',
        'Registry policy: reqeusts is not approved',
      ],
    },
    beat1Note: 'Genuine. The real tell is the near-miss name — reqeusts vs requests.',
    beat2Lead: 'The AI stapled on a danger that appears nowhere in the artifact above:',
    lieLabel: 'declared threat',
    lieValue: (review) => `“${review.planted_claim}”`,
    lieSub: null,
    scan: 'Scanned the artifact for “remote code execution” and “backdoor”',
    scanResult: '0 matches',
    rule: 'A declared danger with no supporting evidence fails the groundedness rule.',
    next: 'a fabricated citation',
  },
  citation: {
    artifact: {
      title: 'Cited evidence · what you would be shown',
      lines: [
        'source: github.blog/…/avoiding-npm-substitution-attacks',
        'status: on the approved receipt list',
      ],
    },
    beat1Note: 'Genuine. This source is on the pre-approved receipt list.',
    beat2Lead: 'The AI swapped the citation for a link that is not on the approved receipt list:',
    lieLabel: 'evidence source',
    lieValue: () => 'https://example.com/fabricated-security-guidance',
    lieSub: (review) => `an ${review.planted_claim} — invented, never vetted`,
    scan: 'Checked the source against the approved receipt list',
    scanResult: 'not found',
    rule: 'Every source must be a pre-approved receipt, so an invented link cannot pose as evidence.',
    next: 'two stacked defects at once',
  },
  stack: {
    artifact: {
      title: 'Install proposal · what you would be shown',
      lines: [
        '$ pip install reqeusts==2.32.0',
        'Approved lockfile entry: requests==2.32.0',
        'source: on the approved receipt list',
      ],
    },
    beat1Note: 'Genuine. The real tell is the near-miss name — reqeusts vs requests.',
    beat2Lead: 'The AI stacked TWO lies on one scenario at once:',
    lieLabel: 'declared threat',
    lieValue: () => '“hidden remote code execution backdoor”',
    lieSub: () =>
      'AND the citation was swapped to an off-catalog link not on the approved receipt list',
    scan: 'Ran every invariant — groundedness AND the approved-receipt list',
    scanResult: '2 defects caught',
    rule: 'Each lie fails a different deterministic rule; the gate reports them all, independently.',
    next: 'a single fabricated tell',
  },
};

function gateBeat(stepClass, label, buildBody) {
  const beat = document.createElement('div');
  beat.className = `gate-beat ${stepClass}`;
  const head = document.createElement('span');
  head.className = 'gate-beat-label';
  head.textContent = label;
  beat.append(head);
  buildBody(beat);
  return beat;
}

document.querySelector('#gate-catch').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const result = document.querySelector('#gate-catch-result');
  const selectedCase = integrityCase;
  const copy = PLANT_COPY[selectedCase];
  integrityCase = { tell: 'citation', citation: 'stack', stack: 'tell' }[integrityCase];
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

    // Beat 1 — the real scenario the learner would have seen.
    const beat1 = gateBeat('step-real', '1 · THE REAL SCENARIO YOU WOULD SEE', (beat) => {
      const art = document.createElement('div');
      art.className = 'gate-artifact';
      const title = document.createElement('span');
      title.className = 'gate-artifact-title';
      title.textContent = copy.artifact.title;
      art.append(title);
      copy.artifact.lines.forEach((line) => {
        const row = document.createElement('span');
        row.className = 'gate-artifact-line';
        row.textContent = line;
        art.append(row);
      });
      beat.append(art);
      const note = document.createElement('span');
      note.className = 'gate-note';
      note.textContent = copy.beat1Note;
      beat.append(note);
    });

    // Beat 2 — the lie we injected on top of it.
    const beat2 = gateBeat('step-lie', '2 · WE PLANTED THIS LIE', (beat) => {
      const lead = document.createElement('span');
      lead.className = 'gate-note';
      lead.textContent = copy.beat2Lead;
      beat.append(lead);
      const lie = document.createElement('div');
      lie.className = 'gate-lie';
      const value = document.createElement('span');
      value.className = 'gate-lie-value';
      value.textContent = `${copy.lieLabel}: ${copy.lieValue(review)}`;
      lie.append(value);
      if (copy.lieSub) {
        const sub = document.createElement('span');
        sub.className = 'gate-lie-sub';
        sub.textContent = copy.lieSub(review);
        lie.append(sub);
      }
      beat.append(lie);
    });

    // Beat 3 — the deterministic gate catching it, plain language + raw log.
    const beat3 = gateBeat('step-gate', '3 · HOW THE GATE CAUGHT IT · NO AI', (beat) => {
      const scan = document.createElement('span');
      scan.className = 'gate-scan';
      scan.append(document.createTextNode(`${copy.scan} → `));
      const hit = document.createElement('strong');
      hit.textContent = copy.scanResult;
      scan.append(hit);
      scan.append(document.createTextNode('.'));
      beat.append(scan);
      const rule = document.createElement('span');
      rule.className = 'gate-note';
      rule.textContent = copy.rule;
      beat.append(rule);
      if (review.reasons.length > 1) {
        // Multi-defect catch: each independent reason as its own chip.
        const chips = document.createElement('div');
        chips.className = 'gate-chips';
        review.reasons.forEach((reason) => {
          const chip = document.createElement('span');
          chip.className = 'gate-chip';
          chip.textContent = reason;
          chips.append(chip);
        });
        beat.append(chips);
      } else {
        const receipt = document.createElement('span');
        receipt.className = 'gate-receipt';
        receipt.textContent = `gate log · ${review.reasons.join(' · ')}`;
        beat.append(receipt);
      }
    });

    // Verdict — the win.
    const verdict = document.createElement('div');
    verdict.className = 'gate-verdict';
    const vLine = document.createElement('strong');
    vLine.className = 'gate-verdict-line';
    vLine.textContent = 'BLOCKED BEFORE DISPLAY — you never saw the fake.';
    const vSub = document.createElement('span');
    vSub.className = 'gate-verdict-sub';
    vSub.textContent = VERDICT_SUB;
    verdict.append(vLine, vSub);

    const hint = document.createElement('span');
    hint.className = 'gate-hint';
    hint.textContent = `Run again — next plant: ${copy.next}.`;

    result.append(beat1, beat2, beat3, verdict, hint);
    window.announceStatus(`${vLine.textContent} ${copy.scan} ${copy.scanResult}.`);
  } catch (error) {
    result.className = 'gate-failed-open';
    result.textContent = error.message;
    window.announceStatus(`Integrity check failed: ${result.textContent}`);
  } finally {
    button.disabled = false;
  }
});

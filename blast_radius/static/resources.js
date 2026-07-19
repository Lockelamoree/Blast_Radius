// Learn (field guide) and Protect (toolkit) screens. Both are read-only content
// served from /api/learn and /api/toolkit. Reuses the globals defined in app.js
// (api, show, announce, escapeFamily) — classic scripts share one global scope.
const resourceLoaded = { learn: false, protect: false };

function resourceLink(source) {
  const isUrl = /^https?:\/\//i.test(source.url || '');
  const link = document.createElement(isUrl ? 'a' : 'span');
  link.className = 'resource-source';
  if (isUrl) {
    link.href = source.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  }
  const badge = document.createElement('b');
  badge.textContent = source.type === 'tool' ? 'TOOL' : 'READ';
  const title = document.createElement('span');
  title.className = 'resource-source-title';
  title.textContent = source.publisher ? `${source.title} · ${source.publisher}` : source.title;
  link.append(badge, title);
  if (source.note) {
    const note = document.createElement('small');
    note.textContent = source.note;
    link.append(note);
  }
  return link;
}

function labelled(text) {
  const label = document.createElement('p');
  label.className = 'resource-card-label';
  label.textContent = text;
  return label;
}

function renderLearn(modules) {
  const grid = document.querySelector('#learn-modules');
  grid.replaceChildren();
  modules.forEach((module) => {
    const card = document.createElement('article');
    card.className = 'resource-card';

    const tag = document.createElement('span');
    tag.className = 'resource-tag';
    tag.textContent = escapeFamily(module.family);
    const title = document.createElement('h3');
    title.textContent = module.title;
    const threat = document.createElement('p');
    threat.className = 'resource-threat';
    threat.textContent = module.threat;
    card.append(tag, title, threat);

    card.append(labelled('TELLS TO SPOT'));
    const tells = document.createElement('ul');
    tells.className = 'resource-tells';
    module.tells.forEach((tell) => {
      const li = document.createElement('li');
      li.textContent = tell;
      tells.append(li);
    });
    card.append(tells);

    card.append(labelled('SAFE DEFAULT'));
    const safe = document.createElement('p');
    safe.className = 'resource-safe';
    safe.textContent = module.safe_default;
    card.append(safe);

    if (module.sources && module.sources.length) {
      card.append(labelled('CITED SOURCES'));
      const sources = document.createElement('div');
      sources.className = 'resource-sources';
      module.sources.forEach((source) => sources.append(resourceLink(source)));
      card.append(sources);
    }
    grid.append(card);
  });
  grid.setAttribute('aria-busy', 'false');
}

function renderSnippet(snippet) {
  const wrap = document.createElement('div');
  wrap.className = 'resource-snippet';
  const head = document.createElement('div');
  head.className = 'resource-snippet-head';
  const label = document.createElement('span');
  label.textContent = snippet.label;
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.className = 'resource-copy';
  copy.textContent = 'Copy';
  copy.addEventListener('click', () => {
    navigator.clipboard.writeText(snippet.code).then(() => {
      copy.textContent = 'Copied ✓';
      window.setTimeout(() => { copy.textContent = 'Copy'; }, 1500);
    }).catch(() => { copy.textContent = 'Copy unavailable'; });
  });
  head.append(label, copy);
  const pre = document.createElement('pre');
  const code = document.createElement('code');
  code.textContent = snippet.code;
  pre.append(code);
  wrap.append(head, pre);
  return wrap;
}

function renderToolkit(cards) {
  const grid = document.querySelector('#toolkit-cards');
  grid.replaceChildren();
  cards.forEach((entry) => {
    const card = document.createElement('article');
    card.className = 'resource-card';

    const tag = document.createElement('span');
    tag.className = 'resource-tag';
    tag.textContent = escapeFamily(entry.family);
    const title = document.createElement('h3');
    title.textContent = entry.title;
    const summary = document.createElement('p');
    summary.className = 'resource-threat';
    summary.textContent = entry.summary;
    card.append(tag, title, summary);

    card.append(labelled('DO THIS'));
    const steps = document.createElement('ol');
    steps.className = 'resource-steps';
    entry.steps.forEach((step) => {
      const li = document.createElement('li');
      li.textContent = step;
      steps.append(li);
    });
    card.append(steps);

    (entry.snippets || []).forEach((snippet) => card.append(renderSnippet(snippet)));

    if (entry.tools && entry.tools.length) {
      card.append(labelled('VETTED TOOLS'));
      const tools = document.createElement('div');
      tools.className = 'resource-sources';
      entry.tools.forEach((tool) => tools.append(resourceLink({
        url: tool.url, title: tool.name, note: tool.note, type: 'tool',
      })));
      card.append(tools);
    }
    grid.append(card);
  });
  grid.setAttribute('aria-busy', 'false');
}

async function ensureResource(kind) {
  if (resourceLoaded[kind]) return;
  const grid = document.querySelector(kind === 'learn' ? '#learn-modules' : '#toolkit-cards');
  try {
    if (kind === 'learn') {
      const data = await api('/api/learn');
      renderLearn(data.modules || []);
    } else {
      const data = await api('/api/toolkit');
      renderToolkit(data.cards || []);
    }
    resourceLoaded[kind] = true;
  } catch (error) {
    grid.setAttribute('aria-busy', 'false');
    grid.textContent = `Could not load this section (${error.message}). Please try again.`;
  }
}

async function openResource(target) {
  if (target === 'landing') {
    show('landing');
    window.announceStatus('Returned to the start.');
    return;
  }
  if (target === 'integrity') {
    show('integrity');
    window.announceStatus('Integrity check: watch the deterministic gate block a planted fake, then see the committed proof.');
    return;
  }
  const screen = target === 'learn' ? 'learn' : 'protect';
  const kind = target === 'learn' ? 'learn' : 'protect';
  show(screen);
  window.announceStatus(
    kind === 'learn'
      ? 'Field guide: six AI coding-agent threat families with cited sources.'
      : 'Toolkit: copy-paste defenses and vetted tools for each threat family.',
  );
  await ensureResource(kind);
}

[...document.querySelectorAll('[data-open]')].forEach((button) => {
  button.addEventListener('click', () => openResource(button.dataset.open));
});

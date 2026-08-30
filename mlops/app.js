const tabs = Array.from(document.querySelectorAll('[data-stage-tab]'));
const stages = Array.from(document.querySelectorAll('[data-stage]'));
const stageList = document.querySelector('.stage-list');
const diagram = document.querySelector('[data-diagram]');
const diagramToggle = document.querySelector('[data-diagram-toggle]');
const validStages = new Set(tabs.map((tab) => tab.dataset.stageTab));

function showStage(requestedValue, moveIntoView = false, updateAddress = true) {
  const value = validStages.has(requestedValue) ? requestedValue : 'all';
  tabs.forEach((tab) => {
    tab.setAttribute('aria-pressed', String(tab.dataset.stageTab === value));
  });
  stages.forEach((stage) => {
    if (value === 'all') stage.removeAttribute('aria-current');
    else if (stage.dataset.stage === value) stage.setAttribute('aria-current', 'step');
    else stage.removeAttribute('aria-current');
  });
  if (moveIntoView && value !== 'all' && stageList) {
    const selected = stages.find((stage) => stage.dataset.stage === value);
    if (selected) {
      const left = selected.offsetLeft - (stageList.clientWidth - selected.clientWidth) / 2;
      stageList.scrollTo({
        left: Math.max(0, left),
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
    }
  }
  if (updateAddress || requestedValue !== value) {
    const address = new URL(window.location.href);
    if (value === 'all') address.searchParams.delete('stage');
    else address.searchParams.set('stage', value);
    history.replaceState({ stage: value }, '', address);
  }
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => showStage(tab.dataset.stageTab, true));
});

window.addEventListener('popstate', () => {
  const stage = new URLSearchParams(window.location.search).get('stage') || 'all';
  showStage(stage, stage !== 'all', false);
});

if (diagram && diagramToggle) {
  diagramToggle.addEventListener('click', () => {
    const original = diagram.classList.toggle('is-original');
    diagramToggle.setAttribute('aria-pressed', String(original));
    diagramToggle.textContent = original ? '화면에 맞추기' : '글자 크게 보기';
  });
}

const initialStage = new URLSearchParams(window.location.search).get('stage') || 'all';
showStage(initialStage, initialStage !== 'all', false);

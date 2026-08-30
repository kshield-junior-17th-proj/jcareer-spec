const tabs = Array.from(document.querySelectorAll('[data-stage-tab]'));
const stages = Array.from(document.querySelectorAll('[data-stage]'));
const stageList = document.querySelector('.stage-list');
const diagram = document.querySelector('[data-diagram]');
const diagramToggle = document.querySelector('[data-diagram-toggle]');
const stageProgress = document.querySelector('[data-stage-progress]');
const stageRunner = document.querySelector('[data-stage-runner]');
const stageReadout = document.querySelector('[data-stage-readout]');
const validStages = new Set(tabs.map((tab) => tab.dataset.stageTab));
let runnerPosition = 100;

function moveStageRunner(position, animate = false) {
  const rail = stageProgress?.parentElement;
  if (!rail || !stageRunner) return;
  runnerPosition = position;
  const x = Math.max(0, rail.clientWidth - stageRunner.clientWidth) * (position / 100);
  if (window.gsap) {
    window.gsap.killTweensOf(stageRunner);
    if (animate && !window.JCareerMotion?.reduced) {
      window.gsap.to(stageRunner, { x, duration: 0.52, ease: 'power3.out' });
    } else {
      window.gsap.set(stageRunner, { x });
    }
  } else {
    stageRunner.style.transform = `translate(${x}px, -50%)`;
  }
}

function showStage(requestedValue, moveIntoView = false, updateAddress = true) {
  const value = validStages.has(requestedValue) ? requestedValue : 'all';
  const updateStage = () => {
    tabs.forEach((tab) => {
      tab.setAttribute('aria-pressed', String(tab.dataset.stageTab === value));
    });
    stages.forEach((stage) => {
      if (value === 'all') stage.removeAttribute('aria-current');
      else if (stage.dataset.stage === value) stage.setAttribute('aria-current', 'step');
      else stage.removeAttribute('aria-current');
    });
    const stageNumber = value === 'all' ? 7 : Number(value);
    const progress = value === 'all' ? 1 : stageNumber / 7;
    const position = value === 'all' ? 100 : ((stageNumber - 1) / 6) * 100;
    const rail = stageProgress?.parentElement;
    rail?.style.setProperty('--stage-progress', String(progress));
    rail?.style.setProperty('--stage-position', `${position}%`);
    moveStageRunner(position, updateAddress);
    if (stageRunner) stageRunner.dataset.currentStage = value;
    if (stageReadout) stageReadout.textContent = value === 'all' ? '전체 7단계' : `${stageNumber} / 7 단계`;
  };
  if (updateAddress && window.JCareerMotion) window.JCareerMotion.transition(updateStage);
  else updateStage();
  if (moveIntoView && value !== 'all' && stageList) {
    const selected = stages.find((stage) => stage.dataset.stage === value);
    if (selected) {
      const left = selected.offsetLeft - (stageList.clientWidth - selected.clientWidth) / 2;
      stageList.scrollTo({
        left: Math.max(0, left),
        behavior: window.JCareerMotion?.reduced || matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
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
    diagramToggle.textContent = '원본 크기로 보기';
  });
}

const initialStage = new URLSearchParams(window.location.search).get('stage') || 'all';
showStage(initialStage, initialStage !== 'all', false);

if ('ResizeObserver' in window && stageProgress?.parentElement) {
  new ResizeObserver(() => moveStageRunner(runnerPosition)).observe(stageProgress.parentElement);
}

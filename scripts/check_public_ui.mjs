#!/usr/bin/env node

import { mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import {
  findChrome,
  removeOwnedTempDirectory,
  startStaticServer,
} from './browser_support.mjs';

const EXPECTED_ROUTES = [
  {
    href: 'terraform/asis/architecture.html',
    flow: 'overview',
    detailHref: '../../assets/JCAREER_AI_RUNTIME_ACTUAL.svg',
    steps: 7,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=candidate',
    flow: 'candidate',
    detailHref: 'index.html#section-31',
    steps: 5,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=recruiter',
    flow: 'recruiter',
    detailHref: 'index.html#section-31',
    steps: 5,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=explanation',
    flow: 'explanation',
    detailHref: 'index.html#section-33',
    steps: 4,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=values',
    flow: 'values',
    detailHref: 'index.html#section-31',
    steps: 5,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=history',
    flow: 'history',
    detailHref: 'index.html#section-31',
    steps: 4,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=mlops',
    flow: 'mlops',
    detailHref: '../../mlops/',
    steps: 6,
    media: 'overview',
  },
  {
    href: 'terraform/asis/architecture.html?flow=audit',
    flow: 'audit',
    detailHref: 'index.html#section-52',
    steps: 5,
    media: 'overview',
  },
];

const PUBLIC_PAGES = [
  {
    path: '/',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/',
  },
  {
    path: '/consulting/',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/consulting/',
  },
  {
    path: '/mlops/',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/mlops/',
  },
  {
    path: '/terraform/lab/',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/lab/',
  },
  {
    path: '/terraform/asis/',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/',
  },
  {
    path: '/terraform/asis/architecture.html',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html',
  },
  {
    path: '/terraform/asis/production-transition.html',
    canonical: 'https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/production-transition.html',
  },
];

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(check, description, timeoutMilliseconds = 12000) {
  const deadline = Date.now() + timeoutMilliseconds;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(80);
  }
  const suffix = lastError ? ' Last error: ' + lastError.message : '';
  throw new Error('Timed out waiting for ' + description + '.' + suffix);
}

class CdpClient {
  constructor(webSocketUrl) {
    if (typeof WebSocket === 'undefined') {
      throw new Error('This check requires the WebSocket API available in Node.js 22 or newer.');
    }
    this.nextId = 1;
    this.pending = new Map();
    this.socket = new WebSocket(webSocketUrl);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', () => reject(new Error('Chrome DevTools WebSocket failed.')), { once: true });
    });
    this.socket.addEventListener('message', async (event) => {
      const raw = typeof event.data === 'string'
        ? event.data
        : event.data && typeof event.data.text === 'function'
          ? await event.data.text()
          : Buffer.from(event.data).toString('utf8');
      const message = JSON.parse(raw);
      if (!message.id || !this.pending.has(message.id)) return;
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timeout);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
    });
    this.socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Chrome DevTools WebSocket closed.'));
      }
      this.pending.clear();
    });
  }

  async send(method, params = {}) {
    await this.ready;
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('Chrome DevTools command timed out: ' + method));
      }, 6000);
      this.pending.set(id, { resolve, reject, timeout });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return response;
  }

  close() {
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close();
    }
  }
}

async function createPageClient(debugPort) {
  const endpoint = 'http://127.0.0.1:' + debugPort + '/json/new?' + encodeURIComponent('about:blank');
  const target = await waitFor(async () => {
    const response = await fetch(endpoint, { method: 'PUT' });
    if (!response.ok) return null;
    const value = await response.json();
    return value.webSocketDebuggerUrl ? value : null;
  }, 'a Chrome page target');
  const client = new CdpClient(target.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  return client;
}

async function evaluate(client, expression) {
  const response = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error('Browser evaluation failed: ' + JSON.stringify(response.exceptionDetails));
  }
  return response.result.value;
}

async function navigate(client, url) {
  const result = await client.send('Page.navigate', { url });
  if (result.errorText) throw new Error('Navigation failed: ' + result.errorText);
  await waitFor(
    async () => (await evaluate(client, 'document.readyState')) === 'complete',
    'document load: ' + url,
  );
  await delay(120);
}

async function inspectStage(client) {
  return evaluate(
    client,
    '(function () {' +
      'const active = document.querySelector("[data-stage-tab][aria-pressed=\\"true\\"]");' +
      'const items = Array.from(document.querySelectorAll("[data-stage]"));' +
      'const current = items.filter((item) => item.getAttribute("aria-current") === "step")' +
        '.map((item) => item.dataset.stage);' +
      'return {' +
        'active: active ? active.dataset.stageTab : null,' +
        'query: new URL(location.href).searchParams.get("stage"),' +
        'current: current,' +
        'itemCount: items.length,' +
        'progress: document.querySelector(".stage-motion__rail")?.style.getPropertyValue("--stage-progress") || "",' +
        'position: document.querySelector(".stage-motion__rail")?.style.getPropertyValue("--stage-position") || "",' +
        'readout: document.querySelector("[data-stage-readout]")?.textContent.trim() || ""' +
      '};' +
    '})()',
  );
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function setViewport(client, width) {
  await client.send('Emulation.setDeviceMetricsOverride', {
    width,
    height: width === 390 ? 844 : 1000,
    deviceScaleFactor: 1,
    mobile: width === 390,
  });
}

async function pressTab(client) {
  const event = {
    key: 'Tab',
    code: 'Tab',
    windowsVirtualKeyCode: 9,
    nativeVirtualKeyCode: 9,
  };
  await client.send('Input.dispatchKeyEvent', { ...event, type: 'keyDown' });
  await client.send('Input.dispatchKeyEvent', { ...event, type: 'keyUp' });
  await delay(20);
}

async function checkPublicPages(client, origin) {
  let checks = 0;
  for (const width of [390, 1440]) {
    await setViewport(client, width);
    for (const page of PUBLIC_PAGES) {
      await navigate(client, origin + page.path);
      await pressTab(client);
      const state = await evaluate(
        client,
        '(function () {' +
          'const canonical = document.querySelector("link[rel=\\"canonical\\"]");' +
          'const ogUrl = document.querySelector("meta[property=\\"og:url\\"]");' +
          'const ogImage = document.querySelector("meta[property=\\"og:image\\"]");' +
          'const ogAlt = document.querySelector("meta[property=\\"og:image:alt\\"]");' +
          'const controls = Array.from(document.querySelectorAll("[data-stage-tab]"));' +
          'const interactive = Array.from(document.querySelectorAll("a, button"));' +
          'const focused = document.activeElement;' +
          'const focusedStyle = focused ? getComputedStyle(focused) : null;' +
          'const measure = (selector) => {' +
            'const element = document.querySelector(selector);' +
            'if (!element) return null;' +
            'const rect = element.getBoundingClientRect();' +
            'return {left: rect.left, right: rect.right, width: rect.width, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth};' +
          '};' +
          'return {' +
            'canonical: canonical ? canonical.href : null,' +
            'ogUrl: ogUrl ? ogUrl.content : null,' +
            'ogImage: ogImage ? ogImage.content : null,' +
            'ogAlt: ogAlt ? ogAlt.content.trim() : "",' +
            'innerWidth: window.innerWidth,' +
            'scrollWidth: document.documentElement.scrollWidth,' +
            'stageTabs: controls.length,' +
            'stageControlsValid: controls.every((control) => {' +
              'const id = control.getAttribute("aria-controls");' +
              'return Boolean(id && document.getElementById(id));' +
            '}),' +
            'interactiveCount: interactive.length,' +
            'touchReady: interactive.every((item) => getComputedStyle(item).touchAction === "manipulation"),' +
            'focusVisible: Boolean(focused && focused.matches(":focus-visible")),' +
            'focusOutlined: Boolean(focusedStyle && parseFloat(focusedStyle.outlineWidth) > 0),' +
            'consultingGeometry: measure(".article-hero__grid") ? {' +
              'grid: measure(".article-hero__grid"),' +
              'copy: measure(".hero-copy"),' +
              'heading: measure(".hero-copy h1"),' +
              'standfirst: measure(".standfirst"),' +
              'nav: measure(".nav")' +
            '} : null' +
          '};' +
        '})()',
      );
      const label = page.path + ' at ' + width + 'px';
      assert(state.innerWidth === width, 'Wrong viewport width: ' + label);
      assert(state.scrollWidth <= state.innerWidth, 'Document overflows horizontally: ' + label);
      assert(state.canonical === page.canonical && state.ogUrl === page.canonical, 'Canonical and og:url diverge: ' + label);
      assert(typeof state.ogImage === 'string' && state.ogImage.startsWith('https://') && state.ogAlt.length > 0, 'Open Graph image metadata is incomplete: ' + label);
      assert(state.interactiveCount > 0 && state.touchReady, 'Touch action is incomplete: ' + label);
      assert(state.focusVisible && state.focusOutlined, 'Keyboard focus is not visibly outlined: ' + label);
      if (page.path === '/consulting/') {
        const geometry = state.consultingGeometry;
        const fits = Object.values(geometry).every((item) =>
          item.left >= -1 && item.right <= state.innerWidth + 1 && item.scrollWidth <= item.clientWidth + 1
        );
        assert(fits, 'Consulting hero content is clipped: ' + label + ' ' + JSON.stringify(geometry));
      }
      if (page.path === '/mlops/') {
        assert(state.stageTabs === 8 && state.stageControlsValid, 'MLOps stage aria-controls contract failed: ' + label);
      }
      checks += 1;
    }
  }
  return checks;
}

async function runChecks(client, origin) {
  const pageViewportChecks = await checkPublicPages(client, origin);
  await setViewport(client, 390);
  await navigate(client, origin + '/');
  const landing = await evaluate(
    client,
    '(function () {' +
      'return {' +
        'routes: Array.from(document.querySelectorAll(".flow-shortcuts a")).map((link) => link.getAttribute("href")),' +
        'innerWidth: window.innerWidth,' +
        'scrollWidth: document.documentElement.scrollWidth' +
      '};' +
    '})()',
  );
  assert(
    JSON.stringify(landing.routes) === JSON.stringify(EXPECTED_ROUTES.map((route) => route.href)),
    'Landing routes do not match the eight architecture states (overview plus seven AI flows).',
  );
  assert(landing.innerWidth === 390, 'Mobile viewport width is not 390 CSS pixels.');
  assert(landing.scrollWidth <= landing.innerWidth, 'Landing page overflows horizontally at 390 CSS pixels.');

  const landingMotion = await evaluate(
    client,
    '(function () {' +
      'const heading = document.querySelector(".hero h1");' +
      'const style = heading ? getComputedStyle(heading) : null;' +
      'const lineHeight = style ? parseFloat(style.lineHeight) : 0;' +
      'return {' +
        'motion: document.documentElement.dataset.motion,' +
        'toggleVisible: Boolean(document.querySelector("[data-motion-toggle]:not([hidden])")),' +
        'gsap: Boolean(window.gsap && window.ScrollTrigger),' +
        'headingOpacity: style ? Number(style.opacity) : 0,' +
        'headingLines: heading && lineHeight ? Math.round(heading.getBoundingClientRect().height / lineHeight) : 99,' +
        'slides: document.querySelectorAll("[data-perspective-slide]").length,' +
        'activeSlides: document.querySelectorAll("[data-perspective-slide]:not([hidden])").length,' +
        'readinessItems: document.querySelectorAll("[data-readiness]").length,' +
        'readinessDone: document.querySelectorAll("[data-readiness=\\"done\\"]").length,' +
        'diagramSource: document.querySelector("[data-animated-diagram]")?.getAttribute("src") || ""' +
      '};' +
    '})()',
  );
  assert(landingMotion.motion === 'full' && landingMotion.toggleVisible, 'Landing motion control did not initialise.');
  assert(landingMotion.gsap, 'Pinned GSAP and ScrollTrigger did not load.');
  assert(landingMotion.headingOpacity === 1 && landingMotion.headingLines <= 3, 'Landing hero is hidden or wraps beyond three lines.');
  assert(landingMotion.slides === 3 && landingMotion.activeSlides === 1, 'Perspective carousel did not initialise one of three views.');
  assert(landingMotion.readinessItems === 9 && landingMotion.readinessDone === 3, 'Demo readiness blockers are incomplete or overstated.');
  assert(landingMotion.diagramSource.endsWith('.svg'), 'Animated architecture source is not active.');

  await evaluate(client, 'document.querySelector("[data-carousel-next]").click(); true');
  await waitFor(async () => evaluate(client, 'document.querySelector("[data-carousel-count]").textContent.trim() === "2 / 3"'), 'the perspective carousel transition');
  const carouselState = await evaluate(client, '(function () { const active = document.querySelector("[data-perspective-slide]:not([hidden])"); return { count: document.querySelectorAll("[data-perspective-slide]:not([hidden])").length, role: document.querySelector("[data-perspective-carousel]")?.getAttribute("role"), perspective: active?.dataset.perspective, query: new URL(location.href).searchParams.get("perspective") }; })()');
  assert(carouselState.count === 1 && carouselState.role === 'region', 'Perspective carousel semantics are incomplete.');
  assert(carouselState.perspective === 'recruiter' && carouselState.query === 'recruiter', 'Perspective carousel URL state is not synchronized.');

  await evaluate(client, 'document.querySelector("[data-motion-toggle]").click(); true');
  await delay(50);
  const reducedMotion = await evaluate(
    client,
    '(function () {' +
      'const toggle = document.querySelector("[data-motion-toggle]");' +
      'return {' +
        'motion: document.documentElement.dataset.motion,' +
        'pressed: toggle?.getAttribute("aria-pressed"),' +
        'label: toggle?.getAttribute("aria-label"),' +
        'source: document.querySelector("[data-animated-diagram]")?.getAttribute("src") || "",' +
        'marquee: getComputedStyle(document.querySelector(".signal-marquee__track")).animationName' +
      '};' +
    '})()',
  );
  assert(reducedMotion.motion === 'reduced' && reducedMotion.pressed === 'true' && reducedMotion.label === '움직임 줄이기', 'Motion control state or accessible name is inconsistent.');
  assert(reducedMotion.source.endsWith('.png') && reducedMotion.marquee === 'none', 'Reduced mode did not stop decorative motion and use the still diagram.');
  await evaluate(client, 'document.querySelector("[data-motion-toggle]").click(); true');
  await delay(50);

  await navigate(client, origin + '/terraform/asis/index.html');
  const assessmentAtlas = await evaluate(
    client,
    '(function () {' +
      'return {' +
        'diagrams: Array.from(document.querySelectorAll(".diagram-trio .diagram-link")).map((link) => link.getAttribute("href").split("/").at(-1)),' +
        'states: Array.from(document.querySelectorAll(".diagram-trio .diagram-card__state")).map((state) => state.textContent.trim())' +
      '};' +
    '})()',
  );
  assert(
    JSON.stringify(assessmentAtlas.diagrams) === JSON.stringify([
      'JCAREER_AI_RUNTIME_ACTUAL.svg',
      'JCAREER_ASSESSMENT_EVIDENCE.svg',
      'JCAREER_ENTERPRISE_TOBE_TARGET.svg',
    ]),
    'Current runtime, assessment evidence, and TO-BE diagrams are not separated on the specification page.',
  );
  assert(
    JSON.stringify(assessmentAtlas.states) === JSON.stringify([
      'SOURCE IMPLEMENTED · APPLY UNVERIFIED',
      'PARTIAL SOURCE · EXECUTION PENDING',
      'PLANNED · NOT DEPLOYED',
    ]),
    'Assessment diagram states are missing or overstate deployment evidence.',
  );

  let checkedRoutes = 0;
  for (const route of EXPECTED_ROUTES) {
    await navigate(client, origin + '/' + route.href);
    const routeState = await evaluate(
      client,
      '(function () {' +
        'const activeButton = document.querySelector("[data-flow-button][aria-pressed=\\"true\\"]");' +
        'const activeLayers = Array.from(document.querySelectorAll("[data-flow-layer].is-active"))' +
          '.map((layer) => layer.dataset.flowLayer);' +
        'const detailLink = document.querySelector("#flow-detail-link");' +
        'const visibleMedia = document.querySelector("[data-flow-media]:not([hidden])");' +
        'const diagram = visibleMedia?.querySelector(".diagram-stage img");' +
        'const fullMap = document.querySelector("[data-full-map] img");' +
        'return {' +
          'activeButton: activeButton ? activeButton.dataset.flowButton : null,' +
          'activeLayers: activeLayers,' +
          'detailHref: detailLink ? detailLink.getAttribute("href") : null,' +
          'detailText: detailLink ? detailLink.textContent.trim() : "",' +
          'query: new URL(location.href).searchParams.get("flow"),' +
          'stepCount: document.querySelectorAll("#flow-steps > li").length,' +
          'markerCount: document.querySelectorAll("[data-flow-layer].is-active [data-flow-step]").length,' +
          'lineCount: document.querySelectorAll("[data-flow-layer].is-active .flow-line").length,' +
          'packetCount: document.querySelectorAll("[data-flow-layer].is-active .flow-packet animateMotion").length,' +
          'visibleMedia: visibleMedia?.dataset.flowMedia || null,' +
          'innerWidth: window.innerWidth,' +
          'scrollWidth: document.documentElement.scrollWidth,' +
          'diagramReady: Boolean(diagram && diagram.complete && diagram.naturalWidth > 0),' +
          'fullMapReady: Boolean(fullMap && fullMap.complete && fullMap.naturalWidth > 0)' +
        '};' +
      '})()',
    );
    const expectedQuery = route.flow === 'overview' ? null : route.flow;
    assert(routeState.activeButton === route.flow, 'Wrong selected button for route: ' + route.href);
    assert(JSON.stringify(routeState.activeLayers) === '["' + route.flow + '"]', 'Wrong active diagram layer for route: ' + route.href);
    assert(routeState.detailHref === route.detailHref && routeState.detailText.length > 0, 'Missing or wrong detail link for route: ' + route.href);
    assert(routeState.query === expectedQuery, 'URL flow state diverged for route: ' + route.href);
    assert(routeState.stepCount === route.steps, 'Wrong step count for route: ' + route.href);
    assert(routeState.markerCount === route.steps, 'Diagram markers diverge from written steps for route: ' + route.href);
    assert(routeState.lineCount > 0 && routeState.packetCount === routeState.lineCount, 'Selected route is missing an animated path or travelling dot: ' + route.href);
    assert(routeState.visibleMedia === route.media, 'Wrong visible diagram media for route: ' + route.href);
    assert(routeState.innerWidth === 390 && routeState.scrollWidth <= routeState.innerWidth, 'Architecture route overflows at 390px: ' + route.href);
    assert(routeState.diagramReady, 'Architecture diagram did not load for route: ' + route.href);
    assert(routeState.fullMapReady, 'Full infrastructure map did not load for route: ' + route.href);
    checkedRoutes += 1;
  }

  await navigate(client, origin + '/terraform/asis/architecture.html?flow=unknown');
  const invalidFlow = await evaluate(
    client,
    '(function () {' +
      'const active = document.querySelector("[data-flow-button][aria-pressed=\\"true\\"]");' +
      'const layers = Array.from(document.querySelectorAll("[data-flow-layer].is-active"))' +
        '.map((layer) => layer.dataset.flowLayer);' +
      'return {' +
        'active: active ? active.dataset.flowButton : null,' +
        'layers: layers,' +
        'query: new URL(location.href).searchParams.get("flow")' +
      '};' +
    '})()',
  );
  assert(
    invalidFlow.active === 'overview' &&
    invalidFlow.query === null &&
    JSON.stringify(invalidFlow.layers) === '["overview"]',
    'Invalid architecture flow did not fail closed to the overview.',
  );

  await navigate(client, origin + '/mlops/?stage=4');
  const deepLink = await inspectStage(client);
  assert(
    deepLink.active === '4' &&
    deepLink.query === '4' &&
    deepLink.itemCount === 7 &&
    JSON.stringify(deepLink.current) === '["4"]',
    'Valid MLOps deep link did not select stage 4: ' + JSON.stringify(deepLink),
  );

  const stageValues = ['all', '1', '2', '3', '4', '5', '6', '7'];
  for (const stage of stageValues) {
    const clicked = await evaluate(
      client,
      '(function () {' +
        'const button = document.querySelector("[data-stage-tab=\\"' + stage + '\\"]");' +
        'if (!button) return false;' +
        'button.click();' +
        'return true;' +
      '})()',
    );
    assert(clicked, 'Missing MLOps stage button: ' + stage);
    const state = await waitFor(
      async () => {
        const current = await inspectStage(client);
        return current.active === stage ? current : null;
      },
      'MLOps stage ' + stage + ' to become active',
    );
    if (stage === 'all') {
      assert(state.query === null && state.itemCount === 7 && state.current.length === 0, 'All-stage state did not show the seven-stage overview or clear the URL.');
      assert(state.progress === '1' && state.position === '100%' && state.readout === '전체 7단계', 'All-stage progress indicator is wrong.');
    } else {
      assert(state.query === stage && state.itemCount === 7 && JSON.stringify(state.current) === '["' + stage + '"]', 'MLOps stage state and URL diverged: ' + stage);
      assert(Math.abs(Number(state.progress) - Number(stage) / 7) < 0.0001 && state.readout === stage + ' / 7 단계', 'MLOps progress indicator diverged for stage ' + stage + '.');
    }
  }

  await navigate(client, origin + '/mlops/?stage=999');
  const invalid = await inspectStage(client);
  assert(invalid.active === 'all' && invalid.query === null && invalid.itemCount === 7 && invalid.current.length === 0, 'Invalid MLOps stage did not fail closed to the full overview.');

  await evaluate(
    client,
    'history.pushState({}, "", "?stage=2"); dispatchEvent(new PopStateEvent("popstate")); true',
  );
  await delay(30);
  const popState = await inspectStage(client);
  assert(popState.active === '2' && popState.query === '2' && JSON.stringify(popState.current) === '["2"]', 'Browser history state did not restore MLOps stage 2.');

  await navigate(client, origin + '/terraform/asis/architecture.html?flow=candidate');
  const animatedFlow = await evaluate(
    client,
    '(function () {' +
      'const line = document.querySelector("[data-flow-layer].is-active .flow-line");' +
      'return {' +
        'animation: line ? getComputedStyle(line).animationName : "",' +
        'toggleVisible: Boolean(document.querySelector("[data-motion-toggle]:not([hidden])"))' +
      '};' +
    '})()',
  );
  assert(animatedFlow.animation === 'flowMarch' && animatedFlow.toggleVisible, 'Architecture flow motion did not initialise.');
  await evaluate(client, 'document.querySelector("[data-motion-toggle]").click(); true');
  await delay(40);
  const stoppedFlow = await evaluate(client, 'getComputedStyle(document.querySelector("[data-flow-layer].is-active .flow-line")).animationName');
  assert(stoppedFlow === 'none', 'Architecture motion control did not stop the selected flow.');
  await evaluate(client, 'document.querySelector("[data-motion-toggle]").click(); true');

  return {
    landingRoutes: checkedRoutes,
    motionChecks: 8,
    pageViewportChecks,
    stageStates: stageValues.length,
    viewport: landing.innerWidth,
  };
}

async function main() {
  let server = null;
  let profileDirectory = null;
  let chromeProcess = null;
  let chromeExited = false;
  let client = null;

  try {
    server = await startStaticServer();
    console.log('public UI: local server ready');
    profileDirectory = await mkdtemp(path.join(os.tmpdir(), 'jcareer-ui-'));
    const chrome = await findChrome();
    chromeProcess = spawn(chrome, [
      '--headless=new',
      '--disable-gpu',
      '--disable-extensions',
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-debugging-port=0',
      '--remote-allow-origins=*',
      '--user-data-dir=' + profileDirectory,
      '--window-size=390,844',
      'about:blank',
    ], {
      stdio: 'ignore',
      windowsHide: true,
    });
    chromeProcess.once('exit', () => {
      chromeExited = true;
    });

    const portFile = path.join(profileDirectory, 'DevToolsActivePort');
    const debugPort = await waitFor(async () => {
      if (chromeExited) throw new Error('Chrome exited before opening DevTools.');
      try {
        const lines = (await readFile(portFile, 'utf8')).trim().split(/\r?\n/);
        return /^\d+$/.test(lines[0]) ? Number(lines[0]) : null;
      } catch {
        return null;
      }
    }, 'Chrome DevTools port');

    client = await createPageClient(debugPort);
    console.log('public UI: browser ready; testing 390px and 1440px');
    const result = await runChecks(client, server.origin);
    console.log('public UI: PASS');
    console.log(
      'landing routes: ' + result.landingRoutes + '/' + EXPECTED_ROUTES.length + '; MLOps stage states: ' +
      result.stageStates + '/8; invalid stage: fail-closed; viewport: ' +
      result.viewport + 'px; page/viewport checks: ' +
      result.pageViewportChecks + '/' + (PUBLIC_PAGES.length * 2) + '; motion checks: ' + result.motionChecks + '/8',
    );
  } finally {
    if (client) {
      await Promise.race([
        client.send('Browser.close').catch(() => null),
        delay(500),
      ]);
      client.close();
    }
    if (chromeProcess && !chromeExited) {
      chromeProcess.kill();
      await Promise.race([
        new Promise((resolve) => chromeProcess.once('exit', resolve)),
        delay(1200),
      ]);
      if (process.platform === 'win32' && !chromeExited) {
        spawnSync('taskkill', ['/PID', String(chromeProcess.pid), '/T', '/F'], {
          stdio: 'ignore',
          windowsHide: true,
        });
      }
    }
    await delay(300);
    console.log('public UI: browser stopped');
    if (server) await server.close();
    console.log('public UI: local server stopped');
    if (profileDirectory) await removeOwnedTempDirectory(profileDirectory, 'jcareer-ui-');
    console.log('public UI: temporary profile removed');
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error('::error::' + error.message);
    process.exit(1);
  });

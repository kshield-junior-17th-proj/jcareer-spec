(() => {
  'use strict';

  const storageKey = 'jcareer-reduce-motion';
  const root = document.documentElement;
  const systemPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const toggle = document.querySelector('[data-motion-toggle]');
  const listeners = [];
  let userPreference = null;
  let motionContext = null;

  try {
    const saved = window.localStorage.getItem(storageKey);
    if (saved === 'true' || saved === 'false') userPreference = saved === 'true';
  } catch {
    userPreference = null;
  }

  const isReduced = () => userPreference ?? systemPreference.matches;

  const transition = (update) => {
    if (isReduced() || typeof document.startViewTransition !== 'function') {
      update();
      return null;
    }
    return document.startViewTransition(update);
  };

  window.JCareerMotion = {
    get reduced() {
      return isReduced();
    },
    transition,
    subscribe(listener) {
      listeners.push(listener);
      return () => {
        const index = listeners.indexOf(listener);
        if (index >= 0) listeners.splice(index, 1);
      };
    },
  };

  const progress = document.createElement('div');
  progress.className = 'scroll-progress';
  progress.setAttribute('aria-hidden', 'true');
  progress.innerHTML = '<span></span>';
  document.body.prepend(progress);

  const syncAnimatedDiagrams = () => {
    document.querySelectorAll('[data-animated-diagram]').forEach((image) => {
      const nextSource = isReduced() ? image.dataset.stillSrc : image.dataset.motionSrc;
      if (nextSource && image.getAttribute('src') !== nextSource) image.setAttribute('src', nextSource);
    });
  };

  const clearMotion = () => {
    if (motionContext) {
      motionContext.revert();
      motionContext = null;
    }
  };

  const initialiseGsap = () => {
    clearMotion();
    if (isReduced() || !window.gsap || !window.ScrollTrigger) return;

    const { gsap, ScrollTrigger } = window;
    gsap.registerPlugin(ScrollTrigger);
    motionContext = gsap.context(() => {
      const progressBar = progress.querySelector('span');
      gsap.set(progressBar, { scaleX: 0, transformOrigin: 'left center' });
      ScrollTrigger.create({
        id: 'jcareer-scroll-progress',
        start: 0,
        end: 'max',
        onUpdate: (self) => gsap.set(progressBar, { scaleX: self.progress }),
      });

      const heroItems = document.querySelectorAll('.hero .eyebrow, .hero h1, .hero-copy, .hero-actions, .signal-marquee');
      if (heroItems.length) {
        gsap.from(heroItems, {
          y: 20,
          duration: 0.62,
          stagger: 0.09,
          ease: 'power3.out',
          clearProps: 'transform',
        });
      }

      gsap.utils.toArray('.section-head, .plain-card, .data-shelf, .spec-block, .readiness-item').forEach((item) => {
        gsap.from(item, {
          y: 46,
          opacity: 0,
          duration: 0.9,
          ease: 'power3.out',
          clearProps: 'transform,opacity',
          scrollTrigger: {
            trigger: item,
            start: 'top 88%',
            once: true,
          },
        });
      });

      const stackCards = gsap.utils.toArray('[data-card-stack] > .workstream');
      stackCards.forEach((card, index) => {
        gsap.fromTo(card, {
          y: 70,
          scale: 0.96,
          opacity: 0.58,
        }, {
          y: 0,
          scale: 1,
          opacity: 1,
          ease: 'none',
          scrollTrigger: {
            trigger: card,
            start: 'top 92%',
            end: 'top 48%',
            scrub: 0.65,
          },
        });
        if (index < stackCards.length - 1) {
          gsap.to(card, {
            scale: 0.965,
            opacity: 0.42,
            ease: 'none',
            scrollTrigger: {
              trigger: stackCards[index + 1],
              start: 'top 72%',
              end: 'top 38%',
              scrub: 0.65,
            },
          });
        }
      });

      gsap.utils.toArray('[data-scale-reveal]').forEach((media) => {
        gsap.fromTo(media, {
          scale: 0.84,
          opacity: 0.25,
        }, {
          scale: 1,
          opacity: 1,
          ease: 'none',
          scrollTrigger: {
            trigger: media,
            start: 'top 92%',
            end: 'center 58%',
            scrub: 0.7,
          },
        });
        gsap.to(media, {
          scale: 0.97,
          opacity: 0.3,
          ease: 'none',
          scrollTrigger: {
            trigger: media,
            start: 'bottom 28%',
            end: 'bottom top',
            scrub: 0.7,
          },
        });
      });

      gsap.utils.toArray('.flow-step-marker').forEach((marker, index) => {
        gsap.fromTo(marker, {
          scale: 0.88,
          opacity: 0.62,
          transformOrigin: 'center center',
        }, {
          scale: 1.12,
          opacity: 1,
          duration: 0.48,
          repeat: 1,
          yoyo: true,
          delay: index * 0.08,
          ease: 'power2.inOut',
        });
      });
    });
  };

  const setMotionState = ({ persist = false } = {}) => {
    const reduced = isReduced();
    root.dataset.motion = reduced ? 'reduced' : 'full';
    if (toggle) {
      toggle.hidden = false;
      toggle.setAttribute('aria-pressed', String(reduced));
      const label = '움직임 줄이기';
      const text = toggle.querySelector('[data-motion-label]');
      if (text) text.textContent = label;
      toggle.setAttribute('aria-label', '움직임 줄이기');
    }
    if (persist) {
      try {
        window.localStorage.setItem(storageKey, String(reduced));
      } catch {
        // 저장소를 사용할 수 없어도 현재 화면의 설정은 유지한다.
      }
    }
    syncAnimatedDiagrams();
    initialiseGsap();
    listeners.forEach((listener) => listener(reduced));
    window.dispatchEvent(new CustomEvent('jcareer:motionchange', { detail: { reduced } }));
  };

  if (toggle) {
    toggle.addEventListener('click', () => {
      userPreference = !isReduced();
      setMotionState({ persist: true });
    });
  }

  systemPreference.addEventListener('change', () => {
    if (userPreference === null) setMotionState();
  });

  document.addEventListener('visibilitychange', () => {
    root.classList.toggle('document-hidden', document.hidden);
  });

  document.querySelectorAll('[data-perspective-carousel]').forEach((carousel) => {
    const slides = Array.from(carousel.querySelectorAll('[data-perspective-slide]'));
    const previous = carousel.querySelector('[data-carousel-previous]');
    const next = carousel.querySelector('[data-carousel-next]');
    const count = carousel.querySelector('[data-carousel-count]');
    const perspectiveIndexes = new Map(
      slides.map((slide, slideIndex) => [slide.dataset.perspective, slideIndex]),
    );
    let index = 0;

    const render = (nextIndex, updateAddress = true) => {
      index = (nextIndex + slides.length) % slides.length;
      const updateSlides = () => {
        slides.forEach((slide, slideIndex) => {
          const active = slideIndex === index;
          slide.hidden = !active;
          slide.setAttribute('aria-hidden', String(!active));
        });
        if (count) count.textContent = `${index + 1} / ${slides.length}`;
      };
      if (updateAddress) transition(updateSlides);
      else updateSlides();
      if (updateAddress) {
        const address = new URL(window.location.href);
        const perspective = slides[index]?.dataset.perspective;
        if (index === 0) address.searchParams.delete('perspective');
        else address.searchParams.set('perspective', perspective);
        history.replaceState({ ...(history.state || {}), perspective }, '', address);
      }
    };

    previous?.addEventListener('click', () => render(index - 1));
    next?.addEventListener('click', () => render(index + 1));
    carousel.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        render(index - 1);
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        render(index + 1);
      }
    });
    window.addEventListener('popstate', () => {
      const perspective = new URLSearchParams(window.location.search).get('perspective');
      render(perspectiveIndexes.get(perspective) ?? 0, false);
    });
    const initialPerspective = new URLSearchParams(window.location.search).get('perspective');
    render(perspectiveIndexes.get(initialPerspective) ?? 0, false);
  });

  setMotionState();
})();

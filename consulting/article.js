(() => {
  const progress = document.querySelector("[data-reading-progress]");
  const article = document.querySelector("#article");

  const updateProgress = () => {
    if (!progress || !article) return;
    const start = article.offsetTop;
    const distance = Math.max(1, article.scrollHeight - window.innerHeight);
    const ratio = Math.min(1, Math.max(0, (window.scrollY - start) / distance));
    progress.style.transform = `scaleX(${ratio})`;
  };

  updateProgress();
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress, { passive: true });

  const links = [...document.querySelectorAll(".toc a[href^='#']")];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  if (!("IntersectionObserver" in window) || sections.length === 0) return;

  const setCurrent = (id) => {
    links.forEach((link) => {
      const current = link.getAttribute("href") === `#${id}`;
      link.classList.toggle("is-active", current);
      if (current) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setCurrent(visible[0].target.id);
    },
    { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.08] }
  );

  sections.forEach((section) => observer.observe(section));
})();

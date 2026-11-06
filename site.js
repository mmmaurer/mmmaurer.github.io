/*!
 * site.js — single source of truth for the site navigation and shared
 * behaviour (dark-mode toggle, BibTeX copy, news "show more", lightbox,
 * link prefetching).
 *
 * Include on every page, right before </body>:
 *     <script src="site.js" defer></script>
 * (use "../site.js" from the /blog/ subdirectory)
 *
 * The initial theme is applied by a tiny inline script in <head> so the
 * first paint already has the right colours; this file only wires up the
 * toggle and keeps the UI in sync.
 */

(() => {
  'use strict';

  // -- environment ---------------------------------------------------------
  const ROOT = location.pathname.includes('/blog/') ? '../' : '';
  const ON_HOME = !location.pathname.includes('/blog/') &&
    /(\/|index\.html)$/.test(location.pathname);
  const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SAVE_DATA = navigator.connection && navigator.connection.saveData;

  const homeLink = (hash) => (ON_HOME ? hash : `${ROOT}index.html${hash}`);
  const supportsSpeculation = () =>
    typeof HTMLScriptElement !== 'undefined' &&
    typeof HTMLScriptElement.supports === 'function' &&
    HTMLScriptElement.supports('speculationrules');

  // -- storage helpers (localStorage can throw in private mode) ------------
  const store = {
    get(key) {
      try { return localStorage.getItem(key); } catch { return null; }
    },
    set(key, value) {
      try { localStorage.setItem(key, value); } catch { /* ignore */ }
    },
  };

  // -- shared data ---------------------------------------------------------
  const NAV_LINKS = [
    { href: '#about', label: 'About', section: 'about' },
    { href: '#news', label: 'News', section: 'news' },
    { href: '#publications', label: 'Publications', section: 'publications' },
    { href: 'blog.html', label: 'Blog' },
    { href: '#contact', label: 'Contact', section: 'contact' },
  ];

  const SOCIAL = [
    { href: 'https://scholar.google.com/citations?user=gKqjcwEAAAAJ', icon: 'gsch.svg', alt: 'Google Scholar' },
    { href: 'https://github.com/mmmaurer', icon: 'github.svg', alt: 'GitHub' },
    { href: 'https://codeberg.org/mmmaurer', icon: 'codeberg.svg', alt: 'Codeberg' },
    { href: 'https://bsky.app/profile/mmmaurer.bsky.social', icon: 'bsky.svg', alt: 'Bluesky' },
    { href: 'https://www.linkedin.com/in/maximilian-martin-maurer-217591268/', icon: 'linkedin.svg', alt: 'LinkedIn' },
  ];

  // =======================================================================
  // Navigation (rendered once into the <nav id="site-nav"> placeholder)
  // =======================================================================
  const nav = document.getElementById('site-nav');
  if (!nav) return; // no nav placeholder on this page — nothing to do

  const navContent = document.createElement('div');
  navContent.className = 'nav-content';

  // -- left: wordmark --
  const brand = document.createElement('a');
  brand.className = 'brand';
  brand.href = `${ROOT}index.html`;
  brand.setAttribute('aria-label', 'Maximilian Maurer — home');
  brand.innerHTML =
    '<span class="brand-mark" aria-hidden="true">M</span>' +
    '<span class="brand-name">Maximilian Maurer</span>';

  // -- centre: section links --
  const ul = document.createElement('ul');
  ul.className = 'nav-list';
  const linkBySection = new Map();

  for (const n of NAV_LINKS) {
    const href = n.href.startsWith('#') ? homeLink(n.href) : `${ROOT}${n.href}`;
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.className = 'nav-link';
    a.href = href;
    a.textContent = n.label;
    if (n.section) {
      a.dataset.section = n.section;
      linkBySection.set(n.section, a);
    }
    li.appendChild(a);
    ul.appendChild(li);
  }

  // Mark the Blog tab on the blog pages.
  if (!ON_HOME) {
    const blogLink = [...ul.querySelectorAll('.nav-link')].find((a) => a.textContent === 'Blog');
    if (blogLink) {
      blogLink.classList.add('is-active');
      blogLink.setAttribute('aria-current', 'page');
    }
  }

  // -- right: social icons + theme toggle --
  const navRight = document.createElement('div');
  navRight.className = 'nav-right';

  const social = document.createElement('div');
  social.className = 'social-icons';
  for (const s of SOCIAL) {
    const a = document.createElement('a');
    a.className = 'social-link';
    a.href = s.href;
    a.title = s.alt;
    a.setAttribute('aria-label', s.alt);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.innerHTML = `<img src="${ROOT}assets/icons/${s.icon}" alt="" loading="lazy" decoding="async">`;
    social.appendChild(a);
  }

  const themeToggle = document.createElement('button');
  themeToggle.id = 'theme-toggle';
  themeToggle.className = 'theme-toggle';
  themeToggle.type = 'button';
  themeToggle.setAttribute('aria-pressed', 'false');
  themeToggle.innerHTML =
    '<span class="toggle-circle">' +
    `<img src="${ROOT}assets/icons/sun.svg" alt="" class="theme-icon theme-icon-sun">` +
    `<img src="${ROOT}assets/icons/moon.svg" alt="" class="theme-icon theme-icon-moon">` +
    '</span>';

  navRight.append(social, themeToggle);
  navContent.append(brand, ul, navRight);

  nav.replaceChildren(navContent);

  // =======================================================================
  // Theme (initial value comes from the inline <head> script)
  // =======================================================================
  const html = document.documentElement;
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');

  const applyTheme = (theme) => {
    html.setAttribute('data-theme', theme);
    const dark = theme === 'dark';
    themeToggle.setAttribute('aria-pressed', String(dark));
    themeToggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    themeToggle.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
    if (themeMeta) themeMeta.content = dark ? '#17161f' : '#fbfbfc';
  };

  const initialTheme = html.getAttribute('data-theme') ||
    (systemDark.matches ? 'dark' : 'light');
  applyTheme(initialTheme);

  themeToggle.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    const swap = () => {
      applyTheme(next);
      store.set('theme', next);
    };
    if (document.startViewTransition && !REDUCED_MOTION) {
      document.startViewTransition(swap);
    } else {
      swap();
    }
  });

  // Follow the OS only while the visitor has not picked a theme explicitly.
  systemDark.addEventListener('change', (event) => {
    if (!store.get('theme')) applyTheme(event.matches ? 'dark' : 'light');
  });

  // =======================================================================
  // Scroll spy — highlights the section currently in view (home page only)
  // =======================================================================
  if (ON_HOME && linkBySection.size) {
    const sections = [...document.querySelectorAll('.section[id]')];
    let frame = 0;

    const updateActive = () => {
      frame = 0;
      const offset = (document.querySelector('.sidebar')?.offsetHeight || 64) + 64;
      let current = '';
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= offset) {
          current = section.id;
        }
      }
      // Short final sections never reach the top of the viewport: once the
      // page is scrolled to the end, highlight the last one.
      const atBottom = window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 2;
      if (atBottom) current = sections[sections.length - 1].id;
      for (const [id, link] of linkBySection) {
        const active = id === current;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
    };

    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(updateActive);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    updateActive();
  }

  // =======================================================================
  // Speculative prefetching — makes same-site navigation feel instant.
  // Chrome prerenders via the inline speculationrules script; other
  // browsers get a hover prefetch here.
  // =======================================================================
  if (!SAVE_DATA && !supportsSpeculation()) {
    const prefetched = new Set();

    const prefetch = (anchor) => {
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin !== location.origin) return;
      if (!/\.html$|\/$/.test(url.pathname)) return;
      if (url.pathname === location.pathname) return;
      if (prefetched.has(url.href)) return;
      prefetched.add(url.href);
      const link = document.createElement('link');
      link.rel = 'prefetch';
      link.href = url.href;
      link.as = 'document';
      document.head.appendChild(link);
    };

    document.addEventListener('pointerover', (event) => {
      prefetch(event.target.closest?.('a[href]'));
    }, { passive: true });

    document.addEventListener('focusin', (event) => {
      prefetch(event.target.closest?.('a[href]'));
    });
  }

  // =======================================================================
  // BibTeX copy-to-clipboard (index.html only)
  // =======================================================================
  const copyText = async (text) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch { /* fall through to the legacy path */ }

    try {
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand('copy');
      area.remove();
      return ok;
    } catch {
      return false;
    }
  };

  document.addEventListener('click', async (event) => {
    const btn = event.target.closest('.bib-btn');
    if (!btn) return;

    const pre = document.getElementById(btn.getAttribute('data-bib-id'));
    if (!pre) return;

    const ok = await copyText(pre.textContent.trim());
    const label = btn.dataset.label || btn.textContent;
    btn.dataset.label = label;

    if (ok) {
      btn.textContent = 'Copied';
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = label;
        btn.disabled = false;
      }, 1600);
    } else {
      // Never leave the visitor empty-handed: reveal the block to copy by hand.
      pre.style.display = 'block';
      pre.scrollIntoView({ block: 'nearest', behavior: REDUCED_MOTION ? 'auto' : 'smooth' });
      const range = document.createRange();
      range.selectNodeContents(pre);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      btn.textContent = 'Press Ctrl/⌘ + C';
      setTimeout(() => { btn.textContent = label; }, 2600);
    }
  });

  // =======================================================================
  // News "show more" toggle (index.html only)
  // =======================================================================
  const newsList = document.getElementById('news-list');
  const newsToggle = document.getElementById('news-toggle');
  if (newsList && newsToggle) {
    const items = Array.from(newsList.querySelectorAll('.news-item'));
    const MAX_VISIBLE = 3;

    if (items.length > MAX_VISIBLE) {
      const hiddenItems = items.slice(MAX_VISIBLE);
      hiddenItems.forEach((item) => item.classList.add('hidden'));
      newsToggle.style.display = '';
      newsToggle.textContent = `More (${hiddenItems.length})`;
      newsToggle.addEventListener('click', () => {
        const expanded = newsToggle.getAttribute('aria-expanded') === 'true';
        hiddenItems.forEach((item) => item.classList.toggle('hidden', expanded));
        newsToggle.textContent = expanded ? `More (${hiddenItems.length})` : 'Less';
        newsToggle.setAttribute('aria-expanded', String(!expanded));
      });
    } else {
      newsToggle.style.display = 'none';
    }
  }

  // =======================================================================
  // Lightbox image viewer (blog post pages only)
  // =======================================================================
  const lightbox = document.getElementById('lightbox');
  if (lightbox) {
    const lightboxImg = lightbox.querySelector('img');
    let lastFocus = null;

    lightbox.setAttribute('aria-hidden', 'true');

    const close = () => {
      if (!lightbox.classList.contains('open')) return;
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
      lastFocus?.focus?.();
    };

    const open = (img, trigger) => {
      if (!img) return;
      lastFocus = trigger || null;
      lightboxImg.src = img.currentSrc || img.src;
      lightboxImg.alt = img.alt;
      lightbox.classList.add('open');
      lightbox.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      requestAnimationFrame(() => lightbox.focus({ preventScroll: true }));
    };

    for (const wrap of document.querySelectorAll('.blog-img-wrap')) {
      const img = wrap.querySelector('img');
      if (!img) continue;

      wrap.setAttribute('role', 'button');
      wrap.setAttribute('tabindex', '0');
      wrap.setAttribute('aria-label', `Zoom image: ${img.alt || 'blog illustration'}`);

      wrap.addEventListener('click', () => open(img, wrap));
      wrap.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open(img, wrap);
        }
      });
    }

    lightbox.addEventListener('click', (event) => {
      if (event.target === lightbox || event.target === lightboxImg) close();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') close();
    });
  }
})();

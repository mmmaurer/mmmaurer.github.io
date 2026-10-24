/*!
 * site.js — single source of truth for the site navigation and shared
 * behaviour (dark-mode toggle, BibTeX copy, news "show more").
 *
 * Include on every page, right after the <nav> placeholder:
 *     <script src="site.js" defer></script>
 * (use "../site.js" from the /blog/ subdirectory)
 *
 * Editing this file updates every page at once — the nav markup and all
 * the interactive behaviour that used to be copied inline across pages.
 */

(() => {
  'use strict';

  // -- resolve the URL root ----------------------------------------------
  // Pages served from / use '' ; pages served from /blog/ use '../'.
  const ROOT = location.pathname.includes('/blog/') ? '../' : '';

  const internal = (fragment) => `${ROOT}index.html${fragment}`;

  // -- shared data -------------------------------------------------------
  const NAV_LINKS = [
    { href: '#about',        label: 'About' },
    { href: '#news',         label: 'News' },
    { href: '#publications', label: 'Publications' },
    { href: 'blog.html',     label: 'Blog' },
    { href: '#contact',      label: 'Contact' },
  ];

  const SOCIAL = [
    { href: 'https://scholar.google.com/citations?user=gKqjcwEAAAAJ', icon: 'gsch.svg',   alt: 'Google Scholar' },
    { href: 'https://github.com/mmmaurer',                            icon: 'github.svg',  alt: 'GitHub' },
    { href: 'https://codeberg.org/mmmaurer',                           icon: 'codeberg.svg',alt: 'Codeberg' },
    { href: 'https://bsky.app/profile/mmmaurer.bsky.social',           icon: 'bsky.svg',    alt: 'Bluesky' },
    { href: 'https://www.linkedin.com/in/maximilian-martin-maurer-217591268/', icon: 'linkedin.svg', alt: 'LinkedIn' },
  ];

  // =====================================================================
  // Navigation (rendered once into the <nav id="site-nav"> placeholder)
  // =====================================================================
  const nav = document.getElementById('site-nav');
  if (!nav) return; // no nav placeholder on this page — nothing to do

  nav.innerHTML = '';
  nav.classList.add('sidebar');

  const navContent = document.createElement('div');
  navContent.className = 'nav-content';

  // -- left: nav links --
  const ul = document.createElement('ul');
  ul.className = 'nav-list';
  for (const n of NAV_LINKS) {
    const href = n.href.startsWith('#') ? internal(n.href) : `${ROOT}${n.href}`;
    const li = document.createElement('li');
    li.innerHTML = `<a href="${href}" class="nav-link">${n.label}</a>`;
    ul.appendChild(li);
  }

  // -- right: social icons + theme toggle --
  const navRight = document.createElement('div');
  navRight.className = 'nav-right';

  const social = document.createElement('div');
  social.className = 'social-icons';
  for (const s of SOCIAL) {
    social.insertAdjacentHTML(
      'beforeend',
      `<a href="${s.href}" class="social-link" title="${s.alt}">` +
      `<img src="${ROOT}assets/icons/${s.icon}" alt="${s.alt}"></a>`
    );
  }

  const themeToggle = document.createElement('button');
  themeToggle.id = 'theme-toggle';
  themeToggle.className = 'theme-toggle';
  themeToggle.type = 'button';
  themeToggle.setAttribute('title', 'Toggle dark mode');
  themeToggle.setAttribute('aria-label', 'Toggle dark mode');
  themeToggle.setAttribute('aria-pressed', 'false');
  themeToggle.innerHTML =
    '<span class="toggle-circle">' +
    `<img src="${ROOT}assets/icons/sun.svg" alt="Light mode" class="theme-icon theme-icon-sun">` +
    `<img src="${ROOT}assets/icons/moon.svg" alt="Dark mode" class="theme-icon theme-icon-moon">` +
    '</span>';

  navRight.append(social, themeToggle);
  navContent.append(ul, navRight);
  nav.appendChild(navContent);

  // =====================================================================
  // Dark-mode toggle (persists preference in localStorage)
  // =====================================================================
  const html = document.documentElement;
  const setTheme = (theme) => {
    html.setAttribute('data-theme', theme);
    themeToggle.setAttribute('aria-pressed', theme === 'dark');
  };

  setTheme(localStorage.getItem('theme') || 'light');

  themeToggle.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', next);
    setTheme(next);
  });

  // =====================================================================
  // BibTeX copy-to-clipboard (index.html only)
  // =====================================================================
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.bib-btn');
    if (!btn) return;
    const pre = document.getElementById(btn.getAttribute('data-bib-id'));
    if (!pre) return;
    try {
      await navigator.clipboard.writeText(pre.textContent.trim());
      const old = btn.textContent;
      btn.textContent = 'Copied!';
      btn.disabled = true;
      setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 1800);
    } catch {
      alert('Copy failed. You can manually select and copy the BibTeX.');
    }
  });

  // =====================================================================
  // News "show more" toggle (index.html only)
  // =====================================================================
  const newsList = document.getElementById('news-list');
  const newsToggle = document.getElementById('news-toggle');
  if (newsList && newsToggle) {
    const items = Array.from(newsList.querySelectorAll('.news-item'));
    const MAX_VISIBLE = 3;
    if (items.length > MAX_VISIBLE) {
      const hiddenItems = items.slice(MAX_VISIBLE);
      hiddenItems.forEach((i) => i.classList.add('hidden'));
      newsToggle.style.display = '';
      newsToggle.textContent = `More (${hiddenItems.length})`;
      newsToggle.addEventListener('click', () => {
        const expanded = newsToggle.getAttribute('aria-expanded') === 'true';
        hiddenItems.forEach((i) => i.classList.toggle('hidden', expanded));
        newsToggle.textContent = expanded ? `More (${hiddenItems.length})` : 'Less';
        newsToggle.setAttribute('aria-expanded', !expanded);
      });
    } else {
      newsToggle.style.display = 'none';
    }
  }

  // =====================================================================
  // Lightbox image viewer (blog post pages only)
  // =====================================================================
  const lightbox    = document.getElementById('lightbox');
  const lightboxImg = document.getElementById('lightbox-img');
  if (lightbox && lightboxImg) {
    document.querySelectorAll('.blog-img-wrap').forEach((wrap) => {
      wrap.addEventListener('click', () => {
        const img = wrap.querySelector('img');
        if (!img) return;
        lightboxImg.src = img.src;
        lightboxImg.alt = img.alt;
        lightbox.classList.add('open');
        document.body.style.overflow = 'hidden';
      });
    });

    lightbox.addEventListener('click', () => {
      lightbox.classList.remove('open');
      document.body.style.overflow = '';
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        lightbox.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  }
})();

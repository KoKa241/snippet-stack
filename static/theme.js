// Run before paint to avoid flashing the wrong theme.
(() => {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  try { preference = localStorage.getItem('theme') || 'system'; } catch (_) {}
  if (!['system', 'light', 'dark'].includes(preference)) preference = 'system';
  const apply = () => {
    const resolved = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#101216' : '#f7f8fa');
    document.querySelectorAll('.theme-control input').forEach(input => { input.checked = input.value === preference; });
  };
  window.snippetTheme = {
    apply,
    set(value) {
      if (!['system', 'light', 'dark'].includes(value)) return;
      preference = value;
      try { localStorage.setItem('theme', value); } catch (_) {}
      apply();
    },
  };
  media.addEventListener('change', () => { if (preference === 'system') apply(); });
  apply();
  document.addEventListener('DOMContentLoaded', apply);
})();

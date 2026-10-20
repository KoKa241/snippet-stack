(async () => {
  let language = 'en';
  try { language = localStorage.getItem('interfaceLanguage') || 'en'; } catch (_) {}
  if (language !== 'ru') return;
  try {
    const response = await fetch('/static/i18n/ru.json');
    if (!response.ok) return;
    const messages = await response.json();
    document.querySelectorAll('[data-i18n]').forEach(element => {
      if (messages[element.dataset.i18n]) element.textContent = messages[element.dataset.i18n];
    });
    document.title = messages['Offline · Snippet Stack'];
    document.documentElement.lang = language;
  } catch (_) { /* Keep the English fallback if the translation cache is unavailable. */ }
})();

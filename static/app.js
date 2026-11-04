// Keep the offline UI aligned with the last explicitly selected interface language.
try { localStorage.setItem('interfaceLanguage', document.documentElement.lang); } catch (_) {}
const toast = (message) => { const el = document.querySelector('.toast'); el.textContent = message; el.hidden = false; clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => el.hidden = true, 3000); };
document.querySelectorAll('.theme-control input').forEach(input => input.addEventListener('change', () => window.snippetTheme.set(input.value)));
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => { try { await navigator.clipboard.writeText(JSON.parse(document.getElementById(button.dataset.copy).textContent)); toast(button.dataset.success || document.querySelector('.toast').dataset.copySuccess); } catch (_) { toast(document.querySelector('.toast').dataset.copyError); } }));
document.querySelectorAll('.auto-submit').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
const dialog = document.getElementById('delete-dialog');
document.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', () => { document.getElementById('delete-form').action = button.dataset.delete; document.getElementById('delete-title').textContent = button.dataset.deleteTitle; dialog.showModal(); document.getElementById('cancel-delete').focus(); }));
document.getElementById('cancel-delete').addEventListener('click', () => dialog.close());
document.addEventListener('keydown', event => { const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName); if (event.key === '/' && !typing) { const search = document.getElementById('search'); if (search) { event.preventDefault(); search.focus(); } } if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !document.querySelector('dialog[open]')) { document.querySelector('.editor-form')?.requestSubmit(); } });
const editor = document.getElementById('id_code');
let releaseTab = false;
if (editor) editor.addEventListener('keydown', event => { if (event.key === 'Escape') { releaseTab = true; return; } if (event.key === 'Tab' && releaseTab) { releaseTab = false; return; } releaseTab = false; if (event.key === 'Tab' && !event.shiftKey) { event.preventDefault(); editor.setRangeText('    ', editor.selectionStart, editor.selectionEnd, 'end'); editor.dispatchEvent(new Event('input', {bubbles:true})); } });
let dirty = false;
const editorForm = document.querySelector('.editor-form');
editorForm?.addEventListener('input', () => dirty = true);
editorForm?.addEventListener('submit', () => dirty = false);
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

document.getElementById('new-key')?.focus();

// Preserve inline errors and provide a focused, linked summary after server validation.
document.querySelectorAll('form').forEach((form, formIndex) => {
  const errors = [...form.querySelectorAll('.errorlist li')];
  if (!errors.length) return;
  const summary = document.createElement('div');
  summary.className = 'error-summary'; summary.tabIndex = -1;
  const heading = document.createElement('h2');
  heading.id = `error-heading-${formIndex}`;
  heading.textContent = document.body.dataset.errorHeading;
  summary.setAttribute('aria-labelledby', heading.id);
  const list = document.createElement('ul');
  errors.forEach((error, index) => {
    const errorList = error.closest('.errorlist');
    const field = (errorList.id.endsWith('_error') ? document.getElementById(errorList.id.slice(0, -6)) : null) || error.closest('.form-field')?.querySelector('input:not([type=hidden]), select, textarea');
    const item = document.createElement('li');
    if (field) {
      error.id ||= `field-error-${formIndex}-${index}`;
      field.setAttribute('aria-invalid', 'true');
      field.setAttribute('aria-describedby', `${field.getAttribute('aria-describedby') || ''} ${error.id}`.trim());
      const link = document.createElement('a'); link.href = `#${field.id}`;
      const label = field.labels?.[0]?.textContent.trim().replace(/:$/, '');
      link.textContent = label ? `${label}: ${error.textContent}` : error.textContent;
      link.addEventListener('click', event => { event.preventDefault(); (field.id === 'id_tag_names' ? document.getElementById('tag-search') : field).focus(); });
      item.append(link);
    } else item.textContent = error.textContent;
    list.append(item);
  });
  summary.append(heading, list); form.prepend(summary);
});
document.querySelector('.error-summary')?.focus();
document.querySelectorAll('.nav-link.active, .tag-nav .selected, .settings-link.selected').forEach(link => link.setAttribute('aria-current', 'page'));

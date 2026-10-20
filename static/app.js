// Keep the offline UI aligned with the last explicitly selected interface language.
try { localStorage.setItem('interfaceLanguage', document.documentElement.lang); } catch (_) {}
const toast = (message) => { const el = document.querySelector('.toast'); el.textContent = message; el.hidden = false; clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => el.hidden = true, 3000); };
document.querySelectorAll('.theme-control input').forEach(input => input.addEventListener('change', () => window.snippetTheme.set(input.value)));
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => { try { await navigator.clipboard.writeText(JSON.parse(document.getElementById(button.dataset.copy).textContent)); toast(button.dataset.success || document.querySelector('.toast').dataset.copySuccess); } catch (_) { toast(document.querySelector('.toast').dataset.copyError); } }));
document.querySelectorAll('.auto-submit').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
const dialog = document.getElementById('delete-dialog');
document.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', () => { document.getElementById('delete-form').action = button.dataset.delete; dialog.showModal(); }));
document.getElementById('cancel-delete').addEventListener('click', () => dialog.close());
document.addEventListener('keydown', event => { const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName); if (event.key === '/' && !typing) { const search = document.getElementById('search'); if (search) { event.preventDefault(); search.focus(); } } if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { document.querySelector('.editor-form')?.requestSubmit(); } });
const editor = document.getElementById('id_code');
if (editor) editor.addEventListener('keydown', event => { if (event.key === 'Tab' && !event.shiftKey) { event.preventDefault(); editor.setRangeText('    ', editor.selectionStart, editor.selectionEnd, 'end'); editor.dispatchEvent(new Event('input', {bubbles:true})); } });
let dirty = false;
const editorForm = document.querySelector('.editor-form');
editorForm?.addEventListener('input', () => dirty = true);
editorForm?.addEventListener('submit', () => dirty = false);
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

document.getElementById('new-key')?.focus();

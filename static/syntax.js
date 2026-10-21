(() => {
  if (!window.Prism) return;
  const aliases = {shell: 'bash', html: 'markup', xml: 'markup', other: 'plain'};
  const languageFor = value => aliases[value] || value;
  // textContent is the only source: saved snippets are never interpreted as HTML.
  document.querySelectorAll('code[data-language]').forEach(code => {
    const language = languageFor(code.dataset.language);
    const grammar = Prism.languages[language];
    if (grammar) {
      try { code.innerHTML = Prism.highlight(code.textContent, grammar, language); } catch (_) {}
    }
  });
  const editor = document.getElementById('id_code');
  const language = document.getElementById('id_language');
  const layer = document.querySelector('.syntax-overlay');
  if (!editor || !language || !layer || !window.Worker) return;
  const wrapper = editor.closest('.syntax-editor');
  const output = layer.querySelector('code');
  const workerURL = document.querySelector('script[data-worker]').dataset.worker;
  let worker, debounce, timeout;
  const stop = () => { worker?.terminate(); worker = null; clearTimeout(timeout); };
  const syncScroll = () => { layer.scrollTop = editor.scrollTop; layer.scrollLeft = editor.scrollLeft; };
  function render() {
    stop();
    wrapper.classList.remove('syntax-ready');
    const selected = languageFor(language.value);
    if (!editor.value || selected === 'plain') return;
    try {
      worker = new Worker(workerURL);
      worker.onmessage = ({data}) => {
        if (typeof data.html === 'string') {
          output.innerHTML = data.html + '\n';
          wrapper.classList.add('syntax-ready');
          syncScroll();
        }
        stop();
      };
      worker.onerror = stop;
      timeout = setTimeout(stop, 1500);
      worker.postMessage({code: editor.value, language: selected});
    } catch (_) { stop(); }
  }
  editor.addEventListener('input', () => {
    stop(); clearTimeout(debounce);
    wrapper.classList.remove('syntax-ready');
    debounce = setTimeout(render, 100);
  });
  editor.addEventListener('scroll', syncScroll);
  language.addEventListener('change', () => { clearTimeout(debounce); render(); });
  window.addEventListener('pagehide', stop);
  render();
})();

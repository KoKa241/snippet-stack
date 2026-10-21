// Progressive enhancement: the ordinary comma-separated field still works without JS.
(() => {
  const widget = document.getElementById('tag-widget');
  if (!widget) return;
  const original = document.getElementById('id_tag_names');
  const input = document.getElementById('tag-search');
  const list = document.getElementById('tag-options');
  const chips = document.getElementById('selected-tags');
  const feedback = document.getElementById('tag-feedback');
  const tags = JSON.parse(document.getElementById('available-tags').textContent);
  let selected = [...new Set(original.value.split(',').map(name => name.trim().toLowerCase()).filter(Boolean))];
  let options = [], active = -1, busy = false, editing = null, returnFocus = null;
  const modal = document.getElementById('tag-color-dialog');
  const picker = document.getElementById('tag-color-picker');
  const hex = document.getElementById('tag-color-hex');
  const preview = document.getElementById('tag-color-preview');
  const colorError = document.getElementById('tag-color-error');
  const palette = document.querySelector('.color-palette');
  const csrf = document.querySelector('.editor-form [name=csrfmiddlewaretoken]').value;
  const validColor = value => /^#[0-9a-f]{6}$/i.test(value);
  function paint(element, color) {
    if (!validColor(color)) return;
    element.style.backgroundColor = color;
    const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    element.style.color = rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 > .179 ? '#000000' : '#ffffff';
  }
  async function post(url, data) {
    const response = await fetch(url, {method: 'POST', headers: {'X-CSRFToken': csrf}, body: new URLSearchParams(data), credentials: 'same-origin'});
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw Error(widget.dataset.error);
    const result = await response.json();
    if (!response.ok) throw Error(result.error || widget.dataset.error);
    return result;
  }
  function sync() {
    original.value = selected.join(', ');
    original.dispatchEvent(new Event('input', {bubbles: true}));
  }
  function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; }
  function highlight(index) {
    active = index;
    [...list.children].forEach((el, i) => el.setAttribute('aria-selected', String(i === active)));
    if (active >= 0) { input.setAttribute('aria-activedescendant', list.children[active].id); list.children[active].scrollIntoView({block: 'nearest'}); }
    else input.removeAttribute('aria-activedescendant');
  }
  function show() {
    const query = input.value.trim().toLowerCase();
    options = tags.filter(tag => !selected.includes(tag.name) && tag.name.includes(query));
    if (query && !tags.some(tag => tag.name === query) && !selected.includes(query)) options.unshift({name: query, create: true});
    list.replaceChildren();
    options.forEach((tag, index) => {
      const el = document.createElement('li'); el.id = `tag-option-${index}`; el.role = 'option'; el.setAttribute('aria-selected', 'false');
      if (tag.color) { const dot = document.createElement('span'); dot.className = 'tag-dot'; paint(dot, tag.color); el.append(dot); }
      el.append(document.createTextNode(tag.create ? `${widget.dataset.add} “${tag.name}”` : tag.name));
      el.addEventListener('mousedown', event => event.preventDefault());
      el.addEventListener('click', () => choose(tag)); list.append(el);
    });
    feedback.textContent = selected.length >= 10 ? widget.dataset.limit : options.length ? '' : widget.dataset.empty;
    list.hidden = options.length === 0 || selected.length >= 10;
    input.setAttribute('aria-expanded', String(!list.hidden)); highlight(-1);
  }
  function render() {
    chips.replaceChildren();
    selected.forEach(name => {
      const tag = tags.find(item => item.name === name);
      const chip = document.createElement('span'); chip.className = 'tag-chip'; if (tag) paint(chip, tag.color);
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'tag-name'; edit.textContent = name; edit.setAttribute('aria-label', `${widget.dataset.edit}: ${name}`);
      edit.addEventListener('click', async () => {
        if (busy) return;
        try {
          busy = true;
          const saved = tag || await post(widget.dataset.createUrl, {name});
          if (!tag) tags.push(saved);
          editing = saved; returnFocus = edit; preview.textContent = name; setColor(saved.color); colorError.textContent = ''; close(); modal.showModal();
        } catch (error) { feedback.textContent = error.message; } finally { busy = false; }
      });
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'tag-remove'; remove.textContent = '×'; remove.setAttribute('aria-label', `${widget.dataset.remove}: ${name}`);
      remove.addEventListener('click', () => { selected = selected.filter(value => value !== name); sync(); render(); input.focus(); show(); });
      chip.append(edit, remove); chips.append(chip);
    });
  }
  async function choose(tag) {
    if (busy || selected.length >= 10) return;
    busy = true; input.setAttribute('aria-busy', 'true');
    try {
      if (tag.create) { tag = await post(widget.dataset.createUrl, {name: tag.name}); if (!tags.some(item => item.id === tag.id)) tags.push(tag); }
      if (!selected.includes(tag.name)) selected.push(tag.name);
      input.value = ''; sync(); render(); close(); feedback.textContent = ''; input.focus();
    } catch (error) { feedback.textContent = error.message; } finally { busy = false; input.removeAttribute('aria-busy'); }
  }
  function setColor(value) {
    if (!validColor(value)) return;
    picker.value = value; hex.value = value; paint(preview, value);
    [...palette.children].forEach(button => button.setAttribute('aria-pressed', String(button.dataset.color === value.toLowerCase())));
  }
  ['#c4b5fd', '#a7f3d0', '#bae6fd', '#fde68a', '#fecdd3', '#fed7aa', '#c7d2fe', '#99f6e4'].forEach(color => {
    const button = document.createElement('button'); button.type = 'button'; button.dataset.color = color; button.setAttribute('aria-label', color); paint(button, color); button.addEventListener('click', () => setColor(color)); palette.append(button);
  });
  picker.addEventListener('input', () => setColor(picker.value));
  hex.addEventListener('input', () => { if (validColor(hex.value)) setColor(hex.value); });
  document.getElementById('cancel-tag-color').addEventListener('click', () => modal.close());
  modal.addEventListener('close', () => {
    const restored = [...chips.querySelectorAll('.tag-name')].find(button => button.textContent === editing?.name);
    if (restored) restored.focus(); else if (returnFocus?.isConnected) returnFocus.focus(); else input.focus();
  });
  document.getElementById('tag-color-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!validColor(hex.value)) { colorError.textContent = colorError.dataset.invalid; hex.focus(); return; }
    const button = event.submitter;
    if (button?.disabled) return;
    if (button) button.disabled = true;
    try {
      const saved = await post(`/tags/${editing.id}/color/`, {color: hex.value});
      Object.assign(editing, saved); document.querySelectorAll(`.tag-color-${saved.id}`).forEach(el => paint(el, saved.color)); render(); modal.close();
    } catch (error) { colorError.textContent = error.message; } finally { if (button) button.disabled = false; }
  });
  input.addEventListener('focus', show); input.addEventListener('click', show); input.addEventListener('input', show);
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); if (list.hidden) show();
      if (!list.hidden) highlight((active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length);
    } else if (event.key === 'Enter') { event.preventDefault(); if (!list.hidden && options.length) choose(options[active < 0 ? 0 : active]); }
  });
  widget.addEventListener('focusout', event => { if (!widget.contains(event.relatedTarget)) close(); });
  document.addEventListener('pointerdown', event => { if (!widget.contains(event.target)) close(); });
  original.type = 'hidden'; original.required = false;
  document.getElementById('tags-label').htmlFor = 'tag-search';
  widget.querySelector('.tag-enhancement').hidden = false; chips.hidden = false; render();
})();

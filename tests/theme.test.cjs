const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/theme.js', 'utf8');
function boot(saved, dark = false, blocked = false) {
  const listeners = {};
  const media = {matches: dark, addEventListener: (name, callback) => { listeners[name] = callback; }};
  const root = {dataset: {}};
  const inputs = ['system', 'light', 'dark'].map(value => ({value}));
  const storage = {value: saved, getItem() { if (blocked) throw Error('blocked'); return this.value; }, setItem(key, value) { if (blocked) throw Error('blocked'); this.value = value; }};
  const window = {matchMedia: () => media};
  vm.runInNewContext(source, {window, localStorage: storage, document: {
    documentElement: root, querySelector: () => null, querySelectorAll: () => inputs, addEventListener: () => {},
  }});
  return {window, media, root, inputs, storage, change: value => { media.matches = value; listeners.change(); }};
}
test('default system follows appearance changes in both directions', () => {
  const app = boot(null);
  assert.equal(app.root.dataset.theme, 'light');
  assert.equal(app.root.dataset.themePreference, 'system');
  app.change(true); assert.equal(app.root.dataset.theme, 'dark');
  app.change(false); assert.equal(app.root.dataset.theme, 'light');
});
test('explicit selection persists and ignores system changes until system is selected', () => {
  const app = boot('dark');
  app.change(false); assert.equal(app.root.dataset.theme, 'dark');
  app.window.snippetTheme.set('light');
  app.change(true); assert.equal(app.root.dataset.theme, 'light');
  assert.equal(app.storage.value, 'light');
  assert.equal(app.inputs.find(input => input.checked).value, 'light');
  app.window.snippetTheme.set('system');
  assert.equal(app.root.dataset.theme, 'dark');
  assert.equal(boot(app.storage.value, false).root.dataset.theme, 'light');
});
test('invalid or unavailable storage safely defaults to system', () => {
  assert.equal(boot('invalid', true).root.dataset.theme, 'dark');
  const app = boot(null, false, true);
  app.window.snippetTheme.set('dark');
  app.window.snippetTheme.set('invalid');
  assert.equal(app.root.dataset.theme, 'dark');
});

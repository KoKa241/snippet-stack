const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('static/vendor/prism.js', 'utf8'), context);
const prism = context.Prism;
const languages = ['python', 'bash', 'powershell', 'javascript', 'typescript', 'jsx', 'tsx', 'c', 'cpp', 'csharp', 'java', 'go', 'rust', 'php', 'ruby', 'swift', 'kotlin', 'dart', 'lua', 'r', 'sql', 'markup', 'css', 'scss', 'json', 'yaml', 'toml', 'markdown', 'docker', 'nginx'];
for (const language of languages) {
  assert.ok(prism.languages[language], `Missing grammar: ${language}`);
  const source = '<script>alert("x")</script>\n  value = "<&>";\n';
  const html = prism.highlight(source, prism.languages[language], language);
  assert.ok(!html.includes('<script>'), `${language} must escape HTML`);
  const restored = html.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&amp;/g, '&');
  assert.equal(restored, source, `${language} must preserve source text`);
}
for (const [language, source] of [['bash', 'echo "$HOME" | grep test'], ['powershell', 'Get-Process | Where-Object { $_.CPU -gt 10 }'], ['python', 'def greet():\n    return "hello"']]) {
  assert.match(prism.highlight(source, prism.languages[language], language), /class="token /);
}
console.log('Syntax tests passed: 30 grammars, HTML escaping, exact source preservation, shell tokens.');

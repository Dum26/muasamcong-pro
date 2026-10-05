const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('web/search-engine.js', 'utf8');
const cutoff = source.indexOf("  node('localSearchButton').addEventListener");
assert.ok(cutoff > 0, 'search UI event boundary exists');
const elements = new Map();
function field(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', type: 'text', checked: false, hidden: false,
    replaceChildren() {}, append() {}, addEventListener() {}, options: [{value: ''}],
  });
  return elements.get(id);
}
function element(tag) {
  return {tag, children: [], textContent: '', append(...children) {this.children.push(...children);}};
}
const context = vm.createContext({
  document: {getElementById: field, createElement: element,
    createTextNode: text => ({tag: '#text', textContent: text})},
  URLSearchParams, Date, Number, String, Object, encodeURIComponent,
});
vm.runInContext(source.slice(0, cutoff) +
  '\n  globalThis.searchTest={params,appendHighlighted};\n})();', context);

field('keyword').value = 'benh vien';
field('localSearchKind').value = 'tender';
field('localSearchSort').value = 'published';
field('localSearchSize').value = '50';
field('localSearchFrom').value = '2026-09-01';
field('localSearchPriceMin').value = '500000000';
field('localSearchResults').type = 'checkbox';
field('localSearchResults').checked = true;
const params = context.searchTest.params();
assert.equal(params.get('q'), 'benh vien');
assert.equal(params.get('kind'), 'tender');
assert.equal(params.get('from'), '2026-09-01');
assert.equal(params.get('price_min'), '500000000');
assert.equal(params.get('results'), '1');

const cell = element('td');
context.searchTest.appendHighlighted(cell, 'Bệnh viện <img src=x onerror=alert(1)>', 'benh vien');
assert.equal(cell.children[1].tag, 'mark');
assert.equal(cell.children[1].textContent, 'Bệnh viện');
assert.equal(cell.children[2].textContent, ' <img src=x onerror=alert(1)>');
assert.equal(cell.children.some(child => child.tag === 'img'), false);
console.log('PASS: local search URL filters and safe Vietnamese highlighting');

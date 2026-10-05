const assert=require('node:assert/strict');
const fs=require('node:fs');

const html=fs.readFileSync('web/admin.html','utf8');
const source=fs.readFileSync('web/admin-ui.js','utf8');

assert.match(html,/Data Sync Engine/);
assert.match(html,/id="adminSyncStart"/);
assert.match(html,/id="adminSyncProcess"/);
assert.match(html,/id="adminSyncToggle"/);
assert.match(html,/id="adminSyncRuns"/);
assert.ok(source.includes("fetch('/api/data-sync')"));
assert.ok(source.includes("'/api/data-sync/runs'"));
assert.ok(source.includes("'/api/data-sync/process'"));
assert.ok(source.includes('/api/data-sync/sources/egp-public/'));
assert.match(source,/safe\(run\.mode\)/);
assert.match(source,/safe\(run\.status\)/);
assert.doesNotMatch(source,/JOB_SECRET|X-Job-Secret/);
console.log('PASS: Data Sync admin controls, safe rendering and API routes');

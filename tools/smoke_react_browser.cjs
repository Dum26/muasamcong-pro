/* Optional local browser smoke: Node 24, project .venv and installed Chrome. */
const { spawn, spawnSync } = require('node:child_process');
const { mkdtempSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve, sep } = require('node:path');
const net = require('node:net');

const root = resolve(__dirname, '..');
const chrome = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const python = join(root, '.venv', 'Scripts', 'python.exe');
const temp = mkdtempSync(join(tmpdir(), 'msc-react-smoke-'));
const pause = ms => new Promise(done => setTimeout(done, ms));
async function freePort() {
  const server = net.createServer();
  await new Promise(done => server.listen(0, '127.0.0.1', done));
  const port = server.address().port;
  await new Promise(done => server.close(done));
  return port;
}
async function until(fn, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { const result = await fn().catch(() => null); if (result) return result; await pause(200); }
  throw new Error('Timed out waiting for browser/server');
}
async function main() {
  const appPort = await freePort(), debugPort = await freePort();
  const base = `http://127.0.0.1:${appPort}`;
  const app = spawn(python, ['web_app.py'], { cwd: root, windowsHide: true,
    env: { ...process.env, PORT: String(appPort), MUASAMCONG_NO_BROWSER: '1', REACT_FRONTEND_ENABLED: '1', DATABASE_URL: `sqlite:///${join(temp, 'smoke.db').replaceAll('\\', '/')}`, ENV: 'development' }, stdio: 'ignore' });
  let browser, socket;
  try {
    await until(async () => (await fetch(base + '/api/health')).ok);
    const account = await fetch(base + '/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'react-browser@example.test', password: 'react-browser-password-123' }) });
    if (!account.ok) throw new Error('Registration failed: ' + await account.text());
    const auth = account.headers.getSetCookie().find(cookie => cookie.startsWith('msc_auth='));
    if (!auth) throw new Error('Auth cookie missing');
    const seeded = await fetch(base + '/api/watchlist', { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: auth.split(';', 1)[0] },
      body: JSON.stringify({ action: 'add', code: 'IB2600000001', name: 'Smoke tender', investor: 'Smoke hospital', deadline: '30/09/2026 09:00' }) });
    if (!seeded.ok) throw new Error('Watchlist seed failed: ' + await seeded.text());
    browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${join(temp, 'chrome')}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
    const target = await until(async () => { const items = await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json(); return items.find(item => item.type === 'page'); });
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((done, fail) => { socket.addEventListener('open', done, { once: true }); socket.addEventListener('error', fail, { once: true }); });
    let nextId = 0; const pending = new Map(); const exceptions = []; const assetFailures = [];
    socket.addEventListener('message', event => { const item = JSON.parse(event.data);
      if (item.method === 'Runtime.exceptionThrown') exceptions.push(item.params.exceptionDetails.text);
      if (item.method === 'Network.responseReceived' && item.params.response.status >= 400 && item.params.response.url.includes('/assets/'))
        assetFailures.push(`${item.params.response.status} ${item.params.response.url}`);
      if (item.id && pending.has(item.id)) { const { done, fail } = pending.get(item.id); pending.delete(item.id); item.error ? fail(new Error(item.error.message)) : done(item.result); }
    });
    function send(method, params = {}) { return new Promise((done, fail) => { const id = ++nextId; pending.set(id, { done, fail }); socket.send(JSON.stringify({ id, method, params })); }); }
    async function evaluate(expression) { const result = await send('Runtime.evaluate', { expression, returnByValue: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result?.value; }
    await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
    await send('Network.setCookie', { name: 'msc_auth', value: auth.split(';', 1)[0].slice('msc_auth='.length), url: base });
    const pages = [
      ['/app', 'Dữ liệu đấu thầu, trong tầm nhìn.'], ['/app/search', 'Tra cứu dữ liệu đấu thầu'],
      ['/app/archive', 'Tìm trong dữ liệu đã thu thập'], ['/app/codes', 'Tra cứu mã TBMT và KHLCNT'],
      ['/app/compare', 'Đặt các gói thầu cạnh nhau'], ['/app/reports', 'Báo cáo và dashboard'],
      ['/app/documents', 'Trung tâm tài liệu'], ['/app/automations', 'Quy tắc đấu thầu'],
      ['/app/analytics', 'Phân tích dữ liệu đấu thầu'], ['/app/ai', 'Phân tích tài liệu đấu thầu'],
      ['/app/settings', 'Bàn làm việc của tôi'], ['/app/downloads', 'File đã xuất'],
      ['/app/notifications', 'Cập nhật của bạn'], ['/app/history', 'Truy vấn gần đây'],
      ['/app/watchlist', 'Gói thầu của tôi'],
    ];
    for (const [path, heading] of pages) {
      await send('Page.navigate', { url: base + path });
      await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === heading);
      const failure = await evaluate('document.querySelector(".center-state h1")?.textContent || document.querySelector("[role=alert]")?.textContent || ""');
      if (failure) throw new Error(`${path}: ${failure}`);
      process.stdout.write(`PASS ${path}\n`);
    }
    await send('Page.navigate', { url: base + '/app' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Dữ liệu đấu thầu, trong tầm nhìn.');
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'k', code: 'KeyK', modifiers: 2 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'k', code: 'KeyK', modifiers: 2 });
    await until(async () => await evaluate('!!document.querySelector("[role=dialog] [data-slot=command-input]")'));
    await send('Input.insertText', { text: 'Tải xuống' });
    await until(async () => await evaluate('document.querySelector("[cmdk-item][data-selected=true]")?.textContent?.includes("Tải xuống")'));
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter' });
    await until(async () => (await evaluate('location.pathname')) === '/app/downloads');
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'k', code: 'KeyK', modifiers: 2 });
    await until(async () => await evaluate('!!document.querySelector("[role=dialog]")'));
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
    await until(async () => await evaluate('!document.querySelector("[role=dialog]")'));
    process.stdout.write('PASS Ctrl+K keyboard navigation/Escape\n');
    await send('Page.navigate', { url: base + '/app/settings' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Bàn làm việc của tôi');
    await evaluate('document.querySelector("[role=switch]").click()');
    await until(async () => await evaluate('!document.documentElement.classList.contains("dark")'));
    await evaluate('document.querySelector("[role=switch]").click()');
    await until(async () => await evaluate('document.documentElement.classList.contains("dark")'));
    await evaluate(`[...document.querySelectorAll('[role=tab]')].find(node => node.textContent === 'Tải xuống').focus()`);
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter' });
    await until(async () => await evaluate('document.body.innerText.includes("Thư mục tải xuống")'));
    process.stdout.write('PASS settings tabs/dark mode\n');
    await send('Page.navigate', { url: base + '/app/watchlist' });
    await until(async () => await evaluate('document.body.innerText.includes("Smoke tender")'));
    await evaluate('document.querySelector("#note-IB2600000001").focus()');
    await send('Input.insertText', { text: 'Smoke note' });
    await evaluate('document.querySelector("#note-IB2600000001").blur()');
    await until(async () => { const response = await fetch(base + '/api/watchlist', { headers: { Cookie: auth.split(';', 1)[0] } });
      return (await response.json()).items?.[0]?.note === 'Smoke note'; });
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Bỏ theo dõi').click()`);
    await until(async () => await evaluate('!!document.querySelector("[role=alertdialog]")'));
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
    await until(async () => await evaluate('!document.querySelector("[role=alertdialog]")'));
    process.stdout.write('PASS watchlist note/confirmation\n');
    await send('Page.navigate', { url: base + '/app/search' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Tra cứu dữ liệu đấu thầu');
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Lưu bộ lọc').click()`);
    await until(async () => await evaluate('!!document.querySelector("[role=dialog] input[aria-label=\'Tên bộ lọc\']")'));
    await evaluate('document.querySelector("[role=dialog] input").focus()');
    await send('Input.insertText', { text: 'Smoke filter' });
    await evaluate(`[...document.querySelectorAll('[role=dialog] button')].find(node => node.textContent === 'Lưu').click()`);
    await until(async () => await evaluate('document.body.innerText.includes("Bộ lọc đã lưu (1)")')).catch(async error => {
      throw new Error(`Preset save: ${error.message}; ${await evaluate('JSON.stringify({value:document.querySelector("[role=dialog] input")?.value, disabled:[...document.querySelectorAll("[role=dialog] button")].find(node => node.textContent === "Lưu")?.disabled, alert:document.querySelector("[role=alert]")?.textContent, dialog:document.querySelector("[role=dialog]")?.textContent})')}`);
    });
    process.stdout.write('PASS search preset dialog/save\n');
    await send('Page.navigate', { url: base + '/app/codes' });
    await until(async () => await evaluate('!!document.querySelector("[role=checkbox]")'));
    const beforeCheck = await evaluate('document.querySelector("[role=checkbox]").getAttribute("aria-checked")');
    await evaluate('document.querySelector("[role=checkbox]").click()');
    await until(async () => (await evaluate('document.querySelector("[role=checkbox]").getAttribute("aria-checked")')) !== beforeCheck);
    process.stdout.write('PASS code list checkbox\n');
    await send('Page.navigate', { url: base + '/app/reports' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Báo cáo và dashboard');
    await until(async () => await evaluate('document.querySelector("button") && document.body.innerText.includes("Thiết kế báo cáo")'));
    await evaluate(`(() => { const input = [...document.querySelectorAll('label')].find(node => node.textContent.includes('Tên báo cáo')).querySelector('input');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Smoke report');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      [...document.querySelectorAll('button')].find(node => node.textContent === 'Xem trước').click(); })()`);
    await until(async () => await evaluate('document.body.innerText.includes("Xem trước · 0 dòng")'));
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Lưu báo cáo').click()`);
    await until(async () => await evaluate('document.body.innerText.includes("Đã lưu báo cáo.")'));
    process.stdout.write('PASS report preview/save\n');
    await evaluate(`[...document.querySelectorAll('[role=tab]')].find(node => node.textContent === 'Dashboard của tôi').click()`);
    await evaluate(`(() => { const input = [...document.querySelectorAll('label')].find(node => node.textContent.includes('Tên') && node.querySelector('input') && !node.textContent.includes('Bản đã lưu')).querySelector('input');
      const widget = [...document.querySelectorAll('label input')].find(node => node.closest('label').textContent === 'Tên' && node.value === '');
      const target = widget || input;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(target, 'Smoke widget');
      target.dispatchEvent(new Event('input', { bubbles: true }));
      [...document.querySelectorAll('button')].find(node => node.textContent.startsWith('Thêm widget')).click(); })()`);
    await until(async () => await evaluate('document.body.innerText.includes("Thêm widget (1/12)")'));
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Lưu dashboard').click()`);
    await until(async () => await evaluate('document.body.innerText.includes("Đã lưu dashboard.")'));
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Cập nhật dữ liệu').click()`);
    await until(async () => await evaluate('document.body.innerText.includes("Chưa có dữ liệu cho widget.")'));
    process.stdout.write('PASS dashboard save/run\n');
    await send('Page.navigate', { url: base + '/app/automations' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Quy tắc đấu thầu');
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Tạo quy tắc').click()`);
    await until(async () => await evaluate('!!document.querySelector("form.automation-editor input[required]")'));
    await evaluate(`(() => { const input = document.querySelector('form.automation-editor input[required]');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Smoke rule');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      [...document.querySelectorAll('button')].find(node => node.textContent.startsWith('Xem trước')).click(); })()`);
    await until(async () => await evaluate('document.body.innerText.includes("Bản xem trước")'));
    await evaluate(`[...document.querySelectorAll('button')].find(node => node.textContent === 'Lưu quy tắc').click()`);
    await until(async () => await evaluate('document.body.innerText.includes("Đã lưu quy tắc.")'));
    process.stdout.write('PASS automation preview/save\n');
    await until(async () => await evaluate('[...document.querySelectorAll(".list-item")].some(node => node.textContent.includes("Smoke rule"))'));
    await evaluate(`[...document.querySelectorAll('.list-item')].find(node => node.textContent.includes('Smoke rule')).querySelector('button:last-child').click()`);
    await until(async () => await evaluate('document.querySelector("[role=alertdialog]")?.textContent?.includes("Xóa quy tắc Smoke rule?")'));
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
    await until(async () => await evaluate('!document.querySelector("[role=alertdialog]")'));
    if (!await evaluate('document.body.innerText.includes("Smoke rule")')) throw new Error('Cancel removed automation rule');
    process.stdout.write('PASS shared destructive confirmation\n');
    await send('Page.navigate', { url: base + '/app/documents' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Trung tâm tài liệu');
    await evaluate(`(() => { const input = document.querySelector('input[aria-label="Chọn tài liệu"]');
      const transfer = new DataTransfer(); transfer.items.add(new File(['Gói thầu thử nghiệm.'], 'smoke.txt', { type: 'text/plain' }));
      input.files = transfer.files; input.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await until(async () => await evaluate('location.pathname.startsWith("/app/documents/upload/")'));
    process.stdout.write('PASS document upload\n');
    await send('Page.navigate', { url: base + '/app/admin' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Không có quyền truy cập');
    process.stdout.write('PASS admin guard\n');
    const promoted = spawnSync(python, ['tools/promote_admin.py', 'react-browser@example.test'], {
      cwd: root, windowsHide: true, encoding: 'utf8',
      env: { ...process.env, DATABASE_URL: `sqlite:///${join(temp, 'smoke.db').replaceAll('\\', '/')}`, ENV: 'development' },
    });
    if (promoted.status !== 0) throw new Error('Admin promotion failed: ' + promoted.stderr);
    await send('Page.navigate', { url: base + '/app/admin' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Vận hành hệ thống');
    for (const tab of ['Đồng bộ', 'Chất lượng dữ liệu', 'Hiệu năng']) {
      await evaluate(`[...document.querySelectorAll('[role=tab]')].find(node => node.textContent === ${JSON.stringify(tab)}).click()`);
      await until(async () => await evaluate(`document.body.innerText.includes(${JSON.stringify(tab === 'Đồng bộ' ? 'Nguồn dữ liệu' : tab === 'Hiệu năng' ? 'Hiệu năng instance' : 'Chất lượng dữ liệu')})`));
      const alert = await evaluate('document.querySelector("[role=alert]")?.textContent || ""');
      if (alert) throw new Error(`Admin ${tab}: ${alert}`);
    }
    process.stdout.write('PASS admin panels\n');
    await send('Page.navigate', { url: base + '/login' });
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Chào mừng trở lại.');
    if (process.env.MSC_UI_SCREENSHOT_LOGIN) {
      const destination = resolve(root, process.env.MSC_UI_SCREENSHOT_LOGIN);
      if (!destination.startsWith(root + sep)) throw new Error('Screenshot path must stay within project');
      await send('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
      await pause(750);
      const screenshot = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(destination, Buffer.from(screenshot.data, 'base64'));
    }
    await evaluate(`(() => { const values = ['react-browser@example.test', 'react-browser-password-123'];
      document.querySelectorAll('form input').forEach((input, index) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, values[index]);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }); document.querySelector('form button').click(); })()`);
    await until(async () => (await evaluate('location.pathname')) === '/app');
    process.stdout.write('PASS login\n');
    await until(async () => await evaluate('!!document.querySelector("button[title=\'Đăng xuất\']")'));
    for (const width of [1280, 1366, 1440, 1920]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height: width === 1280 ? 720 : width === 1366 ? 768 : width === 1440 ? 900 : 1080, deviceScaleFactor: 1, mobile: false });
      for (const [path, heading] of pages) {
        await send('Page.navigate', { url: base + path });
        await until(async () => (await evaluate('document.querySelector(".page h1")?.textContent')) === heading);
        if (await evaluate('document.documentElement.scrollWidth > innerWidth + 2'))
          throw new Error(`${path} overflows ${width}px viewport`);
        const unnamed = await evaluate('[...document.querySelectorAll("button:not([role])")].find(button => button.getClientRects().length && !button.textContent.trim() && !button.getAttribute("aria-label") && !button.getAttribute("title"))?.outerHTML || ""');
        if (unnamed) throw new Error(`${path} has an unnamed icon button: ${unnamed}`);
        if (width === 1366 && path === '/app') {
          await until(async () => await evaluate('!!document.querySelector(".dashboard-metrics")'));
          if (!await evaluate('(() => { const e = document.querySelector(".skip-link"); const probe = document.createElement("span"); probe.style.color = "var(--primary-foreground)"; document.body.append(probe); const matches = getComputedStyle(e).color === getComputedStyle(probe).color; probe.remove(); return matches })()'))
            throw new Error('Skip link text color is overridden');
          await evaluate('document.querySelector(".sidebar-toggle").click()');
          await until(async () => await evaluate('document.querySelector(".app-shell").classList.contains("collapsed")'));
          if (!await evaluate('getComputedStyle(document.querySelector(".brand-icon")).display !== "none"'))
            throw new Error('Collapsed sidebar hides the brand mark');
          await evaluate('document.querySelector(".sidebar-toggle").click()');
          await until(async () => await evaluate('!document.querySelector(".app-shell").classList.contains("collapsed")'));
          if (!await evaluate('(() => { const e = [...document.querySelectorAll("a")].find(a => a.textContent.includes("Tra cứu gói thầu")); const probe = document.createElement("span"); probe.style.color = "var(--primary-foreground)"; document.body.append(probe); const matches = getComputedStyle(e).color === getComputedStyle(probe).color; probe.remove(); return matches })()'))
            throw new Error('Primary action text color is overridden');
          if (process.env.MSC_UI_SCREENSHOT) {
            const destination = resolve(root, process.env.MSC_UI_SCREENSHOT);
            if (!destination.startsWith(root + sep)) throw new Error('Screenshot path must stay within project');
            const screenshot = await send('Page.captureScreenshot', { format: 'png' });
            writeFileSync(destination, Buffer.from(screenshot.data, 'base64'));
          }
        }
      }
    }
    process.stdout.write('PASS 15 routes at 1280/1366/1440/1920\n');
    await evaluate('localStorage.setItem("msc_theme", "light")');
    await send('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
    for (const [path, heading] of pages) {
      await send('Page.navigate', { url: base + path });
      await until(async () => (await evaluate('document.querySelector(".page h1")?.textContent')) === heading);
      if (await evaluate('document.documentElement.classList.contains("dark") || document.documentElement.scrollWidth > innerWidth + 2'))
        throw new Error(`${path} light theme or width failed`);
      if (path === '/app' && process.env.MSC_UI_SCREENSHOT_LIGHT) {
        const destination = resolve(root, process.env.MSC_UI_SCREENSHOT_LIGHT);
        if (!destination.startsWith(root + sep)) throw new Error('Screenshot path must stay within project');
        const screenshot = await send('Page.captureScreenshot', { format: 'png' });
        writeFileSync(destination, Buffer.from(screenshot.data, 'base64'));
      }
    }
    process.stdout.write('PASS 15 routes in light theme\n');
    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await until(async () => await evaluate('getComputedStyle(document.querySelector(".sidebar")).display === "none"'));
    await evaluate('document.querySelector(".mobile-nav-trigger").click()');
    await until(async () => await evaluate('!!document.querySelector("[data-slot=sheet-content]")'));
    await evaluate('document.querySelector("[data-slot=sheet-content] a[href=\'/app/search\']").click()');
    await until(async () => (await evaluate('location.pathname')) === '/app/search');
    await until(async () => await evaluate('!document.querySelector("[data-slot=sheet-content]")'));
    if (await evaluate('document.documentElement.scrollWidth > innerWidth + 2')) throw new Error('Mobile page overflows viewport');
    process.stdout.write('PASS mobile navigation sheet\n');
    await send('Emulation.clearDeviceMetricsOverride');
    await evaluate('document.querySelector("button[title=\'Đăng xuất\']").click()');
    await until(async () => (await evaluate('location.pathname')) === '/login');
    process.stdout.write('PASS logout\n');
    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    if (await evaluate('document.documentElement.scrollWidth > innerWidth + 2')) throw new Error('Mobile login overflows viewport');
    if (process.env.MSC_UI_SCREENSHOT_LOGIN_MOBILE) {
      const destination = resolve(root, process.env.MSC_UI_SCREENSHOT_LOGIN_MOBILE);
      if (!destination.startsWith(root + sep)) throw new Error('Screenshot path must stay within project');
      const screenshot = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(destination, Buffer.from(screenshot.data, 'base64'));
    }
    await evaluate('document.querySelector("a[href=\'/register\']").click()');
    await until(async () => (await evaluate('document.querySelector("h1")?.textContent')) === 'Bắt đầu làm việc.');
    if (await evaluate('document.documentElement.scrollWidth > innerWidth + 2')) throw new Error('Mobile registration overflows viewport');
    process.stdout.write('PASS mobile login/register\n');
    if (exceptions.length) throw new Error('JavaScript exceptions: ' + exceptions.join('; '));
    if (assetFailures.length) throw new Error('Asset responses failed: ' + assetFailures.join('; '));
  } finally {
    socket?.close(); browser?.kill(); app.kill();
    await pause(400);
    if (resolve(temp).startsWith(resolve(tmpdir()) + sep) && temp.includes('msc-react-smoke-'))
      rmSync(temp, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

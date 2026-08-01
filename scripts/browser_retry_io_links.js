#!/usr/bin/env node
/* Retry blocked HTML-like URLs in headed Chromium and save rendered HTML. */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('playwright');

const root = process.argv[2] || '/work/tmp/io-links-full-download';
const source = JSON.parse(fs.readFileSync(path.join(root, 'manifest-latest.json'), 'utf8'));
const outputDir = path.join(root, 'browser-content');
const manifestPath = path.join(root, 'browser-manifest.jsonl');
fs.mkdirSync(outputDir, { recursive: true });

const prior = new Map();
if (fs.existsSync(manifestPath)) {
  for (const line of fs.readFileSync(manifestPath, 'utf8').split(/\r?\n/)) {
    if (!line) continue;
    try { const item = JSON.parse(line); prior.set(item.url, item); } catch (_) {}
  }
}
const documentPattern = /\.(pdf|ps|dvi|docx?|pptx?|zip|gz)(?:[?#]|$)/i;
let queue = Object.values(source)
  .filter(item => item.state === 'blocked' && !documentPattern.test(item.url))
  .filter(item => !prior.has(item.url));
const limit = Number.parseInt(process.env.BROWSER_LIMIT || '0', 10);
if (limit > 0) queue = queue.slice(0, limit);
const blockedPatterns = [
  'cf-chl-', 'cloudflare ray id', 'just a moment...',
  'attention required! | cloudflare', 'verify you are human',
  'checking your browser', 'enable javascript and cookies to continue',
  'captcha', 'access denied |', 'request blocked', 'too many requests'
];

function stableName(url) {
  return crypto.createHash('sha256').update(url).digest('hex').slice(0, 20) + '_rendered.html';
}

async function visit(context, url) {
  const page = await context.newPage();
  const started = Date.now();
  try {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 18000 });
    await page.waitForTimeout(2500);
    const html = await page.content();
    const lowered = html.toLowerCase();
    const status = response ? response.status() : null;
    const challenged = blockedPatterns.some(pattern => lowered.includes(pattern));
    const state = challenged || [401, 403, 407, 409, 423, 429, 451, 503].includes(status)
      ? 'blocked' : (html.length >= 512 && status && status < 400 ? 'ok' : 'error');
    const filename = stableName(url);
    fs.writeFileSync(path.join(outputDir, filename), html, 'utf8');
    return {
      url, state, reason: challenged ? 'challenge_content' : (state === 'ok' ? '' : `http_${status}`),
      status, content_type: 'text/html; rendered=1', size: Buffer.byteLength(html),
      sha256: crypto.createHash('sha256').update(html).digest('hex'),
      file: `browser-content/${filename}`, final_url: page.url(), method: 'chromium',
      elapsed_ms: Date.now() - started
    };
  } catch (error) {
    return { url, state: 'error', reason: error.name || 'browser_error', method: 'chromium', elapsed_ms: Date.now() - started };
  } finally {
    await page.close();
  }
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    locale: 'en-US', timezoneId: 'America/Los_Angeles', viewport: { width: 1440, height: 900 },
    colorScheme: 'light', deviceScaleFactor: 1
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    window.chrome = window.chrome || { runtime: {} };
  });
  const stream = fs.createWriteStream(manifestPath, { flags: 'a' });
  let cursor = 0;
  let completed = 0;
  const workers = Array.from({ length: 20 }, async () => {
    while (cursor < queue.length) {
      const item = queue[cursor++];
      const result = await visit(context, item.url);
      stream.write(JSON.stringify(result) + '\n');
      prior.set(result.url, result);
      completed++;
      if (completed % 50 === 0) console.log(JSON.stringify({ completed, remaining: queue.length - completed }));
    }
  });
  await Promise.all(workers);
  stream.end();
  await new Promise(resolve => stream.on('finish', resolve));
  await browser.close();
  const counts = {};
  for (const item of prior.values()) counts[item.state] = (counts[item.state] || 0) + 1;
  fs.writeFileSync(path.join(root, 'browser-manifest-latest.json'), JSON.stringify(Object.fromEntries(prior), null, 2) + '\n');
  console.log(JSON.stringify({ queued_now: queue.length, total: prior.size, ...counts }));
})().catch(error => { console.error(error); process.exit(1); });

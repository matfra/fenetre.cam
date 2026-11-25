// Requires Playwright and its Chromium browser: node --test tests/test_list_page.cjs
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');

const publicDir = path.join(__dirname, '../src/fenetre/static/public');
const leafletBase = 'https://unpkg.com/leaflet@1.9.4/dist/';
const clusterBase = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/';
const assets = new Map();
let browser;
let server;
let baseUrl;

before(async () => {
    browser = await chromium.launch({ headless: true });
    const request = await browser.newContext();
    try {
        for (const url of [
            `${leafletBase}leaflet.js`, `${leafletBase}leaflet.css`,
            `${clusterBase}leaflet.markercluster.js`,
            `${clusterBase}MarkerCluster.css`, `${clusterBase}MarkerCluster.Default.css`,
        ]) {
            const response = await request.request.get(url);
            assert.equal(response.status(), 200, url);
            assets.set(url, await response.body());
        }
    } finally {
        await request.close();
    }
    server = http.createServer(async (req, res) => {
        const pathname = new URL(req.url, 'http://localhost').pathname;
        let data;
        if (pathname === '/cameras.json') {
            data = {
                global: {
                    deployment_name: 'Test deployment',
                    ui: {
                        show_map_by_default: true,
                        linked_deployments: [{ base_url: `${baseUrl}/remote` }],
                    },
                },
                cameras: [
                    { title: 'local-point', lat: 37, lon: -122, dynamic_metadata: 'metadata.json' },
                    { title: 'local-circle', lat: 38, lon: -121, map_radius_m: 1000, dynamic_metadata: 'metadata.json' },
                ],
            };
        } else if (pathname === '/remote/cameras.json') {
            data = {
                cameras: [
                    { title: 'remote-point', lat: 36, lon: -122 },
                    { title: 'remote-circle', lat: 39, lon: -122, map_radius_m: 1000 },
                ],
            };
        } else if (pathname === '/metadata.json') {
            data = { last_picture_url: '2026-11-25T12-00-00.jpg', iso: 100 };
        }
        if (data) {
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify(data));
            return;
        }
        const filename = pathname === '/' ? 'list.html' : pathname.slice(1);
        if (['list.html', 'list.js', 'list.css'].includes(filename)) {
            res.setHeader('Content-Type', filename.endsWith('.js') ? 'text/javascript' : filename.endsWith('.css') ? 'text/css' : 'text/html');
            res.end(await readFile(path.join(publicDir, filename)));
        } else {
            res.setHeader('Content-Type', 'image/svg+xml');
            res.end('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="blue"/></svg>');
        }
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
});

async function openPage(t, options = {}) {
    const context = await browser.newContext();
    t.after(() => context.close());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://**/*', async route => {
        const url = route.request().url();
        if (url === options.block) return route.abort();
        if (url === options.hang) return;
        if (assets.has(url)) {
            let body = assets.get(url);
            if (url === `${clusterBase}leaflet.markercluster.js`) {
                if (options.incompatible) body = 'window.unrelatedPlugin = {};';
                if (options.initializationError) body = Buffer.concat([
                    body, Buffer.from('\nL.markerClusterGroup = () => { throw new Error("broken plugin initialization"); };'),
                ]);
            }
            return route.fulfill({ body, contentType: url.endsWith('.js') ? 'text/javascript' : 'text/css' });
        }
        return route.abort();
    });
    await page.goto(`${baseUrl}/?camera=local-point`, { waitUntil: 'domcontentloaded' });
    return { page, errors };
}

async function assertCameraListWorks(page) {
    await page.waitForFunction(() => document.querySelectorAll('.camera-item').length === 4);
    await page.waitForFunction(() => document.querySelector('.filename').textContent.includes('2026-11-25'));
    assert.equal(await page.locator('h1').textContent(), 'Test deployment cameras');
    assert.equal(await page.locator('.camera-details.active').count(), 1);
    assert.match(await page.locator('.link-fullscreen').first().getAttribute('href'), /fullscreen.html\?camera=local-point/);
    assert.match(await page.locator('.remote-open-link').first().getAttribute('href'), /remote\/list.html\?camera=remote-point/);
    const darkBefore = await page.locator('body').evaluate(el => el.classList.contains('dark-mode'));
    await page.click('#theme-toggle');
    assert.equal(await page.locator('body').evaluate(el => el.classList.contains('dark-mode')), !darkBefore);
    await page.locator('.camera-header').first().click();
    assert.equal(await page.locator('.camera-details.active').count(), 0);
    await page.locator('.camera-header').first().click();
    assert.equal(await page.locator('.camera-details.active').count(), 1);
}

async function assertMapUnavailable(page) {
    await page.waitForFunction(() => document.querySelector('#map-toggle').title === 'Map unavailable');
    assert.equal(await page.locator('#map-toggle').isDisabled(), true);
    assert.equal(await page.locator('#map').evaluate(el => getComputedStyle(el).visibility), 'hidden');
    assert.equal(await page.evaluate(() => document.querySelector('#list-panel').offsetWidth >= document.body.clientWidth - 2), true);
}

test('healthy map and camera list still work', async t => {
    const { page, errors } = await openPage(t);
    await page.waitForFunction(() => document.querySelector('#map-toggle').classList.contains('map-open'));
    await assertCameraListWorks(page);
    assert.ok(await page.locator('.leaflet-marker-icon').count() > 0);
    assert.ok(await page.locator('.leaflet-overlay-pane path').count() > 0);
    await page.click('#map-toggle');
    assert.equal(await page.locator('#map').evaluate(el => el.style.visibility), 'hidden');
    await page.click('#map-toggle');
    assert.equal(await page.locator('#map').evaluate(el => el.style.visibility), 'visible');
    assert.deepEqual(errors, []);
});

for (const [name, options] of [
    ['Leaflet download fails', { block: `${leafletBase}leaflet.js` }],
    ['markercluster download fails', { block: `${clusterBase}leaflet.markercluster.js` }],
    ['map stylesheet fails', { block: `${leafletBase}leaflet.css` }],
    ['markercluster API is incompatible', { incompatible: true }],
    ['map initialization throws', { initializationError: true }],
]) {
    test(`camera list survives when ${name}`, async t => {
        const { page, errors } = await openPage(t, options);
        await assertMapUnavailable(page);
        await assertCameraListWorks(page);
        await page.evaluate(() => updateAllCameras());
        await assertCameraListWorks(page);
        assert.deepEqual(errors, []);
    });
}

test('stalled dependencies do not delay cameras and eventually disable the map', async t => {
    const { page, errors } = await openPage(t, { hang: `${leafletBase}leaflet.js` });
    await assertCameraListWorks(page);
    assert.equal(await page.locator('#map-toggle').getAttribute('title'), 'Map loading');
    await assertMapUnavailable(page);
    await assertCameraListWorks(page);
    assert.deepEqual(errors, []);
});

test('a map error during refresh preserves cameras and future refreshes', async t => {
    const { page, errors } = await openPage(t);
    await page.waitForFunction(() => document.querySelector('#map-toggle').classList.contains('map-open'));
    await page.evaluate(() => {
        markerCluster.clearLayers = () => { throw new Error('broken map refresh'); };
        updateAllCameras();
    });
    await assertMapUnavailable(page);
    await assertCameraListWorks(page);
    await page.evaluate(() => updateAllCameras());
    await assertCameraListWorks(page);
    assert.deepEqual(errors, []);
});

test('dark theme uses OpenStreetMap without a CARTO key and CARTO with a key', async t => {
    const { page, errors } = await openPage(t);
    await page.waitForFunction(() => document.querySelector('#map-toggle').classList.contains('map-open'));
    await page.click('#theme-toggle');
    assert.equal(await page.locator('body').evaluate(el => el.classList.contains('dark-mode')), true);
    assert.equal(await page.evaluate(() => map.hasLayer(lightTileLayer)), true);
    assert.equal(await page.evaluate(() => map.hasLayer(darkTileLayer)), false);
    await page.evaluate(() => configureCartoApiKey('test-key'));
    assert.equal(await page.evaluate(() => map.hasLayer(darkTileLayer)), true);
    assert.match(await page.evaluate(() => darkTileLayer._url), /\?key=test-key$/);
    await page.evaluate(() => configureCartoApiKey(undefined));
    assert.equal(await page.evaluate(() => map.hasLayer(lightTileLayer)), true);
    assert.equal(await page.evaluate(() => map.hasLayer(darkTileLayer)), false);
    assert.deepEqual(errors, []);
});

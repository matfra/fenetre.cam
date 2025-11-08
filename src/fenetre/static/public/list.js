const themeToggle = document.getElementById('theme-toggle');
const body = document.body;
const mapToggleButton = document.getElementById('map-toggle');

function syncThemeToggleIcon() {
    themeToggle.classList.toggle('dark-mode-active', body.classList.contains('dark-mode'));
}

// Apply theme based on system preference or stored value
const prefersDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
const storedTheme = localStorage.getItem('theme');

if (storedTheme === 'dark' || (storedTheme === null && prefersDarkMode)) {
    body.classList.add('dark-mode');
}
syncThemeToggleIcon();

// Toggle theme on button click
themeToggle.addEventListener('click', () => {
    body.classList.toggle('dark-mode');
    const theme = body.classList.contains('dark-mode') ? 'dark' : 'light';
    localStorage.setItem('theme', theme);
    syncThemeToggleIcon();
    applyMapTheme(theme === 'dark');
});

const cameraListElement = document.getElementById('camera-list');

// --- Map Initialization ---
const mapPanel = document.getElementById('map-panel');
const listPanel = document.getElementById('list-panel');
const mapElement = document.getElementById('map');

const lightTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    minZoom: 0,
    attribution: '&copy; OpenStreetMap contributors'
});

const darkTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 18,
    minZoom: 0,
    subdomains: 'abcd',
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
});

const initialTileLayer = body.classList.contains('dark-mode') ? darkTileLayer : lightTileLayer;
const map = L.map('map', {
    layers: [initialTileLayer]
}).setView([0, 0], 2);
let activeTileLayer = initialTileLayer;
let latestMarkerBounds = null;
const markerBoundsFitOptions = { padding: [50, 50] };
let mapVisible = false;
let mapVisibilityInitialized = false;
let remoteFetchGeneration = 0;

function applyMapTheme(isDark) {
    const desiredLayer = isDark ? darkTileLayer : lightTileLayer;
    if (desiredLayer === activeTileLayer) {
        return;
    }
    map.addLayer(desiredLayer);
    map.removeLayer(activeTileLayer);
    activeTileLayer = desiredLayer;
}

var markerCluster = L.markerClusterGroup();
var circleLayerGroup = L.layerGroup();
map.addLayer(markerCluster);
map.addLayer(circleLayerGroup);

var cameraMarkers = {}; // To store references to map markers or circles

function getLayerBounds(layer) {
    if (!layer) {
        return null;
    }
    if (typeof layer.getBounds === 'function') {
        return layer.getBounds();
    }
    if (typeof layer.getLatLng === 'function') {
        const latLng = layer.getLatLng();
        return L.latLngBounds(latLng, latLng);
    }
    return null;
}

function extendBoundsWithLayer(layer) {
    const layerBounds = getLayerBounds(layer);
    if (!layerBounds) {
        return;
    }
    if (latestMarkerBounds) {
        latestMarkerBounds.extend(layerBounds.getSouthWest());
        latestMarkerBounds.extend(layerBounds.getNorthEast());
    } else {
        latestMarkerBounds = layerBounds;
    }
}

function focusCameraLayer(layer) {
    if (!layer) {
        return;
    }
    if (layer instanceof L.Marker && markerCluster.hasLayer(layer)) {
        markerCluster.zoomToShowLayer(layer, () => layer.openPopup());
        return;
    }
    const bounds = getLayerBounds(layer);
    if (bounds) {
        map.fitBounds(bounds, markerBoundsFitOptions);
        if (typeof layer.openPopup === 'function') {
            layer.openPopup();
        }
    }
}

function addCameraLayer(lat, lon, radiusMeters, popupHtml) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return null;
    }
    const coords = L.latLng(lat, lon);
    const radius = Number.isFinite(radiusMeters) ? radiusMeters : 0;
    let layer;
    if (radius > 0) {
        layer = L.circle(coords, {
            radius,
            color: '#3388ff',
            fillColor: '#3388ff',
            fillOpacity: 0.15,
            weight: 1,
        });
    } else {
        layer = L.marker(coords);
    }
    if (popupHtml) {
        layer.bindPopup(popupHtml);
    }
    if (layer instanceof L.Marker) {
        markerCluster.addLayer(layer);
    } else {
        circleLayerGroup.addLayer(layer);
    }
    extendBoundsWithLayer(layer);
    return layer;
}

function slugify(value, fallback) {
    const base = (value || '').toString().toLowerCase().trim();
    const slug = base.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    return slug || fallback;
}

function joinUrl(base, path) {
    if (!path) {
        return base;
    }
    if (/^https?:\/\//i.test(path)) {
        return path;
    }
    const baseNormalized = base.replace(/\/+$/, '');
    const pathNormalized = path.replace(/^\/+/, '');
    return `${baseNormalized}/${pathNormalized}`;
}

function buildAbsoluteUrl(base, maybeRelative) {
    if (!maybeRelative) {
        return null;
    }
    if (/^https?:\/\//i.test(maybeRelative)) {
        return maybeRelative;
    }
    if (maybeRelative.startsWith('//')) {
        return `${window.location.protocol}${maybeRelative}`;
    }
    return joinUrl(base, maybeRelative);
}

function clearRemoteCameraItems() {
    document.querySelectorAll('.camera-item.remote-camera').forEach((item) => {
        item.remove();
    });
}

function buildRemoteCameraUrl(baseUrl, remoteCameraUrl, cameraSlug) {
    const defaultListUrl = joinUrl(baseUrl, 'list.html');
    const absoluteRemoteUrl = buildAbsoluteUrl(baseUrl, remoteCameraUrl);
    if (!absoluteRemoteUrl) {
        return `${defaultListUrl}?camera=${encodeURIComponent(cameraSlug)}`;
    }

    try {
        const url = new URL(absoluteRemoteUrl);
        url.searchParams.set('camera', cameraSlug);
        return url.toString();
    } catch (e) {
        return `${defaultListUrl}?camera=${encodeURIComponent(cameraSlug)}`;
    }
}

function openMap() {
    if (mapVisible) {
        return;
    }
    mapVisible = true;
    mapPanel.style.width = '50%';
    listPanel.style.width = '50%';
    mapElement.style.visibility = 'visible';
    mapToggleButton.classList.add('map-open');
    setTimeout(() => {
        map.invalidateSize();
        if (latestMarkerBounds) {
            map.fitBounds(latestMarkerBounds, markerBoundsFitOptions);
        }
    }, 500);
}

function closeMap() {
    if (!mapVisible) {
        return;
    }
    mapVisible = false;
    mapPanel.style.width = '0';
    listPanel.style.width = '100%';
    mapElement.style.visibility = 'hidden';
    mapToggleButton.classList.remove('map-open');
}

// --- Map Toggle Functionality ---
mapToggleButton.addEventListener('click', () => {
    if (mapVisible) {
        closeMap();
    } else {
        openMap();
    }
});

function createPopupContent(camera) {
    return `<b>${camera.title}</b>`;
}

function parseTimestampFromFilename(filename) {
    try {
        const match = filename.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})/);
        if (!match) return null;
        const year = parseInt(match[1], 10);
        const month = parseInt(match[2], 10) - 1;
        const day = parseInt(match[3], 10);
        const hour = parseInt(match[4], 10);
        const minute = parseInt(match[5], 10);
        const second = parseInt(match[6], 10);
        const date = new Date(year, month, day, hour, minute, second);
        return isNaN(date.getTime()) ? null : date;
    } catch (e) {
        console.error("Error parsing timestamp from:", filename, e);
        return null;
    }
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function createCameraListItem(camera) {
    const listItem = document.createElement('li');
    listItem.className = 'camera-item';
    listItem.dataset.title = camera.title;
    listItem.dataset.markerId = `camera-${camera.title.replace(/\s+/g, '-')}`;

    listItem.innerHTML = `
        <div class="camera-header">
            <img src="" alt="${camera.title} thumbnail">
            <div class="camera-info">
                <div class="camera-name">${camera.title}</div>
                <div class="last-picture-time">Loading...</div>
            </div>
            <div class="status"></div>
        </div>
        <div class="camera-details">
            <a class="fullscreen-image-link" href="#" target="_blank">
                <img src="" alt="Full image for ${camera.title}">
            </a>
            <a class="filename" href="#" download></a>
            <div class="original-url"></div>
            <div class="links">
                <a class="link-fullscreen" href="#" target="_blank">Fullscreen</a>
                <a class="link-today" href="#" target="_blank">Today's Pictures</a>
                <a class="link-timelapse-today" href="#" target="_blank">Today's Timelapse</a>
                <a class="link-timelapse" href="#" target="_blank">Yesterday's Timelapse</a>
                <a class="link-history" href="#" target="_blank">History</a>
            </div>
        </div>
    `;

    listItem.querySelector('.camera-header').addEventListener('click', () => {
        const details = listItem.querySelector('.camera-details');
        const isActive = details.classList.toggle('active');
        
        document.querySelectorAll('.camera-details.active').forEach(otherDetails => {
            if (otherDetails !== details) {
                otherDetails.classList.remove('active');
            }
        });

        // Also pan map if it's visible
        if (mapVisible) {
            focusCameraLayer(cameraMarkers[listItem.dataset.markerId]);
        }
    });

    return listItem;
}

function createRemotePopupContent(deployment, camera, openUrl) {
    const deploymentLabel = deployment.displayName;
    return `<b>${camera.title}</b><br><a href="${openUrl}" target="_blank" rel="noopener">Open on ${deploymentLabel}</a>`;
}

function addRemoteCameraListItem(camera, deployment, markerId, openUrl, imageUrl) {
    const listItem = document.createElement('li');
    listItem.className = 'camera-item remote-camera';
    listItem.dataset.markerId = markerId;
    listItem.dataset.deployment = deployment.key;

    const header = document.createElement('div');
    header.className = 'camera-header';

    if (imageUrl) {
        const img = document.createElement('img');
        img.src = imageUrl;
        img.alt = `${camera.title} thumbnail`;
        header.appendChild(img);
    }

    const info = document.createElement('div');
    info.className = 'camera-info';

    const nameEl = document.createElement('div');
    nameEl.className = 'camera-name';
    nameEl.textContent = camera.title;
    info.appendChild(nameEl);

    const deploymentEl = document.createElement('div');
    deploymentEl.className = 'last-picture-time';
    deploymentEl.textContent = `Remote: ${deployment.displayName}`;
    info.appendChild(deploymentEl);

    header.appendChild(info);

    const openLink = document.createElement('a');
    openLink.className = 'remote-open-link';
    openLink.href = openUrl;
    openLink.target = '_blank';
    openLink.rel = 'noopener';
    openLink.textContent = `Open on ${deployment.displayName}`;
    header.appendChild(openLink);

    listItem.appendChild(header);

    listItem.addEventListener('click', (event) => {
        if (event.target.closest('.remote-open-link')) {
            return;
        }
        if (mapVisible) {
            focusCameraLayer(cameraMarkers[markerId]);
        }
    });

    cameraListElement.appendChild(listItem);
    return listItem;
}

function integrateRemoteDeployment(deployment, remoteData) {
    if (!remoteData || !Array.isArray(remoteData.cameras)) {
        return;
    }
    const remoteCameras = remoteData.cameras;
    const newLayers = [];
    remoteCameras.forEach((camera, index) => {
        const cameraSlug = slugify(camera.title, `camera-${index}`);
        const markerId = `remote-${deployment.key}-${cameraSlug}-${index}`;
        const openUrl = buildRemoteCameraUrl(deployment.baseUrl, camera.url, cameraSlug);
        const imageCandidate = camera.thumbnail_url || camera.image;
        const imageUrl = buildAbsoluteUrl(deployment.baseUrl, imageCandidate);
        addRemoteCameraListItem(camera, deployment, markerId, openUrl, imageUrl);

        const lat = camera.lat != null ? parseFloat(camera.lat) : null;
        const lon = camera.lon != null ? parseFloat(camera.lon) : null;
        const radius = camera.map_radius_m != null ? parseFloat(camera.map_radius_m) : 0;
        const layer = addCameraLayer(lat, lon, radius, createRemotePopupContent(deployment, camera, openUrl));
        if (layer) {
            cameraMarkers[markerId] = layer;
            newLayers.push(layer);
        }
    });
    if (newLayers.length > 0 && latestMarkerBounds) {
        map.fitBounds(latestMarkerBounds, markerBoundsFitOptions);
    }
}

function refreshLinkedDeployments(linkedDeployments) {
    const generation = ++remoteFetchGeneration;
    clearRemoteCameraItems();
    if (!Array.isArray(linkedDeployments) || linkedDeployments.length === 0) {
        return;
    }
    const seenKeys = new Set();
    linkedDeployments.forEach((deployment, index) => {
        const baseUrl = deployment.base_url;
        if (!baseUrl) {
            return;
        }
        const displayName = deployment.name || baseUrl;
        let key = slugify(displayName, `deployment-${index}`);
        while (seenKeys.has(key)) {
            key = `${key}-${index}`;
        }
        seenKeys.add(key);

        const camerasPath = deployment.cameras_json_url || 'cameras.json';
        const camerasUrl = buildAbsoluteUrl(baseUrl, camerasPath);
        const normalizedDeployment = {
            key,
            displayName,
            baseUrl,
            camerasUrl,
        };

        fetch(normalizedDeployment.camerasUrl)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`Failed to load remote cameras from ${normalizedDeployment.camerasUrl}`);
                }
                return response.json();
            })
            .then((remoteData) => {
                if (generation !== remoteFetchGeneration) {
                    return;
                }
                const resolvedName = remoteData?.global?.deployment_name;
                const deploymentForIntegration = {
                    ...normalizedDeployment,
                    displayName: resolvedName || normalizedDeployment.displayName,
                };
                integrateRemoteDeployment(deploymentForIntegration, remoteData);
            })
            .catch((error) => {
                if (generation !== remoteFetchGeneration) {
                    return;
                }
                console.error(`Failed to pull remote deployment '${displayName}':`, error);
            });
    });
}

function updateCamera(camera, cameraData) {
    let listItem = document.querySelector(`li[data-title="${camera.title}"]`);
    if (!listItem) {
        listItem = createCameraListItem(camera);
        cameraListElement.appendChild(listItem);
    }

    if (camera.source === 'external_website') {
        listItem.innerHTML = `
            <div class="camera-header">
                <a href="${camera.url}" target="_blank">
                    <img src="${camera.thumbnail_url}" alt="${camera.title} thumbnail">
                </a>
                <div class="camera-info">
                    <a href="${camera.url}" target="_blank">
                        <div class="camera-name">${camera.title}</div>
                    </a>
                </div>
            </div>
        `;
        return;
    }

    const thumbImg = listItem.querySelector('.camera-header img');
    const lastPictureTime = listItem.querySelector('.last-picture-time');
    const status = listItem.querySelector('.status');
    const detailsImg = listItem.querySelector('.camera-details img');
    const fullscreenImageLink = listItem.querySelector('.fullscreen-image-link');
    const filenameLink = listItem.querySelector('.camera-details .filename');
    const originalUrlDiv = listItem.querySelector('.original-url');
    const linkFullscreen = listItem.querySelector('.link-fullscreen');
    const linkToday = listItem.querySelector('.link-today');
    const linkTimelapseToday = listItem.querySelector('.link-timelapse-today');
    const linkTimelapse = listItem.querySelector('.link-timelapse');
    const linkHistory = listItem.querySelector('.link-history');

    fetch(camera.dynamic_metadata)
        .then(response => response.ok ? response.json() : Promise.reject('Network response was not ok.'))
        .then(metadata => {
            const lastPictureUrl = metadata.last_picture_url;
            if (!lastPictureUrl) {
                lastPictureTime.textContent = 'No picture available';
                status.className = 'status offline';
                return;
            }

            const basePath = camera.dynamic_metadata.substring(0, camera.dynamic_metadata.lastIndexOf('/'));
            const fullImageUrl = `/${basePath}/${lastPictureUrl}`;
            const filename = lastPictureUrl.substring(lastPictureUrl.lastIndexOf('/') + 1);

            thumbImg.src = fullImageUrl;
            detailsImg.src = fullImageUrl;
            filenameLink.textContent = "Download: " + filename;
            filenameLink.href = fullImageUrl;

            const imageDate = parseTimestampFromFilename(filename);
            if (imageDate) {
                lastPictureTime.textContent = `Last picture: ${imageDate.toLocaleString()}`;
                const isOnline = (new Date() - imageDate) < 3 * 60 * 1000;
                status.className = `status ${isOnline ? 'online' : 'offline'}`;
            } else {
                lastPictureTime.textContent = 'Could not parse date from: ' + filename;
                status.className = 'status offline';
            }

            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(today.getDate() - 1);
            const todayStr = formatDate(today);
            const yesterdayStr = formatDate(yesterday);
            const timelapseExtension = cameraData.global.timelapse_file_extension || 'webm';
            const frequentTimelapseExtension = cameraData.global.frequent_timelapse_file_extension || 'mp4';
            const photo_dir = `/photos/${camera.title}`;

            const fullscreenUrl = `fullscreen.html?camera=${encodeURIComponent(camera.title)}`;
            linkFullscreen.href = fullscreenUrl;
            fullscreenImageLink.href = fullscreenUrl;
            linkToday.href = `${photo_dir}/${todayStr}/`;

            const startOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            const minutesElapsed = (today - startOfDay) / 60000;
            const cacheBuster = Math.floor(minutesElapsed / 20);
            linkTimelapseToday.href = `${photo_dir}/${todayStr}/${todayStr}.${frequentTimelapseExtension}?v=${cacheBuster}`;
            linkTimelapseToday.textContent = `Today's Timelapse`;

            linkTimelapse.href = `${photo_dir}/${yesterdayStr}/${yesterdayStr}.${timelapseExtension}`;
            linkTimelapse.textContent = `Yesterday's Timelapse`;
            linkTimelapse.style.display = 'inline-block';

            linkHistory.href = `${photo_dir}/daylight.html`;

            if (camera.original_url) {
                originalUrlDiv.innerHTML = `Original URL: <a href="${camera.original_url}" target="_blank">${camera.original_url}</a>`;
            } else {
                originalUrlDiv.innerHTML = '';
            }
        })
        .catch(error => {
            lastPictureTime.textContent = 'Error loading metadata';
            status.className = 'status offline';
            console.error(`Failed to load metadata for ${camera.title}:`, error);
        });
}

let initialCameraExpanded = false;

function updateAllCameras() {
    fetch('/cameras.json')
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok.');
            return response.json();
        })
        .then(data => {
            document.querySelector('#list-header h1').textContent = data.global.deployment_name + ' cameras';

            // --- Icon Links Logic ---
            const mainWebsiteLink = document.getElementById('main-website-link');
            const githubLink = document.getElementById('github-link');
            const uiConfig = data.global.ui || {};

            // Main Website Icon
            if (uiConfig.show_main_website_icon === false || !uiConfig.main_website_url) {
                mainWebsiteLink.style.display = 'none';
            } else {
                mainWebsiteLink.style.display = 'flex';
                mainWebsiteLink.href = uiConfig.main_website_url;
            }

            // GitHub Icon
            if (uiConfig.show_github_icon) {
                githubLink.style.display = 'flex';
            } else {
                githubLink.style.display = 'none';
            }
            if (!mapVisibilityInitialized) {
                if (uiConfig.show_map_by_default) {
                    openMap();
                }
                mapVisibilityInitialized = true;
            }
            refreshLinkedDeployments(uiConfig.linked_deployments || []);
            const cameras = data.cameras;
            const existingTitles = new Set();

            cameras.forEach(camera => updateCamera(camera, data));

            // Map marker logic
            markerCluster.clearLayers();
            circleLayerGroup.clearLayers();
            cameraMarkers = {};
            latestMarkerBounds = null;

            cameras.forEach(camera => {
                const lat = camera.lat != null ? parseFloat(camera.lat) : null;
                const lon = camera.lon != null ? parseFloat(camera.lon) : null;
                const radius = camera.map_radius_m != null ? parseFloat(camera.map_radius_m) : 0;
                const markerId = `camera-${camera.title.replace(/\s+/g, '-')}`;
                const layer = addCameraLayer(lat, lon, radius, createPopupContent(camera));
                if (layer) {
                    cameraMarkers[markerId] = layer;
                }
            });

            if (latestMarkerBounds) {
                map.fitBounds(latestMarkerBounds, markerBoundsFitOptions);
            }

            // Auto-expand camera from URL param
            if (!initialCameraExpanded && cameras.length > 0) {
                const urlParams = new URLSearchParams(window.location.search);
                const cameraNameToExpand = urlParams.get('camera');
                if (cameraNameToExpand) {
                    const listItem = document.querySelector(`li[data-title="${cameraNameToExpand}"]`);
                    if (listItem) {
                        const details = listItem.querySelector('.camera-details');
                        details.classList.add('active');
                        listItem.scrollIntoView({ behavior: 'smooth', block: 'center' });

                        // Wait for CSS transition before checking other details
                        setTimeout(() => {
                        }, 500);
                        initialCameraExpanded = true;
                    }
                }
            }
        })
        .catch(error => {
            console.error('Error loading cameras.json:', error);
            cameraListElement.innerHTML = '<li>Error loading camera list.</li>';
        });
}

updateAllCameras();
setInterval(updateAllCameras, 60000); // Refresh every 60 seconds

const themeToggle = document.getElementById('theme-toggle');
const body = document.body;
const mapToggleButton = document.getElementById('map-toggle');

// Apply theme based on system preference or stored value
const prefersDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
const storedTheme = localStorage.getItem('theme');

if (storedTheme === 'dark' || (storedTheme === null && prefersDarkMode)) {
    body.classList.add('dark-mode');
    themeToggle.textContent = '🌙';
} else {
    themeToggle.textContent = '☀️';
}

// Toggle theme on button click
themeToggle.addEventListener('click', () => {
    body.classList.toggle('dark-mode');
    const theme = body.classList.contains('dark-mode') ? 'dark' : 'light';
    localStorage.setItem('theme', theme);
    themeToggle.textContent = theme === 'dark' ? '🌙' : '☀️';
});

const cameraListElement = document.getElementById('camera-list');

// --- Map Initialization ---
const mapPanel = document.getElementById('map-panel');
const listPanel = document.getElementById('list-panel');
const mapElement = document.getElementById('map');

var map = L.map('map').setView([0, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    minZoom: 0
}).addTo(map);

var markerCluster = L.markerClusterGroup();
map.addLayer(markerCluster);

var cameraMarkers = {}; // To store references to map markers

// --- Map Toggle Functionality ---
mapToggleButton.addEventListener('click', () => {
    const isMapVisible = mapPanel.style.width === '50%';
    if (isMapVisible) {
        mapPanel.style.width = '0';
        listPanel.style.width = '100%';
        mapElement.style.visibility = 'hidden';
        mapToggleButton.textContent = 'Show Map';
    } else {
        mapPanel.style.width = '50%';
        listPanel.style.width = '50%';
        mapElement.style.visibility = 'visible';
        mapToggleButton.textContent = 'Hide Map';
        // Invalidate map size to fix rendering issues after being hidden
        setTimeout(() => map.invalidateSize(), 500);
    }
});

function createPopupContent(camera, fullImageUrl) {
    const imageUrl = fullImageUrl || '';
    const imageTag = imageUrl ? `<img src="${imageUrl}" style="width: 280px; height: auto; border-radius: 4px; margin-bottom: 5px;">` : 'Loading image...';
    return `${imageTag}<br><b>${camera.title}</b>`;
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
        const isMapVisible = mapPanel.style.width === '50%';
        if (isMapVisible) {
            const marker = cameraMarkers[listItem.dataset.markerId];
            if (marker) {
                markerCluster.zoomToShowLayer(marker, () => marker.openPopup());
            }
        }
    });

    return listItem;
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
            const cameras = data.cameras;
            const existingTitles = new Set();

            cameras.forEach(camera => updateCamera(camera, data));

            // Map marker logic
            markerCluster.clearLayers();
            cameraMarkers = {};
            const cameraLatLngs = [];

            cameras.forEach(camera => {
                if (camera.lat && camera.lon) {
                    const latLng = [camera.lat, camera.lon];
                    cameraLatLngs.push(latLng);
                    const markerId = `camera-${camera.title.replace(/\s+/g, '-')}`;
                    const marker = L.marker(latLng);
                    marker.bindPopup(createPopupContent(camera));
                    cameraMarkers[markerId] = marker;
                    markerCluster.addLayer(marker);
                }
            });

            // Auto-zoom map to fit all markers
            if (cameraLatLngs.length > 0) {
                const bounds = L.latLngBounds(cameraLatLngs);
                map.fitBounds(bounds, { padding: [50, 50] });
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

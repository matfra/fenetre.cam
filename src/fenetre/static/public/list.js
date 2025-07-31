const themeToggle = document.getElementById('theme-toggle');
const body = document.body;

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
            <img src="" alt="Full image for ${camera.title}">
            <a class="filename" href="#" download></a>
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
    });

    return listItem;
}

function updateCamera(camera, cameraData) {
    let listItem = document.querySelector(`li[data-title="${camera.title}"]`);
    if (!listItem) {
        listItem = createCameraListItem(camera);
        cameraListElement.appendChild(listItem);
    }

    const thumbImg = listItem.querySelector('.camera-header img');
    const lastPictureTime = listItem.querySelector('.last-picture-time');
    const status = listItem.querySelector('.status');
    const detailsImg = listItem.querySelector('.camera-details img');
    const filenameLink = listItem.querySelector('.camera-details .filename');
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
            filenameLink.textContent = filename;
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

            linkFullscreen.href = `fullscreen.html?camera=${encodeURIComponent(camera.title)}`;
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
        })
        .catch(error => {
            lastPictureTime.textContent = 'Error loading metadata';
            status.className = 'status offline';
            console.error(`Failed to load metadata for ${camera.title}:`, error);
        });
}

function updateAllCameras() {
    fetch('/cameras.json')
        .then(response => response.ok ? response.json() : Promise.reject('Network response was not ok.'))
        .then(data => {
            const cameras = data.cameras;
            cameras.forEach(camera => updateCamera(camera, data));
        })
        .catch(error => {
            console.error('Error loading cameras.json:', error);
            cameraListElement.innerHTML = '<li>Error loading camera list.</li>';
        });
}

updateAllCameras();
setInterval(updateAllCameras, 60000);


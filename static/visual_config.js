document.addEventListener('DOMContentLoaded', () => {
    const cameraSelect = document.getElementById('cameraSelect');
    const fetchImageBtn = document.getElementById('fetchImageBtn');
    // const imageContainer = document.getElementById('imageContainer'); // Not directly used, imageWrapper is new parent
    const sourceImage = document.getElementById('sourceImage');
    const cropCanvas = document.getElementById('cropCanvas');
    const cropX1Input = document.getElementById('cropX1');
    const cropY1Input = document.getElementById('cropY1');
    const cropX2Input = document.getElementById('cropX2');
    const cropY2Input = document.getElementById('cropY2');

    const enableSkyAreaCheckbox = document.getElementById('enableSkyArea');
    const skyAreaControlsDiv = document.getElementById('skyAreaControls');
    const skyX1Input = document.getElementById('skyX1');
    const skyY1Input = document.getElementById('skyY1');
    const skyX2Input = document.getElementById('skyX2');
    const skyY2Input = document.getElementById('skyY2');

    const enableSsimAreaCheckbox = document.getElementById('enableSsimArea');
    const ssimAreaControlsDiv = document.getElementById('ssimAreaControls');
    const ssimX1Input = document.getElementById('ssimX1');
    const ssimY1Input = document.getElementById('ssimY1');
    const ssimX2Input = document.getElementById('ssimX2');
    const ssimY2Input = document.getElementById('ssimY2');

    const previewCropBtn = document.getElementById('previewCropBtn');
    const croppedPreviewImage = document.getElementById('croppedPreviewImage');
    const applyCropBtn = document.getElementById('applyCropBtn');
    const visualStatusMessage = document.getElementById('visualStatusMessage');

    let originalImageBlob = null;
    let imageDimensions = { displayWidth: 0, displayHeight: 0, naturalWidth: 0, naturalHeight: 0 };
    let scaleFactors = { x: 1, y: 1 };

    // --- Initialization ---
    async function populateCameraSelect() {
        try {
            const response = await fetch('/config');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const config = await response.json();

            if (config && config.cameras) {
                for (const camName in config.cameras) {
                    if (config.cameras[camName].url) { // Only list URL-based cameras for V1
                        const option = document.createElement('option');
                        option.value = camName;
                        option.textContent = camName;
                        cameraSelect.appendChild(option);
                    }
                }
            }
        } catch (error) {
            console.error('Error fetching config for camera list:', error);
            setStatus(`Error loading camera list: ${error.message}`, 'error');
        }
    }

    // --- Event Listeners ---
    fetchImageBtn.addEventListener('click', handleFetchImage);
    previewCropBtn.addEventListener('click', handlePreviewCrop);
    applyCropBtn.addEventListener('click', handleApplyVisualSettings); // Renamed

    // Event listeners for coordinate inputs
    [cropX1Input, cropY1Input, cropX2Input, cropY2Input,
     skyX1Input, skyY1Input, skyX2Input, skyY2Input,
     ssimX1Input, ssimY1Input, ssimX2Input, ssimY2Input].forEach(input => {
        input.addEventListener('input', drawAllRectangles);
    });

    // Event listeners for checkboxes
    enableSkyAreaCheckbox.addEventListener('change', () => {
        skyAreaControlsDiv.style.display = enableSkyAreaCheckbox.checked ? 'block' : 'none';
        if (!enableSkyAreaCheckbox.checked) {
            // Optionally clear inputs when hiding, or leave them
        }
        drawAllRectangles();
    });

    enableSsimAreaCheckbox.addEventListener('change', () => {
        ssimAreaControlsDiv.style.display = enableSsimAreaCheckbox.checked ? 'block' : 'none';
        if (!enableSsimAreaCheckbox.checked) {
            // Optionally clear inputs
        }
        drawAllRectangles();
    });


    // --- Core Functions ---
    function drawAllRectangles() { // Renamed from drawCropRectangle
        const ctx = cropCanvas.getContext('2d');
        ctx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);

        if (!(imageDimensions.displayWidth > 0 && imageDimensions.displayHeight > 0)) {
            return; // No image loaded or dimensions not set
        }

        // Draw Crop Rectangle (Red)
        const cx1 = parseInt(cropX1Input.value) || 0;
        const cy1 = parseInt(cropY1Input.value) || 0;
        const cx2 = parseInt(cropX2Input.value) || 0;
        const cy2 = parseInt(cropY2Input.value) || 0;
        if (!(cx1 === 0 && cy1 === 0 && cx2 === 0 && cy2 === 0)) { // Avoid drawing 0-size rect if all are 0
             drawRect(ctx, cx1, cy1, cx2, cy2, 'red');
        }


        // Draw Sky Area Rectangle (Cyan)
        if (enableSkyAreaCheckbox.checked) {
            const sx1 = parseInt(skyX1Input.value) || 0;
            const sy1 = parseInt(skyY1Input.value) || 0;
            const sx2 = parseInt(skyX2Input.value) || 0;
            const sy2 = parseInt(skyY2Input.value) || 0;
            if (!(sx1 === 0 && sy1 === 0 && sx2 === 0 && sy2 === 0)) {
                drawRect(ctx, sx1, sy1, sx2, sy2, 'cyan');
            }
        }

        // Draw SSIM Area Rectangle (Yellow)
        if (enableSsimAreaCheckbox.checked) {
            const ssx1 = parseInt(ssimX1Input.value) || 0;
            const ssy1 = parseInt(ssimY1Input.value) || 0;
            const ssx2 = parseInt(ssimX2Input.value) || 0;
            const ssy2 = parseInt(ssimY2Input.value) || 0;
            if (!(ssx1 === 0 && ssy1 === 0 && ssx2 === 0 && ssy2 === 0)) {
                 drawRect(ctx, ssx1, ssy1, ssx2, ssy2, 'yellow');
            }
        }
    }

    function drawRect(ctx, x1, y1, x2, y2, color) {
        const width = Math.abs(x2 - x1);
        const height = Math.abs(y2 - y1);
        const startX = Math.min(x1, x2);
        const startY = Math.min(y1, y2);

        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(startX, startY, width, height);
    }


    async function handleFetchImage() {
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('Please select a camera.', 'error');
            return;
        }

        setStatus(`Fetching image for ${cameraName}...`, 'info');
        sourceImage.src = '';
        croppedPreviewImage.src = '';
        previewCropBtn.disabled = true;
        applyCropBtn.disabled = true;
        originalImageBlob = null;
        imageDimensions = { displayWidth: 0, displayHeight: 0, naturalWidth: 0, naturalHeight: 0 };
        scaleFactors = { x: 1, y: 1 };
        cropCanvas.width = 0;
        cropCanvas.height = 0;

        try {
            const response = await fetch(`/api/camera/${cameraName}/capture_for_ui`, { method: 'POST' });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || `Failed to fetch image for ${cameraName}`);
            }

            originalImageBlob = await response.blob();
            sourceImage.src = URL.createObjectURL(originalImageBlob);

            sourceImage.onload = () => {
                imageDimensions.naturalWidth = sourceImage.naturalWidth;
                imageDimensions.naturalHeight = sourceImage.naturalHeight;
                imageDimensions.displayWidth = sourceImage.offsetWidth;
                imageDimensions.displayHeight = sourceImage.offsetHeight;

                if (imageDimensions.displayWidth > 0 && imageDimensions.displayHeight > 0) {
                    scaleFactors.x = imageDimensions.naturalWidth / imageDimensions.displayWidth;
                    scaleFactors.y = imageDimensions.naturalHeight / imageDimensions.displayHeight;
                } else { // Fallback if offsetWidth/Height are zero (e.g. image hidden)
                    scaleFactors.x = 1;
                    scaleFactors.y = 1;
                }

                cropCanvas.width = imageDimensions.displayWidth;
                cropCanvas.height = imageDimensions.displayHeight;

                cropX1Input.value = 0;
                cropY1Input.value = 0;
                cropX2Input.value = imageDimensions.displayWidth;
                cropY2Input.value = imageDimensions.displayHeight;

                // After image is loaded, fetch full config to check for existing sky/ssim areas
                try {
                    const fullConfigResponse = await fetch('/config');
                    if (fullConfigResponse.ok) {
                        const fullConfig = await fullConfigResponse.json();
                        const camConfig = fullConfig.cameras && fullConfig.cameras[cameraName] ? fullConfig.cameras[cameraName] : null;

                        if (camConfig) {
                            if (camConfig.sky_area) {
                                const [l, t, r, b] = camConfig.sky_area.split(',').map(Number);
                                skyX1Input.value = Math.round(l / scaleFactors.x);
                                skyY1Input.value = Math.round(t / scaleFactors.y);
                                skyX2Input.value = Math.round(r / scaleFactors.x);
                                skyY2Input.value = Math.round(b / scaleFactors.y);
                                enableSkyAreaCheckbox.checked = true;
                                skyAreaControlsDiv.style.display = 'block';
                            } else {
                                enableSkyAreaCheckbox.checked = false;
                                skyAreaControlsDiv.style.display = 'none';
                            }

                            if (camConfig.ssim_area) {
                                const [l, t, r, b] = camConfig.ssim_area.split(',').map(Number);
                                ssimX1Input.value = Math.round(l / scaleFactors.x);
                                ssimY1Input.value = Math.round(t / scaleFactors.y);
                                ssimX2Input.value = Math.round(r / scaleFactors.x);
                                ssimY2Input.value = Math.round(b / scaleFactors.y);
                                enableSsimAreaCheckbox.checked = true;
                                ssimAreaControlsDiv.style.display = 'block';
                            } else {
                                enableSsimAreaCheckbox.checked = false;
                                ssimAreaControlsDiv.style.display = 'none';
                            }
                        }
                    }
                } catch (e) {
                    console.error("Error fetching full config to populate sky/ssim areas:", e);
                    // Proceed without pre-filling sky/ssim, they can still be set manually
                }

                drawAllRectangles(); // Renamed

                setStatus('Image loaded. Adjust crop/area coordinates as needed.', 'success');
                previewCropBtn.disabled = false;
                applyCropBtn.disabled = false;
            };
            sourceImage.onerror = () => {
                 setStatus('Error loading image into display area.', 'error');
            }

        } catch (error) {
            console.error('Error in fetchImage:', error);
            setStatus(`Error: ${error.message}`, 'error');
        }
    }

    async function handlePreviewCrop() {
        if (!originalImageBlob) {
            setStatus('Please fetch an image first.', 'error');
            return;
        }

        const x1 = parseInt(cropX1Input.value);
        const y1 = parseInt(cropY1Input.value);
        const x2 = parseInt(cropX2Input.value);
        const y2 = parseInt(cropY2Input.value);

        // UI coordinates
        const uiCropX = Math.min(x1, x2);
        const uiCropY = Math.min(y1, y2);
        const uiCropWidth = Math.abs(x2 - x1);
        const uiCropHeight = Math.abs(y2 - y1);

        if (uiCropWidth === 0 || uiCropHeight === 0) {
            setStatus('Invalid crop dimensions (width or height is zero).', 'error');
            return;
        }

        // Scale UI coordinates to natural image coordinates for the backend
        const naturalCropX = Math.round(uiCropX * scaleFactors.x);
        const naturalCropY = Math.round(uiCropY * scaleFactors.y);
        const naturalCropWidth = Math.round(uiCropWidth * scaleFactors.x);
        const naturalCropHeight = Math.round(uiCropHeight * scaleFactors.y);

        setStatus('Generating crop preview...', 'info');
        croppedPreviewImage.src = '';

        const formData = new FormData();
        formData.append('image', originalImageBlob, 'source_image.jpg');
        formData.append('crop_data', JSON.stringify({
            x: naturalCropX,
            y: naturalCropY,
            width: naturalCropWidth,
            height: naturalCropHeight,
        }));

        try {
            const response = await fetch('/api/camera/preview_crop', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || 'Failed to generate crop preview.');
            }

            const croppedImageBlob = await response.blob();
            croppedPreviewImage.src = URL.createObjectURL(croppedImageBlob);
            setStatus('Crop preview generated.', 'success');

        } catch (error) {
            console.error('Error in previewCrop:', error);
            setStatus(`Error generating preview: ${error.message}`, 'error');
        }
    }

    async function handleApplyVisualSettings() { // Renamed from handleApplyCrop
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('No camera selected.', 'error');
            return;
        }

        setStatus(`Applying visual settings for ${cameraName} to configuration...`, 'info');

        try {
            const configResponse = await fetch('/config');
            if (!configResponse.ok) throw new Error('Failed to fetch current configuration.');
            let currentConfig = await configResponse.json();

            if (!currentConfig.cameras || !currentConfig.cameras[cameraName]) {
                throw new Error(`Camera ${cameraName} not found in current configuration.`);
            }
            let camConfig = currentConfig.cameras[cameraName];

            // Handle Crop Area
            const cx1 = parseInt(cropX1Input.value);
            const cy1 = parseInt(cropY1Input.value);
            const cx2 = parseInt(cropX2Input.value);
            const cy2 = parseInt(cropY2Input.value);
            const cNatL = Math.round(Math.min(cx1, cx2) * scaleFactors.x);
            const cNatT = Math.round(Math.min(cy1, cy2) * scaleFactors.y);
            const cNatR = Math.round(Math.max(cx1, cx2) * scaleFactors.x);
            const cNatB = Math.round(Math.max(cy1, cy2) * scaleFactors.y);

            if ((cNatR - cNatL) > 0 && (cNatB - cNatT) > 0) {
                if (!camConfig.postprocessing) camConfig.postprocessing = [];
                camConfig.postprocessing = camConfig.postprocessing.filter(step => step.type !== 'crop');
                camConfig.postprocessing.unshift({
                    type: "crop",
                    area: `${cNatL},${cNatT},${cNatR},${cNatB}`
                });
            } else {
                // If crop dimensions are zero, optionally remove existing crop or do nothing
                 camConfig.postprocessing = camConfig.postprocessing.filter(step => step.type !== 'crop');
                 setStatus('Crop area has zero width/height, existing crop (if any) removed.', 'info');
            }

            // Handle Sky Area
            if (enableSkyAreaCheckbox.checked) {
                const sx1 = parseInt(skyX1Input.value);
                const sy1 = parseInt(skyY1Input.value);
                const sx2 = parseInt(skyX2Input.value);
                const sy2 = parseInt(skyY2Input.value);
                const sNatL = Math.round(Math.min(sx1, sx2) * scaleFactors.x);
                const sNatT = Math.round(Math.min(sy1, sy2) * scaleFactors.y);
                const sNatR = Math.round(Math.max(sx1, sx2) * scaleFactors.x);
                const sNatB = Math.round(Math.max(sy1, sy2) * scaleFactors.y);
                if ((sNatR - sNatL) > 0 && (sNatB - sNatT) > 0) {
                    camConfig.sky_area = `${sNatL},${sNatT},${sNatR},${sNatB}`;
                } else {
                    delete camConfig.sky_area; // Invalid dimensions, remove if exists
                    setStatus('Sky area has zero width/height, not saved.', 'info');
                }
            } else {
                delete camConfig.sky_area;
            }

            // Handle SSIM Area
            if (enableSsimAreaCheckbox.checked) {
                const ssx1 = parseInt(ssimX1Input.value);
                const ssy1 = parseInt(ssimY1Input.value);
                const ssx2 = parseInt(ssimX2Input.value);
                const ssy2 = parseInt(ssimY2Input.value);
                const ssNatL = Math.round(Math.min(ssx1, ssx2) * scaleFactors.x);
                const ssNatT = Math.round(Math.min(ssy1, ssy2) * scaleFactors.y);
                const ssNatR = Math.round(Math.max(ssx1, ssx2) * scaleFactors.x);
                const ssNatB = Math.round(Math.max(ssy1, ssy2) * scaleFactors.y);
                 if ((ssNatR - ssNatL) > 0 && (ssNatB - ssNatT) > 0) {
                    camConfig.ssim_area = `${ssNatL},${ssNatT},${ssNatR},${ssNatB}`;
                } else {
                    delete camConfig.ssim_area; // Invalid dimensions, remove if exists
                    setStatus('SSIM area has zero width/height, not saved.', 'info');
                }
            } else {
                delete camConfig.ssim_area;
            }

            const updateResponse = await fetch('/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentConfig)
            });

            if (!updateResponse.ok) {
                const errorData = await updateResponse.json().catch(() => ({ error: `HTTP error! status: ${updateResponse.status}` }));
                throw new Error(errorData.error || 'Failed to save updated configuration.');
            }

            const result = await updateResponse.json();
            setStatus(result.message || `Visual settings for ${cameraName} applied. Remember to reload application config.`, 'success');

        } catch (error) {
            console.error('Error applying visual settings to config:', error);
            setStatus(`Error applying settings: ${error.message}`, 'error');
        }
    }

    function setStatus(message, type = 'info') {
        visualStatusMessage.textContent = message;
        visualStatusMessage.className = 'status-message'; // Clear previous classes
        if (type === 'success') {
            visualStatusMessage.classList.add('success');
        } else if (type === 'error') {
            visualStatusMessage.classList.add('error');
        }
    }

    // --- Initial Load ---
    populateCameraSelect();
});

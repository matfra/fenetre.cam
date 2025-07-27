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

    const cropNaturalCoordsDiv = document.getElementById('cropNaturalCoords');
    const skyNaturalCoordsDiv = document.getElementById('skyNaturalCoords');
    const ssimNaturalCoordsDiv = document.getElementById('ssimNaturalCoords');
    const naturalSizeSpan = document.getElementById('naturalSize');
    const displayScaleSpan = document.getElementById('displayScale');

    const previewCropBtn = document.getElementById('previewCropBtn');
    const croppedPreviewImage = document.getElementById('croppedPreviewImage');
    const applyCropBtn = document.getElementById('applyCropBtn');
    const visualStatusMessage = document.getElementById('visualStatusMessage');

    let originalImageBlob = null;
    let imageDimensions = { displayWidth: 0, displayHeight: 0, naturalWidth: 0, naturalHeight: 0 };
    let scaleFactors = { x: 1, y: 1 };

    // Store the defined areas in NATURAL image coordinates
    let naturalAreas = {
        crop: { x1: 0, y1: 0, x2: 0, y2: 0, active: true }, // Crop is always "active" conceptually
        sky: { x1: 0, y1: 0, x2: 0, y2: 0, active: false },
        ssim: { x1: 0, y1: 0, x2: 0, y2: 0, active: false }
    };

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
    // Event listeners for coordinate inputs - now also update naturalAreas
    function setupCoordinateInputListeners() {
        const inputs = [
            { el: cropX1Input, area: 'crop', coord: 'x1' }, { el: cropY1Input, area: 'crop', coord: 'y1' },
            { el: cropX2Input, area: 'crop', coord: 'x2' }, { el: cropY2Input, area: 'crop', coord: 'y2' },
            { el: skyX1Input, area: 'sky', coord: 'x1' }, { el: skyY1Input, area: 'sky', coord: 'y1' },
            { el: skyX2Input, area: 'sky', coord: 'x2' }, { el: skyY2Input, area: 'sky', coord: 'y2' },
            { el: ssimX1Input, area: 'ssim', coord: 'x1' }, { el: ssimY1Input, area: 'ssim', coord: 'y1' },
            { el: ssimX2Input, area: 'ssim', coord: 'x2' }, { el: ssimY2Input, area: 'ssim', coord: 'y2' }
        ];
        inputs.forEach(item => {
            item.el.addEventListener('input', () => {
                // Update the natural coordinates store based on UI input
                const uiValue = parseInt(item.el.value) || 0;
                let naturalValue;
                if (item.coord === 'x1' || item.coord === 'x2') {
                    naturalValue = Math.round(uiValue * scaleFactors.x);
                } else { // y1, y2
                    naturalValue = Math.round(uiValue * scaleFactors.y);
                }
                naturalAreas[item.area][item.coord] = naturalValue;

                drawAllRectangles(); // Uses UI input values directly for drawing
                updateCoordinateDisplays(); // Uses UI input values and scaleFactors
            });
        });
    }
    setupCoordinateInputListeners();


    // Event listeners for checkboxes
    enableSkyAreaCheckbox.addEventListener('change', () => {
        skyAreaControlsDiv.style.display = enableSkyAreaCheckbox.checked ? 'block' : 'none';
        naturalAreas.sky.active = enableSkyAreaCheckbox.checked;
        if (!naturalAreas.sky.active) { // If disabling, reset its natural coords (optional)
            // naturalAreas.sky = { x1: 0, y1: 0, x2: 0, y2: 0, active: false };
            // updateInputFieldsFromNatural('sky'); // And update UI to reflect reset
        }
        drawAllRectangles();
        updateCoordinateDisplays();
    });

    enableSsimAreaCheckbox.addEventListener('change', () => {
        ssimAreaControlsDiv.style.display = enableSsimAreaCheckbox.checked ? 'block' : 'none';
        naturalAreas.ssim.active = enableSsimAreaCheckbox.checked;
        drawAllRectangles();
        updateCoordinateDisplays();
    });

    window.addEventListener('resize', handleResize);


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

    function updateCoordinateDisplays() {
        if (!imageDimensions.naturalWidth || !imageDimensions.naturalHeight) {
            naturalSizeSpan.textContent = '-';
            displayScaleSpan.textContent = '-';
            cropNaturalCoordsDiv.textContent = 'Natural: -';
            skyNaturalCoordsDiv.textContent = 'Natural: -';
            ssimNaturalCoordsDiv.textContent = 'Natural: -';
            return;
        }

        naturalSizeSpan.textContent = `${imageDimensions.naturalWidth}x${imageDimensions.naturalHeight}`;
        if (scaleFactors.x === 1 && scaleFactors.y === 1) {
            displayScaleSpan.textContent = '1.00 (No scaling)';
        } else {
            displayScaleSpan.textContent = `X: ${scaleFactors.x.toFixed(2)}, Y: ${scaleFactors.y.toFixed(2)}`;
        }

        // Crop Area Natural Coords
        const cx1 = parseInt(cropX1Input.value) || 0;
        const cy1 = parseInt(cropY1Input.value) || 0;
        const cx2 = parseInt(cropX2Input.value) || 0;
        const cy2 = parseInt(cropY2Input.value) || 0;
        const cNatX1 = Math.round(cx1 * scaleFactors.x);
        const cNatY1 = Math.round(cy1 * scaleFactors.y);
        const cNatX2 = Math.round(cx2 * scaleFactors.x);
        const cNatY2 = Math.round(cy2 * scaleFactors.y);
        cropNaturalCoordsDiv.textContent = `Natural: X1:${cNatX1}, Y1:${cNatY1}, X2:${cNatX2}, Y2:${cNatY2}`;

        // Sky Area Natural Coords
        if (enableSkyAreaCheckbox.checked) {
            const sx1 = parseInt(skyX1Input.value) || 0;
            const sy1 = parseInt(skyY1Input.value) || 0;
            const sx2 = parseInt(skyX2Input.value) || 0;
            const sy2 = parseInt(skyY2Input.value) || 0;
            const sNatX1 = Math.round(sx1 * scaleFactors.x);
            const sNatY1 = Math.round(sy1 * scaleFactors.y);
            const sNatX2 = Math.round(sx2 * scaleFactors.x);
            const sNatY2 = Math.round(sy2 * scaleFactors.y);
            skyNaturalCoordsDiv.textContent = `Natural: X1:${sNatX1}, Y1:${sNatY1}, X2:${sNatX2}, Y2:${sNatY2}`;
        } else {
            skyNaturalCoordsDiv.textContent = 'Natural: - (Disabled)';
        }

        // SSIM Area Natural Coords
        if (enableSsimAreaCheckbox.checked) {
            const ssx1 = parseInt(ssimX1Input.value) || 0;
            const ssy1 = parseInt(ssimY1Input.value) || 0;
            const ssx2 = parseInt(ssimX2Input.value) || 0;
            const ssy2 = parseInt(ssimY2Input.value) || 0;
            const ssNatX1 = Math.round(ssx1 * scaleFactors.x);
            const ssNatY1 = Math.round(ssy1 * scaleFactors.y);
            const ssNatX2 = Math.round(ssx2 * scaleFactors.x);
            const ssNatY2 = Math.round(ssy2 * scaleFactors.y);
            ssimNaturalCoordsDiv.textContent = `Natural: X1:${ssNatX1}, Y1:${ssNatY1}, X2:${ssNatX2}, Y2:${ssNatY2}`;
        } else {
            ssimNaturalCoordsDiv.textContent = 'Natural: - (Disabled)';
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

            sourceImage.onload = async () => { // Made this an async function
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

                // Initialize naturalAreas store
                naturalAreas.crop = {
                    x1: 0, y1: 0,
                    x2: imageDimensions.naturalWidth, y2: imageDimensions.naturalHeight,
                    active: true
                };
                naturalAreas.sky = { x1: 0, y1: 0, x2: 0, y2: 0, active: false };
                naturalAreas.ssim = { x1: 0, y1: 0, x2: 0, y2: 0, active: false };


                // After image is loaded, fetch full config to check for existing sky/ssim areas
                try {
                    const fullConfigResponse = await fetch('/config');
                    if (fullConfigResponse.ok) {
                        const fullConfig = await fullConfigResponse.json();
                        const camConfig = fullConfig.cameras && fullConfig.cameras[cameraName] ? fullConfig.cameras[cameraName] : null;

                        if (camConfig) {
                            if (camConfig.sky_area) {
                                const [l, t, r, b] = camConfig.sky_area.split(',').map(Number);
                                naturalAreas.sky = { x1: l, y1: t, x2: r, y2: b, active: true };
                                enableSkyAreaCheckbox.checked = true;
                                skyAreaControlsDiv.style.display = 'block';
                            } else {
                                enableSkyAreaCheckbox.checked = false;
                                skyAreaControlsDiv.style.display = 'none';
                            }

                            if (camConfig.ssim_area) {
                                const [l, t, r, b] = camConfig.ssim_area.split(',').map(Number);
                                naturalAreas.ssim = { x1: l, y1: t, x2: r, y2: b, active: true };
                                enableSsimAreaCheckbox.checked = true;
                                ssimAreaControlsDiv.style.display = 'block';
                            } else {
                                enableSsimAreaCheckbox.checked = false;
                                ssimAreaControlsDiv.style.display = 'none';
                            }
                            // Update UI input fields from naturalAreas after loading config
                            updateAllUiInputsFromNaturalAreas();
                        }
                    }
                } catch (e) {
                    console.error("Error fetching full config to populate sky/ssim areas:", e);
                }

                drawAllRectangles();
                updateCoordinateDisplays();

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

    function updateAllUiInputsFromNaturalAreas() {
        if (!(scaleFactors.x && scaleFactors.y && imageDimensions.naturalWidth > 0)) return; // Guard against division by zero or no scale

        // Crop Area
        cropX1Input.value = Math.round(naturalAreas.crop.x1 / scaleFactors.x);
        cropY1Input.value = Math.round(naturalAreas.crop.y1 / scaleFactors.y);
        cropX2Input.value = Math.round(naturalAreas.crop.x2 / scaleFactors.x);
        cropY2Input.value = Math.round(naturalAreas.crop.y2 / scaleFactors.y);

        // Sky Area
        if (naturalAreas.sky.active) {
            skyX1Input.value = Math.round(naturalAreas.sky.x1 / scaleFactors.x);
            skyY1Input.value = Math.round(naturalAreas.sky.y1 / scaleFactors.y);
            skyX2Input.value = Math.round(naturalAreas.sky.x2 / scaleFactors.x);
            skyY2Input.value = Math.round(naturalAreas.sky.y2 / scaleFactors.y);
        }

        // SSIM Area
        if (naturalAreas.ssim.active) {
            ssimX1Input.value = Math.round(naturalAreas.ssim.x1 / scaleFactors.x);
            ssimY1Input.value = Math.round(naturalAreas.ssim.y1 / scaleFactors.y);
            ssimX2Input.value = Math.round(naturalAreas.ssim.x2 / scaleFactors.x);
            ssimY2Input.value = Math.round(naturalAreas.ssim.y2 / scaleFactors.y);
        }
    }


    function handleResize() {
        if (!originalImageBlob || !sourceImage.src || !(imageDimensions.naturalWidth > 0)) {
            // No image loaded or natural dimensions unknown
            return;
        }

        // Update display dimensions and scale factors
        imageDimensions.displayWidth = sourceImage.offsetWidth;
        imageDimensions.displayHeight = sourceImage.offsetHeight;

        if (imageDimensions.displayWidth > 0 && imageDimensions.displayHeight > 0) {
            scaleFactors.x = imageDimensions.naturalWidth / imageDimensions.displayWidth;
            scaleFactors.y = imageDimensions.naturalHeight / imageDimensions.displayHeight;
        } else { // Fallback if offsetWidth/Height are zero (e.g. image hidden temporarily)
            scaleFactors.x = 1;
            scaleFactors.y = 1;
            // Canvas size also becomes 0, which is fine, drawing will be skipped.
        }

        cropCanvas.width = imageDimensions.displayWidth;
        cropCanvas.height = imageDimensions.displayHeight;

        // Update UI input fields from stored natural coordinates
        updateAllUiInputsFromNaturalAreas();

        drawAllRectangles();
        updateCoordinateDisplays();
    }


    async function handleApplyVisualSettings() {
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

            // Handle Crop Area - use stored natural coordinates
            const cNatL = naturalAreas.crop.x1;
            const cNatT = naturalAreas.crop.y1;
            const cNatR = naturalAreas.crop.x2;
            const cNatB = naturalAreas.crop.y2;

            if ((cNatR - cNatL) > 0 && (cNatB - cNatT) > 0) {
                if (!camConfig.postprocessing) camConfig.postprocessing = [];
                camConfig.postprocessing = camConfig.postprocessing.filter(step => step.type !== 'crop');
                camConfig.postprocessing.unshift({
                    type: "crop",
                    area: `${cNatL},${cNatT},${cNatR},${cNatB}`
                });
            } else {
                 camConfig.postprocessing = camConfig.postprocessing.filter(step => step.type !== 'crop');
                 // setStatus might be overwritten by subsequent messages, consider collecting status messages
            }

            // Handle Sky Area - use stored natural coordinates
            if (naturalAreas.sky.active) {
                const sNatL = naturalAreas.sky.x1;
                const sNatT = naturalAreas.sky.y1;
                const sNatR = naturalAreas.sky.x2;
                const sNatB = naturalAreas.sky.y2;
                if ((sNatR - sNatL) > 0 && (sNatB - sNatT) > 0) {
                    camConfig.sky_area = `${sNatL},${sNatT},${sNatR},${sNatB}`;
                } else {
                    delete camConfig.sky_area;
                }
            } else {
                delete camConfig.sky_area;
            }

            // Handle SSIM Area - use stored natural coordinates
            if (naturalAreas.ssim.active) {
                const ssNatL = naturalAreas.ssim.x1;
                const ssNatT = naturalAreas.ssim.y1;
                const ssNatR = naturalAreas.ssim.x2;
                const ssNatB = naturalAreas.ssim.y2;
                 if ((ssNatR - ssNatL) > 0 && (ssNatB - ssNatT) > 0) {
                    camConfig.ssim_area = `${ssNatL},${ssNatT},${ssNatR},${ssNatB}`;
                } else {
                    delete camConfig.ssim_area;
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

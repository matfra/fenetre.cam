document.addEventListener('DOMContentLoaded', () => {
    const cameraSelect = document.getElementById('cameraSelect');
    const fetchImageBtn = document.getElementById('fetchImageBtn');
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
    const cropPreviewSection = document.getElementById('cropPreviewSection');
    const cropPreviewPlaceholder = document.getElementById('cropPreviewPlaceholder');
    const applyCropBtn = document.getElementById('applyCropBtn');
    const visualStatusMessage = document.getElementById('visualStatusMessage');

    let originalImageBlob = null;
    let imageDimensions = { displayWidth: 0, displayHeight: 0, naturalWidth: 0, naturalHeight: 0 };
    let scaleFactors = { x: 1, y: 1 };

    let naturalAreas = {
        crop: { x1: 0, y1: 0, x2: 0, y2: 0, active: true },
        sky: { x1: 0, y1: 0, x2: 0, y2: 0, active: false },
        ssim: { x1: 0, y1: 0, x2: 0, y2: 0, active: false }
    };

    async function populateCameraSelect() {
        try {
            const response = await fetch('/config');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const config = await response.json();

            if (config.global && config.global.title) {
                document.title = `Visual Config - ${config.global.title}`;
            }

            if (config && config.cameras) {
                for (const camName in config.cameras) {
                    if (config.cameras[camName].url) {
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

    fetchImageBtn.addEventListener('click', handleFetchImage);
    previewCropBtn.addEventListener('click', handlePreviewCrop);
    applyCropBtn.addEventListener('click', handleApplyVisualSettings);

    function setupCoordinateInputListeners() {
        const inputs = [
            { el: cropX1Input, area: 'crop', coord: 'x1', valueEl: document.getElementById('cropX1Value') },
            { el: cropY1Input, area: 'crop', coord: 'y1', valueEl: document.getElementById('cropY1Value') },
            { el: cropX2Input, area: 'crop', coord: 'x2', valueEl: document.getElementById('cropX2Value') },
            { el: cropY2Input, area: 'crop', coord: 'y2', valueEl: document.getElementById('cropY2Value') },
            { el: skyX1Input, area: 'sky', coord: 'x1', valueEl: document.getElementById('skyX1Value') },
            { el: skyY1Input, area: 'sky', coord: 'y1', valueEl: document.getElementById('skyY1Value') },
            { el: skyX2Input, area: 'sky', coord: 'x2', valueEl: document.getElementById('skyX2Value') },
            { el: skyY2Input, area: 'sky', coord: 'y2', valueEl: document.getElementById('skyY2Value') },
            { el: ssimX1Input, area: 'ssim', coord: 'x1', valueEl: document.getElementById('ssimX1Value') },
            { el: ssimY1Input, area: 'ssim', coord: 'y1', valueEl: document.getElementById('ssimY1Value') },
            { el: ssimX2Input, area: 'ssim', coord: 'x2', valueEl: document.getElementById('ssimX2Value') },
            { el: ssimY2Input, area: 'ssim', coord: 'y2', valueEl: document.getElementById('ssimY2Value') }
        ];
        inputs.forEach(item => {
            item.el.addEventListener('input', () => {
                const percentageValue = parseFloat(item.el.value) || 0;
                
                // Update the value display
                if (item.valueEl) {
                    item.valueEl.textContent = percentageValue.toFixed(1) + '%';
                }
                
                // Convert percentage to natural coordinates
                let naturalValue;
                
                if (item.area === 'crop') {
                    // Crop area percentages are relative to the full image
                    if (item.coord === 'x1' || item.coord === 'x2') {
                        naturalValue = Math.round((percentageValue / 100) * imageDimensions.naturalWidth);
                    } else {
                        naturalValue = Math.round((percentageValue / 100) * imageDimensions.naturalHeight);
                    }
                } else {
                    // Sky and SSIM area percentages are relative to the crop area
                    const cropWidth = naturalAreas.crop.x2 - naturalAreas.crop.x1;
                    const cropHeight = naturalAreas.crop.y2 - naturalAreas.crop.y1;
                    
                    if (item.coord === 'x1' || item.coord === 'x2') {
                        naturalValue = naturalAreas.crop.x1 + Math.round((percentageValue / 100) * cropWidth);
                    } else {
                        naturalValue = naturalAreas.crop.y1 + Math.round((percentageValue / 100) * cropHeight);
                    }
                }
                
                naturalAreas[item.area][item.coord] = naturalValue;

                drawAllRectangles();
                updateCoordinateDisplays();
            });
        });
    }
    setupCoordinateInputListeners();

    enableSkyAreaCheckbox.addEventListener('change', () => {
        skyAreaControlsDiv.style.display = enableSkyAreaCheckbox.checked ? 'block' : 'none';
        naturalAreas.sky.active = enableSkyAreaCheckbox.checked;
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

    function drawAllRectangles() {
        const ctx = cropCanvas.getContext('2d');
        ctx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);

        if (!(imageDimensions.displayWidth > 0 && imageDimensions.displayHeight > 0)) {
            return;
        }

        // Convert percentage values to display coordinates for drawing
        const cx1 = (parseFloat(cropX1Input.value) || 0) * imageDimensions.displayWidth / 100;
        const cy1 = (parseFloat(cropY1Input.value) || 0) * imageDimensions.displayHeight / 100;
        const cx2 = (parseFloat(cropX2Input.value) || 0) * imageDimensions.displayWidth / 100;
        const cy2 = (parseFloat(cropY2Input.value) || 0) * imageDimensions.displayHeight / 100;
        if (!(cx1 === 0 && cy1 === 0 && cx2 === 0 && cy2 === 0)) {
             drawRect(ctx, cx1, cy1, cx2, cy2, 'red');
        }

        if (enableSkyAreaCheckbox.checked) {
            // Sky area percentages are relative to the crop area display coordinates
            const cropDisplayWidth = cx2 - cx1;
            const cropDisplayHeight = cy2 - cy1;
            const sx1 = cx1 + (parseFloat(skyX1Input.value) || 0) * cropDisplayWidth / 100;
            const sy1 = cy1 + (parseFloat(skyY1Input.value) || 0) * cropDisplayHeight / 100;
            const sx2 = cx1 + (parseFloat(skyX2Input.value) || 0) * cropDisplayWidth / 100;
            const sy2 = cy1 + (parseFloat(skyY2Input.value) || 0) * cropDisplayHeight / 100;
            if (!(sx1 === cx1 && sy1 === cy1 && sx2 === cx1 && sy2 === cy1)) {
                drawRect(ctx, sx1, sy1, sx2, sy2, 'cyan');
            }
        }

        if (enableSsimAreaCheckbox.checked) {
            // SSIM area percentages are relative to the crop area display coordinates
            const cropDisplayWidth = cx2 - cx1;
            const cropDisplayHeight = cy2 - cy1;
            const ssx1 = cx1 + (parseFloat(ssimX1Input.value) || 0) * cropDisplayWidth / 100;
            const ssy1 = cy1 + (parseFloat(ssimY1Input.value) || 0) * cropDisplayHeight / 100;
            const ssx2 = cx1 + (parseFloat(ssimX2Input.value) || 0) * cropDisplayWidth / 100;
            const ssy2 = cy1 + (parseFloat(ssimY2Input.value) || 0) * cropDisplayHeight / 100;
            if (!(ssx1 === cx1 && ssy1 === cy1 && ssx2 === cx1 && ssy2 === cy1)) {
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

        // Convert percentage values to natural coordinates for display
        const cx1Percent = parseFloat(cropX1Input.value) || 0;
        const cy1Percent = parseFloat(cropY1Input.value) || 0;
        const cx2Percent = parseFloat(cropX2Input.value) || 0;
        const cy2Percent = parseFloat(cropY2Input.value) || 0;
        const cNatX1 = Math.round((cx1Percent / 100) * imageDimensions.naturalWidth);
        const cNatY1 = Math.round((cy1Percent / 100) * imageDimensions.naturalHeight);
        const cNatX2 = Math.round((cx2Percent / 100) * imageDimensions.naturalWidth);
        const cNatY2 = Math.round((cy2Percent / 100) * imageDimensions.naturalHeight);
        cropNaturalCoordsDiv.textContent = `Natural: X1:${cNatX1}, Y1:${cNatY1}, X2:${cNatX2}, Y2:${cNatY2}`;

        // Show cropped area dimensions instead of full image dimensions
        const cropNaturalWidth = cNatX2 - cNatX1;
        const cropNaturalHeight = cNatY2 - cNatY1;
        naturalSizeSpan.textContent = `${cropNaturalWidth}x${cropNaturalHeight} (cropped from ${imageDimensions.naturalWidth}x${imageDimensions.naturalHeight})`;
        
        if (scaleFactors.x === 1 && scaleFactors.y === 1) {
            displayScaleSpan.textContent = '1.00 (No scaling)';
        } else {
            displayScaleSpan.textContent = `X: ${scaleFactors.x.toFixed(2)}, Y: ${scaleFactors.y.toFixed(2)}`;
        }

        if (enableSkyAreaCheckbox.checked) {
            const sx1Percent = parseFloat(skyX1Input.value) || 0;
            const sy1Percent = parseFloat(skyY1Input.value) || 0;
            const sx2Percent = parseFloat(skyX2Input.value) || 0;
            const sy2Percent = parseFloat(skyY2Input.value) || 0;
            
            // Sky area percentages are relative to crop area
            const cropWidth = cNatX2 - cNatX1;
            const cropHeight = cNatY2 - cNatY1;
            const sRelX1 = Math.round((sx1Percent / 100) * cropWidth);
            const sRelY1 = Math.round((sy1Percent / 100) * cropHeight);
            const sRelX2 = Math.round((sx2Percent / 100) * cropWidth);
            const sRelY2 = Math.round((sy2Percent / 100) * cropHeight);
            skyNaturalCoordsDiv.textContent = `Cropped area coords: X1:${sRelX1}, Y1:${sRelY1}, X2:${sRelX2}, Y2:${sRelY2}`;
        } else {
            skyNaturalCoordsDiv.textContent = 'Natural: - (Disabled)';
        }

        if (enableSsimAreaCheckbox.checked) {
            const ssx1Percent = parseFloat(ssimX1Input.value) || 0;
            const ssy1Percent = parseFloat(ssimY1Input.value) || 0;
            const ssx2Percent = parseFloat(ssimX2Input.value) || 0;
            const ssy2Percent = parseFloat(ssimY2Input.value) || 0;
            
            // SSIM area percentages are relative to crop area
            const cropWidth = cNatX2 - cNatX1;
            const cropHeight = cNatY2 - cNatY1;
            const ssRelX1 = Math.round((ssx1Percent / 100) * cropWidth);
            const ssRelY1 = Math.round((ssy1Percent / 100) * cropHeight);
            const ssRelX2 = Math.round((ssx2Percent / 100) * cropWidth);
            const ssRelY2 = Math.round((ssy2Percent / 100) * cropHeight);
            ssimNaturalCoordsDiv.textContent = `Cropped area coords: X1:${ssRelX1}, Y1:${ssRelY1}, X2:${ssRelX2}, Y2:${ssRelY2}`;
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
        croppedPreviewImage.style.display = 'none';
        cropPreviewPlaceholder.style.display = 'flex';
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

            sourceImage.onload = async () => {
                imageDimensions.naturalWidth = sourceImage.naturalWidth;
                imageDimensions.naturalHeight = sourceImage.naturalHeight;
                imageDimensions.displayWidth = sourceImage.offsetWidth;
                imageDimensions.displayHeight = sourceImage.offsetHeight;

                if (imageDimensions.displayWidth > 0 && imageDimensions.displayHeight > 0) {
                    scaleFactors.x = imageDimensions.naturalWidth / imageDimensions.displayWidth;
                    scaleFactors.y = imageDimensions.naturalHeight / imageDimensions.displayHeight;
                } else {
                    scaleFactors.x = 1;
                    scaleFactors.y = 1;
                }

                cropCanvas.width = imageDimensions.displayWidth;
                cropCanvas.height = imageDimensions.displayHeight;

                cropX1Input.value = 0;
                cropY1Input.value = 0;
                cropX2Input.value = imageDimensions.displayWidth;
                cropY2Input.value = imageDimensions.displayHeight;

                naturalAreas.crop = {
                    x1: 0, y1: 0,
                    x2: imageDimensions.naturalWidth, y2: imageDimensions.naturalHeight,
                    active: true
                };
                naturalAreas.sky = { x1: 0, y1: 0, x2: 0, y2: 0, active: false };
                naturalAreas.ssim = { x1: 0, y1: 0, x2: 0, y2: 0, active: false };

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

        const uiCropX = Math.min(x1, x2);
        const uiCropY = Math.min(y1, y2);
        const uiCropWidth = Math.abs(x2 - x1);
        const uiCropHeight = Math.abs(y2 - y1);

        if (uiCropWidth === 0 || uiCropHeight === 0) {
            setStatus('Invalid crop dimensions (width or height is zero).', 'error');
            return;
        }

        const naturalCropX = Math.round(uiCropX * scaleFactors.x);
        const naturalCropY = Math.round(uiCropY * scaleFactors.y);
        const naturalCropWidth = Math.round(uiCropWidth * scaleFactors.x);
        const naturalCropHeight = Math.round(uiCropHeight * scaleFactors.y);

        setStatus('Generating crop preview...', 'info');
        croppedPreviewImage.src = '';
        croppedPreviewImage.style.display = 'none';
        cropPreviewPlaceholder.style.display = 'flex';

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
                throw new Error(errorData.error || 'Failed to generate preview.');
            }

            const blob = await response.blob();
            croppedPreviewImage.src = URL.createObjectURL(blob);
            croppedPreviewImage.style.display = 'block';
            cropPreviewPlaceholder.style.display = 'none';
            setStatus('Crop preview generated successfully.', 'success');

        } catch (error) {
            console.error('Error in handlePreviewCrop:', error);
            setStatus(`Error generating preview: ${error.message}`, 'error');
        }
    }

    function updateAllUiInputsFromNaturalAreas() {
        if (!(imageDimensions.naturalWidth > 0 && imageDimensions.naturalHeight > 0)) return;

        function updateInputFieldsFromNatural(areaName) {
            const area = naturalAreas[areaName];
            if (!area) return;

            let percentX1, percentY1, percentX2, percentY2;

            if (areaName === 'crop') {
                // Crop area percentages are relative to the full image
                percentX1 = (area.x1 / imageDimensions.naturalWidth) * 100;
                percentY1 = (area.y1 / imageDimensions.naturalHeight) * 100;
                percentX2 = (area.x2 / imageDimensions.naturalWidth) * 100;
                percentY2 = (area.y2 / imageDimensions.naturalHeight) * 100;
            } else {
                // Sky and SSIM area percentages are relative to the crop area
                const cropWidth = naturalAreas.crop.x2 - naturalAreas.crop.x1;
                const cropHeight = naturalAreas.crop.y2 - naturalAreas.crop.y1;
                
                if (cropWidth > 0 && cropHeight > 0) {
                    percentX1 = ((area.x1 - naturalAreas.crop.x1) / cropWidth) * 100;
                    percentY1 = ((area.y1 - naturalAreas.crop.y1) / cropHeight) * 100;
                    percentX2 = ((area.x2 - naturalAreas.crop.x1) / cropWidth) * 100;
                    percentY2 = ((area.y2 - naturalAreas.crop.y1) / cropHeight) * 100;
                } else {
                    // If crop area is invalid, default to 0%
                    percentX1 = percentY1 = percentX2 = percentY2 = 0;
                }
            }

            // Update slider values
            document.getElementById(`${areaName}X1`).value = percentX1.toFixed(1);
            document.getElementById(`${areaName}Y1`).value = percentY1.toFixed(1);
            document.getElementById(`${areaName}X2`).value = percentX2.toFixed(1);
            document.getElementById(`${areaName}Y2`).value = percentY2.toFixed(1);

            // Update value displays
            const x1ValueEl = document.getElementById(`${areaName}X1Value`);
            const y1ValueEl = document.getElementById(`${areaName}Y1Value`);
            const x2ValueEl = document.getElementById(`${areaName}X2Value`);
            const y2ValueEl = document.getElementById(`${areaName}Y2Value`);
            
            if (x1ValueEl) x1ValueEl.textContent = percentX1.toFixed(1) + '%';
            if (y1ValueEl) y1ValueEl.textContent = percentY1.toFixed(1) + '%';
            if (x2ValueEl) x2ValueEl.textContent = percentX2.toFixed(1) + '%';
            if (y2ValueEl) y2ValueEl.textContent = percentY2.toFixed(1) + '%';
        }

        updateInputFieldsFromNatural('crop');
        if (naturalAreas.sky.active) {
            updateInputFieldsFromNatural('sky');
        }
        if (naturalAreas.ssim.active) {
            updateInputFieldsFromNatural('ssim');
        }
    }

    async function handleApplyVisualSettings() {
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('Please select a camera first.', 'error');
            return;
        }

        setStatus('Applying settings to main config...', 'info');

        try {
            // First, fetch the current configuration
            const currentConfigResponse = await fetch('/config');
            if (!currentConfigResponse.ok) {
                throw new Error(`Failed to fetch current config: ${currentConfigResponse.status}`);
            }
            const currentConfig = await currentConfigResponse.json();

            // Ensure the cameras object exists
            if (!currentConfig.cameras) {
                currentConfig.cameras = {};
            }
            if (!currentConfig.cameras[cameraName]) {
                currentConfig.cameras[cameraName] = {};
            }

            // Update only the visual settings for this camera
            currentConfig.cameras[cameraName].crop = `${naturalAreas.crop.x1},${naturalAreas.crop.y1},${naturalAreas.crop.x2},${naturalAreas.crop.y2}`;
            
            if (naturalAreas.sky.active) {
                // Calculate Sky area coordinates relative to the crop area
                const skyX1Percent = parseFloat(skyX1Input.value) || 0;
                const skyY1Percent = parseFloat(skyY1Input.value) || 0;
                const skyX2Percent = parseFloat(skyX2Input.value) || 0;
                const skyY2Percent = parseFloat(skyY2Input.value) || 0;
                
                const cropWidth = naturalAreas.crop.x2 - naturalAreas.crop.x1;
                const cropHeight = naturalAreas.crop.y2 - naturalAreas.crop.y1;
                
                const skyRelX1 = Math.round((skyX1Percent / 100) * cropWidth);
                const skyRelY1 = Math.round((skyY1Percent / 100) * cropHeight);
                const skyRelX2 = Math.round((skyX2Percent / 100) * cropWidth);
                const skyRelY2 = Math.round((skyY2Percent / 100) * cropHeight);
                
                currentConfig.cameras[cameraName].sky_area = `${skyRelX1},${skyRelY1},${skyRelX2},${skyRelY2}`;
            } else {
                delete currentConfig.cameras[cameraName].sky_area;
            }
            
            if (naturalAreas.ssim.active) {
                // Calculate SSIM area coordinates relative to the crop area
                const ssimX1Percent = parseFloat(ssimX1Input.value) || 0;
                const ssimY1Percent = parseFloat(ssimY1Input.value) || 0;
                const ssimX2Percent = parseFloat(ssimX2Input.value) || 0;
                const ssimY2Percent = parseFloat(ssimY2Input.value) || 0;
                
                const cropWidth = naturalAreas.crop.x2 - naturalAreas.crop.x1;
                const cropHeight = naturalAreas.crop.y2 - naturalAreas.crop.y1;
                
                const ssimRelX1 = Math.round((ssimX1Percent / 100) * cropWidth);
                const ssimRelY1 = Math.round((ssimY1Percent / 100) * cropHeight);
                const ssimRelX2 = Math.round((ssimX2Percent / 100) * cropWidth);
                const ssimRelY2 = Math.round((ssimY2Percent / 100) * cropHeight);
                
                currentConfig.cameras[cameraName].ssim_area = `${ssimRelX1},${ssimRelY1},${ssimRelX2},${ssimRelY2}`;
            } else {
                delete currentConfig.cameras[cameraName].ssim_area;
            }

            // Save the complete updated configuration
            const response = await fetch('/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentConfig)
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || 'Failed to apply settings.');
            }

            const result = await response.json();
            setStatus(result.message || 'Settings applied successfully!', 'success');

        } catch (error) {
            console.error('Error applying visual settings:', error);
            setStatus(`Error: ${error.message}`, 'error');
        }
    }

    function setStatus(message, type = 'info') {
        visualStatusMessage.textContent = message;
        visualStatusMessage.className = `status-message ${type}`;
    }

    function handleResize() {
        if (!sourceImage.src || !imageDimensions.naturalWidth) {
            return;
        }

        imageDimensions.displayWidth = sourceImage.offsetWidth;
        imageDimensions.displayHeight = sourceImage.offsetHeight;

        if (imageDimensions.displayWidth > 0) {
            scaleFactors.x = imageDimensions.naturalWidth / imageDimensions.displayWidth;
            scaleFactors.y = imageDimensions.naturalHeight / imageDimensions.displayHeight;
        } else {
            scaleFactors = { x: 1, y: 1 };
        }

        cropCanvas.width = imageDimensions.displayWidth;
        cropCanvas.height = imageDimensions.displayHeight;

        updateAllUiInputsFromNaturalAreas();

        drawAllRectangles();
        updateCoordinateDisplays();
    }

    const container = document.querySelector('.visual-config-container');
    container.addEventListener('click', function(event) {
        if (event.target.classList.contains('collapsible')) {
            event.target.classList.toggle('collapsed');
            const content = event.target.nextElementSibling;
            if (content && content.classList.contains('collapsible-content')) {
                content.classList.toggle('collapsed');
            }
        }
    });

    populateCameraSelect();
});

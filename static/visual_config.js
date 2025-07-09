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
    const previewCropBtn = document.getElementById('previewCropBtn');
    const croppedPreviewImage = document.getElementById('croppedPreviewImage');
    const applyCropBtn = document.getElementById('applyCropBtn');
    const visualStatusMessage = document.getElementById('visualStatusMessage');

    let originalImageBlob = null;
    let imageDimensions = { width: 0, height: 0 }; // Store displayed dimensions of sourceImage

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
    applyCropBtn.addEventListener('click', handleApplyCrop);
    [cropX1Input, cropY1Input, cropX2Input, cropY2Input].forEach(input => {
        input.addEventListener('input', drawCropRectangle);
    });


    // --- Core Functions ---
    function drawCropRectangle() {
        const x1 = parseInt(cropX1Input.value) || 0;
        const y1 = parseInt(cropY1Input.value) || 0;
        const x2 = parseInt(cropX2Input.value) || 0;
        const y2 = parseInt(cropY2Input.value) || 0;

        const ctx = cropCanvas.getContext('2d');
        ctx.clearRect(0, 0, cropCanvas.width, cropCanvas.height); // Clear previous rectangle

        // Only draw if we have valid image dimensions
        if (imageDimensions.width > 0 && imageDimensions.height > 0) {
            const width = Math.abs(x2 - x1);
            const height = Math.abs(y2 - y1);
            const startX = Math.min(x1, x2);
            const startY = Math.min(y1, y2);

            ctx.strokeStyle = 'red';
            ctx.lineWidth = 2;
            ctx.strokeRect(startX, startY, width, height);
        }
    }

    async function handleFetchImage() {
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('Please select a camera.', 'error');
            return;
        }

        setStatus(`Fetching image for ${cameraName}...`, 'info');
        sourceImage.src = ''; // Clear previous image
        croppedPreviewImage.src = ''; // Clear preview
        previewCropBtn.disabled = true;
        applyCropBtn.disabled = true;
        originalImageBlob = null;
        imageDimensions = { width: 0, height: 0 };
        cropCanvas.width = 0; // Clear canvas
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
                // Set canvas dimensions to match the displayed image
                imageDimensions.width = sourceImage.offsetWidth;
                imageDimensions.height = sourceImage.offsetHeight;
                cropCanvas.width = imageDimensions.width;
                cropCanvas.height = imageDimensions.height;

                // Initialize crop inputs to full image size
                cropX1Input.value = 0;
                cropY1Input.value = 0;
                cropX2Input.value = imageDimensions.width;
                cropY2Input.value = imageDimensions.height;

                drawCropRectangle(); // Draw initial full-image rectangle

                setStatus('Image loaded. Adjust crop coordinates as needed.', 'success');
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

        const cropX = Math.min(x1, x2);
        const cropY = Math.min(y1, y2);
        const cropWidth = Math.abs(x2 - x1);
        const cropHeight = Math.abs(y2 - y1);

        if (cropWidth === 0 || cropHeight === 0) {
            setStatus('Invalid crop dimensions (width or height is zero).', 'error');
            return;
        }

        setStatus('Generating crop preview...', 'info');
        croppedPreviewImage.src = '';

        const formData = new FormData();
        formData.append('image', originalImageBlob, 'source_image.jpg');
        formData.append('crop_data', JSON.stringify({
            x: cropX,
            y: cropY,
            width: cropWidth,
            height: cropHeight,
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

    async function handleApplyCrop() {
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('No camera selected.', 'error');
            return;
        }

        const x1 = parseInt(cropX1Input.value);
        const y1 = parseInt(cropY1Input.value);
        const x2 = parseInt(cropX2Input.value);
        const y2 = parseInt(cropY2Input.value);

        const left = Math.min(x1, x2);
        const top = Math.min(y1, y2);
        const right = Math.max(x1, x2);
        const bottom = Math.max(y1, y2);

        if ((right - left) === 0 || (bottom - top) === 0) {
            setStatus('Invalid crop dimensions for saving (width or height is zero).', 'error');
            return;
        }

        setStatus(`Applying crop for ${cameraName} to configuration...`, 'info');

        try {
            const configResponse = await fetch('/config');
            if (!configResponse.ok) throw new Error('Failed to fetch current configuration.');
            let currentConfig = await configResponse.json();

            const cropAreaString = `${left},${top},${right},${bottom}`;

            if (currentConfig.cameras && currentConfig.cameras[cameraName]) {
                let camConfig = currentConfig.cameras[cameraName];
                if (!camConfig.postprocessing) {
                    camConfig.postprocessing = [];
                }

                // Remove existing crop steps
                camConfig.postprocessing = camConfig.postprocessing.filter(step => step.type !== 'crop');

                // Add new crop step
                camConfig.postprocessing.unshift({ // Add to the beginning
                    type: "crop",
                    area: cropAreaString
                });
            } else {
                throw new Error(`Camera ${cameraName} not found in current configuration.`);
            }

            // 4. PUT the modified configuration
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
            setStatus(result.message || `Crop for ${cameraName} applied. Remember to reload application config.`, 'success');

        } catch (error) {
            console.error('Error applying crop to config:', error);
            setStatus(`Error applying crop: ${error.message}`, 'error');
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

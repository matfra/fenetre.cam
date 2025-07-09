document.addEventListener('DOMContentLoaded', () => {
    const cameraSelect = document.getElementById('cameraSelect');
    const fetchImageBtn = document.getElementById('fetchImageBtn');
    const imageContainer = document.getElementById('imageContainer');
    const sourceImage = document.getElementById('sourceImage');
    const cropInfo = document.getElementById('cropInfo');
    const previewCropBtn = document.getElementById('previewCropBtn');
    const croppedPreviewImage = document.getElementById('croppedPreviewImage');
    const applyCropBtn = document.getElementById('applyCropBtn');
    const visualStatusMessage = document.getElementById('visualStatusMessage');

    let cropper = null;
    let currentCropData = null;
    let originalImageBlob = null; // To store the fetched image blob for previewing crop

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

    // --- Core Functions ---
    async function handleFetchImage() {
        const cameraName = cameraSelect.value;
        if (!cameraName) {
            setStatus('Please select a camera.', 'error');
            return;
        }

        setStatus(`Fetching image for ${cameraName}...`, 'info');
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
        sourceImage.src = ''; // Clear previous image
        croppedPreviewImage.src = ''; // Clear preview
        cropInfo.textContent = 'Selected area details will appear here.';
        previewCropBtn.disabled = true;
        applyCropBtn.disabled = true;
        originalImageBlob = null;

        try {
            const response = await fetch(`/api/camera/${cameraName}/capture_for_ui`, { method: 'POST' });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || `Failed to fetch image for ${cameraName}`);
            }

            originalImageBlob = await response.blob(); // Store the blob
            sourceImage.src = URL.createObjectURL(originalImageBlob);

            sourceImage.onload = () => {
                cropper = new Cropper(sourceImage, {
                    viewMode: 1, // Allow cropping outside image boundaries, but restrict crop box to be within canvas
                    autoCropArea: 0.8, // Initial crop area size (80% of image)
                    responsive: true,
                    background: false, // No grid background from cropper itself
                    crop(event) {
                        currentCropData = {
                            x: Math.round(event.detail.x),
                            y: Math.round(event.detail.y),
                            width: Math.round(event.detail.width),
                            height: Math.round(event.detail.height),
                            rotate: event.detail.rotate,
                            scaleX: event.detail.scaleX,
                            scaleY: event.detail.scaleY,
                        };
                        cropInfo.textContent = `X: ${currentCropData.x}, Y: ${currentCropData.y}, W: ${currentCropData.width}, H: ${currentCropData.height}`;
                        previewCropBtn.disabled = false;
                        applyCropBtn.disabled = false;
                    },
                });
                setStatus('Image loaded. Select crop area.', 'success');
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
        if (!originalImageBlob || !currentCropData || currentCropData.width === 0 || currentCropData.height === 0) {
            setStatus('Please fetch an image and select a crop area first.', 'error');
            return;
        }

        setStatus('Generating crop preview...', 'info');
        croppedPreviewImage.src = ''; // Clear previous preview

        const formData = new FormData();
        formData.append('image', originalImageBlob, 'source_image.jpg'); // filename is informative
        formData.append('crop_data', JSON.stringify({
            x: currentCropData.x,
            y: currentCropData.y,
            width: currentCropData.width,
            height: currentCropData.height,
        }));

        try {
            const response = await fetch('/api/camera/preview_crop', {
                method: 'POST',
                body: formData, // Sending as FormData
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
        if (!cameraName || !currentCropData || currentCropData.width === 0 || currentCropData.height === 0) {
            setStatus('No camera selected or crop area defined.', 'error');
            return;
        }

        setStatus(`Applying crop for ${cameraName} to configuration...`, 'info');

        try {
            // 1. Fetch current full configuration
            const configResponse = await fetch('/config');
            if (!configResponse.ok) throw new Error('Failed to fetch current configuration.');
            let currentConfig = await configResponse.json();

            // 2. Prepare the crop area string (left,top,right,bottom)
            const x = currentCropData.x;
            const y = currentCropData.y;
            const width = currentCropData.width;
            const height = currentCropData.height;
            const cropAreaString = `${x},${y},${x + width},${y + height}`;

            // 3. Find the camera and update/add its postprocessing for crop
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

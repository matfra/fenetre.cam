document.addEventListener('DOMContentLoaded', () => {
    // Define structures for postprocessing steps
    const postprocessingTypes = {
        crop: {
            fields: { area: { type: 'text', default: '0,0,1920,1080' } },
            order: ['area']
        },
        resize: {
            fields: {
                width: { type: 'number', default: 1280 },
                height: { type: 'number', default: 720 }
            },
            order: ['width', 'height']
        },
        awb: { // Auto White Balance
            fields: {}, // No specific fields, the type itself is the config
            order: []
        },
        timestamp: {
            fields: {
                enabled: { type: 'checkbox', default: true },
                position: { type: 'text', default: 'bottom_right' }, // Could be a select if predefined options
                size: { type: 'number', default: 24 },
                color: { type: 'text', default: 'white' }, // Could be a color picker or select
                format: { type: 'text', default: '%Y-%m-%d %H:%M:%S %Z' }
            },
            order: ['enabled', 'position', 'size', 'color', 'format']
        }
        // Add other postprocessing types here as needed
    };
    const availablePostprocessingTypes = Object.keys(postprocessingTypes);

    // Define structures for camera configurations
    const cameraSourceTypes = {
        url: {
            fields: { url: { type: 'text', default: 'http://example.com/image.jpg' } },
            order: ['url']
        },
        local_command: {
            fields: { local_command: { type: 'text', default: 'ffmpeg -i http://source/stream -vframes 1 -q:v 2 -f singlejpeg -' } },
            order: ['local_command']
        },
        gopro_ip: {
            fields: {
                gopro_ip: { type: 'text', default: '10.5.5.9' },
                gopro_ble_identifier: { type: 'text', default: 'XXXX' },
                gopro_root_ca: { type: 'textarea', default: '-----BEGIN CERTIFICATE-----\nPASTE_CA_HERE\n-----END CERTIFICATE-----' },
                gopro_preset: { type: 'text', default: '65539' }, // Could be a select with known presets
                gopro_utility_poll_interval_s: { type: 'number', default: 10 },
                gopro_bluetooth_retry_delay_s: { type: 'number', default: 180 }
            },
            order: ['gopro_ip', 'gopro_ble_identifier', 'gopro_root_ca', 'gopro_preset', 'gopro_utility_poll_interval_s', 'gopro_bluetooth_retry_delay_s']
        }
    };
    const availableCameraSourceTypes = Object.keys(cameraSourceTypes);

    const commonCameraFields = {
        description: { type: 'text', default: 'A new camera' },
        // snap_interval_s: { type: 'number', default: 60 }, // If not set, implies dynamic SSIM-based interval
        timeout_s: { type: 'number', default: 60 },
        sky_area: { type: 'text', default: '0,0,1920,500' }, // Example, might need better default or placeholder
        ssim_area: { type: 'text', default: '0,0,1920,1080' },
        ssim_setpoint: { type: 'number', default: 0.90, step: 0.01 }, // For float input
        disabled: { type: 'checkbox', default: false },
        mozjpeg_optimize: { type: 'checkbox', default: false },
        postprocessing: { type: 'array', default: [] } // Special handling: this will use the postprocessing logic
    };
    // Order for common fields (can be refined)
    const commonCameraFieldsOrder = [
        'description', 'timeout_s', 'sky_area', 'ssim_area', 'ssim_setpoint',
        'disabled', 'mozjpeg_optimize', 'postprocessing'
        // 'snap_interval_s' can be added if a fixed interval is desired as a common option.
        // If snap_interval_s is present, it overrides SSIM logic.
        // The absence of snap_interval_s implies dynamic interval.
        // This needs to be clear in the UI, perhaps by having snap_interval_s and if it's empty/0, ssim settings apply.
        // For now, keeping snap_interval_s out of common template to encourage dynamic by default.
        // Users can add it manually if the form allows adding arbitrary key-value pairs, or we add it as an optional common field.
    ];


    // Order for common fields (can be refined)
    const commonCameraFieldsOrder = [
        'description', 'timeout_s', 'sky_area', 'ssim_area', 'ssim_setpoint',
        'disabled', 'mozjpeg_optimize', 'postprocessing'
        // 'snap_interval_s' can be added if a fixed interval is desired as a common option.
        // If snap_interval_s is present, it overrides SSIM logic.
        // The absence of snap_interval_s implies dynamic interval.
        // This needs to be clear in the UI, perhaps by having snap_interval_s and if it's empty/0, ssim settings apply.
        // For now, keeping snap_interval_s out of common template to encourage dynamic by default.
        // Users can add it manually if the form allows adding arbitrary key-value pairs, or we add it as an optional common field.
    ];


    const loadConfigBtn = document.getElementById('loadConfigBtn');
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const reloadAppBtn = document.getElementById('reloadAppBtn');
    const addCameraBtn = document.getElementById('addCameraBtn'); // Get the new button
    const configFormContainer = document.getElementById('configFormContainer');
    const statusMessage = document.getElementById('statusMessage');

    loadConfigBtn.addEventListener('click', fetchAndDisplayConfig);
    saveConfigBtn.addEventListener('click', saveConfiguration);
    reloadAppBtn.addEventListener('click', reloadApplication);
    addCameraBtn.addEventListener('click', handleAddCamera); // Add event listener

    async function fetchAndDisplayConfig() {
        setStatus('Loading configuration...', 'info');
        try {
            const response = await fetch('/config');
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const config = await response.json();
            renderConfigForm(config, configFormContainer, '');
            setStatus('Configuration loaded successfully.', 'success');
            saveConfigBtn.disabled = false;
        } catch (error) {
            console.error('Error fetching config:', error);
            setStatus(`Error fetching configuration: ${error.message}`, 'error');
        }
    }

    function renderConfigForm(data, parentElement, parentKey = '') {
        parentElement.innerHTML = ''; // Clear previous form

        for (const key in data) {
            if (!data.hasOwnProperty(key)) continue;

            const value = data[key];
            const currentKey = parentKey ? `${parentKey}.${key}` : key;

            const label = document.createElement('label');
            label.textContent = key;
            label.htmlFor = currentKey;
            parentElement.appendChild(label);

            if (typeof value === 'boolean') {
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.id = currentKey;
                input.checked = value;
                input.dataset.key = currentKey;
                parentElement.appendChild(input);
                parentElement.appendChild(document.createElement('br'));
            } else if (typeof value === 'number') {
                const input = document.createElement('input');
                input.type = 'number';
                input.id = currentKey;
                input.value = value;
                input.dataset.key = currentKey;
                parentElement.appendChild(input);
            } else if (typeof value === 'string') {
                // Use textarea for multi-line strings (e.g. gopro_root_ca)
                if (value.includes('\n')) {
                    const textarea = document.createElement('textarea');
                    textarea.id = currentKey;
                    textarea.value = value;
                    textarea.rows = value.split('\n').length + 1;
                    textarea.dataset.key = currentKey;
                    parentElement.appendChild(textarea);
                } else {
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.id = currentKey;
                    input.value = value;
                    input.dataset.key = currentKey;
                    parentElement.appendChild(input);
                }
            } else if (Array.isArray(value)) {
                const fieldset = document.createElement('fieldset');
                const legend = document.createElement('legend');
                legend.textContent = key + ' (List)';
                fieldset.appendChild(legend);
                fieldset.dataset.key = currentKey;
                fieldset.dataset.type = 'array';

                value.forEach((item, index) => {
                    const itemContainer = createArrayItemContainer(item, `${currentKey}[${index}]`, index, fieldset);
                    fieldset.appendChild(itemContainer);
                });

                const addButton = document.createElement('button');
                addButton.textContent = 'Add Item';
                addButton.type = 'button';
                addButton.classList.add('add-item-btn');
                addButton.addEventListener('click', () => addArrayItem(fieldset, `${currentKey}[${value.length}]`, value.length, (value.length > 0 && typeof value[0] === 'object' ? {} : '')));
                fieldset.appendChild(addButton);
                parentElement.appendChild(fieldset);

            } else if (typeof value === 'object' && value !== null) {
                const fieldset = document.createElement('fieldset');
                const legend = document.createElement('legend');
                legend.textContent = key;
                fieldset.appendChild(legend);
                fieldset.dataset.key = currentKey;
                fieldset.dataset.type = 'object';
                renderConfigForm(value, fieldset, currentKey);
                parentElement.appendChild(fieldset);
            }
        }
    }

    function createArrayItemContainer(item, itemKey, index, parentFieldset) {
        const itemContainer = document.createElement('div');
        itemContainer.classList.add('array-item');
        itemContainer.dataset.index = index;
        itemContainer.dataset.key = itemKey; // e.g., cameras[0]

        if (typeof item === 'object' && item !== null) {
            renderConfigForm(item, itemContainer, itemKey);
        } else { // Primitive type (string, number, boolean)
            const input = document.createElement('input');
            input.type = (typeof item === 'number') ? 'number' : (typeof item === 'boolean') ? 'checkbox' : 'text';
            if (typeof item === 'boolean') input.checked = item; else input.value = item;
            input.id = itemKey;
            input.dataset.key = itemKey; // This input represents the item itself
            itemContainer.appendChild(input);
        }

        const removeButton = document.createElement('button');
        removeButton.textContent = 'Remove';
        removeButton.type = 'button';
        removeButton.classList.add('remove-item-btn');
        removeButton.addEventListener('click', () => {
            itemContainer.remove();
            // Re-index remaining items if necessary, or handle gaps in getFormDataAsJson
        });

        const controlsDiv = document.createElement('div');
        controlsDiv.classList.add('array-item-controls');
        controlsDiv.appendChild(removeButton);
        itemContainer.appendChild(controlsDiv);

        return itemContainer;
    }

    function addArrayItem(parentFieldset, baseKey, newIndex, templateItem) {
        const itemKeyPrefix = baseKey.substring(0, baseKey.lastIndexOf('[')); // e.g., cameras.mycam.postprocessing
        const actualKey = itemKeyPrefix.split('.').pop(); // e.g., postprocessing

        if (actualKey === 'postprocessing') {
            // Special handling for postprocessing items
            const typeSelectorContainer = document.createElement('div');
            typeSelectorContainer.classList.add('type-selector-container');

            const selectLabel = document.createElement('label');
            selectLabel.textContent = 'Select postprocessing type: ';
            typeSelectorContainer.appendChild(selectLabel);

            const typeSelect = document.createElement('select');
            availablePostprocessingTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type;
                typeSelect.appendChild(option);
            });
            typeSelectorContainer.appendChild(typeSelect);

            const confirmButton = document.createElement('button');
            confirmButton.textContent = 'Add Selected Type';
            confirmButton.type = 'button';
            confirmButton.addEventListener('click', () => {
                const selectedType = typeSelect.value;
                typeSelectorContainer.remove(); // Remove selector UI

                // Determine the new index for the actual item
                // This needs to be robust if items can be removed out of order.
                // For simplicity, assume newIndex is roughly correct for now, or re-calculate.
                const currentItemCount = parentFieldset.querySelectorAll(':scope > .array-item, :scope > .postprocessing-item').length;
                const itemKey = `${itemKeyPrefix}[${currentItemCount}]`;

                const newItemContainer = renderPostprocessingItem(selectedType, itemKey, parentFieldset);
                parentFieldset.insertBefore(newItemContainer, parentFieldset.querySelector('.add-item-btn'));
            });
            typeSelectorContainer.appendChild(confirmButton);

            const cancelButton = document.createElement('button');
            cancelButton.textContent = 'Cancel';
            cancelButton.type = 'button';
            cancelButton.addEventListener('click', () => {
                typeSelectorContainer.remove();
            });
            typeSelectorContainer.appendChild(cancelButton);

            // Insert the type selector before the 'Add Item' button
            parentFieldset.insertBefore(typeSelectorContainer, parentFieldset.querySelector('.add-item-btn'));

        } else {
            // Default behavior for other arrays
            const itemContainer = createArrayItemContainer(templateItem, `${itemKeyPrefix}[${newIndex}]`, newIndex, parentFieldset);
            parentFieldset.insertBefore(itemContainer, parentFieldset.querySelector('.add-item-btn'));
        }
    }

    function renderPostprocessingItem(type, itemBaseKey, parentFieldset) {
        const itemContainer = document.createElement('div');
        itemContainer.classList.add('postprocessing-item', 'array-item'); // Add array-item for consistent removal styling/logic
        itemContainer.dataset.key = itemBaseKey; // e.g., cameras.cam1.postprocessing[0]
        itemContainer.dataset.type = type; // Store the type

        const typeDisplay = document.createElement('h5'); // Or a div with styling
        typeDisplay.textContent = `Type: ${type}`;
        itemContainer.appendChild(typeDisplay);

        // Hidden input to store the type, will be picked up by getFormDataAsJson
        const typeInput = document.createElement('input');
        typeInput.type = 'hidden';
        typeInput.dataset.key = `${itemBaseKey}.type`; // Path for the type property
        typeInput.value = type;
        itemContainer.appendChild(typeInput);

        const typeDefinition = postprocessingTypes[type];
        if (typeDefinition && typeDefinition.fields) {
            typeDefinition.order.forEach(fieldName => {
                const field = typeDefinition.fields[fieldName];
                const fieldKey = `${itemBaseKey}.${fieldName}`; // e.g., cameras.cam1.postprocessing[0].area

                const label = document.createElement('label');
                label.textContent = fieldName;
                label.htmlFor = fieldKey;
                itemContainer.appendChild(label);

                let input;
                if (field.type === 'checkbox') {
                    input = document.createElement('input');
                    input.type = 'checkbox';
                    input.checked = field.default;
                } else if (field.type === 'number') {
                    input = document.createElement('input');
                    input.type = 'number';
                    input.value = field.default;
                } else { // 'text' or other
                    input = document.createElement('input');
                    input.type = 'text'; // Default to text
                    input.value = field.default;
                }
                input.id = fieldKey;
                input.dataset.key = fieldKey; // Crucial for getFormDataAsJson
                itemContainer.appendChild(input);
                itemContainer.appendChild(document.createElement('br'));
            });
        }

        const removeButton = document.createElement('button');
        removeButton.textContent = 'Remove This Step';
        removeButton.type = 'button';
        removeButton.classList.add('remove-item-btn');
        removeButton.addEventListener('click', () => {
            itemContainer.remove();
            // Note: Re-indexing siblings or handling gaps in getFormDataAsJson might be needed for arrays.
        });
        itemContainer.appendChild(removeButton);

        return itemContainer;
    }


    function getFormDataAsJson() {
        const data = {};
        function buildObject(element, obj) {
            if (element.dataset.key) {
                const keys = element.dataset.key.split('.');
                let current = obj;
                keys.forEach((k, index) => {
                    // Array handling: key[index]
                    const arrayMatch = k.match(/^([^\[]+)\[(\d+)\]$/);
                    if (arrayMatch) {
                        const arrayKey = arrayMatch[1];
                        const arrayIndex = parseInt(arrayMatch[2]);
                        if (!current[arrayKey]) current[arrayKey] = [];

                        if (index === keys.length - 1) { // Last part of the key path
                            if (element.type === 'checkbox') {
                                current[arrayKey][arrayIndex] = element.checked;
                            } else if (element.type === 'number') {
                                current[arrayKey][arrayIndex] = parseFloat(element.value) || 0;
                            } else {
                                current[arrayKey][arrayIndex] = element.value;
                            }
                        } else {
                            // This part of path is an array, but not the final value holder
                            if (!current[arrayKey][arrayIndex]) {
                                // Check next key part to see if it's another array index or an object key
                                const nextKeyPart = keys[index+1];
                                if (nextKeyPart.includes('[')) {
                                    current[arrayKey][arrayIndex] = [];
                                } else {
                                    current[arrayKey][arrayIndex] = {};
                                }
                            }
                            current = current[arrayKey][arrayIndex];
                        }
                    } else { // Object key
                        if (index === keys.length - 1) {
                            if (element.type === 'checkbox') {
                                current[k] = element.checked;
                            } else if (element.type === 'number') {
                                current[k] = parseFloat(element.value) || 0;
                            } else {
                                current[k] = element.value;
                            }
                        } else {
                            if (!current[k]) {
                                // Check next key part to see if it's an array index or an object key
                                const nextKeyPart = keys[index+1];
                                if (nextKeyPart.includes('[')) {
                                     current[k] = [];
                                } else {
                                     current[k] = {};
                                }
                            }
                            current = current[k];
                        }
                    }
                });
            }
        }

        function processChildren(parentElement, currentObject) {
            for (const child of parentElement.children) {
                if (child.tagName === 'FIELDSET') {
                    const key = child.dataset.key.split('.').pop().replace(/\[\d+\]$/, ''); // Get the actual key name
                    if (child.dataset.type === 'array') {
                        currentObject[key] = [];
                        // Iterate over array item containers
                        Array.from(child.querySelectorAll(':scope > .array-item')).forEach(itemDiv => {
                            let itemValue = {}; // Assume array items that are not primitive are objects
                            // Check if the itemDiv's direct children suggest it's a simple primitive
                            // This check might need to be more robust based on how renderConfigForm structures primitives in arrays
                            const directPrimitiveInput = itemDiv.querySelector(':scope > input, :scope > textarea');
                            let isPrimitiveArrayItem = false;
                            if (directPrimitiveInput) {
                                // If the direct input's key is exactly the itemKey (e.g. "myArray[0]")
                                // it means it's an array of primitives.
                                // An object item would have inputs like "myArray[0].property"
                                const isKeySimpleArrayIndex = !Object.values(directPrimitiveInput.dataset).some(val => val.includes('.'));
                                if (directPrimitiveInput.dataset.key && directPrimitiveInput.dataset.key.endsWith(`[${itemDiv.dataset.index}]` ) && isKeySimpleArrayIndex) {
                                     isPrimitiveArrayItem = true;
                                }
                            }


                            if (isPrimitiveArrayItem && directPrimitiveInput) {
                                if (directPrimitiveInput.type === 'checkbox') itemValue = directPrimitiveInput.checked;
                                else if (directPrimitiveInput.type === 'number') itemValue = parseFloat(directPrimitiveInput.value) || 0;
                                else itemValue = directPrimitiveInput.value;
                            } else {
                                // It's an object within an array. Process its children to build the object.
                                // itemDiv itself contains the fields of the object.
                                processChildren(itemDiv, itemValue);
                            }
                            currentObject[key].push(itemValue);
                        });
                    } else { // Object (not an array)
                        currentObject[key] = {};
                        processChildren(child, currentObject[key]);
                    }
                } else if (child.tagName === 'INPUT' || child.tagName === 'TEXTAREA') {
                    // This branch handles direct properties of an object, not items in an array directly.
                    // Array items are handled within the 'array' fieldset logic.
                    if (child.dataset.key) {
                        const keyParts = child.dataset.key.split('.');
                        const actualKey = keyParts[keyParts.length -1]; // The last part is the actual property name

                        // Ensure we are not trying to process parts of an array item directly here
                        // if (actualKey.includes('[')) continue; // Skip if it looks like an array element part

                        if (child.type === 'checkbox') {
                            currentObject[actualKey] = child.checked;
                        } else if (child.type === 'number') {
                            currentObject[actualKey] = parseFloat(child.value) || 0;
                        } else {
                            currentObject[actualKey] = child.value;
                        }
                    }
                }
            }
        }

        processChildren(configFormContainer, data);
        return data;
    }


    async function saveConfiguration() {
        setStatus('Saving configuration...', 'info');
        const configData = getFormDataAsJson();
        console.log("Saving data:", JSON.stringify(configData, null, 2));

        try {
            const response = await fetch('/config', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const result = await response.json();
            setStatus(result.message || 'Configuration saved successfully!', 'success');
        } catch (error) {
            console.error('Error saving config:', error);
            setStatus(`Error saving configuration: ${error.message}`, 'error');
        }
    }

    async function reloadApplication() {
        setStatus('Sending reload signal to application...', 'info');
        try {
            const response = await fetch('/config/reload', {
                method: 'POST',
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const result = await response.json();
            setStatus(result.message || 'Reload signal sent successfully!', 'success');
        } catch (error) {
            console.error('Error reloading application:', error);
            setStatus(`Error reloading application: ${error.message}`, 'error');
        }
    }

    function setStatus(message, type = 'info') {
        statusMessage.textContent = message;
        statusMessage.className = ''; // Clear previous classes
        if (type === 'success') {
            statusMessage.classList.add('success');
        } else if (type === 'error') {
            statusMessage.classList.add('error');
        }
    }

    // Automatically load the configuration when the page loads
    fetchAndDisplayConfig();

    function handleAddCamera() {
        const cameraName = prompt("Enter a name for the new camera (e.g., 'front-yard-cam'):");
        if (!cameraName || cameraName.trim() === "") {
            setStatus("Camera name cannot be empty.", "error");
            return;
        }
        if (/[.\s\[\]\#\*\/]/.test(cameraName)) {
            setStatus("Camera name contains invalid characters (e.g., . / [ ] # * space). Please use a simple name.", "error");
            return;
        }

        // Check if camera name already exists
        // This requires knowing the current config structure. Assume 'cameras' is a top-level key.
        // A simple check: see if a fieldset with this data-key already exists.
        const existingCameraFieldset = configFormContainer.querySelector(`fieldset[data-key="cameras.${cameraName}"]`);
        if (existingCameraFieldset) {
            setStatus(`A camera with the name '${cameraName}' already exists.`, "error");
            return;
        }

        let camerasFieldset = configFormContainer.querySelector('fieldset[data-key="cameras"]');
        if (!camerasFieldset) {
            // If no cameras section exists yet, create it.
            // This might happen if the config is entirely empty or has no 'cameras' key.
            camerasFieldset = document.createElement('fieldset');
            const legend = document.createElement('legend');
            legend.textContent = 'cameras';
            camerasFieldset.appendChild(legend);
            camerasFieldset.dataset.key = 'cameras';
            camerasFieldset.dataset.type = 'object'; // 'cameras' is an object containing camera items
            configFormContainer.appendChild(camerasFieldset); // Or insert in a specific order if needed
        }

        const newCameraFieldset = document.createElement('fieldset');
        const newCameraLegend = document.createElement('legend');
        newCameraLegend.textContent = cameraName;
        newCameraFieldset.appendChild(newCameraLegend);
        newCameraFieldset.dataset.key = `cameras.${cameraName}`; // This is how it will be identified in getFormDataAsJson
        newCameraFieldset.dataset.type = 'object'; // Each camera is an object

        // Add source type selector
        const typeSelectorContainer = document.createElement('div');
        typeSelectorContainer.classList.add('type-selector-container');
        const selectLabel = document.createElement('label');
        selectLabel.textContent = 'Select camera source type: ';
        typeSelectorContainer.appendChild(selectLabel);

        const sourceTypeSelect = document.createElement('select');
        availableCameraSourceTypes.forEach(type => {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            sourceTypeSelect.appendChild(option);
        });
        typeSelectorContainer.appendChild(sourceTypeSelect);

        const confirmButton = document.createElement('button');
        confirmButton.textContent = 'Confirm Source Type';
        confirmButton.type = 'button';
        confirmButton.addEventListener('click', () => {
            const selectedSourceType = sourceTypeSelect.value;
            typeSelectorContainer.remove(); // Remove selector UI
            renderCameraItem(newCameraFieldset, cameraName, selectedSourceType);
        });
        typeSelectorContainer.appendChild(confirmButton);
        newCameraFieldset.appendChild(typeSelectorContainer);

        camerasFieldset.appendChild(newCameraFieldset);
        setStatus(`Camera '${cameraName}' structure added. Configure and save.`, 'info');
    }

    function renderCameraItem(cameraFieldset, cameraNameKey, selectedSourceType) {
        // cameraNameKey is the string name like "front-yard-cam"
        // cameraFieldset is the fieldset for this specific camera.
        // Its data-key should be `cameras.${cameraNameKey}`

        const basePath = `cameras.${cameraNameKey}`; // Base path for data-keys

        // Hidden input for the source type if needed for saving, though not directly part of fenetre config structure
        // For now, the presence of url/local_command/gopro_ip keys will define the type.

        // Render source-specific fields
        const sourceTypeDefinition = cameraSourceTypes[selectedSourceType];
        if (sourceTypeDefinition) {
            const sourceGroup = document.createElement('div');
            sourceGroup.classList.add('camera-source-group');
            const groupLegend = document.createElement('h4');
            groupLegend.textContent = `Source: ${selectedSourceType}`;
            sourceGroup.appendChild(groupLegend);

            sourceTypeDefinition.order.forEach(fieldName => {
                const field = sourceTypeDefinition.fields[fieldName];
                const fieldKey = `${basePath}.${fieldName}`;
                appendFieldToForm(sourceGroup, fieldName, field, fieldKey);
            });
            cameraFieldset.appendChild(sourceGroup);
        }

        // Render common camera fields
        const commonGroup = document.createElement('div');
        commonGroup.classList.add('camera-common-group');
        const commonLegend = document.createElement('h4');
        commonLegend.textContent = 'Common Settings';
        commonGroup.appendChild(commonLegend);

        commonCameraFieldsOrder.forEach(fieldName => {
            const field = commonCameraFields[fieldName];
            const fieldKey = `${basePath}.${fieldName}`;

            if (fieldName === 'postprocessing') {
                // Create an empty fieldset for postprocessing array
                const ppFieldset = document.createElement('fieldset');
                const ppLegend = document.createElement('legend');
                ppLegend.textContent = 'postprocessing (List)';
                ppFieldset.appendChild(ppLegend);
                ppFieldset.dataset.key = fieldKey; // e.g., cameras.mycam.postprocessing
                ppFieldset.dataset.type = 'array';

                const addButton = document.createElement('button');
                addButton.textContent = 'Add Postprocessing Step';
                addButton.type = 'button';
                addButton.classList.add('add-item-btn');
                // Ensure newIndex is calculated correctly based on items in this specific ppFieldset
                addButton.addEventListener('click', () => {
                     const currentPPItemCount = ppFieldset.querySelectorAll(':scope > .array-item, :scope > .postprocessing-item').length;
                     addArrayItem(ppFieldset, fieldKey, currentPPItemCount, {}); // Pass empty object as template for postproc
                });
                ppFieldset.appendChild(addButton);
                commonGroup.appendChild(ppFieldset);
            } else {
                appendFieldToForm(commonGroup, fieldName, field, fieldKey);
            }
        });
        cameraFieldset.appendChild(commonGroup);

        // Add a remove button for this camera
        const removeCameraButton = document.createElement('button');
        removeCameraButton.textContent = 'Remove This Camera';
        removeCameraButton.type = 'button';
        removeCameraButton.classList.add('remove-camera-btn');
        removeCameraButton.addEventListener('click', () => {
            cameraFieldset.remove();
            setStatus(`Camera '${cameraNameKey}' removed from UI. Save to confirm.`, 'info');
        });
        cameraFieldset.appendChild(removeCameraButton);

    }

    // Helper function to append a single field (label + input) to a parent element
    function appendFieldToForm(parentElement, fieldName, fieldConfig, fieldKey) {
        const label = document.createElement('label');
        label.textContent = fieldName;
        label.htmlFor = fieldKey;
        parentElement.appendChild(label);

        let input;
        if (fieldConfig.type === 'checkbox') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = fieldConfig.default;
        } else if (fieldConfig.type === 'number') {
            input = document.createElement('input');
            input.type = 'number';
            input.value = fieldConfig.default;
            if (fieldConfig.step) input.step = fieldConfig.step;
        } else if (fieldConfig.type === 'textarea') {
            input = document.createElement('textarea');
            input.value = fieldConfig.default;
            input.rows = (fieldConfig.default.match(/\n/g) || []).length + 2;
        } else { // 'text' or other
            input = document.createElement('input');
            input.type = 'text';
            input.value = fieldConfig.default;
        }
        input.id = fieldKey;
        input.dataset.key = fieldKey;
        parentElement.appendChild(input);
        parentElement.appendChild(document.createElement('br'));
    }

});

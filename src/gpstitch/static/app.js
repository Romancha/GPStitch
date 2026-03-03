// GPStitch Application

// State
let sessionId = null;
let fileInfo = null;

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfoDiv = document.getElementById('file-info');
const configureSection = document.getElementById('configure-section');
const previewSection = document.getElementById('preview-section');
const commandSection = document.getElementById('command-section');

const layoutSelect = document.getElementById('layout-select');
const unitsSpeed = document.getElementById('units-speed');
const unitsAltitude = document.getElementById('units-altitude');
const unitsDistance = document.getElementById('units-distance');
const unitsTemperature = document.getElementById('units-temperature');
const mapStyle = document.getElementById('map-style');
const frameTime = document.getElementById('frame-time');

const generatePreviewBtn = document.getElementById('generate-preview');
const previewLoading = document.getElementById('preview-loading');
const previewImage = document.getElementById('preview-image');
const previewInfo = document.getElementById('preview-info');

const outputFilename = document.getElementById('output-filename');
const generateCommandBtn = document.getElementById('generate-command');
const commandContainer = document.getElementById('command-container');
const commandOutput = document.getElementById('command-output');
const copyCommandBtn = document.getElementById('copy-command');

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    setupFileUpload();
    await loadOptions();
    setupEventListeners();

    // Try to restore session from localStorage
    await restoreSession();
}

async function restoreSession() {
    const savedSessionId = localStorage.getItem('gopro_editor_session_id');
    if (!savedSessionId) return;

    try {
        // Check if session still exists on server
        const response = await fetch(`/api/session/${savedSessionId}`);
        if (response.ok) {
            const data = await response.json();
            sessionId = savedSessionId;
            fileInfo = data;
            displayFileInfo(data);
            showConfigureSection();
        } else {
            // Session expired, clear localStorage
            localStorage.removeItem('gopro_editor_session_id');
        }
    } catch (error) {
        console.error('Failed to restore session:', error);
        localStorage.removeItem('gopro_editor_session_id');
    }
}

// File Upload
function setupFileUpload() {
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
}

function handleDragOver(e) {
    e.preventDefault();
    dropZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    dropZone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        uploadFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        uploadFile(files[0]);
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    dropZone.innerHTML = '<p>Uploading...</p>';

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        sessionId = data.session_id;
        fileInfo = data;

        // Save session_id to localStorage so editor can use it
        localStorage.setItem('gopro_editor_session_id', sessionId);

        displayFileInfo(data);
        showConfigureSection();
    } catch (error) {
        dropZone.innerHTML = `
            <p>Drag and drop a file here, or click to select</p>
            <p class="hint">Supported: MP4, GPX, FIT</p>
            <p class="error-message">${error.message}</p>
        `;
    }
}

function displayFileInfo(data) {
    const fileNameDiv = fileInfoDiv.querySelector('.file-name');
    const fileDetailsDiv = fileInfoDiv.querySelector('.file-details');

    fileNameDiv.textContent = data.filename;

    let details = `Type: ${data.file_type.toUpperCase()}`;

    if (data.video_metadata) {
        const vm = data.video_metadata;
        details += ` | Resolution: ${vm.width}x${vm.height}`;
        details += ` | Duration: ${formatDuration(vm.duration_seconds)}`;
        details += ` | FPS: ${vm.frame_rate.toFixed(2)}`;
        details += ` | GPS: ${vm.has_gps ? 'Yes' : 'No'}`;
    }

    if (data.gpx_fit_metadata) {
        const gm = data.gpx_fit_metadata;
        details += ` | GPS Points: ${gm.gps_point_count}`;
        if (gm.duration_seconds) {
            details += ` | Duration: ${formatDuration(gm.duration_seconds)}`;
        }
    }

    fileDetailsDiv.textContent = details;
    fileInfoDiv.classList.remove('hidden');

    // Reset drop zone for potential re-upload
    dropZone.innerHTML = `
        <p>Drag and drop a file here, or click to select</p>
        <p class="hint">Supported: MP4, GPX, FIT</p>
    `;
}

function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Load Options
async function loadOptions() {
    try {
        // Load layouts
        const layoutsResponse = await fetch('/api/layouts');
        const layoutsData = await layoutsResponse.json();
        populateSelect(layoutSelect, layoutsData.layouts.map(l => ({
            value: l.name,
            label: `${l.display_name} (${l.width}x${l.height})`
        })));

        // Load unit options
        const unitsResponse = await fetch('/api/options/units');
        const unitsData = await unitsResponse.json();

        for (const category of unitsData.categories) {
            const select = document.getElementById(`units-${category.name}`);
            if (select) {
                populateSelect(select, category.options.map(o => ({
                    value: o.value,
                    label: o.label
                })), category.default);
            }
        }

        // Load map styles
        const stylesResponse = await fetch('/api/options/map-styles');
        const stylesData = await stylesResponse.json();
        populateSelect(mapStyle, stylesData.styles.map(s => ({
            value: s.name,
            label: s.display_name
        })), 'osm');

    } catch (error) {
        console.error('Failed to load options:', error);
    }
}

function populateSelect(select, options, defaultValue = null) {
    select.innerHTML = '';
    for (const option of options) {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.label;
        if (defaultValue && option.value === defaultValue) {
            opt.selected = true;
        }
        select.appendChild(opt);
    }
}

// Event Listeners
function setupEventListeners() {
    generatePreviewBtn.addEventListener('click', generatePreview);
    generateCommandBtn.addEventListener('click', generateCommand);
    copyCommandBtn.addEventListener('click', copyCommand);
}

function showConfigureSection() {
    configureSection.classList.remove('hidden');
    previewSection.classList.remove('hidden');
    commandSection.classList.remove('hidden');
}

// Preview Generation
async function generatePreview() {
    if (!sessionId) return;

    generatePreviewBtn.disabled = true;
    previewLoading.classList.remove('hidden');
    previewImage.classList.add('hidden');
    previewInfo.textContent = '';

    const requestData = {
        session_id: sessionId,
        layout: layoutSelect.value,
        frame_time_ms: Math.floor(parseFloat(frameTime.value) * 1000),
        units_speed: unitsSpeed.value,
        units_altitude: unitsAltitude.value,
        units_distance: unitsDistance.value,
        units_temperature: unitsTemperature.value,
        map_style: mapStyle.value,
    };

    try {
        const response = await fetch('/api/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Preview generation failed');
        }

        const data = await response.json();

        previewImage.src = `data:image/png;base64,${data.image_base64}`;
        previewImage.classList.remove('hidden');
        previewInfo.textContent = `Preview at ${(data.frame_time_ms / 1000).toFixed(1)}s | ${data.width}x${data.height}`;

    } catch (error) {
        previewInfo.textContent = `Error: ${error.message}`;
        previewInfo.classList.add('error-message');
    } finally {
        generatePreviewBtn.disabled = false;
        previewLoading.classList.add('hidden');
    }
}

// Command Generation
async function generateCommand() {
    if (!sessionId) return;

    const requestData = {
        session_id: sessionId,
        layout: layoutSelect.value,
        output_filename: outputFilename.value || 'output.mp4',
        units_speed: unitsSpeed.value,
        units_altitude: unitsAltitude.value,
        units_distance: unitsDistance.value,
        units_temperature: unitsTemperature.value,
        map_style: mapStyle.value,
    };

    try {
        const response = await fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Command generation failed');
        }

        const data = await response.json();

        commandOutput.textContent = data.command;
        commandContainer.classList.remove('hidden');

    } catch (error) {
        commandOutput.textContent = `Error: ${error.message}`;
        commandContainer.classList.remove('hidden');
    }
}

async function copyCommand() {
    try {
        await navigator.clipboard.writeText(commandOutput.textContent);
        const originalText = copyCommandBtn.textContent;
        copyCommandBtn.textContent = 'Copied!';
        setTimeout(() => {
            copyCommandBtn.textContent = originalText;
        }, 2000);
    } catch (error) {
        console.error('Failed to copy:', error);
    }
}

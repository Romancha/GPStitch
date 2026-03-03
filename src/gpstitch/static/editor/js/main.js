/**
 * Main - Entry point for the visual layout editor
 */

// Components
let canvas, widgetPalette, propertiesPanel, layersPanel;

// Initialize editor
document.addEventListener('DOMContentLoaded', async () => {
    try {
        await initEditor();
    } catch (error) {
        console.error('Failed to initialize editor:', error);
        showStatus('Failed to initialize editor: ' + error.message, 'error');
    }
});

async function initEditor() {
    showStatus('Loading...');

    // Initialize history manager
    editorState.history = new HistoryManager(editorState);

    // Load widget metadata
    const metadata = await apiClient.getWidgetMetadata();
    editorState.widgetMetadata = metadata.widgets;

    // Index by type
    editorState.widgetMetadataByType = {};
    for (const widget of metadata.widgets) {
        editorState.widgetMetadataByType[widget.type] = widget;
    }

    // Initialize components
    widgetPalette = new WidgetPalette(
        document.getElementById('widget-palette'),
        editorState
    );

    canvas = new Canvas(
        document.getElementById('canvas'),
        document.getElementById('canvas-viewport'),
        editorState
    );

    propertiesPanel = new PropertiesPanel(
        document.getElementById('properties-panel'),
        editorState
    );

    layersPanel = new LayersPanel(
        document.getElementById('layers-panel'),
        editorState
    );

    // Load predefined layouts for modal
    loadPredefinedLayouts();

    // Try to restore saved layout or create new
    const savedLayout = storage.loadLayout();
    if (savedLayout) {
        editorState.setLayout(savedLayout);
        showStatus('Restored saved layout');
    } else {
        editorState.newLayout();
        showStatus('Ready');
    }

    // Render components
    widgetPalette.render();
    canvas.render();
    canvas.fitToView();

    // Attach toolbar listeners
    attachToolbarListeners();

    // Attach modal listeners
    attachModalListeners();

    // Update layout name input
    updateLayoutNameInput();

    showStatus('Ready');
}

function attachToolbarListeners() {
    // New layout
    document.getElementById('btn-new').addEventListener('click', () => {
        if (editorState.isDirty && !confirm('Discard unsaved changes?')) return;
        editorState.newLayout();
        storage.clearLayout();
        updateLayoutNameInput();
        showStatus('New layout created');
    });

    // Load layout
    document.getElementById('btn-load').addEventListener('click', () => {
        showModal('load-modal');
    });

    // Save layout
    document.getElementById('btn-save').addEventListener('click', () => {
        storage.saveLayout(editorState.layout);
        editorState.isDirty = false;
        showStatus('Layout saved to browser');
    });

    // Export XML
    document.getElementById('btn-export').addEventListener('click', async () => {
        try {
            showStatus('Exporting...');
            const result = await apiClient.exportToXML(editorState.layout);

            // Download file
            const blob = new Blob([result.xml], { type: 'application/xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = result.filename;
            a.click();
            URL.revokeObjectURL(url);

            showStatus('XML exported');
        } catch (error) {
            showStatus('Export failed: ' + error.message, 'error');
        }
    });

    // Preview
    document.getElementById('btn-preview').addEventListener('click', async () => {
        showModal('preview-modal');
        const loadingEl = document.getElementById('preview-loading');
        const imageEl = document.getElementById('preview-image');
        const errorEl = document.getElementById('preview-error');

        loadingEl.style.display = 'flex';
        imageEl.style.display = 'none';
        errorEl.style.display = 'none';

        try {
            const sessionId = storage.getOrCreateSessionId();

            if (!sessionId) {
                throw new Error('No file uploaded. Please upload a video/GPX/FIT file on the main page first.');
            }

            console.log('Preview request with session:', sessionId);
            console.log('Layout:', editorState.layout);
            const result = await apiClient.generatePreview(sessionId, editorState.layout);
            console.log('Preview result keys:', Object.keys(result));
            console.log('image_base64 length:', result.image_base64 ? result.image_base64.length : 0);

            if (result.image_base64) {
                const imgSrc = 'data:image/png;base64,' + result.image_base64;
                console.log('Setting image src, length:', imgSrc.length);

                // Add onload/onerror handlers
                imageEl.onload = () => {
                    console.log('Image loaded successfully!');
                    console.log('Image natural dimensions:', imageEl.naturalWidth, 'x', imageEl.naturalHeight);
                    console.log('Image display dimensions:', imageEl.offsetWidth, 'x', imageEl.offsetHeight);
                };
                imageEl.onerror = (e) => {
                    console.error('Image failed to load:', e);
                };

                imageEl.src = imgSrc;
                imageEl.style.display = 'block';
                console.log('Image element display set to:', imageEl.style.display);
            } else {
                console.log('No image_base64 in result');
                errorEl.textContent = 'No preview available. Upload a video file first.';
                errorEl.style.display = 'block';
            }
        } catch (error) {
            errorEl.textContent = 'Preview failed: ' + error.message;
            errorEl.style.display = 'block';
        } finally {
            loadingEl.style.display = 'none';
        }
    });

    // Undo/Redo
    document.getElementById('btn-undo').addEventListener('click', () => {
        editorState.history.undo();
    });

    document.getElementById('btn-redo').addEventListener('click', () => {
        editorState.history.redo();
    });

    // History state changes
    editorState.on('history:changed', ({ canUndo, canRedo }) => {
        document.getElementById('btn-undo').disabled = !canUndo;
        document.getElementById('btn-redo').disabled = !canRedo;
    });

    // Keyboard shortcuts for undo/redo
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'z' && !e.shiftKey) {
            e.preventDefault();
            editorState.history.undo();
        }
        if ((e.ctrlKey && e.key === 'y') || (e.ctrlKey && e.shiftKey && e.key === 'z')) {
            e.preventDefault();
            editorState.history.redo();
        }
    });

    // Zoom controls
    document.getElementById('btn-zoom-in').addEventListener('click', () => canvas.zoomIn());
    document.getElementById('btn-zoom-out').addEventListener('click', () => canvas.zoomOut());
    document.getElementById('btn-zoom-fit').addEventListener('click', () => canvas.fitToView());

    // Grid and snap toggles
    document.getElementById('toggle-grid').addEventListener('change', (e) => {
        editorState.updateCanvas({ grid_enabled: e.target.checked });
        canvas.render();
    });

    document.getElementById('toggle-snap').addEventListener('change', (e) => {
        editorState.updateCanvas({ snap_to_grid: e.target.checked });
    });

    // Canvas size
    document.getElementById('canvas-width').addEventListener('change', (e) => {
        const width = parseInt(e.target.value) || 1920;
        editorState.updateCanvas({ width });
        canvas.render();
    });

    document.getElementById('canvas-height').addEventListener('change', (e) => {
        const height = parseInt(e.target.value) || 1080;
        editorState.updateCanvas({ height });
        canvas.render();
    });

    // Layout name
    document.getElementById('layout-name').addEventListener('change', (e) => {
        if (editorState.layout) {
            editorState.layout.metadata.name = e.target.value;
            editorState.isDirty = true;
        }
    });

    // Tab switching
    document.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;

            // Update tab buttons
            document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
            document.getElementById(`${tabName}-tab`).style.display = 'block';
        });
    });
}

function attachModalListeners() {
    // Close modal buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').style.display = 'none';
        });
    });

    // Click outside to close
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    });

    // Load from file
    document.getElementById('btn-load-file').addEventListener('click', () => {
        document.getElementById('load-file-input').click();
    });

    document.getElementById('load-file-input').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            showStatus('Loading file...');
            const result = await apiClient.loadLayoutFromFile(file);
            editorState.setLayout(result.layout);
            hideModal('load-modal');
            updateLayoutNameInput();
            showStatus('Layout loaded');
        } catch (error) {
            showStatus('Failed to load file: ' + error.message, 'error');
        }

        // Reset file input
        e.target.value = '';
    });

    // Load predefined
    document.getElementById('btn-load-predefined').addEventListener('click', async () => {
        const select = document.getElementById('predefined-layouts');
        const layoutName = select.value;
        if (!layoutName) {
            showStatus('Select a layout first', 'error');
            return;
        }

        try {
            showStatus('Loading layout...');
            const sessionId = storage.getOrCreateSessionId();
            const result = await apiClient.loadPredefinedLayout(sessionId, layoutName);
            editorState.setLayout(result.layout);
            hideModal('load-modal');
            updateLayoutNameInput();
            showStatus('Layout loaded');
        } catch (error) {
            showStatus('Failed to load layout: ' + error.message, 'error');
        }
    });
}

async function loadPredefinedLayouts() {
    try {
        const result = await apiClient.getPredefinedLayouts();
        const select = document.getElementById('predefined-layouts');

        select.innerHTML = '<option value="">Select a layout...</option>';
        for (const layout of result.layouts) {
            const option = document.createElement('option');
            option.value = layout.name;
            option.textContent = `${layout.display_name} (${layout.width}x${layout.height})`;
            select.appendChild(option);
        }
    } catch (error) {
        console.error('Failed to load predefined layouts:', error);
    }
}

function updateLayoutNameInput() {
    const input = document.getElementById('layout-name');
    if (editorState.layout) {
        input.value = editorState.layout.metadata.name || 'Untitled Layout';
    }

    // Update canvas size inputs
    if (editorState.layout) {
        document.getElementById('canvas-width').value = editorState.layout.canvas.width;
        document.getElementById('canvas-height').value = editorState.layout.canvas.height;
        document.getElementById('toggle-grid').checked = editorState.layout.canvas.grid_enabled;
        document.getElementById('toggle-snap').checked = editorState.layout.canvas.snap_to_grid;
    }
}

function showModal(modalId) {
    document.getElementById(modalId).style.display = 'flex';
}

function hideModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

function showStatus(message, type = 'info') {
    const statusEl = document.getElementById('status-message');
    statusEl.textContent = message;
    statusEl.className = type;
}

// Auto-save on changes
editorState.on('widget:added', () => storage.saveLayout(editorState.layout));
editorState.on('widget:removed', () => storage.saveLayout(editorState.layout));
editorState.on('property:changed', () => storage.saveLayout(editorState.layout));
editorState.on('widget:updated', () => {
    // Debounce auto-save during drag
    clearTimeout(window._autoSaveTimeout);
    window._autoSaveTimeout = setTimeout(() => {
        storage.saveLayout(editorState.layout);
    }, 500);
});

/**
 * ModeToggle - Handles switching between Quick and Advanced modes
 */

class ModeToggle {
    constructor(state) {
        this.state = state;

        // DOM elements
        this.quickBtn = document.getElementById('mode-quick');
        this.advancedBtn = document.getElementById('mode-advanced');

        // UI elements to toggle
        this.quickToolbar = document.getElementById('quick-toolbar');
        this.advancedToolbar = document.getElementById('advanced-toolbar');
        this.widgetPaletteContainer = document.getElementById('widget-palette-container');
        this.configPanel = document.getElementById('config-panel');
        this.propertiesPanel = document.getElementById('properties-panel');
        this.layersPanel = document.getElementById('layers-panel');
        this.previewContainer = document.getElementById('preview-container');
        this.canvasContainer = document.getElementById('canvas-container');
        this.previewViewport = document.querySelector('.preview-viewport');

        // Editor components (initialized lazily)
        this.editorInitialized = false;
        this.canvas = null;
        this.widgetPalette = null;
        this.propertiesPanel_component = null;
        this.layersPanel_component = null;
        this.templateManager = null;

        // Template and hint elements
        this.templateSelect = document.getElementById('template-select');
        this.canvasEmptyHint = document.getElementById('canvas-empty-hint');

        this._attachEventListeners();

        // Set initial mode from state
        this._applyMode(this.state.mode);
    }

    _attachEventListeners() {
        this.quickBtn.addEventListener('click', () => {
            this.setMode('quick');
        });

        this.advancedBtn.addEventListener('click', () => {
            this.setMode('advanced');
        });

        // Listen for mode changes from state
        this.state.on('mode:changed', ({ mode }) => {
            this._applyMode(mode);
        });

        // Tab switching in right panel
        const tabs = document.querySelectorAll('.panel-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                this._switchTab(tabName);
            });
        });
    }

    /**
     * Set mode
     * @param {'quick' | 'advanced'} mode
     */
    setMode(mode) {
        this.state.setMode(mode);
    }

    /**
     * Apply mode to UI
     */
    _applyMode(mode) {
        if (mode === 'quick') {
            this._showQuickMode();
        } else {
            this._showAdvancedMode();
        }
    }

    _showQuickMode() {
        // Update buttons
        this.quickBtn.classList.add('active');
        this.advancedBtn.classList.remove('active');

        // Show quick toolbar, hide advanced
        this.quickToolbar.style.display = 'flex';
        this.advancedToolbar.style.display = 'none';

        // Hide widget palette
        if (this.widgetPaletteContainer) {
            this.widgetPaletteContainer.style.display = 'none';
        }

        // Remove canvas-active class to restore centering for quick mode
        if (this.previewViewport) {
            this.previewViewport.classList.remove('canvas-active');
        }

        // Show preview container, hide canvas
        if (this.previewContainer) {
            this.previewContainer.classList.remove('hidden');
        }
        // Restore empty state visibility control to UnifiedApp
        const previewEmpty = document.getElementById('preview-empty');
        if (previewEmpty) {
            // Will be controlled by UnifiedApp based on session state
            previewEmpty.classList.remove('force-hidden');
            previewEmpty.style.display = '';
        }
        if (this.canvasContainer) {
            this.canvasContainer.classList.remove('visible');
            this.canvasContainer.style.display = 'none';
        }

        // Switch to config tab
        this._switchTab('config');

        // Make sure config tab is available
        const configTab = document.querySelector('.panel-tab[data-tab="config"]');
        if (configTab) {
            configTab.style.display = '';
        }

        // Hide properties and layers tabs in quick mode
        const propsTab = document.querySelector('.panel-tab[data-tab="properties"]');
        const layersTab = document.querySelector('.panel-tab[data-tab="layers"]');
        if (propsTab) {
            propsTab.style.display = 'none';
        }
        if (layersTab) {
            layersTab.style.display = 'none';
        }
    }

    async _showAdvancedMode() {
        // Update buttons
        this.quickBtn.classList.remove('active');
        this.advancedBtn.classList.add('active');

        // Hide quick toolbar, show advanced
        this.quickToolbar.style.display = 'none';
        this.advancedToolbar.style.display = 'flex';

        // Show widget palette
        if (this.widgetPaletteContainer) {
            this.widgetPaletteContainer.style.display = 'block';
        }

        // Add canvas-active class to disable centering and let canvas-viewport handle scroll
        if (this.previewViewport) {
            this.previewViewport.classList.add('canvas-active');
        }

        // Hide preview container and empty state, show canvas
        if (this.previewContainer) {
            this.previewContainer.classList.add('hidden');
        }
        // Hide empty state in advanced mode
        const previewEmpty = document.getElementById('preview-empty');
        if (previewEmpty) {
            previewEmpty.classList.add('force-hidden');
            previewEmpty.style.display = 'none';
        }
        if (this.canvasContainer) {
            this.canvasContainer.classList.add('visible');
            // Clear any inline display style to let CSS .visible class handle it
            this.canvasContainer.style.display = '';
        }

        // Initialize editor if not already done
        if (!this.editorInitialized) {
            await this._initializeEditor();
        }

        // Note: Don't try to sync Quick Mode layout to Advanced Mode template selector
        // Quick Mode layout names (e.g., "1080p_60fps") don't match Advanced Mode template
        // format ("custom:Name" or "predefined:Name"), causing browser to reset to first option

        // Update canvas hint after mode switch
        this._updateCanvasHint();

        // Switch to properties tab
        this._switchTab('properties');

        // Show all tabs in advanced mode (config, properties, layers)
        const configTab = document.querySelector('.panel-tab[data-tab="config"]');
        const propsTab = document.querySelector('.panel-tab[data-tab="properties"]');
        const layersTab = document.querySelector('.panel-tab[data-tab="layers"]');
        if (configTab) {
            configTab.style.display = '';
        }
        if (propsTab) {
            propsTab.style.display = '';
        }
        if (layersTab) {
            layersTab.style.display = '';
        }
    }

    /**
     * Initialize editor components (lazy loading)
     */
    async _initializeEditor() {
        try {
            // Initialize editor state with history manager
            editorState.history = new HistoryManager(editorState);

            // Load widget metadata with error feedback
            try {
                const metadata = await apiClient.getWidgetMetadata();
                console.log('Widget metadata response:', metadata);
                editorState.widgetMetadata = metadata.widgets || [];
                console.log(`Loaded ${editorState.widgetMetadata.length} widgets`);
                if (editorState.widgetMetadata.length > 0) {
                    console.log('First widget:', editorState.widgetMetadata[0]);
                }

                // Index by type
                editorState.widgetMetadataByType = {};
                for (const widget of editorState.widgetMetadata) {
                    editorState.widgetMetadataByType[widget.type] = widget;
                }
            } catch (error) {
                console.error('Failed to load widget metadata:', error);
                editorState.widgetMetadata = [];
                editorState.widgetMetadataByType = {};
                // Show error to user
                const paletteContainer = document.getElementById('widget-palette');
                if (paletteContainer) {
                    paletteContainer.innerHTML = '<p class="error-text">Failed to load widgets. Please refresh.</p>';
                }
            }

            // Try to load current Quick Mode layout, or create new layout
            if (!editorState.layout) {
                const quickLayout = this.state.quickConfig?.layout;
                if (quickLayout) {
                    try {
                        const sessionId = this.state.sessionId || 'default';
                        const response = await apiClient.loadPredefinedLayout(sessionId, quickLayout);
                        if (response.layout) {
                            editorState.setLayout(response.layout);
                            console.log('Loaded Quick Mode layout:', quickLayout);
                        } else {
                            editorState.newLayout();
                        }
                    } catch (e) {
                        console.log('Could not load Quick Mode layout, creating new:', e);
                        editorState.newLayout();
                    }
                } else {
                    editorState.newLayout();
                }
            }

            // Initialize widget palette
            const paletteContainer = document.getElementById('widget-palette');
            if (paletteContainer && window.WidgetPalette && editorState.widgetMetadata.length > 0) {
                this.widgetPalette = new WidgetPalette(paletteContainer, editorState);
                this.widgetPalette.render();
            }

            // Initialize canvas
            const canvasEl = document.getElementById('canvas');
            const viewportEl = document.getElementById('canvas-viewport');
            if (canvasEl && viewportEl && window.Canvas) {
                this.canvas = new Canvas(canvasEl, viewportEl, editorState);
                this.canvas.render();
                this.canvas.fitToView();
            }

            // Initialize properties panel
            const propsEl = document.getElementById('properties-panel');
            if (propsEl && window.PropertiesPanel) {
                this.propertiesPanel_component = new PropertiesPanel(propsEl, editorState);
            }

            // Initialize layers panel
            const layersEl = document.getElementById('layers-panel');
            if (layersEl && window.LayersPanel) {
                this.layersPanel_component = new LayersPanel(layersEl, editorState);
            }

            // Wire up undo/redo buttons
            this._setupEditorToolbar();

            // Load predefined templates
            await this._loadTemplateList();

            // Update canvas hint visibility
            this._updateCanvasHint();

            // Update hint when widgets change
            editorState.on('layout:changed', () => this._updateCanvasHint());
            editorState.on('widget:added', () => this._updateCanvasHint());
            editorState.on('widget:removed', () => this._updateCanvasHint());

            this.editorInitialized = true;
            console.log('Editor initialized successfully');

        } catch (error) {
            console.error('Failed to initialize editor:', error);
        }
    }

    /**
     * Load list of predefined templates and initialize TemplateManager
     */
    async _loadTemplateList() {
        try {
            const response = await apiClient.getPredefinedLayouts();

            // Initialize TemplateManager
            this.templateManager = new TemplateManager(this, this.state);

            if (response.layouts) {
                this.templateManager.setPredefinedLayouts(response.layouts);
            }
        } catch (error) {
            console.error('Failed to load template list:', error);
        }
    }

    /**
     * Load a specific predefined template (called by TemplateManager)
     */
    async _loadTemplate(templateName) {
        try {
            const sessionId = this.state.sessionId || 'default';
            const response = await apiClient.loadPredefinedLayout(sessionId, templateName);
            if (response.layout) {
                editorState.setLayout(response.layout);
                this._updateCanvasHint();
                if (this.canvas) this.canvas.render();
            }
        } catch (error) {
            console.error('Failed to load template:', error);
            alert('Failed to load template: ' + error.message);
        }
    }

    /**
     * Update canvas hint visibility based on widget count
     */
    _updateCanvasHint() {
        if (this.canvasEmptyHint) {
            const hasWidgets = editorState.layout?.widgets?.length > 0;
            this.canvasEmptyHint.classList.toggle('hidden', hasWidgets);
        }
    }

    _setupEditorToolbar() {
        const undoBtn = document.getElementById('btn-undo');
        const redoBtn = document.getElementById('btn-redo');
        const zoomInBtn = document.getElementById('btn-zoom-in');
        const zoomOutBtn = document.getElementById('btn-zoom-out');
        const zoomFitBtn = document.getElementById('btn-zoom-fit');
        const gridToggle = document.getElementById('toggle-grid');
        const snapToggle = document.getElementById('toggle-snap');

        if (undoBtn) {
            undoBtn.addEventListener('click', () => editorState.history?.undo());
        }

        if (redoBtn) {
            redoBtn.addEventListener('click', () => editorState.history?.redo());
        }

        // Update undo/redo button states
        editorState.on('history:changed', ({ canUndo, canRedo }) => {
            if (undoBtn) undoBtn.disabled = !canUndo;
            if (redoBtn) redoBtn.disabled = !canRedo;
        });

        if (zoomInBtn && this.canvas) {
            zoomInBtn.addEventListener('click', () => this.canvas.zoomIn());
        }

        if (zoomOutBtn && this.canvas) {
            zoomOutBtn.addEventListener('click', () => this.canvas.zoomOut());
        }

        if (zoomFitBtn && this.canvas) {
            zoomFitBtn.addEventListener('click', () => this.canvas.fitToView());
        }

        if (gridToggle) {
            gridToggle.addEventListener('change', (e) => {
                editorState.updateCanvas({ grid_enabled: e.target.checked });
                if (this.canvas) this.canvas.render();
            });
        }

        if (snapToggle) {
            snapToggle.addEventListener('change', (e) => {
                editorState.updateCanvas({ snap_to_grid: e.target.checked });
            });
        }
    }

    /**
     * Switch active tab in right panel
     */
    _switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.panel-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.panel-content').forEach(content => {
            content.classList.add('hidden');
        });

        const activeContent = document.getElementById(`${tabName}-panel`);
        if (activeContent) {
            activeContent.classList.remove('hidden');
        }
    }
}

// Export
window.ModeToggle = ModeToggle;

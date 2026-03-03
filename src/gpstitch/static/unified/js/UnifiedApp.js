/**
 * UnifiedApp - Main application controller
 * Orchestrates all components and handles the main user flow
 */

class UnifiedApp {
    constructor() {
        this.state = window.unifiedState;

        // Components
        this.fileUploader = null;
        this.timeline = null;
        this.modeToggle = null;
        this.previewDebouncer = new PreviewDebouncer(500);

        // DOM elements
        this.fileContextEl = document.getElementById('file-context');
        this.previewEmptyEl = document.getElementById('preview-empty');
        this.previewLoadingEl = document.getElementById('preview-loading');
        this.refreshBtn = document.getElementById('btn-refresh-preview');
        this.previewContainerEl = document.getElementById('preview-container');
        this.previewImageEl = document.getElementById('preview-image');
        this.statusMessageEl = document.getElementById('status-message');
        this.statusFrameEl = document.getElementById('status-frame');

        // Config selects
        this.layoutSelect = document.getElementById('layout-select');
        this.unitsSpeedSelect = document.getElementById('units-speed');
        this.unitsAltitudeSelect = document.getElementById('units-altitude');
        this.unitsDistanceSelect = document.getElementById('units-distance');
        this.unitsTemperatureSelect = document.getElementById('units-temperature');
        this.mapStyleSelect = document.getElementById('map-style');
        this.ffmpegProfileSelect = document.getElementById('ffmpeg-profile');
        this.ffmpegProfileHint = document.getElementById('ffmpeg-profile-hint');

        // GPS filter inputs
        this.gpsDopMaxInput = document.getElementById('gps-dop-max');
        this.gpsSpeedMaxInput = document.getElementById('gps-speed-max');

        // Auto preview checkbox
        this.autoPreviewCheckbox = document.getElementById('auto-preview');
    }

    /**
     * Initialize the application
     */
    async init() {
        try {
            this.showStatus('Loading...');

            // Load options
            await this._loadOptions();

            // Initialize components
            this._initComponents();

            // Set up event listeners
            this._attachEventListeners();

            // Try to restore session
            await this._restoreSession();

            // Apply initial mode (modeToggle handles this in constructor, but ensure it's ready)
            if (this.modeToggle) {
                this.modeToggle._applyMode(this.state.mode);
            }

            this.showStatus('Ready');

        } catch (error) {
            console.error('Failed to initialize app:', error);
            window.toast.error(error.message, { title: 'Initialization Failed', duration: 0 });
        }
    }

    /**
     * Load options from API
     */
    async _loadOptions() {
        // Load layouts
        const layoutsResponse = await fetch('/api/layouts');
        const layoutsData = await layoutsResponse.json();
        this._populateSelect(this.layoutSelect, layoutsData.layouts.map(l => ({
            value: l.name,
            label: `${l.display_name} (${l.width}x${l.height})`
        })), this.state.quickConfig.layout);

        // Load units
        const unitsResponse = await fetch('/api/options/units');
        const unitsData = await unitsResponse.json();

        for (const category of unitsData.categories) {
            const select = document.getElementById(`units-${category.name}`);
            if (select) {
                this._populateSelect(select, category.options.map(o => ({
                    value: o.value,
                    label: o.label
                })), this.state.quickConfig[`units${this._capitalize(category.name)}`] || category.default);
            }
        }

        // Load map styles
        const stylesResponse = await fetch('/api/options/map-styles');
        const stylesData = await stylesResponse.json();

        // Store map styles data for later use
        this._mapStyles = stylesData.styles;

        this._populateSelect(this.mapStyleSelect, stylesData.styles.map(s => ({
            value: s.name,
            label: s.requires_api_key ? `${s.display_name} (API key)` : s.display_name
        })), this.state.quickConfig.mapStyle);

        // Load FFmpeg profiles
        const profilesResponse = await fetch('/api/options/ffmpeg-profiles');
        const profilesData = await profilesResponse.json();

        // Store profiles data for hint display
        this._ffmpegProfiles = profilesData.profiles;

        this._populateSelect(this.ffmpegProfileSelect, profilesData.profiles.map(p => ({
            value: p.name,
            label: p.display_name
        })), this.state.quickConfig.ffmpegProfile);

        // Show initial hint
        this._updateFfmpegProfileHint(this.state.quickConfig.ffmpegProfile);
    }

    /**
     * Update FFmpeg profile hint text
     */
    _updateFfmpegProfileHint(profileName) {
        if (!this._ffmpegProfiles || !this.ffmpegProfileHint) return;

        const profile = this._ffmpegProfiles.find(p => p.name === profileName);
        if (profile) {
            this.ffmpegProfileHint.textContent = profile.description;
        } else {
            this.ffmpegProfileHint.textContent = '';
        }
    }

    /**
     * Check if selected map style requires API key and show warning
     */
    _checkMapStyleApiKey(styleName) {
        if (!this._mapStyles) return;

        const style = this._mapStyles.find(s => s.name === styleName);
        if (style && style.requires_api_key) {
            if (window.toast) {
                window.toast.warning(
                    `Map style "${style.display_name}" requires an API key. Preview may fail without it.`,
                    {
                        title: 'API Key Required',
                        duration: 6000,
                        action: 'Use OSM',
                        onAction: () => {
                            this.state.updateQuickConfig({ mapStyle: 'osm' });
                            this.mapStyleSelect.value = 'osm';
                        }
                    }
                );
            }
        }
    }

    _populateSelect(select, options, defaultValue) {
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

    _capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    /**
     * Initialize UI components
     */
    _initComponents() {
        // File uploader
        const uploaderContainer = document.getElementById('file-uploader-container');
        this.fileUploader = new FileUploader(uploaderContainer, null, this.state);

        // Timeline
        const timelineContainer = document.getElementById('timeline-container');
        this.timeline = new Timeline(timelineContainer, this.state);

        // Mode toggle
        this.modeToggle = new ModeToggle(this.state);

        // GPX Options Panel
        const gpxOptionsContainer = document.getElementById('gpx-options-container');
        if (gpxOptionsContainer) {
            this.gpxOptionsPanel = new GpxOptionsPanel(gpxOptionsContainer, this.state);
        }

        // GPS Quality Card (sidebar)
        const gpsQualityContainer = document.getElementById('gps-quality-container');
        if (gpsQualityContainer) {
            this.gpsQualityCard = new GPSQualityCard(gpsQualityContainer, this.state);
        }

        // GPS Quality Indicator (header)
        const gpsIndicatorContainer = document.getElementById('gps-indicator-container');
        if (gpsIndicatorContainer) {
            this.gpsQualityIndicator = new GPSQualityIndicator(gpsIndicatorContainer, this.state);
        }

        // Render Modal
        this.renderModal = new RenderModal(this.state);

        // Batch Render Modal
        this.batchRenderModal = new BatchRenderModal(this.state);
    }

    /**
     * Attach event listeners
     */
    _attachEventListeners() {
        // Config changes trigger preview update
        this.layoutSelect.addEventListener('change', () => {
            this.state.updateQuickConfig({ layout: this.layoutSelect.value });
            this._requestPreview();
        });

        this.unitsSpeedSelect.addEventListener('change', () => {
            this.state.updateQuickConfig({ unitsSpeed: this.unitsSpeedSelect.value });
            this._requestPreview();
        });

        this.unitsAltitudeSelect.addEventListener('change', () => {
            this.state.updateQuickConfig({ unitsAltitude: this.unitsAltitudeSelect.value });
            this._requestPreview();
        });

        this.unitsDistanceSelect.addEventListener('change', () => {
            this.state.updateQuickConfig({ unitsDistance: this.unitsDistanceSelect.value });
            this._requestPreview();
        });

        this.unitsTemperatureSelect.addEventListener('change', () => {
            this.state.updateQuickConfig({ unitsTemperature: this.unitsTemperatureSelect.value });
            this._requestPreview();
        });

        this.mapStyleSelect.addEventListener('change', () => {
            const newStyle = this.mapStyleSelect.value;
            this._checkMapStyleApiKey(newStyle);
            this.state.updateQuickConfig({ mapStyle: newStyle });
            this._requestPreview();
        });

        // FFmpeg profile change (no preview needed, only affects render)
        this.ffmpegProfileSelect.addEventListener('change', () => {
            const newProfile = this.ffmpegProfileSelect.value;
            this.state.updateQuickConfig({ ffmpegProfile: newProfile });
            this._updateFfmpegProfileHint(newProfile);
        });

        // GPS DOP Max change
        if (this.gpsDopMaxInput) {
            // Initialize from state
            this.gpsDopMaxInput.value = this.state.quickConfig.gpsDopMax;

            this.gpsDopMaxInput.addEventListener('change', () => {
                const value = parseFloat(this.gpsDopMaxInput.value) || 20;
                this.state.updateQuickConfig({ gpsDopMax: value });
                this._requestPreview();
            });
        }

        // GPS Speed Max change
        if (this.gpsSpeedMaxInput) {
            // Initialize from state
            this.gpsSpeedMaxInput.value = this.state.quickConfig.gpsSpeedMax;

            this.gpsSpeedMaxInput.addEventListener('change', () => {
                const value = parseFloat(this.gpsSpeedMaxInput.value) || 200;
                this.state.updateQuickConfig({ gpsSpeedMax: value });
                this._requestPreview();
            });
        }

        // Auto preview checkbox
        if (this.autoPreviewCheckbox) {
            // Initialize from state
            this.autoPreviewCheckbox.checked = this.state.autoPreview;

            this.autoPreviewCheckbox.addEventListener('change', () => {
                this.state.setAutoPreview(this.autoPreviewCheckbox.checked);
            });
        }

        // Refresh preview button
        const refreshBtn = document.getElementById('btn-refresh-preview');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this._generatePreview());
        }

        // Session changes
        this.state.on('session:changed', () => {
            this._updateFileContext();
            this._requestPreview();
        });

        // Files changed (secondary added/removed)
        this.state.on('files:changed', () => {
            this._updateFileContext();
            this._requestPreview();
        });

        // GPX options changed
        this.state.on('gpxOptions:changed', () => {
            this._requestPreview();
        });

        this.state.on('session:cleared', () => {
            this._hideFileContext();
            this._showPreviewEmpty();
        });

        // Timeline seek triggers preview
        this.state.on('timeline:seek', ({ timeMs }) => {
            this.statusFrameEl.textContent = `Frame: ${this.state.formatTime(timeMs)}`;
            if (this.state.mode === 'quick') {
                this._requestPreview();
            } else {
                this._requestPreviewForAdvanced();
            }
        });

        // Mode changes
        this.state.on('mode:changed', ({ mode }) => {
            // When switching modes, request preview if we have a valid session
            if (this.state.hasValidSession()) {
                // Small delay to let the UI update first
                setTimeout(() => this._generatePreview(), 100);
            }
        });

        // Editor state changes (for Advanced mode)
        if (window.editorState) {
            editorState.on('widget:added', () => this._requestPreviewForAdvanced());
            editorState.on('widget:removed', () => this._requestPreviewForAdvanced());
            editorState.on('widget:updated', () => this._requestPreviewForAdvanced());
            editorState.on('property:changed', () => this._requestPreviewForAdvanced());
        }

        // Export button
        const exportBtn = document.getElementById('btn-export');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this._exportXML());
        }

        // Generate command button
        const cmdBtn = document.getElementById('btn-generate-cmd');
        if (cmdBtn) {
            cmdBtn.addEventListener('click', () => this._showCommandModal());
        }

        // Render video button
        const renderBtn = document.getElementById('btn-render');
        if (renderBtn) {
            renderBtn.addEventListener('click', () => this._handleRenderClick());
        }

        // Batch render button
        const batchRenderBtn = document.getElementById('btn-batch-render');
        if (batchRenderBtn) {
            batchRenderBtn.addEventListener('click', () => this._handleBatchRenderClick());
        }

        // Copy command button
        const copyBtn = document.getElementById('btn-copy-command');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => this._copyCommand());
        }

        // Modal close
        document.querySelectorAll('[data-close-modal]').forEach(btn => {
            btn.addEventListener('click', () => {
                btn.closest('.modal-overlay').classList.remove('visible');
            });
        });

        // Close modal on overlay click
        // Skip manage-templates-modal as it has its own handler in TemplateManager
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            if (overlay.id === 'manage-templates-modal') return;
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('visible');
                }
            });
        });
    }

    /**
     * Try to restore session from localStorage
     */
    async _restoreSession() {
        // Use session ID from state (already restored from localStorage)
        const savedSessionId = this.state.sessionId;
        if (!savedSessionId) return;

        try {
            const response = await fetch(`/api/session/${savedSessionId}`);
            if (response.ok) {
                const data = await response.json();
                this.state.setSession(savedSessionId, data);
                this.showStatus('Session restored');
            } else {
                // Session not found on server - clear completely
                console.warn('Session not found on server, clearing local state');
                this.state.clearSession();
            }
        } catch (error) {
            console.error('Failed to restore session:', error);
            this.state.clearSession();
        }
    }

    /**
     * Update file context display in header
     */
    _updateFileContext() {
        const primaryFile = this.state.getPrimaryFile();
        if (!primaryFile) {
            this._hideFileContext();
            return;
        }

        const iconEl = this.fileContextEl.querySelector('.file-context-icon');
        const nameEl = this.fileContextEl.querySelector('.file-context-name');
        const resEl = this.fileContextEl.querySelector('.file-resolution');
        const fpsEl = this.fileContextEl.querySelector('.file-fps');
        const durEl = this.fileContextEl.querySelector('.file-duration');
        const gpsEl = this.fileContextEl.querySelector('.file-gps');

        iconEl.textContent = this.state.getFileTypeIcon(primaryFile.file_type);

        // Show primary filename, and secondary if present
        const secondaryFile = this.state.getSecondaryFile();
        if (secondaryFile) {
            nameEl.textContent = `${primaryFile.filename} + ${secondaryFile.filename}`;
        } else {
            nameEl.textContent = primaryFile.filename;
        }

        if (primaryFile.video_metadata) {
            const vm = primaryFile.video_metadata;
            resEl.textContent = vm.width && vm.height ? `${vm.width}x${vm.height}` : '';
            fpsEl.textContent = vm.frame_rate ? `${vm.frame_rate.toFixed(0)} FPS` : '';
            durEl.textContent = vm.duration_seconds ? this.state.formatTime(vm.duration_seconds * 1000) : '';
            // Show GPS badge if video has GPS or if secondary GPX/FIT is attached
            const hasGps = vm.has_gps || secondaryFile;
            gpsEl.textContent = hasGps ? 'GPS' : '';
            gpsEl.style.display = hasGps ? '' : 'none';
        } else if (primaryFile.gpx_fit_metadata) {
            const gm = primaryFile.gpx_fit_metadata;
            resEl.textContent = gm.gps_point_count ? `${gm.gps_point_count} points` : '';
            fpsEl.textContent = '';
            durEl.textContent = gm.duration_seconds ? this.state.formatTime(gm.duration_seconds * 1000) : '';
            gpsEl.textContent = 'GPS';
            gpsEl.style.display = '';
        } else {
            // Clear metadata display if no metadata available
            resEl.textContent = '';
            fpsEl.textContent = '';
            durEl.textContent = '';
            gpsEl.textContent = '';
            gpsEl.style.display = 'none';
        }

        this.fileContextEl.classList.remove('hidden');
    }

    _hideFileContext() {
        this.fileContextEl.classList.add('hidden');
    }

    /**
     * Request debounced preview
     */
    _requestPreview() {
        if (!this.state.hasValidSession()) return;
        if (this.state.mode !== 'quick') return;
        if (!this.state.autoPreview) return;  // Skip if auto-preview disabled

        this.previewDebouncer.request(async (signal) => {
            await this._generatePreview(signal);
        });
    }

    /**
     * Request preview for Advanced mode
     */
    _requestPreviewForAdvanced() {
        if (!this.state.hasValidSession()) return;
        if (this.state.mode !== 'advanced') return;
        if (!this.state.autoPreview) return;  // Skip if auto-preview disabled

        // Auto-preview in advanced mode too
        this.previewDebouncer.request(async (signal) => {
            await this._generatePreview(signal);
        });
    }

    /**
     * Generate preview
     */
    async _generatePreview(signal) {
        if (!this.state.hasValidSession()) {
            this._showPreviewEmpty();
            return;
        }

        this._showPreviewLoading();

        try {
            const config = this.state.getPreviewConfig();

            let response;
            if (this.state.mode === 'quick') {
                // Use main preview API
                response = await fetch('/api/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: config.sessionId,
                        layout: config.layout,
                        frame_time_ms: Math.round(config.frameTimeMs),
                        units_speed: config.unitsSpeed,
                        units_altitude: config.unitsAltitude,
                        units_distance: config.unitsDistance,
                        units_temperature: config.unitsTemperature,
                        map_style: config.mapStyle,
                        gps_dop_max: config.gpsDopMax,
                        gps_speed_max: config.gpsSpeedMax
                    }),
                    signal
                });
            } else {
                // Use editor preview API
                const frameTimeMs = Math.round(config.frameTimeMs);
                console.log('Advanced preview config:', {
                    session_id: config.sessionId,
                    layout_id: config.layout?.id,
                    layout_widgets: config.layout?.widgets?.length,
                    frame_time_ms: frameTimeMs,
                    units_speed: config.unitsSpeed,
                    units_altitude: config.unitsAltitude,
                    units_distance: config.unitsDistance,
                    units_temperature: config.unitsTemperature,
                    map_style: config.mapStyle,
                    gps_dop_max: config.gpsDopMax,
                    gps_speed_max: config.gpsSpeedMax
                });
                response = await fetch('/api/editor/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: config.sessionId,
                        layout: config.layout,
                        frame_time_ms: frameTimeMs,
                        units_speed: config.unitsSpeed,
                        units_altitude: config.unitsAltitude,
                        units_distance: config.unitsDistance,
                        units_temperature: config.unitsTemperature,
                        map_style: config.mapStyle,
                        gps_dop_max: config.gpsDopMax,
                        gps_speed_max: config.gpsSpeedMax
                    }),
                    signal
                });
            }

            if (!response.ok) {
                const error = await response.json();
                // Check if session/file not found - need to clear session
                if (response.status === 404) {
                    console.warn('Session file not found, clearing session');
                    this.state.clearSession();
                    throw new Error('File not found. Please re-upload your file.');
                }
                throw new Error(error.detail || 'Preview failed');
            }

            const data = await response.json();

            this._showPreview(data.image_base64);
            this.showStatus(`Preview at ${this.state.formatTime(data.frame_time_ms)}`);

        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Preview failed:', error);

            // Handle specific error types with toast notifications
            this._handlePreviewError(error);

            // Hide preview image on error in advanced mode
            if (this.state.mode === 'advanced') {
                const canvasPreviewImg = document.getElementById('canvas-preview-image');
                if (canvasPreviewImg) {
                    canvasPreviewImg.classList.remove('visible');
                }
            }
            this._showPreviewEmpty();
        }
    }

    _showPreviewEmpty() {
        // Only show empty state in Quick mode
        if (this.state.mode === 'quick') {
            this.previewEmptyEl.classList.remove('force-hidden');
            this.previewEmptyEl.style.display = 'flex';
        }
        this._hidePreviewLoading();
        this.previewContainerEl.classList.add('hidden');
    }

    _showPreviewLoading() {
        this.previewEmptyEl.style.display = 'none';
        // Show spinner on refresh button
        if (this.refreshBtn) {
            this.refreshBtn.classList.add('loading');
        }
    }

    _hidePreviewLoading() {
        if (this.refreshBtn) {
            this.refreshBtn.classList.remove('loading');
        }
    }

    _showPreview(imageBase64) {
        console.log('_showPreview called, mode:', this.state.mode);

        // Always hide empty and loading states
        if (this.previewEmptyEl) {
            this.previewEmptyEl.classList.add('force-hidden');
            this.previewEmptyEl.style.display = 'none';
            console.log('previewEmptyEl hidden');
        }
        this._hidePreviewLoading();

        if (this.state.mode === 'quick') {
            // Quick mode: show in preview container
            this.previewContainerEl.classList.remove('hidden');
            const imgSrc = `data:image/png;base64,${imageBase64}`;
            console.log('Quick mode: setting preview image, base64 length:', imageBase64?.length);

            // Add load/error handlers for debugging
            this.previewImageEl.onload = () => {
                console.log('Quick mode: image loaded, natural size:',
                    this.previewImageEl.naturalWidth, 'x', this.previewImageEl.naturalHeight);
            };
            this.previewImageEl.onerror = (e) => {
                console.error('Quick mode: image failed to load:', e);
            };

            this.previewImageEl.src = imgSrc;
        } else {
            // Advanced mode: show preview image behind canvas
            const canvasPreviewImg = document.getElementById('canvas-preview-image');
            const canvasEl = document.getElementById('canvas');
            const canvasSpacer = document.getElementById('canvas-spacer');
            if (canvasPreviewImg && canvasEl) {
                // Add load/error handlers for debugging
                canvasPreviewImg.onload = () => {
                    console.log('Advanced mode: image loaded, natural size:',
                        canvasPreviewImg.naturalWidth, 'x', canvasPreviewImg.naturalHeight);
                    console.log('Advanced mode: display size:',
                        canvasPreviewImg.offsetWidth, 'x', canvasPreviewImg.offsetHeight);
                };
                canvasPreviewImg.onerror = (e) => {
                    console.error('Advanced mode: image failed to load:', e);
                };

                canvasPreviewImg.src = `data:image/png;base64,${imageBase64}`;
                // Match the canvas transform scale
                const scale = parseFloat(canvasEl.style.transform?.match(/scale\(([\d.]+)\)/)?.[1] || 1);
                canvasPreviewImg.style.transform = `scale(${scale})`;
                canvasPreviewImg.style.transformOrigin = '0 0';
                // Sync width/height with canvas
                const canvasWidth = parseInt(canvasEl.style.width) || 1920;
                const canvasHeight = parseInt(canvasEl.style.height) || 1080;
                canvasPreviewImg.style.width = `${canvasWidth}px`;
                canvasPreviewImg.style.height = `${canvasHeight}px`;
                canvasPreviewImg.classList.add('visible');

                // Update spacer to enable proper scrolling
                // (Absolutely positioned elements don't contribute to overflow)
                if (canvasSpacer) {
                    const padding = 40; // 20px padding on each side
                    canvasSpacer.style.width = `${canvasWidth * scale + padding}px`;
                    canvasSpacer.style.height = `${canvasHeight * scale + padding}px`;
                }

                console.log('Canvas preview image set, scale:', scale, 'size:', canvasWidth, 'x', canvasHeight);
            }
        }
    }

    /**
     * Export layout to XML
     */
    async _exportXML() {
        try {
            this.showStatus('Exporting...');

            let response;
            if (this.state.mode === 'advanced' && window.editorState?.layout) {
                response = await apiClient.exportToXML(editorState.layout);
            } else {
                // For quick mode, we can't export (it uses predefined layouts)
                window.toast.error('Export is only available in Advanced mode. Switch to Advanced mode to create and export custom layouts.', { title: 'Export Not Available' });
                return;
            }

            // Download file
            const blob = new Blob([response.xml], { type: 'application/xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = response.filename;
            a.click();
            URL.revokeObjectURL(url);

            this.showStatus('XML exported');

        } catch (error) {
            console.error('Export failed:', error);
            window.toast.error(error.message, { title: 'Export Failed' });
        }
    }

    /**
     * Show command modal
     */
    async _showCommandModal() {
        if (!this.state.hasValidSession()) {
            window.toast.error('Please upload a video file first', { title: 'No File Uploaded' });
            return;
        }

        try {
            const config = this.state.getPreviewConfig();

            // Build request payload (output_filename auto-generated from input file if not specified)
            // Defaults must match backend constants.py
            const requestPayload = {
                session_id: config.sessionId,
                units_speed: config.unitsSpeed || 'kph',
                units_altitude: config.unitsAltitude || 'metre',
                units_distance: config.unitsDistance || 'km',
                units_temperature: config.unitsTemperature || 'degC',
                map_style: config.mapStyle || 'osm',
                ffmpeg_profile: this.state.quickConfig.ffmpegProfile || null
            };

            // Add GPX/FIT options if applicable
            const gpxFitOptions = this.state.getGpxFitOptions();
            if (gpxFitOptions) {
                requestPayload.gpx_fit_options = gpxFitOptions;
            }

            // Handle layout based on mode
            if (this.state.mode === 'quick') {
                // Quick mode: use predefined layout name
                requestPayload.layout = config.layout;
            } else {
                // Advanced mode: check for selected template
                const templateManager = this.modeToggle?.templateManager;
                const selectedTemplate = templateManager?.getSelectedTemplate();

                if (selectedTemplate && selectedTemplate.type === 'custom') {
                    // Custom template: get file path from backend
                    const templateService = new TemplateService();
                    try {
                        const pathResponse = await templateService.getTemplatePath(selectedTemplate.name);
                        requestPayload.layout = 'xml';
                        requestPayload.layout_xml_path = pathResponse.file_path;
                    } catch (err) {
                        throw new Error(`Template "${selectedTemplate.name}" not found. Please save your layout first.`);
                    }
                } else if (selectedTemplate && selectedTemplate.type === 'predefined') {
                    // Predefined template: use layout name
                    requestPayload.layout = selectedTemplate.name;
                } else {
                    // No template selected
                    throw new Error('Please save your layout as a template first, or select a template.');
                }
            }

            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestPayload)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to generate command');
            }

            const data = await response.json();

            document.getElementById('command-output').textContent = data.command;
            document.getElementById('command-modal').classList.add('visible');

        } catch (error) {
            console.error('Command generation failed:', error);
            window.toast.error(error.message, { title: 'Command Generation Failed' });
        }
    }

    /**
     * Handle render button click
     */
    async _handleRenderClick() {
        if (!this.state.hasValidSession()) {
            window.toast.error('Please upload a video file first', { title: 'No File Uploaded' });
            return;
        }

        // Build render config based on current mode
        const config = {};

        if (this.state.mode === 'quick') {
            // Quick mode: use predefined layout
            config.layout = this.state.quickConfig.layout;
        } else {
            // Advanced mode: check for selected template
            const templateManager = this.modeToggle?.templateManager;
            const selectedTemplate = templateManager?.getSelectedTemplate();

            if (selectedTemplate && selectedTemplate.type === 'custom') {
                // Custom template: get file path from backend
                const templateService = new TemplateService();
                try {
                    const pathResponse = await templateService.getTemplatePath(selectedTemplate.name);
                    config.layout = 'xml';
                    config.layout_xml_path = pathResponse.file_path;
                } catch (err) {
                    window.toast.error(`Template "${selectedTemplate.name}" not found. Please save your layout first.`, { title: 'Template Not Found' });
                    return;
                }
            } else if (selectedTemplate && selectedTemplate.type === 'predefined') {
                // Predefined template: use layout name
                config.layout = selectedTemplate.name;
            } else {
                window.toast.error('Please save your layout as a template first, or select a template.', { title: 'No Template Selected' });
                return;
            }
        }

        // Start render
        this.renderModal.startRender(config);
    }

    /**
     * Handle batch render button click
     */
    _handleBatchRenderClick() {
        this.batchRenderModal.open();
    }

    /**
     * Copy command to clipboard
     */
    async _copyCommand() {
        const command = document.getElementById('command-output').textContent;
        try {
            await navigator.clipboard.writeText(command);
            this.showStatus('Command copied to clipboard', 'success');
        } catch (error) {
            console.error('Copy failed:', error);
            window.toast.error('Failed to copy command to clipboard', { title: 'Copy Failed' });
        }
    }

    /**
     * Handle preview errors with smart detection and user-friendly messages
     */
    _handlePreviewError(error) {
        const message = error.message || 'Unknown error';

        // Detect API key errors
        if (message.includes("API key") || message.includes("API keys") || message.includes("can't give key")) {
            // Extract map style name from error if possible
            const mapMatch = message.match(/API '(\w+)'/);
            const mapStyle = mapMatch ? mapMatch[1] : this.state.quickConfig.mapStyle;

            if (window.toast) {
                window.toast.showApiKeyError(mapStyle);
            }
            this.showStatus(`Map "${mapStyle}" requires API key`, 'error');
            return;
        }

        // Detect GPS data errors
        if (message.includes("GPS data") || message.includes("No GPS")) {
            if (window.toast) {
                window.toast.error(message, {
                    title: 'GPS Data Missing',
                    duration: 8000
                });
            }
            this.showStatus('No GPS data found', 'error');
            return;
        }

        // Detect file not found errors
        if (message.includes("File not found") || message.includes("not found")) {
            if (window.toast) {
                window.toast.error(message, {
                    title: 'File Not Found',
                    action: 'Re-upload',
                    onAction: () => {
                        // Clear session and show upload
                        this.state.clearSession();
                    }
                });
            }
            this.showStatus('File not found', 'error');
            return;
        }

        // Generic error - show toast for visibility
        if (window.toast) {
            window.toast.error(message, {
                title: 'Preview Failed',
                duration: 6000
            });
        }
        this.showStatus('Preview failed', 'error');
    }

    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
        this.statusMessageEl.textContent = message;
        this.statusMessageEl.className = 'status-message';
        if (type === 'error') {
            this.statusMessageEl.classList.add('error');
        } else if (type === 'success') {
            this.statusMessageEl.classList.add('success');
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
    window.app = new UnifiedApp();
    await window.app.init();
});

/**
 * UnifiedState - Extends EditorState with app-level state
 * Manages both Quick mode config and Advanced mode editor state
 * Supports multi-file sessions (primary + secondary GPX/FIT)
 */

class UnifiedState {
    constructor() {
        // Reference to EditorState singleton for Advanced mode
        this.editor = window.editorState;

        // Application state
        this.mode = 'quick'; // 'quick' | 'advanced'
        this.sessionId = null;
        this.files = []; // Array of FileInfo objects with roles
        this.isSessionValid = false;

        // Timeline state
        this.currentFrameTimeMs = 0;
        this.duration = 0;
        this.thumbnails = [];

        // Quick mode config
        // Note: unit values must match backend constants.py (kph, metre, km, degC)
        this.quickConfig = {
            layout: 'default-1920x1080',
            unitsSpeed: 'kph',
            unitsAltitude: 'metre',
            unitsDistance: 'km',
            unitsTemperature: 'degC',
            mapStyle: 'osm',
            // GPX/FIT options
            gpxMergeMode: 'OVERWRITE',
            videoTimeAlignment: null,
            // FFmpeg profile (empty = default)
            ffmpegProfile: '',
            // GPS filter settings (less strict than CLI defaults)
            gpsDopMax: 20,      // CLI default: 10
            gpsSpeedMax: 200    // CLI default: 60 kph
        };

        // Preview state
        this.previewLoading = false;
        this.previewError = null;
        this.lastPreviewConfig = null;
        this.autoPreview = true;  // Auto-regenerate preview on changes

        // Event listeners
        this.listeners = new Map();

        // Initialize from localStorage
        this._restoreFromStorage();
    }

    /**
     * Restore state from localStorage
     */
    _restoreFromStorage() {
        const savedSessionId = localStorage.getItem('gopro_editor_session_id');
        if (savedSessionId) {
            this.sessionId = savedSessionId;
        }

        const savedMode = localStorage.getItem('gopro_unified_mode');
        if (savedMode && (savedMode === 'quick' || savedMode === 'advanced')) {
            this.mode = savedMode;
        }

        const savedQuickConfig = localStorage.getItem('gopro_unified_quick_config');
        if (savedQuickConfig) {
            try {
                const parsed = JSON.parse(savedQuickConfig);
                this.quickConfig = { ...this.quickConfig, ...parsed };
            } catch (e) {
                console.warn('Failed to parse saved quick config:', e);
            }
        }

        const savedAutoPreview = localStorage.getItem('gopro_unified_auto_preview');
        if (savedAutoPreview !== null) {
            this.autoPreview = savedAutoPreview === 'true';
        }
    }

    /**
     * Set auto preview state
     */
    setAutoPreview(enabled) {
        this.autoPreview = enabled;
        localStorage.setItem('gopro_unified_auto_preview', enabled.toString());
        this.emit('autoPreview:changed', { enabled });
    }

    /**
     * Set session after file upload
     * @param {string} sessionId
     * @param {Object} responseData - UploadResponse with files array
     */
    setSession(sessionId, responseData) {
        this.sessionId = sessionId;
        this.files = responseData.files || [];
        this.isSessionValid = true;

        // Extract duration from primary file metadata
        const primary = this.getPrimaryFile();
        if (primary?.video_metadata) {
            this.duration = primary.video_metadata.duration_seconds * 1000;
        } else if (primary?.gpx_fit_metadata?.duration_seconds) {
            this.duration = primary.gpx_fit_metadata.duration_seconds * 1000;
        }

        // Reset frame time to middle of video (ensure integer)
        this.currentFrameTimeMs = Math.round(this.duration / 2);

        // Save to localStorage
        localStorage.setItem('gopro_editor_session_id', sessionId);

        this.emit('session:changed', { sessionId, files: this.files });
        this.emit('timeline:changed', {
            duration: this.duration,
            currentTime: this.currentFrameTimeMs
        });
    }

    /**
     * Update files in session (after secondary upload/remove)
     * @param {Array} files - Array of FileInfo objects
     */
    setFiles(files) {
        this.files = files || [];
        this.emit('files:changed', { files: this.files });
    }

    /**
     * Get primary file from session
     * @returns {Object|null} FileInfo with role='primary'
     */
    getPrimaryFile() {
        return this.files.find(f => f.role === 'primary') || null;
    }

    /**
     * Get secondary file from session
     * @returns {Object|null} FileInfo with role='secondary'
     */
    getSecondaryFile() {
        return this.files.find(f => f.role === 'secondary') || null;
    }

    /**
     * Check if session has secondary file
     * @returns {boolean}
     */
    hasSecondaryFile() {
        return !!this.getSecondaryFile();
    }

    /**
     * Check if secondary file can be added
     * Secondary only allowed when primary is video
     * @returns {boolean}
     */
    canAddSecondaryFile() {
        const primary = this.getPrimaryFile();
        return primary && primary.file_type === 'video' && !this.hasSecondaryFile();
    }

    /**
     * Check if current session is in GPX-only mode
     * @returns {boolean}
     */
    isGpxOnlyMode() {
        const primary = this.getPrimaryFile();
        return primary && (primary.file_type === 'gpx' || primary.file_type === 'fit' || primary.file_type === 'srt');
    }

    /**
     * Check if current session has video + GPX/FIT merge
     * @returns {boolean}
     */
    isMergeMode() {
        const primary = this.getPrimaryFile();
        return primary && primary.file_type === 'video' && this.hasSecondaryFile();
    }

    /**
     * Check if secondary file is SRT (DJI telemetry).
     * SRT time sync is handled automatically — no user config needed.
     * @returns {boolean}
     */
    isSrtSecondary() {
        const secondary = this.getSecondaryFile();
        return secondary && secondary.file_type === 'srt';
    }

    /**
     * Clear session
     */
    clearSession() {
        this.sessionId = null;
        this.files = [];
        this.isSessionValid = false;
        this.duration = 0;
        this.currentFrameTimeMs = 0;
        this.thumbnails = [];

        localStorage.removeItem('gopro_editor_session_id');

        this.emit('session:cleared');
    }

    /**
     * Set current mode
     */
    setMode(mode) {
        if (mode !== 'quick' && mode !== 'advanced') {
            console.error('Invalid mode:', mode);
            return;
        }

        const previousMode = this.mode;
        this.mode = mode;

        // Save preference
        localStorage.setItem('gopro_unified_mode', mode);

        // If switching to advanced mode and we have a layout selected,
        // load it into the editor
        if (mode === 'advanced' && previousMode === 'quick') {
            // Advanced mode will use EditorState
        }

        this.emit('mode:changed', { mode, previousMode });
    }

    /**
     * Set current frame time (from timeline)
     */
    setFrameTime(timeMs) {
        // Clamp to valid range and ensure integer
        timeMs = Math.round(Math.max(0, Math.min(timeMs, this.duration)));
        this.currentFrameTimeMs = timeMs;

        this.emit('timeline:seek', { timeMs });
    }

    /**
     * Update quick mode config
     */
    updateQuickConfig(updates) {
        this.quickConfig = { ...this.quickConfig, ...updates };

        // Save to localStorage
        localStorage.setItem('gopro_unified_quick_config', JSON.stringify(this.quickConfig));

        this.emit('quickConfig:changed', { config: this.quickConfig, updates });
    }

    /**
     * Update GPX/FIT options
     */
    updateGpxOptions(options) {
        this.updateQuickConfig(options);
        this.emit('gpxOptions:changed', { options });
    }

    /**
     * Get current layout based on mode
     * For quick mode, returns the preset name
     * For advanced mode, returns the editor layout object
     */
    getCurrentLayout() {
        if (this.mode === 'quick') {
            return this.quickConfig.layout;
        } else {
            return this.editor.layout;
        }
    }

    /**
     * Get current preview config
     */
    getPreviewConfig() {
        const config = {
            sessionId: this.sessionId,
            frameTimeMs: this.currentFrameTimeMs,
            // Units and map style are shared between Quick and Advanced modes
            unitsSpeed: this.quickConfig.unitsSpeed,
            unitsAltitude: this.quickConfig.unitsAltitude,
            unitsDistance: this.quickConfig.unitsDistance,
            unitsTemperature: this.quickConfig.unitsTemperature,
            mapStyle: this.quickConfig.mapStyle,
            // GPS filter settings
            gpsDopMax: this.quickConfig.gpsDopMax,
            gpsSpeedMax: this.quickConfig.gpsSpeedMax
        };

        if (this.mode === 'quick') {
            config.layout = this.quickConfig.layout;
        } else {
            config.layout = this.editor.layout;
        }

        return config;
    }

    /**
     * Get GPX/FIT options for command generation
     */
    getGpxFitOptions() {
        if (this.isMergeMode() || this.isGpxOnlyMode()) {
            return {
                merge_mode: this.quickConfig.gpxMergeMode,
                video_time_alignment: this.quickConfig.videoTimeAlignment
            };
        }
        return null;
    }

    /**
     * Set thumbnails for timeline
     */
    setThumbnails(thumbnails) {
        this.thumbnails = thumbnails;
        this.emit('thumbnails:loaded', { thumbnails });
    }

    /**
     * Set preview loading state
     */
    setPreviewLoading(loading) {
        this.previewLoading = loading;
        this.emit('preview:loading', { loading });
    }

    /**
     * Set preview error
     */
    setPreviewError(error) {
        this.previewError = error;
        this.emit('preview:error', { error });
    }

    // ========================
    // Event System
    // ========================

    /**
     * Subscribe to state changes
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);

        // Return unsubscribe function
        return () => this.off(event, callback);
    }

    /**
     * Unsubscribe from state changes
     */
    off(event, callback) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }

    /**
     * Emit event
     */
    emit(event, data = {}) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            listeners.forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`Error in event listener for ${event}:`, e);
                }
            });
        }
    }

    // ========================
    // Utility Methods
    // ========================

    /**
     * Format time in mm:ss format
     */
    formatTime(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    /**
     * Check if session is valid
     */
    hasValidSession() {
        return this.sessionId !== null && this.isSessionValid;
    }

    /**
     * Get file type icon
     */
    getFileTypeIcon(fileType) {
        switch (fileType) {
            case 'video': return '';
            case 'gpx': return '';
            case 'fit': return '';
            default: return '';
        }
    }

    /**
     * Legacy getter for backward compatibility
     * @deprecated Use getPrimaryFile() instead
     */
    get fileInfo() {
        return this.getPrimaryFile();
    }
}

// Export singleton
window.unifiedState = new UnifiedState();

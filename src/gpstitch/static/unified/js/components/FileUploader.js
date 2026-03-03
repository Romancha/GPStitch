/**
 * FileUploader - Handles video and GPS file uploads
 * Two separate fields:
 * - Video field: MP4/MOV files
 * - GPS field: GPX/FIT files
 *
 * Modes determined by what's loaded:
 * - Video only = GoPro with embedded GPS
 * - GPS only = overlay-only mode
 * - Video + GPS = merge mode
 */

class FileUploader {
    constructor(container, fileInput, state) {
        this.container = container;
        this.fileInput = fileInput;
        this.state = state;

        this.isUploading = false;
        this.localMode = false;

        this._init();
    }

    async _init() {
        // Check if local mode is enabled
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const config = await response.json();
                this.localMode = config.local_mode;
            }
        } catch (e) {
            console.warn('Could not fetch config, using default mode');
        }

        this._render();
        this._attachEventListeners();
    }

    _render() {
        this.container.innerHTML = `
            <!-- Video Field -->
            <div class="file-field" id="video-field">
                <div class="file-field-header">
                    <span class="file-field-label">Video</span>
                    <span class="file-field-hint">MP4 (optional)</span>
                </div>
                ${this.localMode ? `
                    <div class="file-field-input-row">
                        <input type="text" id="video-path-input" class="file-path-input" placeholder="/path/to/video.mp4">
                        <button id="video-load-btn" class="btn btn-sm btn-primary">Load</button>
                    </div>
                ` : `
                    <div id="video-drop-zone" class="file-drop-zone">
                        <span class="drop-zone-text">Drop MP4/MOV or click</span>
                    </div>
                    <input type="file" id="video-file-input" accept=".mp4,.mov" class="visually-hidden">
                `}
                <div id="video-file-info" class="file-info" style="display: none;">
                    <span class="file-info-name"></span>
                    <button class="file-clear-btn" data-field="video" title="Remove">&times;</button>
                </div>
            </div>

            <!-- GPS Field -->
            <div class="file-field" id="gps-field">
                <div class="file-field-header">
                    <span class="file-field-label">GPS Data</span>
                    <span class="file-field-hint">GPX/FIT/SRT (optional)</span>
                </div>
                ${this.localMode ? `
                    <div class="file-field-input-row">
                        <input type="text" id="gps-path-input" class="file-path-input" placeholder="/path/to/track.gpx or .srt">
                        <button id="gps-load-btn" class="btn btn-sm btn-primary">Load</button>
                    </div>
                ` : `
                    <div id="gps-drop-zone" class="file-drop-zone">
                        <span class="drop-zone-text">Drop GPX/FIT/SRT or click</span>
                    </div>
                    <input type="file" id="gps-file-input" accept=".gpx,.fit,.srt" class="visually-hidden">
                `}
                <div id="gps-file-info" class="file-info" style="display: none;">
                    <span class="file-info-name"></span>
                    <button class="file-clear-btn" data-field="gps" title="Remove">&times;</button>
                </div>
            </div>

            <!-- Mode indicator -->
            <div id="mode-indicator" class="mode-indicator" style="display: none;"></div>
        `;

        // Cache DOM references
        this.videoField = document.getElementById('video-field');
        this.gpsField = document.getElementById('gps-field');
        this.videoFileInfo = document.getElementById('video-file-info');
        this.gpsFileInfo = document.getElementById('gps-file-info');
        this.modeIndicator = document.getElementById('mode-indicator');

        if (this.localMode) {
            this.videoPathInput = document.getElementById('video-path-input');
            this.gpsPathInput = document.getElementById('gps-path-input');
        } else {
            this.videoDropZone = document.getElementById('video-drop-zone');
            this.gpsDropZone = document.getElementById('gps-drop-zone');
            this.videoFileInput = document.getElementById('video-file-input');
            this.gpsFileInput = document.getElementById('gps-file-input');
        }
    }

    _attachEventListeners() {
        if (this.localMode) {
            // Local mode: path inputs
            document.getElementById('video-load-btn')?.addEventListener('click', () => this._loadLocalFile('video'));
            document.getElementById('gps-load-btn')?.addEventListener('click', () => this._loadLocalFile('gps'));

            this.videoPathInput?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this._loadLocalFile('video');
            });
            this.gpsPathInput?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this._loadLocalFile('gps');
            });

            // Auto-clean quotes on paste
            [this.videoPathInput, this.gpsPathInput].forEach(input => {
                input?.addEventListener('paste', () => {
                    setTimeout(() => {
                        input.value = this._cleanPath(input.value);
                    }, 0);
                });
            });
        } else {
            // Upload mode: drop zones
            this._setupDropZone(this.videoDropZone, this.videoFileInput, 'video');
            this._setupDropZone(this.gpsDropZone, this.gpsFileInput, 'gps');
        }

        // Clear buttons
        document.querySelectorAll('.file-clear-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const field = e.target.dataset.field;
                this._clearFile(field);
            });
        });

        // State events
        this.state.on('session:changed', () => this._updateUI());
        this.state.on('session:cleared', () => this._updateUI());
        this.state.on('files:changed', () => this._updateUI());
    }

    _setupDropZone(dropZone, fileInput, type) {
        if (!dropZone || !fileInput) return;

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this._uploadFile(e.dataTransfer.files[0], type);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this._uploadFile(e.target.files[0], type);
            }
            e.target.value = '';
        });
    }

    _cleanPath(path) {
        if (!path) return '';
        path = path.trim();
        if ((path.startsWith('"') && path.endsWith('"')) ||
            (path.startsWith("'") && path.endsWith("'"))) {
            path = path.slice(1, -1);
        }
        return path.trim();
    }

    async _loadLocalFile(type) {
        const input = type === 'video' ? this.videoPathInput : this.gpsPathInput;
        const path = this._cleanPath(input.value);
        if (!path) return;

        // Determine role based on current state and type
        const hasVideo = this.state.getPrimaryFile()?.file_type === 'video';
        const hasGps = this.state.getSecondaryFile() ||
                       (this.state.getPrimaryFile()?.file_type === 'gpx' ||
                        this.state.getPrimaryFile()?.file_type === 'fit' ||
                        this.state.getPrimaryFile()?.file_type === 'srt');

        const hasGpsPrimary = !hasVideo &&
            (this.state.getPrimaryFile()?.file_type === 'gpx' ||
             this.state.getPrimaryFile()?.file_type === 'fit' ||
             this.state.getPrimaryFile()?.file_type === 'srt');

        try {
            let response;

            if (type === 'video') {
                // If session has GPX/FIT/SRT as primary, send session_id to reuse session
                const body = { file_path: path };
                if (hasGpsPrimary && this.state.sessionId) {
                    body.session_id = this.state.sessionId;
                }
                response = await fetch('/api/local-file', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
            } else {
                // GPS file
                if (hasVideo && this.state.sessionId) {
                    // Add as secondary to existing video session
                    response = await fetch('/api/local-file-secondary', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            session_id: this.state.sessionId,
                            file_path: path
                        })
                    });
                } else {
                    // No video - GPS becomes primary (gpx-only mode)
                    response = await fetch('/api/local-file', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file_path: path })
                    });
                }
            }

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to load file');
            }

            const data = await response.json();

            if (type === 'video' && hasGpsPrimary && this.state.sessionId) {
                // Session reused — update files without resetting session
                this.state.setFiles(data.files);
            } else if (type === 'video' || !hasVideo) {
                this.state.setSession(data.session_id, data);
            } else {
                this.state.setFiles(data.files);
            }

            input.value = '';

        } catch (error) {
            console.error('Load failed:', error);
            alert(error.message);
        }
    }

    async _uploadFile(file, type) {
        const validExtensions = type === 'video' ? ['.mp4', '.mov'] : ['.gpx', '.fit', '.srt'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!validExtensions.includes(ext)) {
            alert(`Invalid file type. Expected: ${validExtensions.join(', ')}`);
            return;
        }

        const hasVideo = this.state.getPrimaryFile()?.file_type === 'video';
        const hasGpsPrimary = !hasVideo &&
            (this.state.getPrimaryFile()?.file_type === 'gpx' ||
             this.state.getPrimaryFile()?.file_type === 'fit' ||
             this.state.getPrimaryFile()?.file_type === 'srt');

        try {
            const formData = new FormData();
            formData.append('file', file);

            let response;

            if (type === 'video') {
                // If session has GPX/FIT as primary, send session_id to reuse session
                if (hasGpsPrimary && this.state.sessionId) {
                    formData.append('session_id', this.state.sessionId);
                }
                response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
            } else {
                if (hasVideo && this.state.sessionId) {
                    formData.append('session_id', this.state.sessionId);
                    response = await fetch('/api/upload-secondary', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    response = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                }
            }

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const data = await response.json();

            if (type === 'video' && hasGpsPrimary && this.state.sessionId) {
                // Session reused — update files without resetting session
                this.state.setFiles(data.files);
            } else if (type === 'video' || !hasVideo) {
                this.state.setSession(data.session_id, data);
            } else {
                this.state.setFiles(data.files);
            }

        } catch (error) {
            console.error('Upload failed:', error);
            alert(error.message);
        }
    }

    async _clearFile(type) {
        const primary = this.state.getPrimaryFile();
        const secondary = this.state.getSecondaryFile();

        if (type === 'video') {
            if (primary?.file_type === 'video') {
                // Clear entire session if video is primary
                this.state.clearSession();
            }
        } else {
            // Clearing GPS
            if (secondary) {
                // Remove secondary file
                try {
                    const response = await fetch(`/api/session/${this.state.sessionId}/secondary`, {
                        method: 'DELETE'
                    });
                    if (response.ok) {
                        const data = await response.json();
                        this.state.setFiles(data.files);
                    }
                } catch (error) {
                    console.error('Failed to remove GPS file:', error);
                }
            } else if (primary?.file_type === 'gpx' || primary?.file_type === 'fit' || primary?.file_type === 'srt') {
                // GPS is primary (gpx-only mode) - clear session
                this.state.clearSession();
            }
        }
    }

    _updateUI() {
        const primary = this.state.getPrimaryFile();
        const secondary = this.state.getSecondaryFile();

        // Determine what's loaded
        const videoFile = primary?.file_type === 'video' ? primary : null;
        const gpsFile = secondary ||
                        (primary?.file_type === 'gpx' || primary?.file_type === 'fit' || primary?.file_type === 'srt' ? primary : null);

        // Update Video field
        this._updateFieldUI('video', videoFile);

        // Update GPS field
        this._updateFieldUI('gps', gpsFile);

        // Update mode indicator
        this._updateModeIndicator(videoFile, gpsFile);
    }

    _updateFieldUI(type, file) {
        const fileInfo = type === 'video' ? this.videoFileInfo : this.gpsFileInfo;
        const dropZone = type === 'video' ? this.videoDropZone : this.gpsDropZone;
        const pathInput = type === 'video' ? this.videoPathInput : this.gpsPathInput;

        if (file) {
            // Show file info
            const nameEl = fileInfo.querySelector('.file-info-name');
            nameEl.textContent = file.filename;
            fileInfo.style.display = 'flex';

            if (this.localMode && pathInput) {
                pathInput.parentElement.style.display = 'none';
            } else if (dropZone) {
                dropZone.style.display = 'none';
            }
        } else {
            // Show input
            fileInfo.style.display = 'none';

            if (this.localMode && pathInput) {
                pathInput.parentElement.style.display = 'flex';
            } else if (dropZone) {
                dropZone.style.display = 'flex';
            }
        }
    }

    _updateModeIndicator(videoFile, gpsFile) {
        if (!videoFile && !gpsFile) {
            this.modeIndicator.style.display = 'none';
            return;
        }

        this.modeIndicator.style.display = 'block';

        if (videoFile && gpsFile) {
            this.modeIndicator.innerHTML = '<span class="mode-badge mode-merge">Merge Mode</span> Video + external GPS';
        } else if (videoFile) {
            this.modeIndicator.innerHTML = '<span class="mode-badge mode-video">Video Mode</span> Using embedded GPS';
        } else if (gpsFile) {
            this.modeIndicator.innerHTML = '<span class="mode-badge mode-gps">GPS Only</span> Overlay without video';
        }
    }
}

// Export
window.FileUploader = FileUploader;

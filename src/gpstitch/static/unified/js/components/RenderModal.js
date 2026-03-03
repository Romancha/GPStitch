/**
 * RenderModal - Video rendering progress modal
 * Shows progress, logs, and allows cancellation
 */

class RenderModal {
    constructor(state) {
        this.state = state;
        this.jobId = null;
        this.pollInterval = null;
        this.logPollInterval = null;
        this.isOpen = false;
        this.currentStatus = null;  // Track current job status
        this.consecutiveFailures = 0;
        this.MAX_FAILURES = 10;

        // Prevent overlapping requests
        this._statusRequestPending = false;
        this._logsRequestPending = false;

        this._createModal();
        this._attachEventListeners();
        // Check for active render on init (browser reconnection)
        this._checkActiveRender();

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            this._stopPolling();
        });
    }

    _createModal() {
        // Create modal HTML
        const modalHtml = `
            <div id="render-modal" class="modal-overlay" style="display: none;">
                <div class="modal render-modal">
                    <div class="modal-header">
                        <h3>Rendering Video</h3>
                        <button class="modal-close" id="render-modal-close">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="render-progress-section">
                            <div class="progress-bar-container">
                                <div id="render-progress-bar" class="progress-bar"></div>
                            </div>
                            <div id="render-progress-text" class="progress-text">Preparing...</div>
                        </div>

                        <div class="render-details">
                            <div class="render-detail-row">
                                <span class="detail-label">Status:</span>
                                <span id="render-status" class="detail-value">Pending</span>
                            </div>
                            <div class="render-detail-row">
                                <span class="detail-label">Frame:</span>
                                <span id="render-frames" class="detail-value">-</span>
                            </div>
                            <div class="render-detail-row">
                                <span class="detail-label">Speed:</span>
                                <span id="render-fps" class="detail-value">-</span>
                            </div>
                            <div class="render-detail-row">
                                <span class="detail-label">ETA:</span>
                                <span id="render-eta" class="detail-value">-</span>
                            </div>
                            <div class="render-detail-row">
                                <span class="detail-label">Output:</span>
                                <span id="render-output-path" class="detail-value output-path">-</span>
                            </div>
                        </div>

                        <div class="render-log-section">
                            <div class="log-header">
                                <span>Log Output</span>
                                <button id="render-log-toggle" class="btn-link">Hide</button>
                            </div>
                            <pre id="render-log-content" class="log-content"></pre>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button id="render-cancel-btn" class="btn btn-secondary">Cancel</button>
                        <button id="render-close-btn" class="btn btn-primary" style="display: none;">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Get elements
        this.modal = document.getElementById('render-modal');
        this.progressBar = document.getElementById('render-progress-bar');
        this.progressText = document.getElementById('render-progress-text');
        this.statusEl = document.getElementById('render-status');
        this.framesEl = document.getElementById('render-frames');
        this.fpsEl = document.getElementById('render-fps');
        this.etaEl = document.getElementById('render-eta');
        this.outputPathEl = document.getElementById('render-output-path');
        this.logContent = document.getElementById('render-log-content');
        this.logToggleBtn = document.getElementById('render-log-toggle');
        this.cancelBtn = document.getElementById('render-cancel-btn');
        this.closeBtn = document.getElementById('render-close-btn');
        this.modalCloseBtn = document.getElementById('render-modal-close');
    }

    _attachEventListeners() {
        this.cancelBtn.addEventListener('click', () => this._handleCancel());
        this.closeBtn.addEventListener('click', () => this.close());
        this.modalCloseBtn.addEventListener('click', () => this._handleModalClose());

        this.logToggleBtn.addEventListener('click', () => {
            const isHidden = this.logContent.style.display === 'none';
            this.logContent.style.display = isHidden ? 'block' : 'none';
            this.logToggleBtn.textContent = isHidden ? 'Hide' : 'Show';
        });
    }

    async _checkActiveRender() {
        // Check if there's an active render (for browser reconnection)
        try {
            const response = await fetch('/api/render/current');
            const data = await response.json();

            if (data.job_id) {
                console.log('Found active render on reconnect:', data.job_id);
                this.jobId = data.job_id;
                this.open();
            }
        } catch (error) {
            console.error('Failed to check active render:', error);
        }
    }

    async startRender(config) {
        try {
            // Check GPS quality and warn if poor (check primary then secondary)
            const primaryFile = this.state.getPrimaryFile?.();
            const secondaryFile = this.state.getSecondaryFile?.();
            const gpsQuality = primaryFile?.gps_quality || secondaryFile?.gps_quality;

            if (GPSWarningModal.shouldWarn(gpsQuality)) {
                const proceed = await window.gpsWarningModal.show(gpsQuality);
                if (!proceed) {
                    return; // User cancelled
                }
            }

            // Build request from state and config
            const request = {
                session_id: this.state.sessionId,
                layout: config.layout || this.state.quickConfig.layout,
                layout_xml_path: config.layout_xml_path || null,
                output_file: config.output_file || null,
                units_speed: this.state.quickConfig.unitsSpeed || 'kph',
                units_altitude: this.state.quickConfig.unitsAltitude || 'metre',
                units_distance: this.state.quickConfig.unitsDistance || 'km',
                units_temperature: this.state.quickConfig.unitsTemperature || 'degC',
                map_style: this.state.quickConfig.mapStyle || 'osm',
                gpx_merge_mode: this.state.quickConfig.gpxMergeMode || 'OVERWRITE',
                video_time_alignment: this.state.quickConfig.videoTimeAlignment || null,
                ffmpeg_profile: this.state.quickConfig.ffmpegProfile || null,
                gps_dop_max: this.state.quickConfig.gpsDopMax || 20,
                gps_speed_max: this.state.quickConfig.gpsSpeedMax || 200
            };

            // Determine output file path for checking
            let outputFile = request.output_file;
            if (!outputFile) {
                const primary = this.state.getPrimaryFile?.() || this.state.files?.find(f => f.role === 'PRIMARY');
                if (primary && primary.file_path) {
                    const lastSlash = primary.file_path.lastIndexOf('/');
                    const dir = lastSlash > -1 ? primary.file_path.substring(0, lastSlash) : '.';
                    const filename = primary.filename || primary.file_path.substring(lastSlash + 1);
                    const lastDot = filename.lastIndexOf('.');
                    const name = lastDot > -1 ? filename.substring(0, lastDot) : filename;
                    outputFile = `${dir}/${name}_overlay.mp4`;
                }
            }

            // Check if output file exists
            if (outputFile) {
                try {
                    const checkResponse = await fetch('/api/render/check-files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ output_files: [outputFile] })
                    });

                    if (checkResponse.ok) {
                        const checkData = await checkResponse.json();
                        if (checkData.existing_files && checkData.existing_files.length > 0) {
                            // File exists - show confirmation (no Skip for single file)
                            let decision;
                            if (window.overwriteConfirmDialog) {
                                decision = await window.overwriteConfirmDialog.show(
                                    checkData.existing_files,
                                    { showSkip: false }
                                );
                            } else {
                                // Fallback to browser confirm
                                decision = confirm(`File already exists:\n${checkData.existing_files[0]}\n\nOverwrite?`)
                                    ? 'overwrite' : null;
                            }

                            if (decision !== 'overwrite') {
                                // User cancelled
                                return;
                            }
                        }
                    }
                } catch (checkError) {
                    console.warn('File check failed, proceeding anyway:', checkError);
                }
            }

            const response = await fetch('/api/render/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start render');
            }

            const data = await response.json();
            this.jobId = data.job_id;
            this.outputPathEl.textContent = data.output_file;

            this.open();

        } catch (error) {
            console.error('Failed to start render:', error);
            alert('Failed to start render: ' + error.message);
        }
    }

    open() {
        this.isOpen = true;
        this.modal.style.display = 'flex';
        this._resetUI();
        this._startPolling();
    }

    close() {
        this.isOpen = false;
        this.modal.style.display = 'none';
        this._stopPolling();
        this.jobId = null;
    }

    _resetUI() {
        this.progressBar.style.width = '0%';
        this.progressBar.className = 'progress-bar';
        this.progressText.textContent = 'Preparing...';
        this.statusEl.textContent = 'Pending';
        this.framesEl.textContent = '-';
        this.fpsEl.textContent = '-';
        this.etaEl.textContent = '-';
        this.logContent.textContent = '';
        this.logContent.style.display = 'block';
        this.logToggleBtn.textContent = 'Hide';
        this.cancelBtn.style.display = 'inline-block';
        this.closeBtn.style.display = 'none';
        this.modalCloseBtn.style.display = 'none';
    }

    _startPolling() {
        this._stopPolling(); // Clear any existing
        // Poll status every 2 seconds, logs every 3 seconds
        this.pollInterval = setInterval(() => this._updateStatus(), 2000);
        this.logPollInterval = setInterval(() => this._updateLogs(), 3000);
        this._updateStatus(); // Initial update
        this._updateLogs();
    }

    _stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        if (this.logPollInterval) {
            clearInterval(this.logPollInterval);
            this.logPollInterval = null;
        }
    }

    async _updateStatus() {
        if (!this.jobId || !this.isOpen) return;

        // Skip if previous request is still pending
        if (this._statusRequestPending) return;

        this._statusRequestPending = true;
        try {
            const response = await fetch(`/api/render/status/${this.jobId}`);
            if (!response.ok) {
                throw new Error('Failed to fetch status');
            }

            const status = await response.json();
            this.currentStatus = status.status;  // Track current status
            this.consecutiveFailures = 0;  // Reset on success
            this._updateUI(status);

            // Stop polling if done
            if (this._isTerminal(status.status)) {
                this._stopPolling();
            }

        } catch (error) {
            console.error('Failed to update render status:', error);
            this.consecutiveFailures++;

            // Stop polling after too many failures
            if (this.consecutiveFailures >= this.MAX_FAILURES) {
                this._stopPolling();
                this.progressText.textContent = 'Connection lost. Check server status.';
                this.progressBar.classList.add('error');
                this.cancelBtn.style.display = 'none';
                this.closeBtn.style.display = 'inline-block';
                this.modalCloseBtn.style.display = 'block';
            }
        } finally {
            this._statusRequestPending = false;
        }
    }

    async _updateLogs() {
        if (!this.jobId || !this.isOpen) return;

        // Skip if previous request is still pending
        if (this._logsRequestPending) return;

        this._logsRequestPending = true;
        try {
            const response = await fetch(`/api/render/logs/${this.jobId}?tail=100`);
            if (!response.ok) return;

            const data = await response.json();
            if (data.log_lines && data.log_lines.length > 0) {
                this.logContent.textContent = data.log_lines.join('\n');
                // Auto-scroll to bottom
                this.logContent.scrollTop = this.logContent.scrollHeight;
            }
        } catch (error) {
            // Silently ignore log fetch errors
        } finally {
            this._logsRequestPending = false;
        }
    }

    _updateUI(status) {
        // Update progress bar
        const percent = status.progress?.percent || 0;
        this.progressBar.style.width = `${percent}%`;

        // Update status text
        this.statusEl.textContent = this._formatStatus(status.status);

        // Update progress text
        if (status.status === 'pending') {
            this.progressText.textContent = 'Waiting to start...';
        } else if (status.status === 'running') {
            if (status.progress?.current_frame && status.progress?.total_frames) {
                this.progressText.textContent = `${Math.round(percent)}% - Frame ${status.progress.current_frame} / ${status.progress.total_frames}`;
            } else {
                this.progressText.textContent = `${Math.round(percent)}%`;
            }
        } else if (status.status === 'completed') {
            this.progressText.textContent = 'Completed!';
            this._showComplete();
        } else if (status.status === 'failed') {
            this.progressText.textContent = `Failed: ${status.error || 'Unknown error'}`;
            this._showError();
        } else if (status.status === 'cancelled') {
            this.progressText.textContent = 'Cancelled';
            this._showCancelled();
        }

        // Update frames
        if (status.progress?.current_frame) {
            const framesText = status.progress.total_frames
                ? `${status.progress.current_frame} / ${status.progress.total_frames}`
                : `${status.progress.current_frame}`;
            this.framesEl.textContent = framesText;
        }

        // Update FPS
        if (status.progress?.fps) {
            this.fpsEl.textContent = `${status.progress.fps.toFixed(1)} frames/s`;
        }

        // Update ETA
        if (status.progress?.eta_seconds) {
            this.etaEl.textContent = this._formatEta(status.progress.eta_seconds);
        } else if (status.status === 'completed') {
            this.etaEl.textContent = 'Done';
        }

        // Update output path
        if (status.output_file) {
            this.outputPathEl.textContent = status.output_file;
        }
    }

    _formatEta(seconds) {
        if (!seconds || seconds <= 0) return '-';
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        if (hours > 0) {
            return `${hours}h ${mins}m ${secs}s`;
        } else if (mins > 0) {
            return `${mins}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    _formatStatus(status) {
        const statusMap = {
            'pending': 'Pending',
            'running': 'Running',
            'completed': 'Completed',
            'failed': 'Failed',
            'cancelled': 'Cancelled'
        };
        return statusMap[status] || status;
    }

    _isTerminal(status) {
        return ['completed', 'failed', 'cancelled'].includes(status);
    }

    _showComplete() {
        this.progressBar.classList.add('success');
        this.cancelBtn.style.display = 'none';
        this.closeBtn.style.display = 'inline-block';
        this.modalCloseBtn.style.display = 'block';
    }

    _showError() {
        this.progressBar.classList.add('error');
        this.cancelBtn.style.display = 'none';
        this.closeBtn.style.display = 'inline-block';
        this.modalCloseBtn.style.display = 'block';
    }

    _showCancelled() {
        this.progressBar.classList.add('cancelled');
        this.cancelBtn.style.display = 'none';
        this.closeBtn.style.display = 'inline-block';
        this.modalCloseBtn.style.display = 'block';
    }

    _handleModalClose() {
        // Only allow closing if job is terminal or no job
        if (!this.jobId) {
            this.close();
            return;
        }

        // Check if we're in a terminal state before closing
        if (this._isTerminal(this.currentStatus)) {
            this.close();
        }
        // If not terminal, ignore the close attempt (button should be hidden anyway)
    }

    async _handleCancel() {
        if (!this.jobId) return;

        if (!confirm('Are you sure you want to cancel this render?')) {
            return;
        }

        try {
            const response = await fetch(`/api/render/cancel/${this.jobId}`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to cancel render');
            }

            // UI will update via polling

        } catch (error) {
            console.error('Failed to cancel render:', error);
            alert('Failed to cancel render: ' + error.message);
        }
    }
}

// Export
window.RenderModal = RenderModal;

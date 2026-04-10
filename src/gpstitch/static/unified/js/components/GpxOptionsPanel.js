/**
 * GpxOptionsPanel - Panel for GPX/FIT merge options
 * Shows merge mode dropdown when video + GPX/FIT are loaded
 * Shows time alignment options with auto-detection hints and manual offset
 */

class GpxOptionsPanel {
    constructor(container, state) {
        this.container = container;
        this.state = state;
        this._offsetDebounceTimer = null;

        this._init();
    }

    _init() {
        this._render();
        this._attachListeners();

        // Listen for file changes
        this.state.on('session:changed', () => this._updateVisibility());
        this.state.on('files:changed', () => this._updateVisibility());
        this.state.on('session:cleared', () => this._updateVisibility());

        // Check visibility on init (in case session already exists)
        this._updateVisibility();
    }

    _render() {
        this.container.innerHTML = `
            <div class="gpx-options-panel" id="gpx-options-content" style="display: none;">
                <!-- Merge Mode (video + GPX/FIT) -->
                <div class="gpx-option-group" id="merge-mode-group" style="display: none;">
                    <div class="gpx-option-row">
                        <label for="gpx-merge-mode">GPS Merge</label>
                        <select id="gpx-merge-mode">
                            <option value="OVERWRITE">Overwrite</option>
                            <option value="EXTEND">Extend</option>
                        </select>
                    </div>
                    <div class="gpx-option-desc" id="merge-mode-desc">Replace video GPS with GPX data</div>
                </div>

                <!-- Time Alignment (Merge Mode and GPX-only mode) -->
                <div class="gpx-option-group" id="time-alignment-group" style="display: none;">
                    <div class="gpx-option-row">
                        <label for="video-time-alignment">Time Sync</label>
                        <select id="video-time-alignment">
                            <option value="auto">Auto (recommended)</option>
                            <option value="gpx-timestamps">Use GPX timestamps</option>
                            <option value="manual">Manual offset...</option>
                        </select>
                    </div>
                    <div class="gpx-option-desc" id="time-alignment-desc"></div>

                    <!-- Time sync hint -->
                    <div class="time-sync-hint" id="time-sync-hint" style="display: none;"></div>

                    <!-- Manual offset panel -->
                    <div class="manual-offset-panel" id="manual-offset-panel" style="display: none;">
                        <div class="manual-offset-row">
                            <button class="offset-btn" id="offset-minus" title="Decrease offset">-</button>
                            <input type="number" id="time-offset-seconds" value="0" step="1" class="offset-input" />
                            <button class="offset-btn" id="offset-plus" title="Increase offset">+</button>
                            <span class="offset-label">seconds</span>
                        </div>
                        <div class="manual-offset-info" id="manual-offset-info"></div>
                    </div>
                </div>
            </div>
        `;

        // Get element references
        this.panel = document.getElementById('gpx-options-content');
        this.mergeModeGroup = document.getElementById('merge-mode-group');
        this.timeAlignmentGroup = document.getElementById('time-alignment-group');
        this.mergeModeSelect = document.getElementById('gpx-merge-mode');
        this.timeAlignmentSelect = document.getElementById('video-time-alignment');
        this.mergeModeDesc = document.getElementById('merge-mode-desc');
        this.timeAlignmentDesc = document.getElementById('time-alignment-desc');
        this.timeSyncHint = document.getElementById('time-sync-hint');
        this.manualOffsetPanel = document.getElementById('manual-offset-panel');
        this.offsetInput = document.getElementById('time-offset-seconds');
        this.offsetMinusBtn = document.getElementById('offset-minus');
        this.offsetPlusBtn = document.getElementById('offset-plus');
        this.manualOffsetInfo = document.getElementById('manual-offset-info');

        // Set initial values from state
        this.mergeModeSelect.value = this.state.quickConfig.gpxMergeMode || 'OVERWRITE';
        this.timeAlignmentSelect.value = this.state.quickConfig.videoTimeAlignment || 'auto';
        this.offsetInput.value = this.state.quickConfig.timeOffsetSeconds || 0;

        // Update description for initial value
        this._updateMergeModeDesc();
        this._updateTimeAlignmentDesc();
        this._updateManualPanelVisibility();
    }

    _updateMergeModeDesc() {
        const descriptions = {
            'OVERWRITE': 'Replace video GPS with GPX data',
            'EXTEND': 'Keep video GPS, add HR/cadence/power'
        };
        if (this.mergeModeDesc) {
            this.mergeModeDesc.textContent = descriptions[this.mergeModeSelect.value] || '';
        }
    }

    _updateTimeAlignmentDesc() {
        const descriptions = {
            'auto': 'Sync video to GPS using video metadata timestamp, with automatic timezone validation',
            'gpx-timestamps': 'Use GPS timestamps as-is, no alignment with video. Best when GPX is pre-trimmed to match the video',
            'manual': 'Same as Auto, but with a manual time correction in seconds'
        };
        if (this.timeAlignmentDesc) {
            this.timeAlignmentDesc.textContent = descriptions[this.timeAlignmentSelect.value] || '';
        }
    }

    _attachListeners() {
        this.mergeModeSelect?.addEventListener('change', (e) => {
            this.state.updateGpxOptions({ gpxMergeMode: e.target.value });
            this._updateMergeModeDesc();
        });

        this.timeAlignmentSelect?.addEventListener('change', (e) => {
            this.state.updateGpxOptions({ videoTimeAlignment: e.target.value });
            this._updateTimeAlignmentDesc();
            this._updateManualPanelVisibility();
            // Reset offset when switching away from manual and trigger re-analysis
            if (e.target.value !== 'manual') {
                this.offsetInput.value = 0;
                this.state.updateGpxOptions({ timeOffsetSeconds: 0 });
                this.state.emit('timeOffset:changed', { offset: 0 });
            }
        });

        // Manual offset controls
        this.offsetMinusBtn?.addEventListener('click', () => {
            const current = parseInt(this.offsetInput.value) || 0;
            this.offsetInput.value = current - 1;
            this._onOffsetChanged();
        });

        this.offsetPlusBtn?.addEventListener('click', () => {
            const current = parseInt(this.offsetInput.value) || 0;
            this.offsetInput.value = current + 1;
            this._onOffsetChanged();
        });

        this.offsetInput?.addEventListener('input', () => {
            this._onOffsetChangedDebounced();
        });

        // Listen for time sync info updates
        this.state.on('timeSyncInfo:changed', () => this._updateTimeSyncHint());
    }

    _onOffsetChanged() {
        const value = parseInt(this.offsetInput.value) || 0;
        this.state.updateGpxOptions({ timeOffsetSeconds: value });
        this._updateManualOffsetInfo();
        this.state.emit('timeOffset:changed', { offset: value });
    }

    _onOffsetChangedDebounced() {
        clearTimeout(this._offsetDebounceTimer);
        this._offsetDebounceTimer = setTimeout(() => {
            this._onOffsetChanged();
        }, 300);
    }

    _updateManualPanelVisibility() {
        const isManual = this.timeAlignmentSelect.value === 'manual';
        this.manualOffsetPanel.style.display = isManual ? 'block' : 'none';
        if (isManual) {
            this._updateManualOffsetInfo();
        }
    }

    _updateManualOffsetInfo() {
        const info = this.state.timeSyncInfo;
        if (!info || !this.manualOffsetInfo) return;

        // Clear previous content
        this.manualOffsetInfo.textContent = '';

        const offset = parseInt(this.offsetInput.value) || 0;
        if (info.video_start) {
            const adjustedDate = new Date(info.video_start);
            // video_start is already post-correction (system-tz, exhaustive, etc.)
            // Undo the TZ correction to derive the actual original creation_time
            const tzCorrectionMs = (info.tz_correction_hours || 0) * 3600 * 1000;
            const baseDate = new Date(adjustedDate.getTime() - tzCorrectionMs - offset * 1000);

            const addRow = (label, value) => {
                const row = document.createElement('div');
                row.className = 'manual-offset-row-info';
                const labelSpan = document.createElement('span');
                labelSpan.className = 'manual-offset-label';
                labelSpan.textContent = label;
                const valueSpan = document.createElement('span');
                valueSpan.className = 'manual-offset-value';
                valueSpan.textContent = value;
                row.appendChild(labelSpan);
                row.appendChild(valueSpan);
                this.manualOffsetInfo.appendChild(row);
            };

            // Use source-specific label: for mtime/file-created, baseDate is NOT the
            // original creation_time — it's the file modification/creation time.
            const baseLabel = info.source === 'mtime' ? 'File-derived start:'
                : info.source === 'file-created' ? 'File creation time:'
                : 'Original creation_time:';
            addRow(baseLabel, this._formatDateTime(baseDate));
            addRow('Corrected video start:', this._formatDateTime(adjustedDate));

            if (info.gps_start && info.gps_end) {
                const gpsStartFmt = this._formatDateTime(new Date(info.gps_start));
                const gpsEndFmt = this._formatTime(new Date(info.gps_end));
                addRow('GPS range:', `${gpsStartFmt} — ${gpsEndFmt}`);
            }

            if (info.overlap && info.overlap.points > 0) {
                const speed = info.overlap.avg_speed_kph?.toFixed(1) || '0.0';
                addRow('Overlap:', `${info.overlap.points} pts | ${speed} km/h`);
            }
        }
    }

    /**
     * Update the time sync hint based on timeSyncInfo state
     */
    _updateTimeSyncHint() {
        const info = this.state.timeSyncInfo;
        if (!info) {
            this.timeSyncHint.style.display = 'none';
            return;
        }

        this.timeSyncHint.style.display = 'block';
        // Clear previous content (removes old text nodes and event listeners)
        this.timeSyncHint.textContent = '';

        const startDate = new Date(info.video_start);
        const endDate = new Date(startDate.getTime() + info.video_duration_sec * 1000);
        const startFmt = this._formatDateTime(startDate);
        const endFmt = this._formatTime(endDate);

        switch (info.source) {
            case 'system-tz': {
                const hours = info.tz_correction_hours ?? 0;
                const sign = hours >= 0 ? '+' : '';
                let text = `[\u2139] Applied ${sign}${hours}h from your system timezone`;
                if (info.overlap) {
                    const speed = info.overlap.avg_speed_kph?.toFixed(1) || '0.0';
                    text += ` | ${info.overlap.points} pts | ${speed} km/h`;
                }
                const mainSpan = document.createElement('span');
                mainSpan.textContent = text;
                this.timeSyncHint.appendChild(mainSpan);
                const subtitle = document.createElement('div');
                subtitle.className = 'time-sync-subtitle';
                subtitle.textContent = 'Wrong? \u2192 Use Manual Offset';
                this.timeSyncHint.appendChild(subtitle);
                this.timeSyncHint.className = 'time-sync-hint time-sync-info';
                break;
            }

            case 'exhaustive': {
                const hours = info.tz_correction_hours ?? 0;
                const sign = hours >= 0 ? '+' : '';
                let text = `[!] Timezone auto-detected: ${sign}${hours}h (from GPS overlap)`;
                if (info.overlap) {
                    const speed = info.overlap.avg_speed_kph?.toFixed(1) || '0.0';
                    text += ` | ${info.overlap.points} pts | ${speed} km/h`;
                }
                const mainSpan = document.createElement('span');
                mainSpan.textContent = text;
                this.timeSyncHint.appendChild(mainSpan);
                const subtitle = document.createElement('div');
                subtitle.className = 'time-sync-subtitle';
                subtitle.textContent = 'Verify this looks right';
                this.timeSyncHint.appendChild(subtitle);
                this.timeSyncHint.className = 'time-sync-hint time-sync-warning';
                break;
            }

            case 'mtime': {
                this.timeSyncHint.textContent = `[!] ${startFmt}-${endFmt} (using file date)`;
                this.timeSyncHint.className = 'time-sync-hint time-sync-warning';
                break;
            }

            case 'failed': {
                const ctFmt = startFmt;
                let gpsInfo = '';
                if (info.gps_start && info.gps_end) {
                    const gpsStartFmt = this._formatDateTime(new Date(info.gps_start));
                    const gpsEndFmt = this._formatTime(new Date(info.gps_end));
                    gpsInfo = ` | GPS: ${gpsStartFmt}-${gpsEndFmt}`;
                }
                const mainSpan = document.createElement('span');
                mainSpan.textContent = `[\u26A0] Couldn't auto-align time | Video: ${ctFmt}${gpsInfo}`;
                this.timeSyncHint.appendChild(mainSpan);

                if (info.suggested_manual_offset_seconds != null) {
                    this.timeSyncHint.appendChild(
                        this._renderSwitchToManualButton(info.suggested_manual_offset_seconds)
                    );
                }
                this.timeSyncHint.className = 'time-sync-hint time-sync-error';
                break;
            }

            case 'file-created': {
                if (info.overlap) {
                    const speed = info.overlap.avg_speed_kph?.toFixed(1) || '0.0';
                    this.timeSyncHint.textContent = `[!] ${startFmt}-${endFmt} (file date) | ${info.overlap.points} pts | ${speed} km/h`;
                } else {
                    this.timeSyncHint.textContent = `[!] ${startFmt} (file date, may be inaccurate)`;
                }
                this.timeSyncHint.className = 'time-sync-hint time-sync-warning';
                break;
            }

            case 'media-created':
            default: {
                if (info.overlap) {
                    const speed = info.overlap.avg_speed_kph?.toFixed(1) || '0.0';
                    this.timeSyncHint.textContent = `${startFmt}-${endFmt} | ${info.overlap.points} pts | ${speed} km/h`;
                    this.timeSyncHint.className = 'time-sync-hint';
                } else {
                    this.timeSyncHint.textContent = `[!] ${startFmt}-${endFmt} | No GPS data found`;
                    this.timeSyncHint.className = 'time-sync-hint time-sync-warning';
                }
                break;
            }
        }

        // Update manual offset info too
        this._updateManualOffsetInfo();
    }

    /**
     * Create a button that switches to Manual mode with a pre-filled offset
     */
    _renderSwitchToManualButton(seconds) {
        const hours = (seconds / 3600).toFixed(1);
        const sign = seconds >= 0 ? '+' : '';
        const btn = document.createElement('button');
        btn.className = 'time-sync-switch-manual-btn';
        btn.textContent = `Switch to Manual with ${sign}${hours}h`;
        btn.addEventListener('click', () => {
            this.timeAlignmentSelect.value = 'manual';
            this.state.updateGpxOptions({ videoTimeAlignment: 'manual' });
            this._updateTimeAlignmentDesc();
            this._updateManualPanelVisibility();
            this.offsetInput.value = seconds;
            this._onOffsetChanged();
        });
        return btn;
    }

    _formatDateTime(date) {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${months[date.getUTCMonth()]} ${date.getUTCDate()}, ${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}:${String(date.getUTCSeconds()).padStart(2, '0')}`;
    }

    _formatTime(date) {
        return `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}:${String(date.getUTCSeconds()).padStart(2, '0')}`;
    }

    _updateVisibility() {
        const isMergeMode = this.state.isMergeMode();
        const isGpxOnlyMode = this.state.isGpxOnlyMode();
        const isSrt = this.state.isSrtSecondary();

        // Show panel if either mode is active
        if (isMergeMode || isGpxOnlyMode) {
            this.panel.style.display = 'block';
        } else {
            this.panel.style.display = 'none';
            return;
        }

        if (isSrt) {
            // DJI SRT: time sync is automatic, no user config needed.
            // Reset alignment to 'auto' to ensure backend uses file-modified mode.
            if (this.state.quickConfig.videoTimeAlignment !== 'auto') {
                this.state.updateGpxOptions({ videoTimeAlignment: 'auto' });
                this.timeAlignmentSelect.value = 'auto';
            }
            this.mergeModeGroup.style.display = 'none';
            this.timeAlignmentGroup.style.display = 'none';
        } else {
            // Show appropriate options based on mode
            this.timeAlignmentGroup.style.display = 'block';
            if (isMergeMode) {
                this.mergeModeGroup.style.display = 'block';
            } else {
                this.mergeModeGroup.style.display = 'none';
            }
        }
    }

    show() {
        this.panel.style.display = 'block';
    }

    hide() {
        this.panel.style.display = 'none';
    }
}

// Export
window.GpxOptionsPanel = GpxOptionsPanel;

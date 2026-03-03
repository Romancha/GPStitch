/**
 * GpxOptionsPanel - Panel for GPX/FIT merge options
 * Shows merge mode dropdown when video + GPX/FIT are loaded
 * Shows time alignment options when GPX/FIT is loaded
 */

class GpxOptionsPanel {
    constructor(container, state) {
        this.container = container;
        this.state = state;

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
                            <option value="">Use GPX timestamps</option>
                            <option value="file-created">File created time</option>
                            <option value="file-modified">File modified time</option>
                        </select>
                    </div>
                    <div class="gpx-option-desc">How to align GPX time with video</div>
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

        // Set initial values from state
        this.mergeModeSelect.value = this.state.quickConfig.gpxMergeMode || 'OVERWRITE';
        this.timeAlignmentSelect.value = this.state.quickConfig.videoTimeAlignment || '';

        // Update description for initial value
        this._updateMergeModeDesc();
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

    _attachListeners() {
        this.mergeModeSelect?.addEventListener('change', (e) => {
            this.state.updateGpxOptions({ gpxMergeMode: e.target.value });
            this._updateMergeModeDesc();
        });

        this.timeAlignmentSelect?.addEventListener('change', (e) => {
            const value = e.target.value || null;
            this.state.updateGpxOptions({ videoTimeAlignment: value });
        });
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
            // DJI SRT: time sync is automatic, no user config needed
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

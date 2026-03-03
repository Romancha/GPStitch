/**
 * GPSWarningModal - Warning dialog before rendering with poor GPS quality
 * Returns a promise that resolves to true (proceed) or false (cancel)
 */

class GPSWarningModal {
    constructor() {
        this._createModal();
    }

    _createModal() {
        const modal = document.createElement('div');
        modal.id = 'gps-warning-modal';
        modal.className = 'modal-overlay';
        modal.style.display = 'none';

        modal.innerHTML = `
            <div class="modal gps-warning-modal">
                <div class="modal-header">
                    <span class="modal-warning-icon">
                        <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
                            <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
                        </svg>
                    </span>
                    <h2 class="modal-title">Low GPS Quality Warning</h2>
                </div>
                <div class="modal-body">
                    <div class="gps-warning-message" id="gps-warning-message"></div>
                    <div class="gps-warning-consequences">
                        <p><strong>The overlay may show:</strong></p>
                        <ul>
                            <li>Incorrect speed and position data</li>
                            <li>Jumpy or missing values</li>
                            <li>Map not tracking correctly</li>
                        </ul>
                    </div>
                </div>
                <div class="modal-footer">
                    <button id="gps-warning-cancel" class="btn btn-secondary">Cancel</button>
                    <button id="gps-warning-proceed" class="btn btn-warning">Render Anyway</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        this.modal = modal;
        this.messageEl = document.getElementById('gps-warning-message');
        this.cancelBtn = document.getElementById('gps-warning-cancel');
        this.proceedBtn = document.getElementById('gps-warning-proceed');

        // Close on overlay click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this._resolve(false);
            }
        });

        // Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.style.display !== 'none') {
                this._resolve(false);
            }
        });
    }

    /**
     * Show warning modal and return user decision
     * @param {Object} gpsQuality - GPS quality report from API
     * @returns {Promise<boolean>} - true if user wants to proceed, false if cancelled
     */
    show(gpsQuality) {
        return new Promise((resolve) => {
            this._resolve = (result) => {
                this.modal.style.display = 'none';
                resolve(result);
            };

            // Build message based on quality
            this._buildMessage(gpsQuality);

            // Setup buttons
            this.cancelBtn.onclick = () => this._resolve(false);
            this.proceedBtn.onclick = () => this._resolve(true);

            // Show modal
            this.modal.style.display = 'flex';
            this.cancelBtn.focus();
        });
    }

    _buildMessage(quality) {
        let html = '<p>This video has poor GPS signal:</p><ul>';

        if (quality.quality_score === 'no_signal') {
            html += '<li>GPS signal was not acquired during recording</li>';
            html += '<li>DOP: 99.99 (invalid)</li>';
        } else {
            if (quality.usable_percentage < 50) {
                html += `<li>Only ${quality.usable_percentage.toFixed(0)}% of GPS points are usable</li>`;
            }
            if (quality.dop_mean && quality.dop_mean > 10) {
                html += `<li>Average DOP: ${quality.dop_mean.toFixed(1)} (recommended &lt; 10)</li>`;
            }
            if (quality.lock_rate < 50) {
                html += `<li>GPS lock rate: ${quality.lock_rate.toFixed(0)}%</li>`;
            }
        }

        html += '</ul>';
        this.messageEl.innerHTML = html;
    }

    /**
     * Check if warning should be shown for given quality
     */
    static shouldWarn(gpsQuality) {
        if (!gpsQuality) return false;
        return gpsQuality.quality_score === 'poor' || gpsQuality.quality_score === 'no_signal';
    }
}

// Singleton instance
window.gpsWarningModal = new GPSWarningModal();

/**
 * GPSQualityCard - Displays GPS signal quality analysis
 * Shows quality distribution, DOP statistics, and warnings
 */

class GPSQualityCard {
    constructor(container, state) {
        this.container = container;
        this.state = state;

        this._init();
    }

    _init() {
        this._render();

        // Listen for file changes
        this.state.on('session:changed', () => this._update());
        this.state.on('session:cleared', () => this._update());
        this.state.on('files:changed', () => this._update());
    }

    _render() {
        this.container.innerHTML = `
            <div id="gps-quality-card" class="gps-quality-card" style="display: none;">
                <div class="gps-quality-header">
                    <span class="gps-quality-icon"></span>
                    <span class="gps-quality-title">GPS Quality</span>
                    <span class="gps-quality-badge"></span>
                </div>
                <div class="gps-quality-body">
                    <div class="gps-quality-bars"></div>
                    <div class="gps-quality-stats"></div>
                    <div class="gps-quality-warnings"></div>
                </div>
            </div>
        `;

        this.card = document.getElementById('gps-quality-card');
        this.badge = this.card.querySelector('.gps-quality-badge');
        this.bars = this.card.querySelector('.gps-quality-bars');
        this.stats = this.card.querySelector('.gps-quality-stats');
        this.warnings = this.card.querySelector('.gps-quality-warnings');
    }

    _update() {
        const gpsQuality = this._getGpsQuality();

        if (!gpsQuality) {
            this.card.style.display = 'none';
            return;
        }

        this.card.style.display = 'block';
        this._renderQuality(gpsQuality);
    }

    _getGpsQuality() {
        // Check primary file first (video with embedded GPS)
        const primaryFile = this.state.getPrimaryFile();
        if (primaryFile?.gps_quality) return primaryFile.gps_quality;
        // Check secondary file (external GPX/FIT/SRT)
        const secondaryFile = this.state.getSecondaryFile();
        return secondaryFile?.gps_quality || null;
    }

    _renderQuality(quality) {
        // Update badge
        const badgeInfo = this._getBadgeInfo(quality.quality_score);
        this.badge.textContent = badgeInfo.label;
        this.badge.className = `gps-quality-badge gps-quality-${quality.quality_score}`;

        // Update bars (distribution)
        if (quality.quality_score === 'no_signal') {
            this.bars.innerHTML = `
                <div class="gps-no-signal">
                    <div class="gps-no-signal-icon">
                        <svg viewBox="0 0 24 24" fill="currentColor" width="32" height="32">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                        </svg>
                    </div>
                    <div class="gps-no-signal-text">No GPS Signal</div>
                    <div class="gps-no-signal-hint">GPS lock: ${quality.lock_rate}%</div>
                </div>
            `;
        } else {
            const total = quality.excellent_count + quality.good_count +
                         quality.moderate_count + quality.poor_count;

            this.bars.innerHTML = `
                ${this._renderBar('Excellent', quality.excellent_count, total, 'excellent')}
                ${this._renderBar('Good', quality.good_count, total, 'good')}
                ${this._renderBar('OK', quality.moderate_count, total, 'ok')}
                ${this._renderBar('Poor', quality.poor_count, total, 'poor')}
            `;
        }

        // Update stats
        if (quality.quality_score !== 'no_signal') {
            const dopDisplay = quality.dop_mean != null ? quality.dop_mean.toFixed(2) : '—';
            this.stats.innerHTML = `
                <div class="gps-stat">
                    <span class="gps-stat-label">DOP avg:</span>
                    <span class="gps-stat-value">${dopDisplay}</span>
                </div>
                <div class="gps-stat">
                    <span class="gps-stat-label">Lock rate:</span>
                    <span class="gps-stat-value">${quality.lock_rate}%</span>
                </div>
                <div class="gps-stat">
                    <span class="gps-stat-label">Usable:</span>
                    <span class="gps-stat-value">${quality.usable_percentage}%</span>
                </div>
            `;
            this.stats.style.display = 'flex';
        } else {
            this.stats.style.display = 'none';
        }

        // Update warnings
        if (quality.warnings && quality.warnings.length > 0) {
            this.warnings.innerHTML = quality.warnings.map(w =>
                `<div class="gps-warning-item">
                    <span class="gps-warning-icon">!</span>
                    <span>${this._escapeHtml(w)}</span>
                </div>`
            ).join('');
            this.warnings.style.display = 'block';
        } else {
            this.warnings.style.display = 'none';
        }
    }

    _renderBar(label, count, total, type) {
        const pct = total > 0 ? (count / total * 100) : 0;
        if (pct === 0) return '';

        return `
            <div class="gps-bar-row">
                <div class="gps-bar-label">${label}</div>
                <div class="gps-bar-track">
                    <div class="gps-bar-fill gps-bar-${type}" style="width: ${pct}%"></div>
                </div>
                <div class="gps-bar-pct">${pct.toFixed(0)}%</div>
            </div>
        `;
    }

    _getBadgeInfo(score) {
        const badges = {
            'excellent': { label: 'Excellent', color: 'green' },
            'good': { label: 'Good', color: 'green' },
            'ok': { label: 'OK', color: 'yellow' },
            'poor': { label: 'Poor', color: 'orange' },
            'no_signal': { label: 'No Signal', color: 'red' }
        };
        return badges[score] || badges['no_signal'];
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Get GPS quality data for current file
     */
    getQuality() {
        return this._getGpsQuality();
    }

    /**
     * Check if GPS quality requires warning before render
     */
    shouldWarnBeforeRender() {
        const quality = this.getQuality();
        if (!quality) return false;
        return quality.quality_score === 'poor' || quality.quality_score === 'no_signal';
    }
}

// Export
window.GPSQualityCard = GPSQualityCard;

/**
 * Timeline - Timeline scrubber component for frame selection
 */

class Timeline {
    constructor(container, state) {
        this.container = container;
        this.state = state;

        // DOM elements
        this.track = container.querySelector('#timeline-track');
        this.playhead = container.querySelector('#timeline-playhead');
        this.thumbnailsContainer = container.querySelector('#timeline-thumbnails');
        this.currentTimeEl = container.querySelector('#timeline-current');
        this.durationEl = container.querySelector('#timeline-duration');

        // State
        this.isDragging = false;
        this.duration = 0;

        this._attachEventListeners();
        this._attachStateListeners();
    }

    _attachEventListeners() {
        // Playhead drag
        this.playhead.addEventListener('mousedown', this._onPlayheadMouseDown.bind(this));
        document.addEventListener('mousemove', this._onMouseMove.bind(this));
        document.addEventListener('mouseup', this._onMouseUp.bind(this));

        // Click on track to seek
        this.track.addEventListener('click', this._onTrackClick.bind(this));

        // Quick seek buttons
        const quickBtns = this.container.querySelectorAll('.timeline-quick-btn');
        quickBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const percent = parseInt(btn.dataset.percent);
                this.seekToPercent(percent);
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', this._onKeyDown.bind(this));
    }

    _attachStateListeners() {
        // Update when session changes
        this.state.on('session:changed', () => {
            const fileInfo = this.state.getPrimaryFile();
            if (fileInfo?.video_metadata) {
                this.setDuration(fileInfo.video_metadata.duration_seconds * 1000);
            } else if (fileInfo?.gpx_fit_metadata?.duration_seconds) {
                this.setDuration(fileInfo.gpx_fit_metadata.duration_seconds * 1000);
            }
            this.show();
        });

        this.state.on('session:cleared', () => {
            this.hide();
        });

        this.state.on('timeline:seek', ({ timeMs }) => {
            this._updatePlayheadPosition(timeMs);
            this._updateTimeDisplay(timeMs);
        });

        this.state.on('thumbnails:loaded', ({ thumbnails }) => {
            this._renderThumbnails(thumbnails);
        });
    }

    /**
     * Set video duration
     * @param {number} durationMs - Duration in milliseconds
     */
    setDuration(durationMs) {
        this.duration = durationMs;
        this.durationEl.textContent = '/ ' + this.state.formatTime(durationMs);

        // Update current time display
        this._updateTimeDisplay(this.state.currentFrameTimeMs);
        this._updatePlayheadPosition(this.state.currentFrameTimeMs);
    }

    /**
     * Show timeline
     */
    show() {
        this.container.classList.add('visible');
    }

    /**
     * Hide timeline
     */
    hide() {
        this.container.classList.remove('visible');
    }

    /**
     * Seek to specific time
     * @param {number} timeMs
     */
    seekTo(timeMs) {
        timeMs = Math.max(0, Math.min(timeMs, this.duration));
        this.state.setFrameTime(timeMs);
    }

    /**
     * Seek to percentage of video
     * @param {number} percent - 0-100
     */
    seekToPercent(percent) {
        const timeMs = (this.duration * percent) / 100;
        this.seekTo(timeMs);
    }

    _onPlayheadMouseDown(e) {
        e.preventDefault();
        this.isDragging = true;
        this.playhead.style.cursor = 'grabbing';
    }

    _onMouseMove(e) {
        if (!this.isDragging) return;

        const rect = this.track.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = Math.max(0, Math.min(1, x / rect.width));
        const timeMs = percent * this.duration;

        this._updatePlayheadPosition(timeMs);
        this._updateTimeDisplay(timeMs);
    }

    _onMouseUp(e) {
        if (!this.isDragging) return;

        this.isDragging = false;
        this.playhead.style.cursor = '';

        // Calculate final time and seek
        const rect = this.track.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = Math.max(0, Math.min(1, x / rect.width));
        const timeMs = percent * this.duration;

        this.seekTo(timeMs);
    }

    _onTrackClick(e) {
        if (this.isDragging) return;

        // Ignore clicks on playhead
        if (e.target === this.playhead || e.target.closest('.timeline-playhead')) return;

        const rect = this.track.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = Math.max(0, Math.min(1, x / rect.width));
        const timeMs = percent * this.duration;

        this.seekTo(timeMs);
    }

    _onKeyDown(e) {
        // Don't handle if focus is in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }

        // Only handle if timeline is visible
        if (!this.container.classList.contains('visible')) {
            return;
        }

        const stepSmall = 1000; // 1 second
        const stepLarge = 5000; // 5 seconds
        const step = e.shiftKey ? stepLarge : stepSmall;

        switch (e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                this.seekTo(this.state.currentFrameTimeMs - step);
                break;
            case 'ArrowRight':
                e.preventDefault();
                this.seekTo(this.state.currentFrameTimeMs + step);
                break;
            case 'Home':
                e.preventDefault();
                this.seekTo(0);
                break;
            case 'End':
                e.preventDefault();
                this.seekTo(this.duration);
                break;
        }
    }

    _updatePlayheadPosition(timeMs) {
        if (this.duration === 0) return;
        const percent = (timeMs / this.duration) * 100;
        this.playhead.style.left = `${percent}%`;
    }

    _updateTimeDisplay(timeMs) {
        this.currentTimeEl.textContent = this.state.formatTime(timeMs);
    }

    _renderThumbnails(thumbnails) {
        if (!thumbnails || thumbnails.length === 0) {
            this.thumbnailsContainer.innerHTML = '';
            return;
        }

        this.thumbnailsContainer.innerHTML = thumbnails.map(thumb => `
            <div class="timeline-thumbnail">
                <img src="data:image/jpeg;base64,${thumb.image_base64}" alt="Frame at ${this.state.formatTime(thumb.time_seconds * 1000)}">
            </div>
        `).join('');
    }
}

// Export
window.Timeline = Timeline;

/**
 * Toast - Notification system for showing messages to user
 * Supports different types: info, success, warning, error
 */

class Toast {
    constructor() {
        this.container = null;
        this.toasts = new Map();
        this.toastId = 0;
        this._createContainer();
    }

    _createContainer() {
        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    }

    /**
     * Show a toast notification
     * @param {string} message - Message to display
     * @param {string} type - Type: 'info', 'success', 'warning', 'error'
     * @param {object} options - Additional options
     * @param {number} options.duration - Duration in ms (0 = permanent until dismissed)
     * @param {string} options.title - Optional title
     * @param {boolean} options.dismissible - Show close button (default: true)
     * @param {string} options.action - Optional action button text
     * @param {function} options.onAction - Callback for action button
     * @returns {number} Toast ID for programmatic dismissal
     */
    show(message, type = 'info', options = {}) {
        const {
            duration = type === 'error' ? 8000 : 5000,
            title = null,
            dismissible = true,
            action = null,
            onAction = null
        } = options;

        const id = ++this.toastId;
        const toast = this._createToast(id, message, type, title, dismissible, action, onAction);

        this.container.appendChild(toast);
        this.toasts.set(id, toast);

        // Trigger animation
        requestAnimationFrame(() => {
            toast.classList.add('visible');
        });

        // Auto dismiss
        if (duration > 0) {
            setTimeout(() => this.dismiss(id), duration);
        }

        return id;
    }

    _createToast(id, message, type, title, dismissible, action, onAction) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.dataset.toastId = id;

        const icon = this._getIcon(type);

        let html = `
            <div class="toast-icon">${icon}</div>
            <div class="toast-content">
                ${title ? `<div class="toast-title">${this._escapeHtml(title)}</div>` : ''}
                <div class="toast-message">${this._escapeHtml(message)}</div>
            </div>
        `;

        if (action && onAction) {
            html += `<button class="toast-action">${this._escapeHtml(action)}</button>`;
        }

        if (dismissible) {
            html += `<button class="toast-close" aria-label="Dismiss">&times;</button>`;
        }

        toast.innerHTML = html;

        // Event listeners
        if (dismissible) {
            toast.querySelector('.toast-close').addEventListener('click', () => this.dismiss(id));
        }

        if (action && onAction) {
            toast.querySelector('.toast-action').addEventListener('click', () => {
                onAction();
                this.dismiss(id);
            });
        }

        return toast;
    }

    _getIcon(type) {
        const icons = {
            info: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>`,
            success: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>`,
            warning: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>`,
            error: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>`
        };
        return icons[type] || icons.info;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Dismiss a toast by ID
     */
    dismiss(id) {
        const toast = this.toasts.get(id);
        if (!toast) return;

        toast.classList.remove('visible');
        toast.classList.add('hiding');

        setTimeout(() => {
            toast.remove();
            this.toasts.delete(id);
        }, 300);
    }

    /**
     * Dismiss all toasts
     */
    dismissAll() {
        this.toasts.forEach((_, id) => this.dismiss(id));
    }

    // Convenience methods
    info(message, options = {}) {
        return this.show(message, 'info', options);
    }

    success(message, options = {}) {
        return this.show(message, 'success', options);
    }

    warning(message, options = {}) {
        return this.show(message, 'warning', options);
    }

    error(message, options = {}) {
        return this.show(message, 'error', options);
    }

    /**
     * Show API key error with helpful message
     */
    showApiKeyError(mapStyle) {
        const message = `Map style "${mapStyle}" requires an API key. Please configure API keys in gopro-dashboard settings or choose a different map style.`;
        return this.show(message, 'warning', {
            title: 'API Key Required',
            duration: 10000,
            action: 'Use OSM',
            onAction: () => {
                // Switch to OSM map style
                if (window.app && window.app.state) {
                    window.app.state.updateQuickConfig({ mapStyle: 'osm' });
                    const mapStyleSelect = document.getElementById('map-style');
                    if (mapStyleSelect) {
                        mapStyleSelect.value = 'osm';
                    }
                }
            }
        });
    }
}

// Singleton instance
window.toast = new Toast();

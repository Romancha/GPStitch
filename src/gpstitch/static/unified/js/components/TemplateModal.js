/**
 * TemplateModal - Reusable modal component for template operations
 */
class TemplateModal {
    constructor() {
        this.modal = null;
        this.resolvePromise = null;
        this.rejectPromise = null;
        this._createModal();
    }

    /**
     * Create modal DOM structure
     */
    _createModal() {
        this.modal = document.createElement('div');
        this.modal.className = 'modal-overlay template-modal';
        this.modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3 class="modal-title">Title</h3>
                    <button class="modal-close" data-action="close">&times;</button>
                </div>
                <div class="modal-body"></div>
                <div class="modal-footer"></div>
            </div>
        `;
        document.body.appendChild(this.modal);

        // Event delegation
        this.modal.addEventListener('click', (e) => this._handleClick(e));
        this.modal.addEventListener('keydown', (e) => this._handleKeydown(e));
    }

    /**
     * Handle click events
     */
    _handleClick(e) {
        // Ignore if modal is not visible
        if (!this.modal.classList.contains('visible')) {
            return;
        }

        const action = e.target.dataset.action;
        if (action === 'close' || e.target === this.modal) {
            this._resolve(null);
        } else if (action === 'confirm') {
            this._handleConfirm();
        } else if (action === 'cancel') {
            this._resolve(null);
        }
    }

    /**
     * Handle keyboard events
     */
    _handleKeydown(e) {
        // Ignore if modal is not visible
        if (!this.modal.classList.contains('visible')) {
            return;
        }

        if (e.key === 'Escape') {
            this._resolve(null);
        } else if (e.key === 'Enter' && e.target.tagName !== 'BUTTON') {
            e.preventDefault();
            this._handleConfirm();
        }
    }

    /**
     * Handle confirm action
     */
    _handleConfirm() {
        const input = this.modal.querySelector('.template-input');
        if (input) {
            const value = input.value.trim();
            const errorHint = this.modal.querySelector('.input-hint');

            if (!value) {
                input.classList.add('input-error');
                if (errorHint) errorHint.textContent = 'Name cannot be empty';
                input.focus();
                return;
            }

            if (value.length > 100) {
                input.classList.add('input-error');
                if (errorHint) errorHint.textContent = 'Name is too long (max 100 characters)';
                input.focus();
                return;
            }

            this._resolve(value);
        } else {
            this._resolve(true);
        }
    }

    /**
     * Resolve the promise and hide modal
     */
    _resolve(value) {
        this.hide();
        if (this.resolvePromise) {
            const currentResolve = this.resolvePromise;
            currentResolve(value);
            // Only null out if resolvePromise wasn't changed during the call
            // (e.g., by _showOverwriteConfirm setting a new one)
            if (this.resolvePromise === currentResolve) {
                this.resolvePromise = null;
                this.rejectPromise = null;
            }
        }
    }

    /**
     * Show the modal
     */
    show() {
        this.modal.classList.add('visible');
        const input = this.modal.querySelector('.template-input');
        if (input) {
            input.focus();
            input.select();
        }
    }

    /**
     * Hide the modal
     */
    hide() {
        this.modal.classList.remove('visible');
    }

    /**
     * Show save template dialog
     * @param {string} defaultName - Default name for the template
     * @param {string[]} existingNames - List of existing template names
     * @returns {Promise<{name: string, overwrite: boolean}|null>}
     */
    showSaveDialog(defaultName = '', existingNames = []) {
        return new Promise((resolve) => {
            this.resolvePromise = resolve;

            const title = this.modal.querySelector('.modal-title');
            const body = this.modal.querySelector('.modal-body');
            const footer = this.modal.querySelector('.modal-footer');

            title.textContent = 'Save Template';
            body.innerHTML = `
                <div class="form-group">
                    <label for="template-name-input">Template Name</label>
                    <input type="text"
                           id="template-name-input"
                           class="template-input"
                           value="${this._escapeHtml(defaultName)}"
                           placeholder="Enter template name..."
                           autocomplete="off">
                    <div class="input-hint">Choose a name for your template</div>
                </div>
            `;
            footer.innerHTML = `
                <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                <button class="btn btn-primary" data-action="confirm">Save</button>
            `;

            // Override confirm handler for name conflict check
            const originalResolve = this.resolvePromise;
            this.resolvePromise = (value) => {
                if (value && typeof value === 'string') {
                    if (existingNames.includes(value)) {
                        // Show overwrite confirmation
                        this._showOverwriteConfirm(value).then(overwrite => {
                            if (overwrite) {
                                originalResolve({ name: value, overwrite: true });
                            } else {
                                // Re-show save dialog
                                this.showSaveDialog(value, existingNames).then(originalResolve);
                            }
                        });
                    } else {
                        originalResolve({ name: value, overwrite: false });
                    }
                } else {
                    originalResolve(null);
                }
            };

            this.show();
        });
    }

    /**
     * Show overwrite confirmation
     */
    _showOverwriteConfirm(name) {
        return new Promise((resolve) => {
            const title = this.modal.querySelector('.modal-title');
            const body = this.modal.querySelector('.modal-body');
            const footer = this.modal.querySelector('.modal-footer');

            title.textContent = 'Template Exists';
            body.innerHTML = `
                <p class="confirm-message">
                    Template "<strong>${this._escapeHtml(name)}</strong>" already exists.
                    <br>Do you want to overwrite it?
                </p>
            `;
            footer.innerHTML = `
                <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                <button class="btn btn-primary" data-action="confirm">Overwrite</button>
            `;

            this.resolvePromise = (value) => {
                resolve(value === true);
            };

            // Show the modal (it was hidden by previous _resolve call)
            this.show();
        });
    }

    /**
     * Show rename dialog
     * @param {string} currentName
     * @param {string[]} existingNames
     * @returns {Promise<string|null>}
     */
    showRenameDialog(currentName, existingNames = []) {
        return new Promise((resolve) => {
            this.resolvePromise = resolve;

            const title = this.modal.querySelector('.modal-title');
            const body = this.modal.querySelector('.modal-body');
            const footer = this.modal.querySelector('.modal-footer');

            title.textContent = 'Rename Template';
            body.innerHTML = `
                <div class="form-group">
                    <label for="template-name-input">New Name</label>
                    <input type="text"
                           id="template-name-input"
                           class="template-input"
                           value="${this._escapeHtml(currentName)}"
                           placeholder="Enter new name..."
                           autocomplete="off">
                    <div class="input-error-message hidden">This name already exists</div>
                </div>
            `;
            footer.innerHTML = `
                <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                <button class="btn btn-primary" data-action="confirm">Rename</button>
            `;

            // Validate on confirm
            const originalResolve = this.resolvePromise;
            this.resolvePromise = (value) => {
                if (value && typeof value === 'string') {
                    if (value === currentName) {
                        originalResolve(null); // No change
                    } else if (existingNames.includes(value)) {
                        const errorMsg = this.modal.querySelector('.input-error-message');
                        const input = this.modal.querySelector('.template-input');
                        if (errorMsg) errorMsg.classList.remove('hidden');
                        if (input) input.classList.add('input-error');
                        // Don't close, let user fix
                        this.resolvePromise = originalResolve;
                    } else {
                        originalResolve(value);
                    }
                } else {
                    originalResolve(null);
                }
            };

            this.show();
        });
    }

    /**
     * Show delete confirmation dialog (safe from XSS)
     * @param {string} templateName - Raw template name (will be escaped)
     * @returns {Promise<boolean>}
     */
    showDeleteConfirmDialog(templateName) {
        return new Promise((resolve) => {
            this.resolvePromise = resolve;

            const title = this.modal.querySelector('.modal-title');
            const body = this.modal.querySelector('.modal-body');
            const footer = this.modal.querySelector('.modal-footer');

            title.textContent = 'Confirm Delete';

            // Safely construct the message using DOM methods to avoid XSS
            body.innerHTML = '';
            const p = document.createElement('p');
            p.className = 'confirm-message';
            p.appendChild(document.createTextNode('Delete template "'));
            const strong = document.createElement('strong');
            strong.textContent = templateName;
            p.appendChild(strong);
            p.appendChild(document.createTextNode('"?'));
            p.appendChild(document.createElement('br'));
            p.appendChild(document.createTextNode('This action cannot be undone.'));
            body.appendChild(p);

            footer.innerHTML = `
                <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                <button class="btn btn-danger" data-action="confirm">Delete</button>
            `;

            this.resolvePromise = (value) => {
                resolve(value === true);
            };

            this.show();
        });
    }

    /**
     * Escape HTML
     */
    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Export singleton
window.TemplateModal = TemplateModal;
window.templateModal = new TemplateModal();

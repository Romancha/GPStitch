/**
 * OverwriteConfirmDialog - Confirmation dialog for file overwrites
 * Shows list of files that will be overwritten with three action options
 */

class OverwriteConfirmDialog {
    constructor() {
        this.resolvePromise = null;
        this._createModal();
        this._attachEventListeners();
    }

    _createModal() {
        const modalHtml = `
            <div id="overwrite-confirm-modal" class="modal-overlay" style="display: none;">
                <div class="modal overwrite-confirm-modal">
                    <div class="modal-header">
                        <h3 id="overwrite-confirm-title">Files Already Exist</h3>
                    </div>
                    <div class="modal-body">
                        <p id="overwrite-confirm-message" class="overwrite-message"></p>
                        <div id="overwrite-file-list" class="overwrite-file-list"></div>
                    </div>
                    <div class="modal-footer overwrite-footer">
                        <button id="overwrite-cancel-btn" class="btn btn-secondary">Cancel</button>
                        <button id="overwrite-skip-btn" class="btn btn-primary">Skip Existing</button>
                        <button id="overwrite-confirm-btn" class="btn btn-danger">Overwrite All</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        this.modal = document.getElementById('overwrite-confirm-modal');
        this.titleEl = document.getElementById('overwrite-confirm-title');
        this.messageEl = document.getElementById('overwrite-confirm-message');
        this.fileListEl = document.getElementById('overwrite-file-list');
        this.cancelBtn = document.getElementById('overwrite-cancel-btn');
        this.skipBtn = document.getElementById('overwrite-skip-btn');
        this.confirmBtn = document.getElementById('overwrite-confirm-btn');
    }

    _attachEventListeners() {
        this.cancelBtn.addEventListener('click', () => this._resolve(null));
        this.skipBtn.addEventListener('click', () => this._resolve('skip'));
        this.confirmBtn.addEventListener('click', () => this._resolve('overwrite'));

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.style.display === 'flex') {
                this._resolve(null);
            }
        });
    }

    /**
     * Show the confirmation dialog
     * @param {string[]} existingFiles - List of file paths that already exist
     * @param {Object} options - Optional configuration
     * @param {string} options.title - Dialog title
     * @param {string} options.message - Dialog message
     * @param {boolean} options.showSkip - Whether to show Skip button (default: true)
     * @returns {Promise<'overwrite'|'skip'|null>} User's choice
     */
    show(existingFiles, options = {}) {
        return new Promise((resolve) => {
            this.resolvePromise = resolve;

            // Set title and message
            this.titleEl.textContent = options.title || 'Files Already Exist';
            this.messageEl.textContent = options.message ||
                `The following ${existingFiles.length} file(s) will be overwritten:`;

            // Populate file list
            this.fileListEl.innerHTML = '';
            existingFiles.forEach(filePath => {
                const item = document.createElement('div');
                item.className = 'overwrite-file-item';
                item.textContent = filePath;
                this.fileListEl.appendChild(item);
            });

            // Show/hide skip button
            this.skipBtn.style.display = options.showSkip === false ? 'none' : 'inline-block';

            // Show modal
            this.modal.style.display = 'flex';
        });
    }

    _resolve(value) {
        this.modal.style.display = 'none';
        if (this.resolvePromise) {
            this.resolvePromise(value);
            this.resolvePromise = null;
        }
    }
}

// Export as singleton
window.OverwriteConfirmDialog = OverwriteConfirmDialog;
window.overwriteConfirmDialog = new OverwriteConfirmDialog();

/**
 * TemplateManager - Manages custom templates (save, load, delete, rename, upload)
 * Uses backend filesystem storage for templates.
 */
class TemplateManager {
    /**
     * @param {ModeToggle} modeToggle
     * @param {UnifiedState} state
     */
    constructor(modeToggle, state) {
        this.modeToggle = modeToggle;
        this.state = state;
        this.apiClient = window.apiClient;
        this.modal = window.templateModal;
        this.templateService = new TemplateService();

        // Predefined layouts from API
        this.predefinedLayouts = [];

        // Cached custom templates
        this._customTemplates = [];

        // Refresh counter to prevent race conditions
        this._refreshId = 0;

        // DOM elements
        this.templateSelect = document.getElementById('template-select');
        this.manageModal = null;
        this.templateList = null;

        this._createManageModal();
        this._attachEventListeners();
    }

    /**
     * Create manage templates modal
     */
    _createManageModal() {
        this.manageModal = document.createElement('div');
        this.manageModal.id = 'manage-templates-modal';
        this.manageModal.className = 'modal-overlay';
        this.manageModal.innerHTML = `
            <div class="modal modal-wide">
                <div class="modal-header">
                    <h3>My Templates</h3>
                    <button class="modal-close" data-close-modal>&times;</button>
                </div>
                <div class="modal-body">
                    <div id="template-list-container"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-close-modal>Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(this.manageModal);

        // Initialize template list
        const listContainer = this.manageModal.querySelector('#template-list-container');
        this.templateList = new TemplateList(listContainer, (action, name) => {
            this._handleListAction(action, name);
        });

        // Close on backdrop click or close button
        this.manageModal.addEventListener('click', (e) => {
            // Only close if clicking on backdrop itself or close button
            const isBackdrop = e.target === this.manageModal;
            const isCloseBtn = e.target.closest('[data-close-modal]');

            if (isBackdrop || isCloseBtn) {
                e.stopPropagation();
                this.hideManageModal();
            }
        });
    }

    /**
     * Attach event listeners for toolbar buttons
     */
    _attachEventListeners() {
        // Save button
        const saveBtn = document.getElementById('btn-save-template');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveTemplate());
        }

        // Upload button and file input
        const uploadBtn = document.getElementById('btn-upload-template');
        const fileInput = document.getElementById('template-file-input');
        if (uploadBtn && fileInput) {
            uploadBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.uploadTemplate(file);
                    e.target.value = ''; // Reset input
                }
            });
        }

        // Manage button
        const manageBtn = document.getElementById('btn-manage-templates');
        if (manageBtn) {
            manageBtn.addEventListener('click', () => this.showManageModal());
        }

        // Template select change
        if (this.templateSelect) {
            this.templateSelect.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.loadTemplate(e.target.value);
                }
            });
        }
    }

    /**
     * Set predefined layouts from API
     * @param {Array} layouts
     */
    setPredefinedLayouts(layouts) {
        this.predefinedLayouts = layouts || [];
        this.refreshTemplateDropdown();
    }

    /**
     * Refresh template dropdown with both predefined and custom sections
     */
    async refreshTemplateDropdown() {
        if (!this.templateSelect) return;

        // Increment refresh ID to track current refresh operation
        const currentRefreshId = ++this._refreshId;

        // Fetch custom templates first (async)
        let customTemplates = [];
        try {
            customTemplates = await this.templateService.listTemplates();
            this._customTemplates = customTemplates;
        } catch (error) {
            console.error('Failed to load custom templates:', error);
        }

        // Check if this refresh is still current (not superseded by another refresh)
        if (currentRefreshId !== this._refreshId) {
            return; // Another refresh started, abandon this one
        }

        // Now rebuild the dropdown (all synchronous from here)
        this.templateSelect.innerHTML = '<option value="">-- Select Template --</option>';

        // Predefined templates group
        if (this.predefinedLayouts.length > 0) {
            const predefinedGroup = document.createElement('optgroup');
            predefinedGroup.label = 'Predefined Templates';
            for (const layout of this.predefinedLayouts) {
                const option = document.createElement('option');
                option.value = `predefined:${layout.name}`;
                option.textContent = layout.display_name || layout.name;
                predefinedGroup.appendChild(option);
            }
            this.templateSelect.appendChild(predefinedGroup);
        }

        // Custom templates group
        if (customTemplates.length > 0) {
            const customGroup = document.createElement('optgroup');
            customGroup.label = 'My Templates';
            for (const template of customTemplates) {
                const option = document.createElement('option');
                option.value = `custom:${template.name}`;
                option.textContent = template.name;
                option.dataset.filePath = template.file_path;  // Store file path
                customGroup.appendChild(option);
            }
            this.templateSelect.appendChild(customGroup);
        }
    }

    /**
     * Get the currently selected template's file path
     * @returns {string|null}
     */
    getSelectedTemplatePath() {
        if (!this.templateSelect) return null;

        const selectedValue = this.templateSelect.value;
        if (!selectedValue || !selectedValue.startsWith('custom:')) return null;

        const selectedOption = this.templateSelect.querySelector(`option[value="${selectedValue}"]`);
        return selectedOption?.dataset.filePath || null;
    }

    /**
     * Get the currently selected template name
     * @returns {{type: string, name: string}|null}
     */
    getSelectedTemplate() {
        if (!this.templateSelect || !this.templateSelect.value) return null;

        const colonIndex = this.templateSelect.value.indexOf(':');
        if (colonIndex === -1) return null;

        return {
            type: this.templateSelect.value.substring(0, colonIndex),
            name: this.templateSelect.value.substring(colonIndex + 1)
        };
    }

    /**
     * Load template by value (predefined:name or custom:name)
     * @param {string} value
     */
    async loadTemplate(value) {
        if (!value) return;

        const colonIndex = value.indexOf(':');
        if (colonIndex === -1) return;

        const type = value.substring(0, colonIndex);
        const name = value.substring(colonIndex + 1);

        if (type === 'predefined') {
            await this._loadPredefinedTemplate(name);
        } else if (type === 'custom') {
            await this._loadCustomTemplate(name);
        }
    }

    /**
     * Load predefined template from API
     */
    async _loadPredefinedTemplate(name) {
        try {
            const sessionId = this.state.sessionId || 'default';
            const response = await this.apiClient.loadPredefinedLayout(sessionId, name);
            if (response.layout) {
                window.editorState.setLayout(response.layout);
                this._updateEditor();
            }
        } catch (error) {
            console.error('Failed to load predefined template:', error);
            this._showError('Failed to load template: ' + error.message);
        }
    }

    /**
     * Load custom template from backend
     */
    async _loadCustomTemplate(name) {
        try {
            const response = await this.templateService.loadTemplate(name);

            if (!response.layout) {
                this._showError(`Template "${name}" not found`);
                return;
            }

            window.editorState.setLayout(response.layout);
            this._updateEditor();
        } catch (error) {
            console.error('Failed to load custom template:', error);
            this._showError(`Failed to load template "${name}"`);
        }
    }

    /**
     * Update editor after loading template
     */
    _updateEditor() {
        if (this.modeToggle) {
            this.modeToggle._updateCanvasHint();
            if (this.modeToggle.canvas) {
                this.modeToggle.canvas.render();
                this.modeToggle.canvas.fitToView();
            }
        }
    }

    /**
     * Save current layout as template
     */
    async saveTemplate() {
        const layout = window.editorState?.layout;
        if (!layout) {
            this._showError('No layout to save');
            return;
        }

        // Get default name - prefer currently selected custom template name
        const selectedTemplate = this.getSelectedTemplate();
        let defaultName = 'My Template';
        if (selectedTemplate && selectedTemplate.type === 'custom') {
            defaultName = selectedTemplate.name;
        } else if (layout.metadata?.name) {
            defaultName = layout.metadata.name;
        }

        // Get existing template names from backend
        try {
            const templates = await this.templateService.listTemplates();
            const existingNames = templates.map(t => t.name);

            // Show save dialog
            const result = await this.modal.showSaveDialog(defaultName, existingNames);
            if (!result) return;

            // Save to backend
            await this.templateService.saveTemplate(result.name, layout);
            await this.refreshTemplateDropdown();

            // Select the saved template in dropdown
            if (this.templateSelect) {
                this.templateSelect.value = `custom:${result.name}`;
            }

            this._showSuccess(`Template "${result.name}" saved`);
        } catch (error) {
            console.error('Failed to save template:', error);
            this._showError('Failed to save template: ' + error.message);
        }
    }

    /**
     * Upload XML template file
     * @param {File} file
     */
    async uploadTemplate(file) {
        try {
            const response = await this.apiClient.loadLayoutFromFile(file);

            if (response.layout) {
                // Set layout immediately for preview
                window.editorState.setLayout(response.layout);
                this._updateEditor();

                // Ask if user wants to save
                const defaultName = file.name.replace(/\.xml$/i, '');
                const templates = await this.templateService.listTemplates();
                const existingNames = templates.map(t => t.name);

                const result = await this.modal.showSaveDialog(defaultName, existingNames);
                if (result) {
                    await this.templateService.saveTemplate(result.name, response.layout);
                    await this.refreshTemplateDropdown();

                    // Select the saved template in dropdown
                    if (this.templateSelect) {
                        this.templateSelect.value = `custom:${result.name}`;
                    }

                    this._showSuccess(`Template "${result.name}" saved`);
                }
            }
        } catch (error) {
            console.error('Failed to upload template:', error);
            this._showError('Failed to load template: ' + error.message);
        }
    }

    /**
     * Show manage templates modal
     */
    async showManageModal() {
        try {
            const templates = await this.templateService.listTemplates();
            // Convert to format expected by TemplateList
            const templatesObj = {};
            for (const t of templates) {
                templatesObj[t.name] = {
                    layout: {},  // Not needed for display
                    savedAt: t.modified_at || t.created_at
                };
            }
            this.templateList.render(templatesObj);
            this.manageModal.classList.add('visible');
        } catch (error) {
            console.error('Failed to load templates:', error);
            this._showError('Failed to load templates: ' + error.message);
        }
    }

    /**
     * Hide manage templates modal
     */
    hideManageModal() {
        this.manageModal.classList.remove('visible');
    }

    /**
     * Handle action from template list
     */
    async _handleListAction(action, name) {
        switch (action) {
            case 'load':
                await this._loadCustomTemplate(name);
                this.hideManageModal();
                // Update dropdown selection
                if (this.templateSelect) {
                    this.templateSelect.value = `custom:${name}`;
                }
                break;

            case 'rename':
                await this._renameTemplate(name);
                break;

            case 'delete':
                await this._deleteTemplate(name);
                break;
        }
    }

    /**
     * Rename template
     */
    async _renameTemplate(oldName) {
        try {
            const templates = await this.templateService.listTemplates();
            const existingNames = templates.map(t => t.name).filter(n => n !== oldName);
            const newName = await this.modal.showRenameDialog(oldName, existingNames);

            if (newName && newName !== oldName) {
                await this.templateService.renameTemplate(oldName, newName);
                await this.refreshTemplateDropdown();
                await this._refreshManageModal();
                this._showSuccess(`Template renamed to "${newName}"`);
            }
        } catch (error) {
            console.error('Failed to rename template:', error);
            this._showError('Failed to rename template: ' + error.message);
        }
    }

    /**
     * Delete template with confirmation
     */
    async _deleteTemplate(name) {
        const confirmed = await this.modal.showDeleteConfirmDialog(name);

        if (confirmed) {
            try {
                await this.templateService.deleteTemplate(name);
                await this.refreshTemplateDropdown();
                await this._refreshManageModal();
                this._showSuccess(`Template "${name}" deleted`);
            } catch (error) {
                console.error('Failed to delete template:', error);
                this._showError('Failed to delete template: ' + error.message);
            }
        }
    }

    /**
     * Refresh manage modal list
     */
    async _refreshManageModal() {
        if (this.manageModal.classList.contains('visible')) {
            try {
                const templates = await this.templateService.listTemplates();
                const templatesObj = {};
                for (const t of templates) {
                    templatesObj[t.name] = {
                        layout: {},
                        savedAt: t.modified_at || t.created_at
                    };
                }
                this.templateList.render(templatesObj);
            } catch (error) {
                console.error('Failed to refresh templates:', error);
            }
        }
    }

    /**
     * Show success message
     */
    _showSuccess(message) {
        const statusEl = document.getElementById('status-message');
        if (statusEl) {
            statusEl.textContent = message;
            setTimeout(() => {
                if (statusEl.textContent === message) {
                    statusEl.textContent = 'Ready';
                }
            }, 3000);
        }
    }

    /**
     * Show error message
     */
    _showError(message) {
        const statusEl = document.getElementById('status-message');
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.classList.add('error');
            setTimeout(() => {
                statusEl.classList.remove('error');
                if (statusEl.textContent === message) {
                    statusEl.textContent = 'Ready';
                }
            }, 5000);
        }
        console.error(message);
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

// Export
window.TemplateManager = TemplateManager;

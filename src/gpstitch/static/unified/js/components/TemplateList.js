/**
 * TemplateList - Renders list of saved templates with actions
 */
class TemplateList {
    /**
     * @param {HTMLElement} container
     * @param {Function} onAction - callback(action, templateName)
     */
    constructor(container, onAction) {
        this.container = container;
        this.onAction = onAction;
        this._attachEventListeners();
    }

    /**
     * Attach event delegation
     */
    _attachEventListeners() {
        this.container.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (btn) {
                const action = btn.dataset.action;
                const name = btn.dataset.name;
                if (action && name && this.onAction) {
                    this.onAction(action, name);
                }
            }
        });
    }

    /**
     * Render template list
     * @param {Object} templates - {name: {layout, savedAt}, ...}
     */
    render(templates) {
        const names = Object.keys(templates).sort((a, b) =>
            a.toLowerCase().localeCompare(b.toLowerCase())
        );

        if (names.length === 0) {
            this._renderEmptyState();
            return;
        }

        // Build table using DOM methods for XSS safety
        const table = document.createElement('table');
        table.className = 'template-list-table';

        // Header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        ['Name', 'Saved', 'Actions'].forEach(text => {
            const th = document.createElement('th');
            th.textContent = text;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        names.forEach(name => {
            const row = this._renderTemplateRow(name, templates[name]);
            tbody.appendChild(row);
        });
        table.appendChild(tbody);

        this.container.innerHTML = '';
        this.container.appendChild(table);
    }

    /**
     * Render single template row using DOM methods for safety
     */
    _renderTemplateRow(name, data) {
        const date = this._formatDate(data.savedAt);

        const tr = document.createElement('tr');
        tr.className = 'template-list-item';

        // Name cell with load button
        const tdName = document.createElement('td');
        tdName.className = 'template-name';
        const loadBtn = document.createElement('button');
        loadBtn.className = 'template-load-btn';
        loadBtn.dataset.action = 'load';
        loadBtn.dataset.name = name;
        loadBtn.textContent = name;
        tdName.appendChild(loadBtn);
        tr.appendChild(tdName);

        // Date cell
        const tdDate = document.createElement('td');
        tdDate.className = 'template-date';
        tdDate.textContent = date;
        tr.appendChild(tdDate);

        // Actions cell
        const tdActions = document.createElement('td');
        tdActions.className = 'template-actions';

        // Rename button
        const renameBtn = document.createElement('button');
        renameBtn.className = 'btn btn-sm btn-icon';
        renameBtn.dataset.action = 'rename';
        renameBtn.dataset.name = name;
        renameBtn.title = 'Rename';
        renameBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
        </svg>`;
        tdActions.appendChild(renameBtn);

        // Delete button
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-icon btn-danger-icon';
        deleteBtn.dataset.action = 'delete';
        deleteBtn.dataset.name = name;
        deleteBtn.title = 'Delete';
        deleteBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
        </svg>`;
        tdActions.appendChild(deleteBtn);

        tr.appendChild(tdActions);

        return tr;
    }

    /**
     * Render empty state
     */
    _renderEmptyState() {
        this.container.innerHTML = `
            <div class="template-list-empty">
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                    </svg>
                </div>
                <p class="empty-title">No saved templates</p>
                <p class="empty-hint">Save your first template using the Save button</p>
            </div>
        `;
    }

    /**
     * Clear the list
     */
    clear() {
        this.container.innerHTML = '';
    }

    /**
     * Format date for display
     */
    _formatDate(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return '';
        }
    }
}

// Export
window.TemplateList = TemplateList;

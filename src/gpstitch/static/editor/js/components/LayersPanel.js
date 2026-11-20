/**
 * LayersPanel - Widget hierarchy/layers panel
 */

class LayersPanel {
    constructor(container, state) {
        this.container = container;
        this.state = state;

        this._dragSourceId = null;

        this._attachStateListeners();
        this._attachContainerDragListeners();
        this.render();
    }

    _attachStateListeners() {
        this.state.on('layout:changed', () => this.render());
        this.state.on('layout:restored', () => this.render());
        this.state.on('widget:added', () => this.render());
        this.state.on('widget:removed', () => this.render());
        this.state.on('widget:updated', () => this.render());
        this.state.on('selection:changed', () => this._updateSelection());
    }

    /**
     * Render the layers panel
     */
    render() {
        if (!this.state.layout) {
            this.container.innerHTML = '<p class="no-selection">No layout loaded</p>';
            return;
        }

        const widgets = this.state.layout.widgets;
        if (widgets.length === 0) {
            this.container.innerHTML = '<p class="no-selection">No widgets in layout</p>';
            return;
        }

        // Render in reverse order (top layers first)
        const html = this._renderLayers([...widgets].reverse(), 0);
        this.container.innerHTML = html;

        this._attachLayerListeners();
    }

    _renderLayers(widgets, depth) {
        return widgets.map(widget => this._renderLayer(widget, depth)).join('');
    }

    _renderLayer(widget, depth) {
        const isSelected = this.state.selectedWidgets.has(widget.id);
        const metadata = this.state.widgetMetadataByType[widget.type];
        const icon = metadata?.icon || widget.type.charAt(0).toUpperCase();
        const displayName = widget.name || metadata?.name || widget.type;
        const subtype = widget.name ? (metadata?.name || widget.type) : null;
        const description = metadata?.description || '';

        const classes = [
            'layer-item',
            isSelected ? 'selected' : '',
            depth > 0 ? 'nested' : ''
        ].filter(c => c).join(' ');

        const subtypeHtml = subtype
            ? `<div class="layer-subtype">${this._escapeHtml(subtype)}</div>`
            : '';

        let html = `
            <div class="${classes}" data-widget-id="${widget.id}" draggable="true" style="padding-left: ${depth * 16 + 8}px;" title="${this._escapeHtml(description)}">
                <span class="layer-drag-handle" title="Drag to reorder">⠿</span>
                <span class="layer-icon">${icon}</span>
                <div class="layer-name-group">
                    <div class="layer-name">${this._escapeHtml(displayName)}</div>
                    ${subtypeHtml}
                </div>
                <div class="layer-actions">
                    <button class="layer-action" data-action="visibility" title="${widget.visible ? 'Hide' : 'Show'}">
                        ${widget.visible ? '👁' : '🚫'}
                    </button>
                    <button class="layer-action" data-action="lock" title="${widget.locked ? 'Unlock' : 'Lock'}">
                        ${widget.locked ? '🔒' : '🔓'}
                    </button>
                    <button class="layer-action" data-action="delete" title="Delete">🗑</button>
                </div>
            </div>
        `;

        // Render children
        if (widget.children && widget.children.length > 0) {
            html += this._renderLayers([...widget.children].reverse(), depth + 1);
        }

        return html;
    }

    _attachLayerListeners() {
        const items = this.container.querySelectorAll('.layer-item');

        items.forEach(item => {
            const widgetId = item.dataset.widgetId;

            // Click to select
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('layer-action')) return;
                if (e.target.classList.contains('layer-drag-handle')) return;
                this.state.select(widgetId, e.shiftKey);
            });

            // Action buttons
            const actions = item.querySelectorAll('.layer-action');
            actions.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const action = btn.dataset.action;
                    const widget = this.state.findWidget(widgetId);

                    if (action === 'visibility') {
                        this.state.updateWidget(widgetId, { visible: !widget.visible });
                        this.render();
                    } else if (action === 'lock') {
                        this.state.updateWidget(widgetId, { locked: !widget.locked });
                        this.render();
                    } else if (action === 'delete') {
                        this.state.removeWidget(widgetId);
                    }
                });
            });

            // Drag-and-drop — reordering (dragstart/dragend per item)
            item.addEventListener('dragstart', (e) => {
                this._dragSourceId = widgetId;
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', widgetId);
            });

            item.addEventListener('dragend', () => {
                this._dragSourceId = null;
                item.classList.remove('dragging');
            });
        });

    }

    _attachContainerDragListeners() {
        this.container.addEventListener('dragover', (e) => {
            if (!this._dragSourceId) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        });

        this.container.addEventListener('drop', (e) => {
            e.preventDefault();
            const sourceId = this._dragSourceId;
            if (!sourceId) return;

            const targetItem = e.target.closest('.layer-item');
            if (!targetItem || targetItem.dataset.widgetId === sourceId) return;

            const targetId = targetItem.dataset.widgetId;
            const rect = targetItem.getBoundingClientRect();
            const isBefore = e.clientY < rect.top + rect.height / 2;

            // The layers panel renders in REVERSE order (top-of-stack first).
            // "before" visually means "after" in the real array (higher index = drawn later = on top).
            // "after" visually means "before" in the real array.
            const position = isBefore ? 'after' : 'before';
            this.state.reorderWidget(sourceId, targetId, position);
        });
    }

    _updateSelection() {
        const items = this.container.querySelectorAll('.layer-item');
        items.forEach(item => {
            const widgetId = item.dataset.widgetId;
            if (this.state.selectedWidgets.has(widgetId)) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
    }

    _escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        // Also escape quotes for use in HTML attributes
        return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
}

window.LayersPanel = LayersPanel;

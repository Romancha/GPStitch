/**
 * EditorState - Central state management for the visual editor
 * Uses observer pattern for reactive UI updates
 */

class EditorState {
    constructor() {
        /** @type {Object|null} Layout object */
        this.layout = null;

        /** @type {Set<string>} Selected widget IDs */
        this.selectedWidgets = new Set();

        /** @type {Array} Widget metadata from server */
        this.widgetMetadata = [];

        /** @type {Object} Widget metadata indexed by type */
        this.widgetMetadataByType = {};

        /** @type {boolean} Has unsaved changes */
        this.isDirty = false;

        /** @type {Object|null} Clipboard for copy/paste */
        this.clipboard = null;

        /** @type {Map<string, Function[]>} Event listeners */
        this.listeners = new Map();

        /** @type {HistoryManager} Undo/redo manager */
        this.history = null;
    }

    /**
     * Initialize with a new or loaded layout
     * @param {Object} layout
     */
    setLayout(layout) {
        const previous = this.layout;
        this.layout = layout;
        this.isDirty = false;
        this.selectedWidgets.clear();

        if (this.history) {
            this.history.clear();
            this.history.snapshot();
        }

        this.emit('layout:changed', { previous, current: layout });
        this.emit('selection:changed', { selected: [] });
    }

    /**
     * Create a new blank layout
     * @param {number} width
     * @param {number} height
     */
    newLayout(width = 1920, height = 1080) {
        this.setLayout({
            id: this._generateId(),
            metadata: {
                name: 'Untitled Layout',
                version: '1.0'
            },
            canvas: {
                width,
                height,
                grid_enabled: true,
                grid_size: 10,
                snap_to_grid: false
            },
            widgets: []
        });
    }

    /**
     * Add a widget to the layout
     * @param {string} type Widget type
     * @param {number} x X position
     * @param {number} y Y position
     * @param {string|null} parentId Parent widget ID for nesting
     * @returns {Object} The created widget
     */
    addWidget(type, x, y, parentId = null) {
        const metadata = this.widgetMetadataByType[type];
        if (!metadata) {
            console.error(`Unknown widget type: ${type}`);
            return null;
        }

        // Create widget with default properties
        const widget = {
            id: this._generateId(),
            type,
            name: null,
            x,
            y,
            properties: this._getDefaultProperties(metadata),
            children: [],
            locked: false,
            visible: true
        };

        if (parentId) {
            const parent = this.findWidget(parentId);
            if (parent && parent.children) {
                parent.children.push(widget);
            }
        } else {
            this.layout.widgets.push(widget);
        }

        this.isDirty = true;
        if (this.history) this.history.snapshot();
        this.emit('widget:added', { widget, parentId });

        return widget;
    }

    /**
     * Remove a widget by ID
     * @param {string} widgetId
     */
    removeWidget(widgetId) {
        const removed = this._removeWidgetRecursive(this.layout.widgets, widgetId);
        if (removed) {
            this.selectedWidgets.delete(widgetId);
            this.isDirty = true;
            if (this.history) this.history.snapshot();
            this.emit('widget:removed', { widgetId });
            this.emit('selection:changed', { selected: Array.from(this.selectedWidgets) });
        }
    }

    /**
     * Update a widget's position or properties
     * @param {string} widgetId
     * @param {Object} updates
     */
    updateWidget(widgetId, updates) {
        const widget = this.findWidget(widgetId);
        if (widget) {
            Object.assign(widget, updates);
            this.isDirty = true;
            this.emit('widget:updated', { widgetId, updates });
        }
    }

    /**
     * Update a widget's property
     * @param {string} widgetId
     * @param {string} propertyName
     * @param {*} value
     */
    setWidgetProperty(widgetId, propertyName, value) {
        const widget = this.findWidget(widgetId);
        if (widget) {
            if (propertyName === 'x' || propertyName === 'y') {
                widget[propertyName] = value;
            } else {
                widget.properties[propertyName] = value;
            }
            this.isDirty = true;
            if (this.history) this.history.snapshot();
            this.emit('property:changed', { widgetId, propertyName, value });
        }
    }

    /**
     * Save snapshot for undo
     */
    saveSnapshot() {
        if (this.history) this.history.snapshot();
    }

    /**
     * Find a widget by ID (searches recursively)
     * @param {string} widgetId
     * @returns {Object|null}
     */
    findWidget(widgetId) {
        return this._findWidgetRecursive(this.layout.widgets, widgetId);
    }

    /**
     * Select widgets
     * @param {string|string[]} widgetIds
     * @param {boolean} addToSelection
     */
    select(widgetIds, addToSelection = false) {
        if (!addToSelection) {
            this.selectedWidgets.clear();
        }

        const ids = Array.isArray(widgetIds) ? widgetIds : [widgetIds];
        ids.forEach(id => this.selectedWidgets.add(id));

        this.emit('selection:changed', { selected: Array.from(this.selectedWidgets) });
    }

    /**
     * Clear selection
     */
    clearSelection() {
        this.selectedWidgets.clear();
        this.emit('selection:changed', { selected: [] });
    }

    /**
     * Get selected widgets
     * @returns {Object[]}
     */
    getSelectedWidgets() {
        return Array.from(this.selectedWidgets)
            .map(id => this.findWidget(id))
            .filter(w => w !== null);
    }

    /**
     * Get first selected widget
     * @returns {Object|null}
     */
    getSelectedWidget() {
        const selected = this.getSelectedWidgets();
        return selected.length > 0 ? selected[0] : null;
    }

    /**
     * Update canvas settings
     * @param {Object} settings
     */
    updateCanvas(settings) {
        Object.assign(this.layout.canvas, settings);
        this.isDirty = true;
        this.emit('canvas:changed', { canvas: this.layout.canvas });
    }

    /**
     * Subscribe to state changes
     * @param {string} event
     * @param {Function} callback
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    /**
     * Unsubscribe from state changes
     * @param {string} event
     * @param {Function} callback
     */
    off(event, callback) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }

    /**
     * Emit an event
     * @param {string} event
     * @param {*} data
     */
    emit(event, data) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            listeners.forEach(cb => {
                try {
                    cb(data);
                } catch (e) {
                    console.error(`Error in event listener for ${event}:`, e);
                }
            });
        }
    }

    /**
     * Export layout to JSON
     * @returns {Object}
     */
    toJSON() {
        return JSON.parse(JSON.stringify(this.layout));
    }

    /**
     * Import layout from JSON
     * @param {Object} data
     */
    fromJSON(data) {
        this.setLayout(data);
    }

    // Private helper methods

    _generateId() {
        return 'w_' + Math.random().toString(36).substr(2, 9);
    }

    _getDefaultProperties(metadata) {
        const props = {};
        for (const propDef of metadata.properties) {
            if (propDef.name === 'x' || propDef.name === 'y') continue;
            if (propDef.constraints && propDef.constraints.default !== undefined) {
                props[propDef.name] = propDef.constraints.default;
            }
        }
        return props;
    }

    _findWidgetRecursive(widgets, widgetId) {
        for (const widget of widgets) {
            if (widget.id === widgetId) {
                return widget;
            }
            if (widget.children && widget.children.length > 0) {
                const found = this._findWidgetRecursive(widget.children, widgetId);
                if (found) return found;
            }
        }
        return null;
    }

    _removeWidgetRecursive(widgets, widgetId) {
        for (let i = 0; i < widgets.length; i++) {
            if (widgets[i].id === widgetId) {
                widgets.splice(i, 1);
                return true;
            }
            if (widgets[i].children && widgets[i].children.length > 0) {
                if (this._removeWidgetRecursive(widgets[i].children, widgetId)) {
                    return true;
                }
            }
        }
        return false;
    }
}

// Export singleton
window.editorState = new EditorState();

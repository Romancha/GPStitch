/**
 * Storage - localStorage wrapper for saving layouts
 */

class Storage {
    constructor(prefix = 'gopro_editor_') {
        this.prefix = prefix;
    }

    /**
     * Save layout to localStorage
     * @param {Object} layout
     */
    saveLayout(layout) {
        try {
            const key = this.prefix + 'current_layout';
            localStorage.setItem(key, JSON.stringify(layout));
            return true;
        } catch (e) {
            console.error('Failed to save layout:', e);
            return false;
        }
    }

    /**
     * Load layout from localStorage
     * @returns {Object|null}
     */
    loadLayout() {
        try {
            const key = this.prefix + 'current_layout';
            const data = localStorage.getItem(key);
            return data ? JSON.parse(data) : null;
        } catch (e) {
            console.error('Failed to load layout:', e);
            return null;
        }
    }

    /**
     * Save named layout
     * @param {string} name
     * @param {Object} layout
     */
    saveNamedLayout(name, layout) {
        try {
            const layouts = this.getNamedLayouts();
            layouts[name] = {
                layout,
                savedAt: new Date().toISOString()
            };
            localStorage.setItem(this.prefix + 'named_layouts', JSON.stringify(layouts));
            return true;
        } catch (e) {
            console.error('Failed to save named layout:', e);
            return false;
        }
    }

    /**
     * Get all named layouts
     * @returns {Object}
     */
    getNamedLayouts() {
        try {
            const data = localStorage.getItem(this.prefix + 'named_layouts');
            return data ? JSON.parse(data) : {};
        } catch (e) {
            return {};
        }
    }

    /**
     * Delete named layout
     * @param {string} name
     */
    deleteNamedLayout(name) {
        const layouts = this.getNamedLayouts();
        delete layouts[name];
        localStorage.setItem(this.prefix + 'named_layouts', JSON.stringify(layouts));
    }

    /**
     * Rename named layout
     * @param {string} oldName
     * @param {string} newName
     * @returns {boolean}
     */
    renameNamedLayout(oldName, newName) {
        const layouts = this.getNamedLayouts();
        if (!layouts[oldName]) return false;
        layouts[newName] = layouts[oldName];
        layouts[newName].savedAt = new Date().toISOString();
        delete layouts[oldName];
        localStorage.setItem(this.prefix + 'named_layouts', JSON.stringify(layouts));
        return true;
    }

    /**
     * Check if named layout exists
     * @param {string} name
     * @returns {boolean}
     */
    hasNamedLayout(name) {
        const layouts = this.getNamedLayouts();
        return name in layouts;
    }

    /**
     * Get list of named layout names
     * @returns {string[]}
     */
    getNamedLayoutNames() {
        return Object.keys(this.getNamedLayouts());
    }

    /**
     * Clear current layout
     */
    clearLayout() {
        localStorage.removeItem(this.prefix + 'current_layout');
    }

    /**
     * Get session ID (uses the one from file upload if available)
     * @returns {string|null}
     */
    getOrCreateSessionId() {
        // First try to get session_id from file upload (set by main page)
        const uploadSessionId = localStorage.getItem(this.prefix + 'session_id');
        if (uploadSessionId) {
            return uploadSessionId;
        }
        // No file uploaded yet
        return null;
    }
}

window.storage = new Storage();

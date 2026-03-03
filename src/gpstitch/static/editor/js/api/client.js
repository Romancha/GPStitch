/**
 * API Client - Handles all API calls for the editor
 */

class APIClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    /**
     * Fetch widget metadata
     * @returns {Promise<Object>}
     */
    async getWidgetMetadata() {
        const response = await fetch(`${this.baseUrl}/api/editor/widgets`);
        if (!response.ok) {
            throw new Error(`Failed to fetch widget metadata: ${response.statusText}`);
        }
        return response.json();
    }

    /**
     * Get predefined layouts
     * @returns {Promise<Object>}
     */
    async getPredefinedLayouts() {
        const response = await fetch(`${this.baseUrl}/api/editor/layouts`);
        if (!response.ok) {
            throw new Error(`Failed to fetch layouts: ${response.statusText}`);
        }
        return response.json();
    }

    /**
     * Load a predefined layout
     * @param {string} sessionId
     * @param {string} layoutName
     * @returns {Promise<Object>}
     */
    async loadPredefinedLayout(sessionId, layoutName) {
        const response = await fetch(`${this.baseUrl}/api/editor/layout/load`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                layout_name: layoutName
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to load layout');
        }
        return response.json();
    }

    /**
     * Load layout from XML string
     * @param {string} sessionId
     * @param {string} xml
     * @returns {Promise<Object>}
     */
    async loadLayoutFromXML(sessionId, xml) {
        const response = await fetch(`${this.baseUrl}/api/editor/layout/load`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                xml: xml
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to parse XML');
        }
        return response.json();
    }

    /**
     * Load layout from file upload
     * @param {File} file
     * @returns {Promise<Object>}
     */
    async loadLayoutFromFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${this.baseUrl}/api/editor/layout/load-file`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to load file');
        }
        return response.json();
    }

    /**
     * Export layout to XML
     * @param {Object} layout
     * @returns {Promise<Object>}
     */
    async exportToXML(layout) {
        const response = await fetch(`${this.baseUrl}/api/editor/layout/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ layout })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to export XML');
        }
        return response.json();
    }

    /**
     * Save layout (generates XML)
     * @param {string} sessionId
     * @param {Object} layout
     * @returns {Promise<Object>}
     */
    async saveLayout(sessionId, layout) {
        const response = await fetch(`${this.baseUrl}/api/editor/layout/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                layout
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save layout');
        }
        return response.json();
    }

    /**
     * Generate preview
     * @param {string} sessionId
     * @param {Object} layout
     * @param {number} frameTimeMs
     * @returns {Promise<Object>}
     */
    async generatePreview(sessionId, layout, frameTimeMs = 0) {
        const response = await fetch(`${this.baseUrl}/api/editor/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                layout,
                frame_time_ms: frameTimeMs
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate preview');
        }
        return response.json();
    }
}

// Export singleton
window.apiClient = new APIClient();

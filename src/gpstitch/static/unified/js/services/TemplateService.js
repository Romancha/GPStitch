/**
 * TemplateService - Backend API client for template management
 */
class TemplateService {
    constructor() {
        this.baseUrl = '/api/templates';
    }

    /**
     * Save template to backend
     * @param {string} name
     * @param {Object} layout
     * @param {string} description
     * @returns {Promise<{name: string, file_path: string, success: boolean}>}
     */
    async saveTemplate(name, layout, description = null) {
        const response = await fetch(`${this.baseUrl}/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, layout, description })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save template');
        }

        return await response.json();
    }

    /**
     * List all templates
     * @returns {Promise<Array<{name: string, file_path: string, created_at: string, ...}>>}
     */
    async listTemplates() {
        const response = await fetch(`${this.baseUrl}/list`);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to list templates');
        }

        const data = await response.json();
        return data.templates;
    }

    /**
     * Load a specific template
     * @param {string} name
     * @returns {Promise<{layout: Object, success: boolean}>}
     */
    async loadTemplate(name) {
        const response = await fetch(`${this.baseUrl}/${encodeURIComponent(name)}`);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Template "${name}" not found`);
        }

        return await response.json();
    }

    /**
     * Get template file path
     * @param {string} name
     * @returns {Promise<{name: string, file_path: string, success: boolean}>}
     */
    async getTemplatePath(name) {
        const response = await fetch(`${this.baseUrl}/${encodeURIComponent(name)}/path`);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Template "${name}" not found`);
        }

        return await response.json();
    }

    /**
     * Delete a template
     * @param {string} name
     * @returns {Promise<{success: boolean}>}
     */
    async deleteTemplate(name) {
        const response = await fetch(`${this.baseUrl}/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Failed to delete template "${name}"`);
        }

        return await response.json();
    }

    /**
     * Rename a template
     * @param {string} oldName
     * @param {string} newName
     * @returns {Promise<{success: boolean}>}
     */
    async renameTemplate(oldName, newName) {
        const response = await fetch(`${this.baseUrl}/${encodeURIComponent(oldName)}/rename`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: newName })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to rename template');
        }

        return await response.json();
    }
}

// Export as global
window.TemplateService = TemplateService;

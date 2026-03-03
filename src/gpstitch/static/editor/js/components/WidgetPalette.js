/**
 * WidgetPalette - Widget selection panel component
 */

class WidgetPalette {
    constructor(container, state) {
        this.container = container;
        this.state = state;
        this.searchInput = document.getElementById('widget-search');

        this.init();
    }

    init() {
        // Search functionality
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => this.render());
        }
    }

    /**
     * Render the widget palette
     */
    render() {
        console.log('WidgetPalette.render() called');
        console.log('widgetMetadata:', this.state.widgetMetadata);
        console.log('widgetMetadata length:', this.state.widgetMetadata?.length);

        const searchTerm = this.searchInput ? this.searchInput.value.toLowerCase() : '';

        // Group widgets by category
        const categories = {};
        for (const widget of this.state.widgetMetadata || []) {
            // Filter by search term
            if (searchTerm && !widget.name.toLowerCase().includes(searchTerm) &&
                !widget.type.toLowerCase().includes(searchTerm)) {
                continue;
            }

            const category = widget.category;
            if (!categories[category]) {
                categories[category] = [];
            }
            categories[category].push(widget);
        }

        // Category display order
        const categoryOrder = ['text', 'metrics', 'maps', 'gauges', 'charts', 'indicators', 'containers', 'cairo'];

        // Build HTML
        let html = '';
        for (const category of categoryOrder) {
            const widgets = categories[category];
            if (!widgets || widgets.length === 0) continue;

            html += `
                <div class="widget-category">
                    <h3>${this._formatCategory(category)}</h3>
                    ${widgets.map(w => this._renderWidgetItem(w)).join('')}
                </div>
            `;
        }

        this.container.innerHTML = html || '<p class="no-selection">No widgets match your search</p>';

        // Make sure palette is visible
        this.container.classList.add('visible');

        // Attach drag listeners
        this._attachDragListeners();
    }

    _formatCategory(category) {
        return category.charAt(0).toUpperCase() + category.slice(1);
    }

    _renderWidgetItem(widget) {
        const cairoClass = widget.requires_cairo ? 'requires-cairo' : '';
        return `
            <div class="widget-item ${cairoClass}"
                 draggable="true"
                 data-widget-type="${widget.type}"
                 title="${widget.description}">
                <span class="widget-icon">${widget.icon || widget.type.charAt(0).toUpperCase()}</span>
                <span class="widget-name">${widget.name}</span>
            </div>
        `;
    }

    _attachDragListeners() {
        const items = this.container.querySelectorAll('.widget-item');

        items.forEach(item => {
            // Track drag end time to prevent dblclick from firing after drop
            let lastDragEnd = 0;

            item.addEventListener('dragstart', (e) => {
                const widgetType = item.dataset.widgetType;
                e.dataTransfer.setData('widget-type', widgetType);
                e.dataTransfer.effectAllowed = 'copy';
                item.classList.add('dragging');
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                lastDragEnd = Date.now();
            });

            // Also allow double-click to add at center (only if not recently dragged)
            item.addEventListener('dblclick', () => {
                // Prevent dblclick within 150ms of drag end
                if (Date.now() - lastDragEnd < 150) return;
                const widgetType = item.dataset.widgetType;
                const canvas = this.state.layout.canvas;
                const x = Math.floor(canvas.width / 2 - 50);
                const y = Math.floor(canvas.height / 2 - 25);
                this.state.addWidget(widgetType, x, y);
            });
        });
    }
}

window.WidgetPalette = WidgetPalette;

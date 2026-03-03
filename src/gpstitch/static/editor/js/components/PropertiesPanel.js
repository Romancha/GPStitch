/**
 * PropertiesPanel - Widget property editor component
 */

class PropertiesPanel {
    constructor(container, state) {
        this.container = container;
        this.state = state;

        this._attachStateListeners();
    }

    _attachStateListeners() {
        this.state.on('selection:changed', () => this.render());
        this.state.on('widget:updated', () => this.render());
        this.state.on('property:changed', () => this.render());
    }

    /**
     * Render the properties panel
     */
    render() {
        const selectedWidgets = this.state.getSelectedWidgets();

        if (selectedWidgets.length === 0) {
            this.container.innerHTML = '<p class="no-selection">Select a widget to edit its properties</p>';
            return;
        }

        if (selectedWidgets.length > 1) {
            this.container.innerHTML = `<p class="no-selection">${selectedWidgets.length} widgets selected</p>`;
            return;
        }

        const widget = selectedWidgets[0];
        const metadata = this.state.widgetMetadataByType[widget.type];

        if (!metadata) {
            this.container.innerHTML = '<p class="no-selection">Unknown widget type</p>';
            return;
        }

        // Group properties by category
        const groups = {};
        for (const propDef of metadata.properties) {
            const category = propDef.category || 'General';
            if (!groups[category]) {
                groups[category] = [];
            }
            groups[category].push(propDef);
        }

        // Check if widget extends beyond canvas boundaries
        const boundsWarning = this._checkWidgetBounds(widget, metadata);

        // Build HTML with widget name and description
        let html = `<div class="widget-type-header">${metadata.name}</div>`;
        if (metadata.description) {
            html += `<div class="widget-description">${this._escapeHtml(metadata.description)}</div>`;
        }

        // Show out-of-bounds warning
        if (boundsWarning) {
            html += `<div class="bounds-warning">${boundsWarning}</div>`;
        }

        for (const [category, props] of Object.entries(groups)) {
            html += `
                <div class="property-group">
                    <h4>${category}</h4>
                    ${props.map(p => this._renderProperty(widget, p)).join('')}
                </div>
            `;
        }

        this.container.innerHTML = html;

        // Attach input listeners
        this._attachInputListeners(widget);
        this._attachTooltipListeners();
    }

    _renderProperty(widget, propDef) {
        const value = propDef.name === 'x' ? widget.x :
                      propDef.name === 'y' ? widget.y :
                      widget.properties[propDef.name];

        const id = `prop-${propDef.name}`;

        let input = '';
        switch (propDef.type) {
            case 'number':
                const min = propDef.constraints?.min ?? '';
                const max = propDef.constraints?.max ?? '';
                const step = propDef.constraints?.step ?? 1;
                input = `<input type="number" id="${id}" name="${propDef.name}"
                         value="${value ?? propDef.constraints?.default ?? ''}"
                         min="${min}" max="${max}" step="${step}">`;
                break;

            case 'string':
                input = `<input type="text" id="${id}" name="${propDef.name}"
                         value="${value ?? propDef.constraints?.default ?? ''}">`;
                break;

            case 'boolean':
                const checked = value ?? propDef.constraints?.default ?? false;
                input = `<input type="checkbox" id="${id}" name="${propDef.name}"
                         ${checked ? 'checked' : ''}>`;
                break;

            case 'color':
                const colorValue = this._formatColorForInput(value ?? propDef.constraints?.default);
                const hexValue = this._rgbToHex(value ?? propDef.constraints?.default);
                input = `
                    <div class="color-input-wrapper">
                        <input type="color" id="${id}-picker" name="${propDef.name}-picker" value="${hexValue}">
                        <input type="text" id="${id}" name="${propDef.name}" value="${colorValue}" placeholder="255,255,255">
                    </div>
                `;
                break;

            case 'select':
            case 'metric':
            case 'units':
                const options = propDef.options || [];
                const selectedValue = value ?? propDef.constraints?.default ?? '';
                input = `
                    <select id="${id}" name="${propDef.name}">
                        ${options.map(opt => `
                            <option value="${opt.value}" ${opt.value === selectedValue ? 'selected' : ''}>
                                ${opt.label}
                            </option>
                        `).join('')}
                    </select>
                `;
                break;

            default:
                input = `<input type="text" id="${id}" name="${propDef.name}"
                         value="${value ?? ''}">`;
        }

        const tooltipClass = propDef.description ? ' has-tooltip' : '';
        const tooltipData = propDef.description
            ? ` data-tooltip="${this._escapeHtml(propDef.description)}"`
            : '';

        return `
            <div class="property-row${tooltipClass}"${tooltipData}>
                <label for="${id}">${propDef.label}</label>
                ${input}
            </div>
        `;
    }

    _attachInputListeners(widget) {
        const inputs = this.container.querySelectorAll('input, select');

        inputs.forEach(input => {
            const propName = input.name.replace('-picker', '');

            const updateValue = () => {
                let value;

                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (input.type === 'number') {
                    value = parseFloat(input.value);
                    if (isNaN(value)) return;
                } else if (input.type === 'color') {
                    // Update text input and use RGB format
                    const rgb = this._hexToRgb(input.value);
                    const textInput = this.container.querySelector(`#prop-${propName}`);
                    if (textInput) {
                        textInput.value = rgb.join(',');
                    }
                    value = rgb.join(',');
                } else if (input.name.endsWith('-picker')) {
                    // Skip color picker, handled above
                    return;
                } else {
                    value = input.value;
                }

                this.state.setWidgetProperty(widget.id, propName, value);
            };

            if (input.type === 'color') {
                input.addEventListener('input', updateValue);
            } else {
                input.addEventListener('change', updateValue);
            }

            // For text inputs, also update on blur
            if (input.type === 'text' && !input.name.endsWith('-picker')) {
                input.addEventListener('blur', updateValue);
            }
        });
    }

    _formatColorForInput(value) {
        if (!value) return '';
        if (Array.isArray(value)) {
            return value.join(',');
        }
        return String(value);
    }

    _rgbToHex(value) {
        if (!value) return '#ffffff';

        let rgb;
        if (Array.isArray(value)) {
            rgb = value;
        } else if (typeof value === 'string' && value.includes(',')) {
            rgb = value.split(',').map(v => parseInt(v.trim()));
        } else {
            return '#ffffff';
        }

        if (rgb.length < 3) return '#ffffff';

        return '#' + rgb.slice(0, 3).map(v => {
            const hex = Math.max(0, Math.min(255, v)).toString(16);
            return hex.length === 1 ? '0' + hex : hex;
        }).join('');
    }

    _hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? [
            parseInt(result[1], 16),
            parseInt(result[2], 16),
            parseInt(result[3], 16)
        ] : [255, 255, 255];
    }

    _attachTooltipListeners() {
        const rows = this.container.querySelectorAll('.has-tooltip');
        let tooltipTimeout = null;

        rows.forEach(row => {
            row.addEventListener('mouseenter', (e) => {
                const text = row.dataset.tooltip;
                if (!text) return;

                tooltipTimeout = setTimeout(() => {
                    // Remove existing tooltip
                    const existing = document.querySelector('.property-tooltip');
                    if (existing) existing.remove();

                    const tooltip = document.createElement('div');
                    tooltip.className = 'property-tooltip';
                    tooltip.textContent = text;
                    document.body.appendChild(tooltip);

                    const rect = row.getBoundingClientRect();
                    tooltip.style.left = `${rect.left}px`;
                    tooltip.style.top = `${rect.top - tooltip.offsetHeight - 6}px`;
                }, 200);
            });

            row.addEventListener('mouseleave', () => {
                if (tooltipTimeout) {
                    clearTimeout(tooltipTimeout);
                    tooltipTimeout = null;
                }
                const tooltip = document.querySelector('.property-tooltip');
                if (tooltip) tooltip.remove();
            });
        });
    }

    _checkWidgetBounds(widget, metadata) {
        const canvas = this.state.layout?.canvas;
        if (!canvas) return null;

        // Calculate widget display bounds
        const WIDGETS_WITH_SIZE_AS_BOX = new Set([
            'moving_map', 'journey_map', 'moving_journey_map', 'circuit_map',
            'compass', 'compass_arrow', 'asi', 'msi', 'gps_lock_icon', 'icon',
            'cairo_circuit_map', 'cairo_gauge_marker', 'cairo_gauge_round_annotated',
            'cairo_gauge_arc_annotated', 'cairo_gauge_donut'
        ]);

        const sizeAsDimension = WIDGETS_WITH_SIZE_AS_BOX.has(widget.type) ? widget.properties.size : null;
        const width = widget.properties.width || sizeAsDimension || metadata?.default_width || 100;
        const height = widget.properties.height || sizeAsDimension || metadata?.default_height || 50;

        const align = widget.properties.align;
        let displayX = widget.x;
        if (align === 'right') {
            displayX = widget.x - width;
        } else if (align === 'centre' || align === 'center') {
            displayX = widget.x - width / 2;
        }

        const issues = [];
        if (displayX < 0) {
            issues.push(`Left edge: ${displayX}px (${Math.abs(displayX)}px beyond)`);
        }
        if (widget.y < 0) {
            issues.push(`Top edge: ${widget.y}px (${Math.abs(widget.y)}px beyond)`);
        }
        if (displayX + width > canvas.width) {
            const overflow = displayX + width - canvas.width;
            issues.push(`Right edge: ${displayX + width}px (${overflow}px beyond ${canvas.width})`);
        }
        if (widget.y + height > canvas.height) {
            const overflow = widget.y + height - canvas.height;
            issues.push(`Bottom edge: ${widget.y + height}px (${overflow}px beyond ${canvas.height})`);
        }

        if (issues.length === 0) return null;

        return `⚠️ Widget extends beyond canvas:<br>${issues.join('<br>')}`;
    }

    _escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

window.PropertiesPanel = PropertiesPanel;

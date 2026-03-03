/**
 * Canvas - Main visual editing canvas component
 */

// Widget types where 'size' property means box dimensions (not font size)
// For text-based widgets, 'size' means font size
const WIDGETS_WITH_SIZE_AS_BOX = new Set([
    'moving_map', 'journey_map', 'moving_journey_map', 'circuit_map',
    'compass', 'compass_arrow', 'asi', 'msi', 'gps_lock_icon', 'icon',
    'cairo_circuit_map', 'cairo_gauge_marker', 'cairo_gauge_round_annotated',
    'cairo_gauge_arc_annotated', 'cairo_gauge_donut'
]);

class Canvas {
    constructor(container, viewport, state) {
        this.container = container;
        this.viewport = viewport;
        this.state = state;

        this.scale = 0.5;
        this.minScale = 0.1;
        this.maxScale = 2;

        this.dragState = {
            isDragging: false,
            widgetId: null,
            startX: 0,
            startY: 0,
            offsetX: 0,
            offsetY: 0
        };

        this.resizeState = {
            isResizing: false,
            widgetId: null,
            handle: null,
            startX: 0,
            startY: 0,
            startWidth: 0,
            startHeight: 0,
            startWidgetX: 0,
            startWidgetY: 0
        };

        // Duplicate drop prevention
        this._lastDropTime = 0;
        this._lastDropType = null;

        this.init();
    }

    init() {
        this._attachEventListeners();
        this._attachStateListeners();
    }

    _attachEventListeners() {
        // Canvas mouse events
        this.container.addEventListener('mousedown', this._onMouseDown.bind(this));
        document.addEventListener('mousemove', this._onMouseMove.bind(this));
        document.addEventListener('mouseup', this._onMouseUp.bind(this));

        // Keyboard events
        document.addEventListener('keydown', this._onKeyDown.bind(this));

        // Drag and drop from palette
        this.container.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });

        this.container.addEventListener('drop', this._onDrop.bind(this));

        // Click on empty area to deselect
        this.container.addEventListener('click', (e) => {
            if (e.target === this.container) {
                this.state.clearSelection();
            }
        });
    }

    _attachStateListeners() {
        this.state.on('layout:changed', () => this.render());
        this.state.on('layout:restored', () => this.render());
        this.state.on('widget:added', () => this.render());
        this.state.on('widget:removed', () => this.render());
        this.state.on('widget:updated', () => this.render());
        this.state.on('property:changed', () => this.render());
        this.state.on('selection:changed', () => this._updateSelection());
        this.state.on('canvas:changed', () => this._updateCanvasSize());
    }

    /**
     * Render the canvas and all widgets
     */
    render() {
        if (!this.state.layout) return;

        const canvas = this.state.layout.canvas;

        // Set canvas size
        this.container.style.width = `${canvas.width}px`;
        this.container.style.height = `${canvas.height}px`;
        this.container.style.transform = `scale(${this.scale})`;

        // Update spacer for proper scrolling
        this._updateSpacer();

        // Toggle grid
        if (canvas.grid_enabled) {
            this.container.classList.add('show-grid');
            this.container.style.setProperty('--grid-size', `${canvas.grid_size}px`);
        } else {
            this.container.classList.remove('show-grid');
        }

        // Render widgets
        this.container.innerHTML = this._renderWidgets(this.state.layout.widgets);

        // Reattach widget listeners
        this._attachWidgetListeners();
    }

    _renderWidgets(widgets, depth = 0) {
        return widgets.map(widget => this._renderWidget(widget, depth)).join('');
    }

    /**
     * Calculate the display bounds of a widget (accounting for alignment)
     */
    _getWidgetDisplayBounds(widget) {
        const metadata = this.state.widgetMetadataByType[widget.type];
        const sizeAsDimension = WIDGETS_WITH_SIZE_AS_BOX.has(widget.type) ? widget.properties.size : null;
        const width = widget.properties.width || widget.properties._displayWidth || sizeAsDimension || metadata?.default_width || 100;
        const height = widget.properties.height || widget.properties._displayHeight || sizeAsDimension || metadata?.default_height || 50;

        const align = widget.properties.align;
        let displayX = widget.x;
        if (align === 'right') {
            displayX = widget.x - width;
        } else if (align === 'centre' || align === 'center') {
            displayX = widget.x - width / 2;
        }

        return { x: displayX, y: widget.y, width, height };
    }

    /**
     * Calculate bounding box that encompasses all children
     */
    _getChildrenBounds(children) {
        if (!children || children.length === 0) return null;

        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;

        for (const child of children) {
            if (!child.visible) continue;
            const bounds = this._getWidgetDisplayBounds(child);
            minX = Math.min(minX, bounds.x);
            minY = Math.min(minY, bounds.y);
            maxX = Math.max(maxX, bounds.x + bounds.width);
            maxY = Math.max(maxY, bounds.y + bounds.height);
        }

        if (minX === Infinity) return null;

        return {
            x: minX,
            y: minY,
            width: maxX - minX,
            height: maxY - minY
        };
    }

    _renderWidget(widget, depth = 0) {
        if (!widget.visible) return '';

        const metadata = this.state.widgetMetadataByType[widget.type];
        const isSelected = this.state.selectedWidgets.has(widget.id);
        const isContainer = metadata && metadata.is_container;

        // For text-based widgets, 'size' is font size, not box size
        // Only use properties.size as dimension for widgets where size means box size
        const sizeAsDimension = WIDGETS_WITH_SIZE_AS_BOX.has(widget.type) ? widget.properties.size : null;

        // Use display size properties (underscore prefixed) as fallback for widgets without size props
        let width = widget.properties.width || widget.properties._displayWidth || sizeAsDimension || metadata?.default_width || 100;
        let height = widget.properties.height || widget.properties._displayHeight || sizeAsDimension || metadata?.default_height || 50;

        // Adjust position based on text alignment
        // For right-aligned text, x is the RIGHT edge, so box should extend left
        // For center-aligned text, x is the CENTER, so box should extend both ways
        const align = widget.properties.align;
        let displayX = widget.x;
        if (align === 'right') {
            displayX = widget.x - width;
        } else if (align === 'centre' || align === 'center') {
            displayX = widget.x - width / 2;
        }

        // For containers, calculate bounds from children
        let childrenOffsetX = 0;
        let childrenOffsetY = 0;
        if (isContainer && widget.children && widget.children.length > 0) {
            const childBounds = this._getChildrenBounds(widget.children);
            if (childBounds) {
                // Adjust container display position to encompass children
                // Children are positioned relative to container, so we need to offset
                displayX = widget.x + childBounds.x;
                width = childBounds.width;
                height = childBounds.height;
                // Store offset so children render correctly inside the adjusted container
                childrenOffsetX = -childBounds.x;
                childrenOffsetY = -childBounds.y;
            }
        }

        // Check if widget extends beyond canvas boundaries
        const canvas = this.state.layout?.canvas;
        const isOutOfBounds = canvas && (
            displayX < 0 ||
            widget.y < 0 ||
            displayX + width > canvas.width ||
            widget.y + height > canvas.height
        );

        const classes = [
            'canvas-widget',
            isSelected ? 'selected' : '',
            widget.locked ? 'locked' : '',
            isContainer ? 'container' : '',
            isOutOfBounds ? 'out-of-bounds' : ''
        ].filter(c => c).join(' ');

        const label = widget.name || widget.type;

        let html = `
            <div class="${classes}"
                 data-widget-id="${widget.id}"
                 style="left: ${displayX}px; top: ${widget.y}px; width: ${width}px; height: ${height}px;"
                 ${isOutOfBounds ? 'title="Widget extends beyond canvas boundaries"' : ''}>
                <div class="widget-label">${label}</div>
        `;

        // Render children for containers with offset adjustment
        if (widget.children && widget.children.length > 0) {
            if (childrenOffsetX !== 0 || childrenOffsetY !== 0) {
                html += `<div style="position: absolute; left: ${childrenOffsetX}px; top: ${childrenOffsetY}px;">`;
                html += this._renderWidgets(widget.children, depth + 1);
                html += `</div>`;
            } else {
                html += this._renderWidgets(widget.children, depth + 1);
            }
        }

        // Add resize handles for selected widgets
        if (isSelected && !widget.locked) {
            html += `
                <div class="resize-handle nw"></div>
                <div class="resize-handle n"></div>
                <div class="resize-handle ne"></div>
                <div class="resize-handle w"></div>
                <div class="resize-handle e"></div>
                <div class="resize-handle sw"></div>
                <div class="resize-handle s"></div>
                <div class="resize-handle se"></div>
            `;
        }

        html += '</div>';
        return html;
    }

    _attachWidgetListeners() {
        const widgets = this.container.querySelectorAll('.canvas-widget');

        widgets.forEach(widgetEl => {
            // Attach resize handle listeners
            const resizeHandles = widgetEl.querySelectorAll('.resize-handle');
            resizeHandles.forEach(handle => {
                handle.addEventListener('mousedown', (e) => {
                    e.stopPropagation();

                    const widgetId = widgetEl.dataset.widgetId;
                    const widget = this.state.findWidget(widgetId);
                    if (!widget || widget.locked) return;

                    const metadata = this.state.widgetMetadataByType[widget.type];
                    const sizeAsDimension = WIDGETS_WITH_SIZE_AS_BOX.has(widget.type) ? widget.properties.size : null;
                    const currentWidth = widget.properties.width || widget.properties._displayWidth || sizeAsDimension || metadata?.default_width || 100;
                    const currentHeight = widget.properties.height || widget.properties._displayHeight || sizeAsDimension || metadata?.default_height || 50;

                    const coords = this._getCanvasCoordinates(e);

                    // Determine handle direction
                    const handleClass = handle.className.replace('resize-handle ', '').trim();

                    this.resizeState = {
                        isResizing: true,
                        widgetId,
                        handle: handleClass,
                        startX: coords.x,
                        startY: coords.y,
                        startWidth: currentWidth,
                        startHeight: currentHeight,
                        startWidgetX: widget.x,
                        startWidgetY: widget.y
                    };
                });
            });

            widgetEl.addEventListener('mousedown', (e) => {
                // Don't start drag if clicking on resize handle
                if (e.target.classList.contains('resize-handle')) return;

                e.stopPropagation();

                const widgetId = widgetEl.dataset.widgetId;
                const widget = this.state.findWidget(widgetId);
                if (!widget || widget.locked) return;

                // Select on click
                this.state.select(widgetId, e.shiftKey);

                // Start drag - calculate position relative to canvas
                const coords = this._getCanvasCoordinates(e);

                // Get actual rendered position from DOM (handles nested containers correctly)
                const widgetRect = widgetEl.getBoundingClientRect();
                const canvasRect = this.container.getBoundingClientRect();
                const actualDisplayX = (widgetRect.left - canvasRect.left) / this.scale;
                const actualDisplayY = (widgetRect.top - canvasRect.top) / this.scale;

                // Get alignment and width for position conversion on move
                const metadata = this.state.widgetMetadataByType[widget.type];
                const sizeAsDimension = WIDGETS_WITH_SIZE_AS_BOX.has(widget.type) ? widget.properties.size : null;
                const width = widget.properties.width || widget.properties._displayWidth || sizeAsDimension || metadata?.default_width || 100;
                const align = widget.properties.align;

                this.dragState = {
                    isDragging: true,
                    widgetId,
                    startX: widget.x,
                    startY: widget.y,
                    startDisplayX: actualDisplayX,  // Canvas position at drag start
                    startDisplayY: actualDisplayY,
                    offsetX: coords.x - actualDisplayX,  // Click offset within widget
                    offsetY: coords.y - actualDisplayY,
                    align: align,
                    width: width
                };
            });
        });
    }

    /**
     * Convert mouse event coordinates to canvas coordinates
     * Accounts for scale transform and scroll position
     */
    _getCanvasCoordinates(e) {
        const rect = this.container.getBoundingClientRect();
        // getBoundingClientRect returns visual (scaled) position
        // clientX/Y are viewport-relative, so subtraction gives visual offset
        // Divide by scale to get unscaled canvas coordinates
        const x = (e.clientX - rect.left) / this.scale;
        const y = (e.clientY - rect.top) / this.scale;
        return { x, y };
    }

    _onMouseDown(e) {
        // Handled by widget mousedown
    }

    _onMouseMove(e) {
        // Handle resize
        if (this.resizeState.isResizing) {
            this._handleResize(e);
            return;
        }

        if (!this.dragState.isDragging) return;

        const coords = this._getCanvasCoordinates(e);

        // Calculate new display position (top-left of visual box in canvas coords)
        let newDisplayX = Math.round(coords.x - this.dragState.offsetX);
        let newDisplayY = Math.round(coords.y - this.dragState.offsetY);

        // Snap to grid if enabled
        if (this.state.layout.canvas.snap_to_grid) {
            const gridSize = this.state.layout.canvas.grid_size;
            newDisplayX = Math.round(newDisplayX / gridSize) * gridSize;
            newDisplayY = Math.round(newDisplayY / gridSize) * gridSize;
        }

        // Constrain to canvas bounds
        newDisplayX = Math.max(0, newDisplayX);
        newDisplayY = Math.max(0, newDisplayY);

        // Use delta-based movement: apply visual movement to original widget position
        // This works correctly for nested widgets because delta is the same in both coordinate systems
        const deltaX = newDisplayX - this.dragState.startDisplayX;
        const deltaY = newDisplayY - this.dragState.startDisplayY;

        const newX = Math.round(this.dragState.startX + deltaX);
        const newY = Math.round(this.dragState.startY + deltaY);

        this.state.updateWidget(this.dragState.widgetId, { x: newX, y: newY });

        // Update status bar
        this._updateStatusPosition(newX, newY);
    }

    _handleResize(e) {
        const coords = this._getCanvasCoordinates(e);
        const { handle, startX, startY, startWidth, startHeight, startWidgetX, startWidgetY, widgetId } = this.resizeState;

        const deltaX = coords.x - startX;
        const deltaY = coords.y - startY;

        let newWidth = startWidth;
        let newHeight = startHeight;
        let newX = startWidgetX;
        let newY = startWidgetY;

        const minSize = 20;

        // Calculate new dimensions based on handle
        switch (handle) {
            case 'e':
                newWidth = Math.max(minSize, startWidth + deltaX);
                break;
            case 'w':
                newWidth = Math.max(minSize, startWidth - deltaX);
                newX = startWidgetX + (startWidth - newWidth);
                break;
            case 's':
                newHeight = Math.max(minSize, startHeight + deltaY);
                break;
            case 'n':
                newHeight = Math.max(minSize, startHeight - deltaY);
                newY = startWidgetY + (startHeight - newHeight);
                break;
            case 'se':
                newWidth = Math.max(minSize, startWidth + deltaX);
                newHeight = Math.max(minSize, startHeight + deltaY);
                break;
            case 'sw':
                newWidth = Math.max(minSize, startWidth - deltaX);
                newHeight = Math.max(minSize, startHeight + deltaY);
                newX = startWidgetX + (startWidth - newWidth);
                break;
            case 'ne':
                newWidth = Math.max(minSize, startWidth + deltaX);
                newHeight = Math.max(minSize, startHeight - deltaY);
                newY = startWidgetY + (startHeight - newHeight);
                break;
            case 'nw':
                newWidth = Math.max(minSize, startWidth - deltaX);
                newHeight = Math.max(minSize, startHeight - deltaY);
                newX = startWidgetX + (startWidth - newWidth);
                newY = startWidgetY + (startHeight - newHeight);
                break;
        }

        // Snap to grid if enabled
        if (this.state.layout.canvas.snap_to_grid) {
            const gridSize = this.state.layout.canvas.grid_size;
            newWidth = Math.round(newWidth / gridSize) * gridSize;
            newHeight = Math.round(newHeight / gridSize) * gridSize;
            newX = Math.round(newX / gridSize) * gridSize;
            newY = Math.round(newY / gridSize) * gridSize;
        }

        // Round values
        newWidth = Math.round(newWidth);
        newHeight = Math.round(newHeight);
        newX = Math.round(newX);
        newY = Math.round(newY);

        // Update widget
        const widget = this.state.findWidget(widgetId);
        if (widget) {
            const metadata = this.state.widgetMetadataByType[widget.type];
            const propNames = metadata?.properties?.map(p => p.name) || [];

            widget.x = newX;
            widget.y = newY;

            // Check which size properties exist in metadata
            const hasWidthProp = propNames.includes('width');
            const hasHeightProp = propNames.includes('height');
            const hasSizeProp = propNames.includes('size');

            if (hasWidthProp && hasHeightProp) {
                // Widget supports separate width/height
                widget.properties.width = newWidth;
                widget.properties.height = newHeight;
            } else if (hasSizeProp) {
                // Widget uses single 'size' property (square widgets like maps, gauges)
                // Use the smaller dimension to maintain aspect ratio
                widget.properties.size = Math.min(newWidth, newHeight);
            } else {
                // Widget has no explicit size props - store in internal properties
                // (underscore prefix is skipped by XML converter)
                widget.properties._displayWidth = newWidth;
                widget.properties._displayHeight = newHeight;
            }

            this.state.isDirty = true;
            this.state.emit('widget:updated', { widgetId, updates: { x: newX, y: newY, width: newWidth, height: newHeight } });
        }

        // Update status bar
        this._updateStatusSize(newWidth, newHeight);
    }

    _onMouseUp(e) {
        if (this.resizeState.isResizing) {
            this.resizeState.isResizing = false;
            this.state.saveSnapshot();
        }

        if (this.dragState.isDragging) {
            this.dragState.isDragging = false;

            // Save to history if position changed
            const widget = this.state.findWidget(this.dragState.widgetId);
            if (widget && (widget.x !== this.dragState.startX || widget.y !== this.dragState.startY)) {
                this.state.saveSnapshot();
            }
        }
    }

    _onKeyDown(e) {
        // Delete selected widgets
        if ((e.key === 'Delete' || e.key === 'Backspace') && this.state.selectedWidgets.size > 0) {
            // Don't delete if focus is in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            e.preventDefault();
            const selected = Array.from(this.state.selectedWidgets);
            selected.forEach(id => this.state.removeWidget(id));
        }

        // Arrow keys to move
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            const widgets = this.state.getSelectedWidgets();
            if (widgets.length === 0) return;

            e.preventDefault();

            const delta = e.shiftKey ? 10 : 1;
            const dx = e.key === 'ArrowLeft' ? -delta : e.key === 'ArrowRight' ? delta : 0;
            const dy = e.key === 'ArrowUp' ? -delta : e.key === 'ArrowDown' ? delta : 0;

            widgets.forEach(widget => {
                if (!widget.locked) {
                    this.state.updateWidget(widget.id, {
                        x: widget.x + dx,
                        y: widget.y + dy
                    });
                }
            });
            this.state.saveSnapshot();
        }

        // Ctrl+A to select all
        if (e.ctrlKey && e.key === 'a') {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            e.preventDefault();
            const allIds = this.state.layout.widgets.map(w => w.id);
            this.state.select(allIds);
        }
    }

    _onDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();

        const widgetType = e.dataTransfer.getData('widget-type');
        if (!widgetType) return;

        // Prevent duplicate drops - use time-based deduplication regardless of widget type
        const now = Date.now();
        if (this._lastDropTime && (now - this._lastDropTime) < 300) {
            console.log('Duplicate drop prevented');
            return;
        }
        this._lastDropTime = now;
        this._lastDropType = widgetType;

        const coords = this._getCanvasCoordinates(e);
        let x = Math.round(coords.x);
        let y = Math.round(coords.y);

        // Snap to grid if enabled
        if (this.state.layout.canvas.snap_to_grid) {
            const gridSize = this.state.layout.canvas.grid_size;
            x = Math.round(x / gridSize) * gridSize;
            y = Math.round(y / gridSize) * gridSize;
        }

        const widget = this.state.addWidget(widgetType, x, y);
        if (widget) {
            this.state.select(widget.id);
        }
    }

    _updateSelection() {
        // Update selected class on widgets
        const widgets = this.container.querySelectorAll('.canvas-widget');
        widgets.forEach(widgetEl => {
            const widgetId = widgetEl.dataset.widgetId;
            if (this.state.selectedWidgets.has(widgetId)) {
                widgetEl.classList.add('selected');
            } else {
                widgetEl.classList.remove('selected');
            }
        });
    }

    _updateCanvasSize() {
        if (!this.state.layout) return;
        const canvas = this.state.layout.canvas;
        this.container.style.width = `${canvas.width}px`;
        this.container.style.height = `${canvas.height}px`;
    }

    _updateStatusPosition(x, y) {
        const statusEl = document.getElementById('status-position');
        if (statusEl) {
            statusEl.textContent = `X: ${x}, Y: ${y}`;
        }
    }

    _updateStatusSize(width, height) {
        const statusEl = document.getElementById('status-size');
        if (statusEl) {
            statusEl.textContent = `W: ${width}, H: ${height}`;
        }
    }

    /**
     * Set zoom level
     * @param {number} scale
     * @param {boolean} centerView - whether to center the view after zoom
     */
    setZoom(scale, centerView = false) {
        this.scale = Math.max(this.minScale, Math.min(this.maxScale, scale));
        this.container.style.transform = `scale(${this.scale})`;
        this._updateZoomDisplay();
        this._updateSpacer();

        // Also update the preview image scale if it exists
        const canvasPreviewImg = document.getElementById('canvas-preview-image');
        if (canvasPreviewImg) {
            canvasPreviewImg.style.transform = `scale(${this.scale})`;
        }

        if (centerView) {
            this._centerView();
        }
    }

    /**
     * Center the viewport scroll position
     */
    _centerView() {
        if (!this.state.layout || !this.viewport) return;

        const canvas = this.state.layout.canvas;
        const viewportRect = this.viewport.getBoundingClientRect();

        // Calculate the content size (canvas * scale + padding)
        const contentWidth = canvas.width * this.scale + 40;
        const contentHeight = canvas.height * this.scale + 40;

        // Center the scroll if content is larger than viewport
        if (contentWidth > viewportRect.width) {
            this.viewport.scrollLeft = (contentWidth - viewportRect.width) / 2;
        } else {
            this.viewport.scrollLeft = 0;
        }

        if (contentHeight > viewportRect.height) {
            this.viewport.scrollTop = (contentHeight - viewportRect.height) / 2;
        } else {
            this.viewport.scrollTop = 0;
        }
    }

    /**
     * Update spacer element dimensions to enable proper scrolling
     * (Absolutely positioned elements don't contribute to overflow)
     */
    _updateSpacer() {
        const spacer = document.getElementById('canvas-spacer');
        if (spacer && this.state.layout) {
            const canvas = this.state.layout.canvas;
            // Spacer dimensions = canvas dimensions * scale + padding
            const padding = 40; // 20px padding on each side
            spacer.style.width = `${canvas.width * this.scale + padding}px`;
            spacer.style.height = `${canvas.height * this.scale + padding}px`;
        }
    }

    /**
     * Zoom in
     */
    zoomIn() {
        this.setZoom(this.scale * 1.2);
    }

    /**
     * Zoom out
     */
    zoomOut() {
        this.setZoom(this.scale / 1.2);
    }

    /**
     * Fit canvas to viewport
     */
    fitToView() {
        if (!this.state.layout) return;

        const canvas = this.state.layout.canvas;
        const viewportRect = this.viewport.getBoundingClientRect();

        // Account for padding (20px on each side)
        const availableWidth = viewportRect.width - 40;
        const availableHeight = viewportRect.height - 40;

        const scaleX = availableWidth / canvas.width;
        const scaleY = availableHeight / canvas.height;

        // Use the smaller scale to fit both dimensions, cap at 100%
        const newScale = Math.min(scaleX, scaleY, 1);

        this.setZoom(newScale);

        // Reset scroll position to show from top-left
        if (this.viewport) {
            this.viewport.scrollLeft = 0;
            this.viewport.scrollTop = 0;
        }
    }

    _updateZoomDisplay() {
        const zoomEl = document.getElementById('zoom-level');
        if (zoomEl) {
            zoomEl.textContent = `${Math.round(this.scale * 100)}%`;
        }
    }
}

window.Canvas = Canvas;

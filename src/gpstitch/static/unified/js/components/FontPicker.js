/**
 * FontPicker - Searchable dropdown for choosing the overlay font
 * Lists installed fonts grouped by family, each shown in its own face via a
 * server-rendered PNG (PIL can render any face of a .ttc collection; browsers can't).
 * Recently picked fonts are listed first. "Auto" keeps the built-in font detection.
 */

class FontPicker {
    static RECENT_FONTS_KEY = 'gopro_unified_recent_fonts';
    static RECENT_FONTS_MAX = 5;

    /**
     * @param {HTMLElement} container - Element to render the trigger button into
     * @param {Object} options
     * @param {function(Object|null)} options.onChange - Called with the picked font or null for Auto
     * @param {function()} [options.onOpen] - Called when the list opens, e.g. to refresh the fonts
     */
    constructor(container, { onChange, onOpen = () => {} }) {
        this.container = container;
        this.onChange = onChange;
        this.onOpen = onOpen;
        this.fonts = null; // null until loaded
        this.loadFailed = false;
        this.selected = null;
        this._rows = [];
        this._activeIndex = -1;

        this._render();
        this._attachListeners();
    }

    static _el(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    static _sameFont(a, b) {
        return a.path === b.path && a.index === b.index;
    }

    static _matchesTerms(font, terms) {
        const haystack = `${font.family} ${font.style}`.toLowerCase();
        return terms.every(term => haystack.includes(term));
    }

    _render() {
        this.trigger = FontPicker._el('button', 'font-picker-trigger');
        this.trigger.type = 'button';
        this.trigger.id = 'font-picker-trigger';
        this.trigger.setAttribute('aria-haspopup', 'listbox');
        this.trigger.setAttribute('aria-expanded', 'false');
        this.container.appendChild(this.trigger);

        this.searchInput = FontPicker._el('input', 'font-picker-search');
        this.searchInput.type = 'text';
        this.searchInput.setAttribute('aria-label', 'Search fonts');
        this.searchInput.setAttribute('aria-controls', 'font-picker-list');
        this.searchInput.autocomplete = 'off';
        this.searchInput.spellcheck = false;

        this.list = FontPicker._el('div', 'font-picker-list');
        this.list.id = 'font-picker-list';
        this.list.setAttribute('role', 'listbox');

        this.popover = FontPicker._el('div', 'font-picker-popover hidden');
        this.popover.append(this.searchInput, this.list);
        document.body.appendChild(this.popover);

        this._renderTrigger();
    }

    _attachListeners() {
        this.trigger.addEventListener('click', () => (this.isOpen() ? this.close() : this.open()));
        this.trigger.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown' && !this.isOpen()) {
                e.preventDefault();
                this.open();
            }
        });

        this.searchInput.addEventListener('input', () => this._renderList());
        this.searchInput.addEventListener('keydown', (e) => this._handleKeydown(e));

        // Close on outside click, and on scroll/resize since the popover is fixed-positioned
        document.addEventListener('mousedown', (e) => {
            if (this.isOpen() && !this.popover.contains(e.target) && !this.trigger.contains(e.target)) {
                this.close();
            }
        });
        document.addEventListener('scroll', (e) => {
            if (this.isOpen() && !this.popover.contains(e.target)) this.close();
        }, true);
        window.addEventListener('resize', () => this.isOpen() && this.close());
    }

    /**
     * Set the list of installed fonts (from /api/options/fonts). Call setValue
     * afterwards to match the current selection against the list. An open list is
     * re-rendered in place, keeping the search text.
     */
    setFonts(fonts) {
        this.fonts = fonts;
        this.loadFailed = false;
        if (this.isOpen()) this._renderList();
    }

    /**
     * Mark the font list as unavailable. The current selection stays as is, since
     * renders keep using it.
     */
    setLoadFailed() {
        this.loadFailed = true;
        if (this.isOpen()) this._renderList();
    }

    /**
     * Select a font by path and face index; null path means Auto.
     * Returns false if fonts are loaded and the font isn't among them.
     */
    setValue(path, index = 0) {
        if (!path) {
            this.selected = null;
            this._renderTrigger();
            return true;
        }
        // Until fonts load (or if they can't), show the file name so a saved choice stays visible
        const font = this.fonts
            ? this._findFont(path, index)
            : { path, index, family: path.split(/[\\/]/).pop(), style: '' };
        this.selected = font;
        this._renderTrigger();
        return Boolean(font);
    }

    isOpen() {
        return !this.popover.classList.contains('hidden');
    }

    open() {
        this.searchInput.value = '';
        this.searchInput.placeholder = this.fonts ? `Search ${this.fonts.length} fonts...` : 'Search fonts...';
        this.popover.classList.remove('hidden');
        this.trigger.setAttribute('aria-expanded', 'true');
        this._position();
        this._renderList();
        this.searchInput.focus();
        this.onOpen();
    }

    close({ restoreFocus = false } = {}) {
        this.popover.classList.add('hidden');
        this.trigger.setAttribute('aria-expanded', 'false');
        if (restoreFocus) this.trigger.focus();
    }

    _findFont(path, index) {
        return this.fonts.find(f => FontPicker._sameFont(f, { path, index })) || null;
    }

    _position() {
        const rect = this.trigger.getBoundingClientRect();
        const width = Math.max(rect.width, 300);
        const margin = 8;
        // Right-align with the trigger: the config panel sits at the right edge of the window
        const left = Math.max(margin, Math.min(rect.right - width, window.innerWidth - width - margin));
        const spaceBelow = window.innerHeight - rect.bottom - margin;
        const spaceAbove = rect.top - margin;
        const openUp = spaceBelow < 260 && spaceAbove > spaceBelow;
        const maxHeight = Math.min(420, openUp ? spaceAbove : spaceBelow);

        this.popover.style.left = `${left}px`;
        this.popover.style.width = `${width}px`;
        this.popover.style.maxHeight = `${maxHeight}px`;
        this.popover.style.top = openUp ? '' : `${rect.bottom + 4}px`;
        this.popover.style.bottom = openUp ? `${window.innerHeight - rect.top + 4}px` : '';
    }

    _renderTrigger() {
        if (this.selected) {
            this.trigger.replaceChildren(...this._label(this.selected));
            this.trigger.title = `${this.selected.family} ${this.selected.style}\n${this.selected.path}`;
        } else {
            this.trigger.replaceChildren(FontPicker._el('span', 'font-picker-auto', 'Auto'));
            this.trigger.title = 'Use the default font';
        }
    }

    /**
     * Font name in its own face, followed by its style.
     */
    _label(font) {
        return [this._sample(font), FontPicker._el('span', 'font-picker-style', font.style)];
    }

    /**
     * Font name rendered in its own face; plain text before fonts load or if the preview fails.
     */
    _sample(font) {
        const text = FontPicker._el('span', 'font-picker-family', font.family);
        if (!font.id) return text;

        const img = FontPicker._el('img', 'font-picker-sample');
        img.src = `/api/options/fonts/${encodeURIComponent(font.id)}/preview.png`;
        img.alt = font.family;
        img.loading = 'lazy';
        img.draggable = false;
        img.addEventListener('error', () => img.replaceWith(text), { once: true });
        return img;
    }

    _renderList() {
        const terms = this.searchInput.value.toLowerCase().split(/\s+/).filter(Boolean);
        this._rows = [];
        this.list.replaceChildren();

        if (terms.length === 0 || 'auto'.startsWith(terms.join(' '))) {
            this._addRow(null);
        }

        if (!this.fonts) {
            this._addNote('font-picker-message', this.loadFailed ? 'Could not load fonts' : 'Loading fonts...');
            this._setActive(0);
            return;
        }

        if (terms.length === 0) {
            const recent = this._getRecent()
                .map(r => this._findFont(r.path, r.index))
                .filter(Boolean);
            if (recent.length > 0) {
                this._addNote('font-picker-header', 'Recent');
                recent.forEach(font => this._addRow(font));
                this._addNote('font-picker-header', 'All fonts');
            }
        }

        let previousFamily = null;
        let matched = 0;
        for (const font of this.fonts) {
            if (terms.length > 0 && !FontPicker._matchesTerms(font, terms)) continue;
            this._addRow(font, font.family !== previousFamily);
            previousFamily = font.family;
            matched++;
        }
        if (matched === 0 && terms.length > 0) {
            this._addNote('font-picker-message', 'No fonts match');
        }

        // Start on the current selection when it's in the list, else on the first row
        const selectedRow = this._rows.findIndex(row => this._isSelected(row.font));
        this._setActive(selectedRow >= 0 ? selectedRow : 0, { scroll: true });
    }

    _isSelected(font) {
        if (!font || !this.selected) return font === this.selected;
        return FontPicker._sameFont(font, this.selected);
    }

    _addRow(font, familyStart = false) {
        const row = FontPicker._el('div', 'font-picker-option');
        row.id = `font-picker-option-${this._rows.length}`;
        row.setAttribute('role', 'option');
        if (familyStart) row.classList.add('family-start');
        if (this._isSelected(font)) {
            row.classList.add('selected');
            row.setAttribute('aria-selected', 'true');
        }

        if (font) {
            row.append(...this._label(font));
            row.title = `${font.family} ${font.style}`;
            row.dataset.family = font.family;
            row.dataset.style = font.style;
        } else {
            row.append(FontPicker._el('span', 'font-picker-auto', 'Auto'), FontPicker._el('span', 'font-picker-style', 'default font'));
        }

        const rowIndex = this._rows.length;
        row.addEventListener('mousemove', () => this._activeIndex !== rowIndex && this._setActive(rowIndex));
        row.addEventListener('click', () => this._select(font));
        this._rows.push({ el: row, font });
        this.list.appendChild(row);
    }

    _addNote(className, text) {
        this.list.appendChild(FontPicker._el('div', className, text));
    }

    _setActive(index, { scroll = false } = {}) {
        this._rows[this._activeIndex]?.el.classList.remove('active');
        this._activeIndex = index;
        const row = this._rows[index];
        if (!row) {
            this.searchInput.removeAttribute('aria-activedescendant');
            return;
        }
        row.el.classList.add('active');
        this.searchInput.setAttribute('aria-activedescendant', row.el.id);
        if (scroll) row.el.scrollIntoView({ block: 'nearest' });
    }

    _handleKeydown(e) {
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this._setActive(Math.min(this._activeIndex + 1, this._rows.length - 1), { scroll: true });
                break;
            case 'ArrowUp':
                e.preventDefault();
                this._setActive(Math.max(this._activeIndex - 1, 0), { scroll: true });
                break;
            case 'Enter': {
                e.preventDefault();
                const row = this._rows[this._activeIndex];
                if (row) this._select(row.font);
                break;
            }
            case 'Escape':
                e.preventDefault();
                this.close({ restoreFocus: true });
                break;
            case 'Tab':
                this.close();
                break;
        }
    }

    _select(font) {
        this.selected = font;
        if (font) this._addRecent(font);
        this._renderTrigger();
        this.close({ restoreFocus: true });
        this.onChange(font);
    }

    _getRecent() {
        try {
            const recent = JSON.parse(localStorage.getItem(FontPicker.RECENT_FONTS_KEY) || '[]');
            return Array.isArray(recent) ? recent : [];
        } catch {
            return [];
        }
    }

    _addRecent(font) {
        const recent = this._getRecent().filter(r => !FontPicker._sameFont(r, font));
        recent.unshift({ path: font.path, index: font.index });
        try {
            localStorage.setItem(
                FontPicker.RECENT_FONTS_KEY,
                JSON.stringify(recent.slice(0, FontPicker.RECENT_FONTS_MAX))
            );
        } catch {
            // Recent fonts are a convenience; ignore storage failures
        }
    }
}

// Export
window.FontPicker = FontPicker;

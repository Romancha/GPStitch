/**
 * HistoryManager - Manages undo/redo history
 */

class HistoryManager {
    constructor(state) {
        this.state = state;
        this.history = [];
        this.currentIndex = -1;
        this.maxHistory = 50;
        this.lastSnapshot = null;
        this.isRestoring = false;
    }

    /**
     * Take a snapshot of current state
     */
    snapshot() {
        if (this.isRestoring) return;
        if (!this.state.layout) return;

        const snapshot = JSON.stringify(this.state.layout);

        // Don't snapshot if nothing changed
        if (snapshot === this.lastSnapshot) return;

        // Remove any history after current index
        this.history = this.history.slice(0, this.currentIndex + 1);

        // Add new snapshot
        this.history.push(snapshot);
        this.currentIndex++;

        // Limit history size
        if (this.history.length > this.maxHistory) {
            this.history.shift();
            this.currentIndex--;
        }

        this.lastSnapshot = snapshot;
        this._emitChange();
    }

    /**
     * Undo to previous state
     */
    undo() {
        if (!this.canUndo()) return;

        this.currentIndex--;
        this._restore();
        this._emitChange();
    }

    /**
     * Redo to next state
     */
    redo() {
        if (!this.canRedo()) return;

        this.currentIndex++;
        this._restore();
        this._emitChange();
    }

    /**
     * Check if undo is available
     * @returns {boolean}
     */
    canUndo() {
        return this.currentIndex > 0;
    }

    /**
     * Check if redo is available
     * @returns {boolean}
     */
    canRedo() {
        return this.currentIndex < this.history.length - 1;
    }

    /**
     * Clear all history
     */
    clear() {
        this.history = [];
        this.currentIndex = -1;
        this.lastSnapshot = null;
        this._emitChange();
    }

    /**
     * Restore state from current index
     */
    _restore() {
        if (this.currentIndex < 0 || this.currentIndex >= this.history.length) {
            return;
        }

        this.isRestoring = true;

        const snapshot = this.history[this.currentIndex];
        this.state.layout = JSON.parse(snapshot);
        this.lastSnapshot = snapshot;
        this.state.emit('layout:restored', { layout: this.state.layout });

        this.isRestoring = false;
    }

    /**
     * Emit history change event
     */
    _emitChange() {
        this.state.emit('history:changed', {
            canUndo: this.canUndo(),
            canRedo: this.canRedo(),
            historySize: this.history.length,
            currentIndex: this.currentIndex
        });
    }
}

// Don't export globally - will be instantiated in main.js
window.HistoryManager = HistoryManager;

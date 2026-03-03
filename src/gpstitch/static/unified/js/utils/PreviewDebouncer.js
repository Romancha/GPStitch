/**
 * PreviewDebouncer - Debounces preview generation requests
 * Prevents API spam when user makes rapid changes
 */

class PreviewDebouncer {
    constructor(delay = 500) {
        this.delay = delay;
        this.timeoutId = null;
        this.abortController = null;
        this.pendingCallback = null;
    }

    /**
     * Request a debounced preview
     * @param {Function} callback - Async function to call after debounce
     */
    request(callback) {
        // Cancel previous timeout
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }

        // Cancel previous in-flight request
        this.cancel();

        // Store callback
        this.pendingCallback = callback;

        // Schedule new request
        this.timeoutId = setTimeout(async () => {
            this.timeoutId = null;

            // Create new abort controller for this request
            this.abortController = new AbortController();

            try {
                await this.pendingCallback(this.abortController.signal);
            } catch (error) {
                if (error.name !== 'AbortError') {
                    console.error('Preview generation failed:', error);
                }
            } finally {
                this.abortController = null;
            }
        }, this.delay);
    }

    /**
     * Request immediate preview (no debounce)
     * Still cancels any pending requests
     * @param {Function} callback - Async function to call immediately
     */
    async requestImmediate(callback) {
        // Cancel pending debounced request
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }

        // Cancel previous in-flight request
        this.cancel();

        // Create new abort controller
        this.abortController = new AbortController();

        try {
            await callback(this.abortController.signal);
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Preview generation failed:', error);
            }
        } finally {
            this.abortController = null;
        }
    }

    /**
     * Cancel pending and in-flight requests
     */
    cancel() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    /**
     * Check if a request is pending
     */
    isPending() {
        return this.timeoutId !== null || this.abortController !== null;
    }
}

// Export
window.PreviewDebouncer = PreviewDebouncer;

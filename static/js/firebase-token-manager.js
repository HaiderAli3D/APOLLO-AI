/**
 * Firebase Token Manager
 * This module handles token refresh and authentication state management.
 */

class FirebaseTokenManager {
    constructor() {
        this.listeners = [];
        this.initialized = false;
        this.init();
    }

    /**
     * Initialize the token manager and set up auth state listeners
     */
    init() {
        if (this.initialized) return;
        this.initialized = true;

        // Set up Firebase auth state listener
        firebase.auth().onAuthStateChanged(user => {
            if (user) {
                console.log('User is signed in');
                // User is signed in, refresh token if needed
                this.refreshTokenIfNeeded(user);
                // Notify listeners of auth state change
                this.notifyListeners(user);
            } else {
                console.log('User is signed out');
                // Notify listeners of sign out
                this.notifyListeners(null);
            }
        });

        // Set up token refresh timer
        setInterval(() => {
            const user = firebase.auth().currentUser;
            if (user) {
                this.refreshTokenIfNeeded(user);
            }
        }, 300000); // Check every 5 minutes
    }

    /**
     * Check if the token needs to be refreshed and refresh it if necessary
     * @param {Object} user - Firebase user object
     */
    async refreshTokenIfNeeded(user) {
        try {
            // Get token metadata
            const tokenResult = await user.getIdTokenResult();
            
            // Calculate when token expires
            const expirationTime = new Date(tokenResult.expirationTime).getTime();
            const currentTime = new Date().getTime();
            const timeToExpiration = expirationTime - currentTime;
            
            // If token expires in less than 30 minutes, refresh it
            if (timeToExpiration < 1800000) { // 30 minutes in milliseconds
                console.log('Refreshing ID token...');
                const newToken = await user.getIdToken(true);
                
                // Send the new token to the backend
                await this.sendTokenToBackend(newToken);
                
                console.log('Token refreshed and sent to backend');
            }
        } catch (error) {
            console.error('Error refreshing token:', error);
        }
    }

    /**
     * Send the updated token to the backend
     * @param {string} token - Firebase ID token
     */
    async sendTokenToBackend(token) {
        try {
            // Send token to backend endpoint
            const response = await fetch('/refresh-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ idToken: token }),
            });
            
            if (!response.ok) {
                throw new Error('Failed to update token on server');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error sending token to backend:', error);
            throw error;
        }
    }

    /**
     * Add a listener for auth state changes
     * @param {Function} listener - Callback function that receives the user object
     */
    addAuthStateListener(listener) {
        this.listeners.push(listener);
        
        // Immediately notify with current state
        const currentUser = firebase.auth().currentUser;
        if (currentUser) {
            listener(currentUser);
        } else {
            listener(null);
        }
    }

    /**
     * Remove a listener
     * @param {Function} listener - The listener to remove
     */
    removeAuthStateListener(listener) {
        this.listeners = this.listeners.filter(l => l !== listener);
    }

    /**
     * Notify all listeners of auth state change
     * @param {Object|null} user - Firebase user object or null if signed out
     */
    notifyListeners(user) {
        this.listeners.forEach(listener => {
            try {
                listener(user);
            } catch (error) {
                console.error('Error in auth state listener:', error);
            }
        });
    }

    /**
     * Get the current user's ID token
     * @returns {Promise<string|null>} The ID token or null if not signed in
     */
    async getCurrentToken() {
        const user = firebase.auth().currentUser;
        if (!user) {
            return null;
        }
        
        try {
            return await user.getIdToken();
        } catch (error) {
            console.error('Error getting current token:', error);
            return null;
        }
    }

    /**
     * Sign out the current user
     * @returns {Promise<void>}
     */
    async signOut() {
        try {
            await firebase.auth().signOut();
            
            // Also call the backend logout endpoint
            await fetch('/logout', {
                method: 'GET',
                credentials: 'same-origin'
            });
            
            console.log('User signed out successfully');
            
            // Redirect to home page
            window.location.href = '/';
        } catch (error) {
            console.error('Error signing out:', error);
            throw error;
        }
    }
}

// Create a singleton instance
window.firebaseTokenManager = new FirebaseTokenManager();

// Add a global sign-out function for easy access
window.signOut = function() {
    window.firebaseTokenManager.signOut();
};

// Add authorization header to all fetch requests
const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
    // Skip for certain URLs (like external APIs)
    if (url.startsWith('http') && !url.includes(window.location.host)) {
        return originalFetch(url, options);
    }
    
    try {
        const token = await window.firebaseTokenManager.getCurrentToken();
        
        if (token) {
            // Create headers object if it doesn't exist
            options.headers = options.headers || {};
            
            // Add Authorization header with token
            options.headers['Authorization'] = `Bearer ${token}`;
        }
    } catch (error) {
        console.error('Error adding auth token to fetch:', error);
    }
    
    return originalFetch(url, options);
};

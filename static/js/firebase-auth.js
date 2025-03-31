/**
 * Firebase Authentication Module
 * 
 * This file handles Firebase initialization and provides authentication utilities
 * with comprehensive error handling for a smooth user experience.
 */

// Initialize Firebase with configuration from app.py
function initializeFirebase() {
  // Firebase configuration - these values should match those in app.py
  const firebaseConfig = {
    apiKey: "AIzaSyBVLWsgEgQxBKDpQ4a7nb-CKhMf-ZEwnmA",
    authDomain: "apollo-auth-753b5.firebaseapp.com",
    projectId: "apollo-auth-753b5",
    storageBucket: "apollo-auth-753b5.firebasestorage.app",
    messagingSenderId: "233177806452",
    appId: "1:233177806452:web:189d47b01c3de6e8110321",
    measurementId: "G-DJXDJWE6PJ"
  };

  // Initialize Firebase if not already initialized
  if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
    console.log("Firebase initialized successfully");
  }
  
  // Make sure auth instance is available
  window.firebaseAuth = firebase.auth();
  
  // Listen for auth state changes
  firebase.auth().onAuthStateChanged(function(user) {
    if (user) {
      console.log("User is signed in:", user.email);
    } else {
      console.log("User is signed out");
    }
  });
}

// Initialize Firebase when the document is loaded
document.addEventListener('DOMContentLoaded', function() {
  initializeFirebase();
});

/**
 * Translates Firebase auth error codes to user-friendly messages.
 * 
 * @param {string} errorCode Firebase auth error code
 * @returns {string} User-friendly error message
 */
function getFirebaseErrorMessage(errorCode) {
  const errorMessages = {
    // Email/password related errors
    'auth/email-already-in-use': 'This email is already registered. Please sign in instead or reset your password if you forgot it.',
    'auth/invalid-email': 'The email address is not valid. Please check and try again.',
    'auth/user-disabled': 'This account has been disabled. Please contact support.',
    'auth/user-not-found': 'No account found with this email. Please check the email or register.',
    'auth/wrong-password': 'Incorrect password. Please try again or use the password reset option.',
    'auth/weak-password': 'Password is too weak. Please use a stronger password.',
    
    // Account linking/credential errors
    'auth/account-exists-with-different-credential': 'An account already exists with the same email but different sign-in credentials. Try signing in using a different method.',
    'auth/credential-already-in-use': 'These credentials are already associated with another account.',
    'auth/email-already-exists': 'This email address is already in use by another account.',
    
    // Session/token errors
    'auth/invalid-credential': 'The authentication credential is invalid. Please try signing in again.',
    'auth/invalid-verification-code': 'The verification code is invalid. Please try again.',
    'auth/invalid-verification-id': 'The verification ID is invalid. Please try again.',
    'auth/requires-recent-login': 'This operation requires re-authentication. Please sign in again.',
    
    // Network/timeout errors
    'auth/network-request-failed': 'A network error occurred. Please check your connection and try again.',
    'auth/timeout': 'The operation has timed out. Please try again.',
    
    // Other common errors
    'auth/operation-not-allowed': 'This operation is not allowed. Please contact support.',
    'auth/popup-blocked': 'The popup was blocked by your browser. Please allow popups for this site.',
    'auth/popup-closed-by-user': 'The authentication popup was closed before completion. Please try again.',
    
    // Default fallback error
    'default': 'An authentication error occurred. Please try again later.'
  };
  
  return errorMessages[errorCode] || errorMessages['default'];
}

/**
 * Displays an error message to the user in a consistent way
 * 
 * @param {string} message Error message to display
 * @param {HTMLElement} container Element to display the error in (optional)
 */
function showAuthError(message, container = null) {
  console.error('Auth error:', message);
  
  // If a container is provided, display the error there
  if (container) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-danger';
    errorDiv.textContent = message;
    
    // Clear previous errors
    const existingErrors = container.querySelectorAll('.alert-danger');
    existingErrors.forEach(el => el.remove());
    
    // Add new error
    container.insertBefore(errorDiv, container.firstChild);
    
    // Auto-dismiss after 10 seconds
    setTimeout(() => {
      if (errorDiv.parentNode) {
        errorDiv.classList.add('fade-out');
        setTimeout(() => errorDiv.remove(), 500);
      }
    }, 10000);
  } else {
    // If no container, use alert (fallback)
    alert(message);
  }
}

/**
 * Displays a success message to the user
 * 
 * @param {string} message Success message to display
 * @param {HTMLElement} container Element to display the message in (optional)
 */
function showAuthSuccess(message, container = null) {
  console.log('Auth success:', message);
  
  // If a container is provided, display the message there
  if (container) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'alert alert-success';
    messageDiv.textContent = message;
    
    // Clear previous messages
    const existingMessages = container.querySelectorAll('.alert-success');
    existingMessages.forEach(el => el.remove());
    
    // Add new message
    container.insertBefore(messageDiv, container.firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (messageDiv.parentNode) {
        messageDiv.classList.add('fade-out');
        setTimeout(() => messageDiv.remove(), 500);
      }
    }, 5000);
  }
}

// Enhanced Firebase auth utilities
window.firebaseAuth = {
  // Core Firebase auth instance
  auth: firebase.auth(),
  
  /**
   * Sign in with email and password
   * 
   * @param {string} email User email
   * @param {string} password User password
   * @param {HTMLElement} errorContainer Container to display errors in
   * @returns {Promise} Firebase auth user credential
   */
  signIn: async function(email, password, errorContainer = null) {
    try {
      return await firebase.auth().signInWithEmailAndPassword(email, password);
    } catch (error) {
      const errorMessage = getFirebaseErrorMessage(error.code);
      showAuthError(errorMessage, errorContainer);
      throw error;
    }
  },
  
  /**
   * Create a new user
   * 
   * @param {string} email User email
   * @param {string} password User password
   * @param {HTMLElement} errorContainer Container to display errors in
   * @returns {Promise} Firebase auth user credential
   */
  createUser: async function(email, password, errorContainer = null) {
    try {
      return await firebase.auth().createUserWithEmailAndPassword(email, password);
    } catch (error) {
      // Special handling for 'email already in use' error
      if (error.code === 'auth/email-already-in-use') {
        // Try to fetch sign-in methods for this email
        try {
          const methods = await firebase.auth().fetchSignInMethodsForEmail(email);
          if (methods && methods.length > 0) {
            // User exists with sign-in methods
            showAuthError(`This email is already registered. Please sign in using one of: ${methods.join(', ')}`, errorContainer);
          } else {
            // User exists but has no sign-in methods (edge case)
            showAuthError('This email is already registered but has no valid sign-in methods. Please try resetting your password or use a different email.', errorContainer);
          }
        } catch (signInMethodsError) {
          // Fallback to generic error if we can't fetch sign-in methods
          showAuthError(getFirebaseErrorMessage(error.code), errorContainer);
        }
      } else {
        // Handle other errors
        showAuthError(getFirebaseErrorMessage(error.code), errorContainer);
      }
      throw error;
    }
  },
  
  /**
   * Update a user's profile
   * 
   * @param {Object} user Firebase user object
   * @param {Object} profile Profile data to update
   * @param {HTMLElement} errorContainer Container to display errors in
   * @returns {Promise} Promise that resolves when complete
   */
  updateProfile: async function(user, profile, errorContainer = null) {
    try {
      return await user.updateProfile(profile);
    } catch (error) {
      showAuthError(getFirebaseErrorMessage(error.code) || error.message, errorContainer);
      throw error;
    }
  },
  
  /**
   * Send password reset email
   * 
   * @param {string} email User email address
   * @param {HTMLElement} container Container to display messages in
   * @returns {Promise} Promise that resolves when complete
   */
  sendPasswordResetEmail: async function(email, container = null) {
    try {
      await firebase.auth().sendPasswordResetEmail(email);
      showAuthSuccess(`Password reset email sent to ${email}. Please check your inbox.`, container);
      return true;
    } catch (error) {
      showAuthError(getFirebaseErrorMessage(error.code) || error.message, container);
      throw error;
    }
  },
  
  /**
   * Sign out current user
   * 
   * @returns {Promise} Promise that resolves when complete
   */
  signOut: async function() {
    try {
      return await firebase.auth().signOut();
    } catch (error) {
      console.error('Error signing out:', error);
      throw error;
    }
  },
  
  /**
   * Get the current authenticated user
   * 
   * @returns {Object|null} Firebase user object or null if not signed in
   */
  getCurrentUser: function() {
    return firebase.auth().currentUser;
  },
  
  /**
   * Check if a user is authenticated
   * 
   * @returns {boolean} True if user is signed in
   */
  isAuthenticated: function() {
    return !!firebase.auth().currentUser;
  },
  
  /**
   * Get ID token for current user
   * 
   * @param {boolean} forceRefresh Whether to force a token refresh
   * @returns {Promise} Promise resolving to the ID token string
   */
  getIdToken: async function(forceRefresh = false) {
    const user = firebase.auth().currentUser;
    if (!user) {
      throw new Error('No user is signed in');
    }
    return await user.getIdToken(forceRefresh);
  },
  
  /**
   * Check sign-in methods available for an email
   * 
   * @param {string} email Email to check
   * @returns {Promise} Promise resolving to array of available sign-in methods
   */
  getSignInMethodsForEmail: async function(email) {
    try {
      return await firebase.auth().fetchSignInMethodsForEmail(email);
    } catch (error) {
      console.error('Error fetching sign-in methods:', error);
      throw error;
    }
  }
};

// Add CSS for auth message styling
document.addEventListener('DOMContentLoaded', function() {
  const style = document.createElement('style');
  style.textContent = `
    .alert {
      padding: 10px 15px;
      margin: 10px 0;
      border-radius: 4px;
      position: relative;
    }
    .alert-danger {
      background-color: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
    .alert-success {
      background-color: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .fade-out {
      opacity: 0;
      transition: opacity 0.5s;
    }
  `;
  document.head.appendChild(style);
});

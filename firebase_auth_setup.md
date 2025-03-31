# Firebase Authentication Integration Guide

This document provides an overview of how Firebase Authentication is integrated into the OCR A-Level Computer Science AI Tutor application.

## Configuration Files

1. **Firebase Admin SDK Service Account**:
   - The app uses a Firebase Admin SDK service account JSON file (`apollo-auth-753b5-firebase-adminsdk-fbsvc-6b6d2904d5.json`) for server-side authentication verification.
   - This file should be kept secure and never committed to public repositories.

2. **Firebase Configuration**:
   - Client-side Firebase configuration is stored in `app.py` and `templates/base.html`.
   - Firebase is initialized with your project-specific credentials.

## Authentication Flow

### Registration Process:
1. User fills out registration form or uses Firebase UI.
2. Firebase creates a new user account.
3. The client gets an ID token from Firebase.
4. The ID token is sent to the server via `/register` endpoint.
5. Server verifies the token using Firebase Admin SDK.
6. Server creates or links a local user account.
7. User session is established.

### Login Process:
1. User logs in via form or Firebase UI.
2. Firebase authenticates the user.
3. The client gets an ID token.
4. The token is sent to the server via login endpoints.
5. Server verifies the token.
6. Server creates a session with appropriate permissions.

### Token Refresh:
1. ID tokens expire after 1 hour.
2. The `firebase-token-manager.js` periodically checks token expiration.
3. If a token is about to expire, it's refreshed and sent to the server.
4. Server updates the session with the new token.

## Key Files

1. **Firebase Auth Middleware** (`firebase_auth_middleware.py`):
   - Provides decorators for route protection.
   - Verifies tokens and ensures proper authorization.
   - Handles appropriate redirects for unauthorized access.

2. **Firebase Token Manager** (`static/js/firebase-token-manager.js`):
   - Client-side management of Firebase authentication.
   - Handles token refreshes to prevent session expiration.
   - Adds authorization headers to fetch requests.

3. **Firebase Auth Utilities** (`static/js/firebase-auth.js`):
   - Provides utility functions for Firebase Auth interactions.
   - Handles initialization of Firebase.

4. **Login Templates**:
   - `templates/login.html`, `templates/student/login.html`, `templates/register.html`:
   - Include both Firebase UI and traditional form-based authentication.
   - Allow for a smooth transition between authentication methods.

## Authentication Methods

The application supports multiple authentication methods:

1. **Email/Password Authentication**:
   - Traditional form-based login.
   - Firebase UI email/password login.

2. **Social Authentication** (configurable):
   - Google Sign-In (enabled by default)
   - Other providers can be added in Firebase UI configuration.

## User Migration

The application includes a migration path for existing users:

1. When existing users sign in with Firebase for the first time, the system attempts to match their email.
2. If a match is found, their local account is linked to their Firebase account.
3. The `account_migrated` flag is set to track migration status.

## Security Considerations

1. **Token Verification**:
   - All ID tokens are verified on the server side.
   - Firebase Admin SDK handles cryptographic verification.

2. **Role-Based Access Control**:
   - User roles (student, admin, developer) are stored in the local database.
   - Separate decorators enforce different access permissions.

3. **Session Security**:
   - Sessions include both user ID and Firebase UID for additional validation.
   - Token refreshes maintain session without requiring reauthentication.

## Troubleshooting

If you encounter authentication issues:

1. Check browser console for Firebase Auth errors.
2. Verify the Firebase configuration matches your Firebase project.
3. Ensure the Firebase Admin SDK service account file is properly placed.
4. Check server logs for token verification errors.
5. Clear browser cookies and local storage if authentication state becomes inconsistent.

# Firebase Authentication Implementation Guide

This guide documents the implementation of Firebase Authentication in the APOLLO AI OCR A-Level Computer Science tutoring application, including email/password and Google sign-in options.

## Overview

Firebase Authentication has been integrated into the application to provide:

1. Email/password authentication
2. Google sign-in (social login)
3. Profile picture support
4. Role-based access control
5. Enhanced security and error handling

## Implementation Details

### 1. Backend Integration (app.py)

- User management using Firebase UID
- Token validation and refresh
- Profile picture storage
- Role-based access control

### 2. Frontend Components

#### Firebase Authentication Utilities (firebase-auth.js)

- Error translation and user-friendly messages
- Authentication state management
- Profile management

#### Token Management (firebase-token-manager.js)

- Automatic token refresh
- Session management
- Security enforcement

### 3. Authentication Flow

#### Registration

1. User can register using email/password or Google sign-in
2. Firebase creates user account
3. Backend creates corresponding database entry
4. User profile, including picture (if from Google), is saved

#### Login

1. User can log in with email/password or Google
2. Firebase validates credentials
3. Backend verifies user and role permissions
4. Session is established with appropriate permissions

### 4. Google Sign-In Configuration

Google sign-in has been enabled for:
- Student login
- Admin login
- Registration

The application will automatically use the profile picture from Google accounts when users sign in with Google.

### 5. Error Handling

Enhanced error handling has been implemented:
- Friendly error messages for authentication failures
- Password reset options
- Registration suggestions for non-existent accounts
- Network error recovery

### 6. UI/UX Improvements

- Profile pictures displayed in navigation
- Loading states during authentication
- Success/error messages with auto-dismissal
- Smooth transitions between states

## Firebase Project Configuration

The application uses the following Firebase configuration:

```javascript
const firebaseConfig = {
  apiKey: "AIzaSyBVLWsgEgQxBKDpQ4a7nb-CKhMf-ZEwnmA",
  authDomain: "apollo-auth-753b5.firebaseapp.com",
  projectId: "apollo-auth-753b5",
  storageBucket: "apollo-auth-753b5.firebasestorage.app",
  messagingSenderId: "233177806452",
  appId: "1:233177806452:web:189d47b01c3de6e8110321",
  measurementId: "G-DJXDJWE6PJ"
};
```

## Database Schema Updates

The user_database.db schema has been updated to include:
- `firebase_uid` column for mapping to Firebase users
- `account_migrated` flag for tracking migration status
- `profile_picture_url` column for storing profile image URLs

## Future Improvements

1. Additional social login providers (GitHub, Microsoft, etc.)
2. Email verification
3. Two-factor authentication
4. Enhanced profile management
5. Admin user management interface

## Troubleshooting

### Common Issues

1. **Login fails after registration**: Ensure the backend successfully created the user record

2. **Profile picture not appearing**: Check network access to the image URL and ensure it's loading properly

3. **Token expiration issues**: Verify token-manager.js is properly refreshing tokens

4. **Role permissions problems**: Check that the proper role is being assigned during registration/login

### Getting Help

For issues with Firebase Authentication:
1. Check the Firebase console for error logs
2. Review browser console for JavaScript errors
3. Verify network requests in browser developer tools

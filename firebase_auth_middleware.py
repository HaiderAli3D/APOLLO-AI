"""
Firebase Authentication Middleware

This module provides middleware functions to handle Firebase token verification and session management.
"""

import functools
from flask import session, request, redirect, url_for, flash, jsonify
import firebase_admin
from firebase_admin import auth, credentials

def validate_firebase_token():
    """
    Validate the Firebase token stored in the session.
    
    Returns:
        bool: True if the token is valid, False otherwise
    """
    firebase_token = session.get('firebase_token')
    
    if not firebase_token:
        return False
    
    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(firebase_token)
        
        # Check if token is close to expiration (within 5 minutes)
        # If so, a new token should be obtained by the client
        if 'exp' in decoded_token:
            import time
            current_time = time.time()
            expiration_time = decoded_token['exp']
            
            # Token is valid but will expire soon
            if expiration_time - current_time < 300:  # 5 minutes
                session['token_expiring_soon'] = True
            else:
                session['token_expiring_soon'] = False
        
        return True
    except Exception as e:
        print(f"Token validation error: {e}")
        return False

def firebase_auth_required(f):
    """
    Decorator to require Firebase authentication for routes.
    
    Args:
        f: The route function to decorate
        
    Returns:
        function: The decorated function
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # If request has a valid Firebase ID token in the Authorization header, use it
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]
            try:
                # Verify the ID token
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token['uid']
                
                # If the session UID doesn't match the token UID, update the session
                if session.get('firebase_uid') != uid:
                    # Update session with new Firebase UID
                    session['firebase_uid'] = uid
                    session['firebase_token'] = id_token
                    
                    # You may want to populate other session fields like user_id, user_email, etc.
                    # This would require looking up the user in your database
                
                # Continue to the route
                return f(*args, **kwargs)
            except Exception as e:
                print(f"Bearer token validation error: {e}")
                # Fall through to check session token
        
        # Check if user is authenticated via session
        if session.get('user_id') and validate_firebase_token():
            return f(*args, **kwargs)
            
        # For API endpoints, return JSON error
        if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
            return jsonify({'error': 'Authentication required'}), 401
            
        # For web endpoints, redirect to login
        flash('Please log in to access this page', 'error')
        return redirect(url_for('student_login'))
        
    return decorated_function

def admin_auth_required(f):
    """
    Decorator to require Firebase authentication with admin role for routes.
    
    Args:
        f: The route function to decorate
        
    Returns:
        function: The decorated function
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if user is authenticated
        if not session.get('user_id') or not validate_firebase_token():
            # For API endpoints, return JSON error
            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                return jsonify({'error': 'Authentication required'}), 401
                
            # For web endpoints, redirect to login
            flash('Please log in to access this page', 'error')
            return redirect(url_for('admin_login'))
        
        # Then check if user has admin role
        if not session.get('is_admin'):
            # For API endpoints, return JSON error
            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                return jsonify({'error': 'Admin privileges required'}), 403
                
            # For web endpoints, redirect to login
            flash('Admin access required', 'error')
            return redirect(url_for('admin_login'))
            
        return f(*args, **kwargs)
        
    return decorated_function

def developer_auth_required(f):
    """
    Decorator to require Firebase authentication with developer role for routes.
    
    Args:
        f: The route function to decorate
        
    Returns:
        function: The decorated function
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if user is authenticated
        if not session.get('user_id') or not validate_firebase_token():
            # For API endpoints, return JSON error
            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                return jsonify({'error': 'Authentication required'}), 401
                
            # For web endpoints, redirect to login
            flash('Please log in to access this page', 'error')
            return redirect(url_for('developer_login'))
        
        # Then check if user has developer role
        if not session.get('is_developer'):
            # For API endpoints, return JSON error
            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                return jsonify({'error': 'Developer privileges required'}), 403
                
            # For web endpoints, redirect to login
            flash('Developer access required', 'error')
            return redirect(url_for('developer_login'))
            
        return f(*args, **kwargs)
        
    return decorated_function

def refresh_firebase_token():
    """
    Helper function to check if Firebase token needs refreshing.
    
    Returns:
        bool: True if token is expiring soon and needs refreshing, False otherwise
    """
    return session.get('token_expiring_soon', False)

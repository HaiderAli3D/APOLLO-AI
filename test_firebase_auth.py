#!/usr/bin/env python3
"""
Integration Tests for Firebase Authentication

This script tests the Firebase authentication integration in the OCR A-Level Computer Science AI Tutor app.
It checks various auth flows and verifies middleware functionality.

Usage:
    python test_firebase_auth.py

Note: This requires a valid Firebase Admin SDK service account file to be present.
"""

import unittest
import requests
import firebase_admin
from firebase_admin import credentials, auth
import json
import os
import time
import sys

# Base URL for the application (modify as needed)
BASE_URL = "http://localhost:5000"

# Temporary test user credentials
TEST_EMAIL = "test_user@example.com"
TEST_PASSWORD = "testPassword123!"
TEST_NAME = "Test User"


class FirebaseAuthTests(unittest.TestCase):
    """Test suite for Firebase Authentication integration."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment before running tests."""
        try:
            # Initialize Firebase Admin SDK for testing
            if not firebase_admin._apps:
                cred = credentials.Certificate("apollo-auth-753b5-firebase-adminsdk-fbsvc-6b6d2904d5.json")
                firebase_admin.initialize_app(cred)
            
            # Create a test user or use existing one
            try:
                cls.user = auth.create_user(
                    email=TEST_EMAIL,
                    password=TEST_PASSWORD,
                    display_name=TEST_NAME
                )
                print(f"Created test user: {TEST_EMAIL}")
            except firebase_admin.exceptions.FirebaseError as e:
                if "ALREADY_EXISTS" in str(e):
                    # Get the existing user
                    cls.user = auth.get_user_by_email(TEST_EMAIL)
                    print(f"Using existing test user: {TEST_EMAIL}")
                else:
                    raise
                    
            # Create a custom token for testing
            cls.custom_token = auth.create_custom_token(cls.user.uid).decode('utf-8')
            
            # Server should be running separately
            print(f"Testing against server at: {BASE_URL}")
        except Exception as e:
            print(f"Error in setup: {e}")
            raise

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        try:
            # Delete the test user
            auth.delete_user(cls.user.uid)
            print(f"Deleted test user: {TEST_EMAIL}")
        except Exception as e:
            print(f"Error cleaning up: {e}")

    def get_id_token(self):
        """Get a valid Firebase ID token for the test user using REST API."""
        # Use Firebase REST API to exchange custom token for ID token
        response = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
            params={"key": os.getenv("FIREBASE_API_KEY")},
            json={"token": self.custom_token, "returnSecureToken": True}
        )
        response.raise_for_status()
        return response.json()["idToken"]

    def test_01_register_endpoint(self):
        """Test the registration endpoint with Firebase token."""
        try:
            # Get an ID token
            id_token = self.get_id_token()
            
            # Submit registration request
            response = requests.post(
                f"{BASE_URL}/register",
                json={"idToken": id_token, "full_name": TEST_NAME}
            )
            
            # Check response
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertIn("redirect", data)
            print("✓ Registration endpoint test passed")
        except Exception as e:
            print(f"✗ Registration endpoint test failed: {e}")
            raise

    def test_02_student_login_endpoint(self):
        """Test the student login endpoint with Firebase token."""
        try:
            # Get an ID token
            id_token = self.get_id_token()
            
            # Submit login request
            response = requests.post(
                f"{BASE_URL}/student/login",
                json={"idToken": id_token}
            )
            
            # Check response
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertIn("redirect", data)
            print("✓ Student login endpoint test passed")
        except Exception as e:
            print(f"✗ Student login endpoint test failed: {e}")
            raise

    def test_03_token_refresh_endpoint(self):
        """Test the token refresh endpoint."""
        try:
            # Get an ID token
            id_token = self.get_id_token()
            
            # Submit refresh request
            response = requests.post(
                f"{BASE_URL}/refresh-token",
                json={"idToken": id_token}
            )
            
            # Check response
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            print("✓ Token refresh endpoint test passed")
        except Exception as e:
            print(f"✗ Token refresh endpoint test failed: {e}")
            raise

    def test_04_protected_route_access(self):
        """Test access to protected route with valid token."""
        try:
            # Get an ID token
            id_token = self.get_id_token()
            
            # Create a session by logging in
            session = requests.Session()
            response = session.post(
                f"{BASE_URL}/student/login",
                json={"idToken": id_token}
            )
            response.raise_for_status()
            
            # Try to access a protected route
            response = session.get(f"{BASE_URL}/student/dashboard")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Dashboard", response.text)
            print("✓ Protected route access test passed")
        except Exception as e:
            print(f"✗ Protected route access test failed: {e}")
            raise

    def test_05_unauthorized_access(self):
        """Test that unauthorized access is properly blocked."""
        try:
            # Try to access a protected route without authentication
            response = requests.get(f"{BASE_URL}/student/dashboard", allow_redirects=False)
            
            # Should redirect to login page
            self.assertEqual(response.status_code, 302)
            self.assertIn("/student/login", response.headers["Location"])
            print("✓ Unauthorized access test passed")
        except Exception as e:
            print(f"✗ Unauthorized access test failed: {e}")
            raise


if __name__ == "__main__":
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code != 200:
            print(f"Server returned unexpected status code: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Error connecting to server at {BASE_URL}. Is it running?")
        sys.exit(1)
    
    # Run the tests
    unittest.main()

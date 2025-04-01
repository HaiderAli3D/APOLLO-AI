"""
Firebase Storage Adapter for OCR A-Level Computer Science AI Tutor

This module provides an adapter for Firebase Storage to handle PDF uploads and deletions.
"""

import os
import time
import urllib.parse
from firebase_admin import storage, auth
import re
from datetime import datetime, timedelta
import secrets
import string

# Initialize Firebase Storage bucket
_bucket = None

def _get_bucket():
    """Get or initialize the Firebase Storage bucket."""
    global _bucket
    if _bucket is None:
        # Specify the bucket name explicitly
        _bucket = storage.bucket('apollo-auth-753b5.firebasestorage.app')
    return _bucket

def upload_pdf(local_pdf_path, user_id, pdf_filename):
    """
    Upload a PDF file to Firebase Storage.
    
    Args:
        local_pdf_path: Path to the local PDF file
        user_id: ID of the user who owns the PDF
        pdf_filename: Filename for the uploaded PDF
        
    Returns:
        Tuple (success, result)
            success (bool): Whether the upload succeeded
            result (str): If successful, the public URL; if failed, an error message
    """
    try:
        if not os.path.exists(local_pdf_path):
            return False, f"Local file not found: {local_pdf_path}"
        
        # Sanitize filename and create a unique Storage path
        sanitized_name = sanitize_filename(pdf_filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_str = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        storage_path = f"pdfs/{user_id}/{timestamp}_{random_str}_{sanitized_name}"
        
        # Get bucket and upload file
        bucket = _get_bucket()
        blob = bucket.blob(storage_path)
        
        # Set metadata (optional)
        blob.metadata = {
            'user_id': user_id,
            'original_filename': pdf_filename,
            'uploaded_at': datetime.now().isoformat()
        }
        
        # Upload the file
        blob.upload_from_filename(local_pdf_path)
        
        # Make the file publicly accessible
        blob.make_public()
        
        # Return the public URL
        return True, blob.public_url
    
    except Exception as e:
        return False, str(e)

def delete_pdf(storage_url_or_path, user_id):
    """
    Delete a PDF file from Firebase Storage.
    
    Args:
        storage_url_or_path: Either a public URL or a storage path
        user_id: ID of the user who owns the PDF
        
    Returns:
        bool: Whether the delete succeeded
    """
    try:
        # Convert URL to path if needed
        if storage_url_or_path.startswith('http'):
            storage_path = url_to_storage_path(storage_url_or_path)
        else:
            storage_path = storage_url_or_path
        
        # Validate that this path belongs to the user
        if not storage_path.startswith(f"pdfs/{user_id}/"):
            print(f"Warning: Attempted to delete file not owned by user: {storage_path}")
            return False
        
        # Get bucket and delete file
        bucket = _get_bucket()
        blob = bucket.blob(storage_path)
        
        # Check if file exists
        if not blob.exists():
            print(f"Warning: File not found in Storage: {storage_path}")
            return False
        
        # Delete the file
        blob.delete()
        return True
    
    except Exception as e:
        print(f"Error deleting from Storage: {e}")
        return False

def url_to_storage_path(storage_url):
    """
    Convert a Firebase Storage public URL to a storage path.
    
    Args:
        storage_url: Public URL from Firebase Storage
        
    Returns:
        str: The corresponding storage path
    """
    # Extract the path from the URL
    # URLs look like: https://firebasestorage.googleapis.com/v0/b/BUCKET_NAME/o/PATH?token=TOKEN
    match = re.search(r'/o/([^?]+)', storage_url)
    if match:
        # URL-decode the path
        path = urllib.parse.unquote(match.group(1))
        return path
    
    # Fallback for unexpected URL formats
    return None

def sanitize_filename(filename):
    """
    Sanitize a filename to be safe for Firebase Storage.
    
    Args:
        filename: Original filename
        
    Returns:
        str: Sanitized filename
    """
    # Remove any unsafe characters
    safe_name = re.sub(r'[^\w\-\.]', '_', filename)
    
    # Ensure filename isn't too long
    if len(safe_name) > 100:
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:95] + ext
    
    return safe_name

def generate_signed_url(storage_path, expires_in_minutes=30):
    """
    Generate a signed URL for temporary access to a private file.
    
    Args:
        storage_path: Firebase Storage path
        expires_in_minutes: Number of minutes until URL expires
        
    Returns:
        str: Signed URL
    """
    bucket = _get_bucket()
    blob = bucket.blob(storage_path)
    
    # Generate URL that expires in specified minutes
    expiration = datetime.now() + timedelta(minutes=expires_in_minutes)
    
    # Create signed URL
    url = blob.generate_signed_url(
        version="v4",
        expiration=expiration,
        method="GET"
    )
    
    return url

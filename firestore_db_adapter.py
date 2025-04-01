"""
Firestore Database Adapter for OCR A-Level Computer Science AI Tutor

This module provides an adapter between the application and Firebase Firestore,
replacing the SQLite database with cloud-based storage.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Optional, Union
from firebase_admin import firestore, auth

# Firebase collection names
USERS_COLLECTION = 'users'
SESSIONS_COLLECTION = 'sessions'
MESSAGES_COLLECTION = 'messages'
TOPIC_PROGRESS_COLLECTION = 'topic_progress'
EXAM_PRACTICE_COLLECTION = 'exam_practice'
GENERATED_PDFS_COLLECTION = 'generated_pdfs'
USER_ACTIVITY_COLLECTION = 'user_activity'

# Firestore DB instance
_db = None
_db_wrapper = None

class FirestoreDBWrapper:
    """
    Wrapper class that provides method-based access to the Firestore adapter functions.
    This maintains compatibility with code that expects to call methods on a database object.
    """
    def __init__(self, db_client):
        self.db = db_client
    
    def collection(self, collection_name):
        """Pass-through method to access Firestore collections directly."""
        return self.db.collection(collection_name)
    
    # User methods
    def get_user_by_email(self, email):
        return get_user_by_email(email)
    
    def get_user_by_id(self, user_id):
        return get_user_by_id(user_id)
    
    def get_user_by_firebase_uid(self, firebase_uid):
        return get_user_by_firebase_uid(firebase_uid)
    
    def create_user(self, email, password, full_name, role='student'):
        return create_user(email, password, full_name, role)
    
    def get_or_create_firebase_user(self, uid, email, full_name, role='student', profile_picture_url=None, decoded_token=None):
        return get_or_create_firebase_user(uid, email, full_name, role, profile_picture_url, decoded_token)
    
    # Session methods
    def start_session(self, context_info, user_id=None):
        return start_session(context_info, user_id)
    
    def add_message(self, session_id, role, content):
        return add_message(session_id, role, content)
    
    def get_session_messages(self, session_id):
        return get_session_messages(session_id)
    
    def verify_session_ownership(self, session_id, user_id):
        return verify_session_ownership(session_id, user_id)
    
    def delete_session_messages(self, session_id):
        """Delete all messages for a session."""
        messages_ref = self.db.collection(SESSIONS_COLLECTION).document(session_id).collection(MESSAGES_COLLECTION)
        
        # Get all messages
        messages = messages_ref.stream()
        
        # Delete each message
        for message in messages:
            message.reference.delete()
        
        return True
    
    # PDF methods (enhanced versions)
    def get_pdf_by_id(self, pdf_id, user_id):
        return get_pdf_by_id(pdf_id, user_id)
    
    # Topic progress methods
    def update_topic_progress(self, topic_code, topic_title, rating, notes='', user_id=None, last_studied=None):
        return update_topic_progress(topic_code, topic_title, rating, notes, user_id, last_studied)
    
    def get_topic_progress(self, user_id=None):
        return get_topic_progress(user_id)
    
    # Exam practice methods
    def record_exam_practice(self, topic_code, question_type, difficulty, score, max_score, user_id=None):
        return record_exam_practice(topic_code, question_type, difficulty, score, max_score, user_id)
    
    def get_exam_progress(self, user_id=None):
        return get_exam_progress(user_id)
    
    # PDF methods
    def add_pdf_to_database(self, user_id, topic_code, topic_title, filename):
        return add_pdf_to_database(user_id, topic_code, topic_title, filename)
    
    def add_pdf_to_generated_pdfs(self, user_id, topic_code, title, latex_content, pdf_path, storage_url=None, storage_path=None):
        return add_pdf_to_generated_pdfs(user_id, topic_code, title, latex_content, pdf_path, storage_url, storage_path)
    
    def get_pdfs_for_user(self, user_id):
        return get_pdfs_for_user(user_id)
    
    def delete_pdf(self, user_id, pdf_id):
        return delete_pdf(user_id, pdf_id)
    
    # Activity tracking methods
    def track_activity(self, user_id, activity_type='page_view', session_duration=0):
        return track_activity(user_id, activity_type, session_duration)
    
    def get_activity_data(self, user_id, start_date, end_date):
        return get_activity_data(user_id, start_date, end_date)
    
    def calculate_user_streak(self, user_id):
        return calculate_user_streak(user_id)
    
    # Cleanup old PDFs
    def cleanup_old_pdfs(self, user_id):
        """Remove old PDF files if a user has more than 10 saved."""
        try:
            # Get all PDFs for the user (without ordering, to avoid need for index)
            query = (
                self.db.collection(GENERATED_PDFS_COLLECTION)
                .where('user_id', '==', user_id)
            )
            
            pdfs = list(query.stream())
            
            # Sort locally by created_at (oldest first)
            # Convert Firestore timestamps to strings for comparison if needed
            def get_sort_key(doc):
                created_at = doc.to_dict().get('created_at', '')
                # If created_at is a Firestore timestamp object, convert to string
                if hasattr(created_at, 'isoformat'):
                    return created_at.isoformat()
                return created_at
                
            pdfs.sort(key=get_sort_key)
            
            # If there are more than 10 PDFs, delete the oldest ones
            if len(pdfs) > 10:
                to_delete = pdfs[:-10]  # Keep the 10 newest PDFs
                
                for pdf_doc in to_delete:
                    # Get PDF data to delete files
                    pdf_data = pdf_doc.to_dict()
                    
                    # Check if it has a Firebase Storage URL
                    storage_url = pdf_data.get('storage_url')
                    if storage_url:
                        # Import the Firebase Storage adapter
                        from firebase_storage_adapter import delete_pdf as delete_storage_pdf
                        
                        # Delete from Firebase Storage
                        try:
                            delete_storage_pdf(storage_url, user_id)
                        except Exception as e:
                            print(f"Error deleting from Storage during cleanup: {e}")
                    
                    # Also delete local file if it exists
                    pdf_path = pdf_data.get('pdf_path')
                    if pdf_path:
                        full_path = os.path.join('static', pdf_path)
                        try:
                            if os.path.exists(full_path):
                                os.remove(full_path)
                        except Exception as e:
                            print(f"Error deleting local file {pdf_path}: {e}")
                    
                    # Delete the Firestore document
                    pdf_doc.reference.delete()
            
            return True
        except Exception as e:
            print(f"Error in cleanup_old_pdfs: {e}")
            # Non-fatal error, return True to continue
            return True

def get_db():
    """Get a Firestore database wrapper instance."""
    global _db, _db_wrapper
    if _db is None:
        _db = firestore.client()
    
    if _db_wrapper is None:
        _db_wrapper = FirestoreDBWrapper(_db)
    
    return _db_wrapper

def get_user_by_email(email: str) -> Optional[tuple]:
    """
    Get a user from Firestore by email.
    Returns data in SQLite-compatible tuple format for backward compatibility.
    """
    global _db
    if _db is None:
        _db = firestore.client()
    users_ref = _db.collection(USERS_COLLECTION)
    query = users_ref.where('email', '==', email).limit(1)
    results = query.stream()
    
    for doc in results:
        user_data = doc.to_dict()
        # Convert to tuple format matching the legacy SQLite format:
        # (id, email, password_hash, full_name, role, created_at, firebase_uid, account_migrated, profile_picture_url)
        return (
            doc.id,  # Using Firestore ID as user ID
            user_data.get('email'),
            user_data.get('password_hash', ''),
            user_data.get('full_name', ''),
            user_data.get('role', 'student'),
            user_data.get('created_at', datetime.now().isoformat()),
            user_data.get('firebase_uid', ''),
            user_data.get('account_migrated', True),
            user_data.get('profile_picture_url', '')
        )
    
    return None

def get_user_by_id(user_id: str) -> Optional[tuple]:
    """
    Get a user from Firestore by ID.
    Returns data in SQLite-compatible tuple format for backward compatibility.
    """
    db = get_db()
    user_doc = db.collection(USERS_COLLECTION).document(user_id).get()
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        # Convert to tuple format matching the legacy SQLite format
        return (
            user_id,
            user_data.get('email'),
            user_data.get('password_hash', ''),
            user_data.get('full_name', ''),
            user_data.get('role', 'student'),
            user_data.get('created_at', datetime.now().isoformat()),
            user_data.get('firebase_uid', ''),
            user_data.get('account_migrated', True),
            user_data.get('profile_picture_url', '')
        )
    
    return None

def get_user_by_firebase_uid(firebase_uid: str) -> Optional[dict]:
    """Get a user from Firestore by Firebase UID."""
    db = get_db()
    users_ref = db.collection(USERS_COLLECTION)
    query = users_ref.where('firebase_uid', '==', firebase_uid).limit(1)
    results = query.stream()
    
    for doc in results:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        return user_data
    
    return None

def create_user(email: str, password: str, full_name: str, role: str = 'student') -> Tuple[bool, Union[str, str]]:
    """
    Create a new user in Firestore.
    Returns (success, user_id) or (False, error_message)
    """
    db = get_db()
    
    # Check if user already exists
    existing_user = get_user_by_email(email)
    if existing_user:
        return False, "Email already registered"
    
    try:
        # Create user document
        user_ref = db.collection(USERS_COLLECTION).document()
        user_ref.set({
            'email': email,
            'password_hash': password,  # Should already be hashed
            'full_name': full_name,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'account_migrated': False,
            'firebase_uid': ''
        })
        
        return True, user_ref.id
    except Exception as e:
        return False, str(e)

def get_or_create_firebase_user(
    uid: str, 
    email: str, 
    full_name: str, 
    role: str = 'student', 
    profile_picture_url: str = None, 
    decoded_token: dict = None
) -> tuple:
    """
    Get existing user by Firebase UID or create a new one in Firestore.
    Returns user data in tuple format for backward compatibility.
    """
    db = get_db()
    
    # Get profile picture from token if not provided explicitly
    if profile_picture_url is None and decoded_token:
        # Check if token has picture URL (common with Google authentication)
        profile_picture_url = decoded_token.get('picture', None)
        
        # Check Firebase provider
        provider = decoded_token.get('firebase', {}).get('sign_in_provider', '')
        if provider == 'google.com' and not profile_picture_url:
            # Try alternative picture field that might be present in Google auth
            profile_picture_url = decoded_token.get('photoURL', None)
    
    # Check if user exists by Firebase UID
    existing_user = get_user_by_firebase_uid(uid)
    
    if existing_user:
        # User exists, update profile picture if provided
        user_id = existing_user['id']
        user_ref = db.collection(USERS_COLLECTION).document(user_id)
        
        if profile_picture_url:
            user_ref.update({
                'profile_picture_url': profile_picture_url
            })
            existing_user['profile_picture_url'] = profile_picture_url
        
        # Return in tuple format for compatibility
        return (
            user_id,
            existing_user.get('email'),
            existing_user.get('password_hash', ''),
            existing_user.get('full_name', ''),
            existing_user.get('role', 'student'),
            existing_user.get('created_at', datetime.now().isoformat()),
            existing_user.get('firebase_uid', ''),
            existing_user.get('account_migrated', True),
            existing_user.get('profile_picture_url', '')
        )
    
    # Check if user exists by email
    existing_user_by_email = get_user_by_email(email)
    
    if existing_user_by_email:
        # Update existing user with Firebase UID and profile picture
        user_id = existing_user_by_email[0]
        user_ref = db.collection(USERS_COLLECTION).document(user_id)
        
        update_data = {
            'firebase_uid': uid,
            'account_migrated': True
        }
        
        if profile_picture_url:
            update_data['profile_picture_url'] = profile_picture_url
            
        user_ref.update(update_data)
        
        # Get updated user data
        updated_user = user_ref.get().to_dict()
        
        # Return in tuple format for compatibility
        return (
            user_id,
            updated_user.get('email'),
            updated_user.get('password_hash', ''),
            updated_user.get('full_name', ''),
            updated_user.get('role', 'student'),
            updated_user.get('created_at', datetime.now().isoformat()),
            updated_user.get('firebase_uid', ''),
            updated_user.get('account_migrated', True),
            updated_user.get('profile_picture_url', '')
        )
    
    # Create new user
    user_ref = db.collection(USERS_COLLECTION).document()
    
    user_data = {
        'email': email,
        'password_hash': 'firebase_auth',
        'full_name': full_name,
        'role': role,
        'firebase_uid': uid,
        'account_migrated': True,
        'created_at': datetime.now().isoformat()
    }
    
    if profile_picture_url:
        user_data['profile_picture_url'] = profile_picture_url
        
    user_ref.set(user_data)
    
    # Return in tuple format for compatibility
    return (
        user_ref.id,
        email,
        'firebase_auth',  # password_hash
        full_name,
        role,
        user_data['created_at'],
        uid,  # firebase_uid
        True,  # account_migrated
        profile_picture_url or ''
    )

def start_session(context_info: List[str], user_id: str = None) -> str:
    """
    Start a new learning session in Firestore.
    Returns the session ID.
    """
    db = get_db()
    
    # Create a unique ID for this session
    session_id = str(uuid.uuid4())
    
    # Create session document
    session_data = {
        'context': context_info,
        'started_at': datetime.now().isoformat(),
        'last_activity': datetime.now().isoformat()
    }
    
    if user_id:
        session_data['user_id'] = user_id
    
    db.collection(SESSIONS_COLLECTION).document(session_id).set(session_data)
    
    return session_id

def add_message(session_id: str, role: str, content: str) -> bool:
    """
    Add a message to a session in Firestore.
    Returns True if the message was added successfully.
    """
    db = get_db()
    
    # Update session's last activity timestamp
    session_ref = db.collection(SESSIONS_COLLECTION).document(session_id)
    session_ref.update({
        'last_activity': datetime.now().isoformat()
    })
    
    # Create message document
    message_ref = session_ref.collection(MESSAGES_COLLECTION).document()
    message_ref.set({
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    
    return True

def get_session_messages(session_id: str) -> List[Tuple[str, str, str]]:
    """
    Get all messages for a session from Firestore.
    Returns a list of (id, role, content) tuples for backward compatibility.
    """
    db = get_db()
    
    messages_ref = db.collection(SESSIONS_COLLECTION).document(session_id).collection(MESSAGES_COLLECTION)
    messages = messages_ref.order_by('timestamp').stream()
    
    result = []
    for msg in messages:
        msg_data = msg.to_dict()
        result.append((msg.id, msg_data.get('role'), msg_data.get('content')))
    
    return result

def verify_session_ownership(session_id: str, user_id: str) -> bool:
    """
    Check if a session belongs to a user.
    Returns True if the session belongs to the user or if the session has no user_id.
    """
    db = get_db()
    
    session_ref = db.collection(SESSIONS_COLLECTION).document(session_id)
    session = session_ref.get()
    
    if not session.exists:
        return False
    
    session_data = session.to_dict()
    session_user_id = session_data.get('user_id')
    
    # If session has no user_id or matches the given user_id
    return not session_user_id or session_user_id == user_id

def update_topic_progress(
    topic_code: str, 
    topic_title: str, 
    rating: int, 
    notes: str = '', 
    user_id: str = None,
    last_studied: str = None
) -> bool:
    """
    Update a user's progress on a topic in Firestore.
    Returns True if the update was successful.
    """
    db = get_db()
    
    if not last_studied:
        last_studied = datetime.now().strftime('%Y-%m-%d')
    
    # Create a document ID that combines user_id and topic_code
    doc_id = f"{user_id}_{topic_code}" if user_id else topic_code
    
    # Get reference to the document
    topic_ref = db.collection(TOPIC_PROGRESS_COLLECTION).document(doc_id)
    
    # Check if document exists
    topic_doc = topic_ref.get()
    
    if topic_doc.exists:
        # Update existing document
        topic_ref.update({
            'topic_title': topic_title,
            'proficiency': rating,
            'notes': notes,
            'last_studied': last_studied,
            'last_updated': datetime.now().isoformat()
        })
    else:
        # Create new document
        topic_data = {
            'topic_code': topic_code,
            'topic_title': topic_title,
            'proficiency': rating,
            'notes': notes,
            'last_studied': last_studied,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        if user_id:
            topic_data['user_id'] = user_id
            
        topic_ref.set(topic_data)
    
    return True

def get_topic_progress(user_id: str = None) -> List[Tuple[str, str, str, int, str]]:
    """
    Get a user's progress on all topics from Firestore.
    Returns a list of (topic_code, topic_title, last_studied, proficiency, notes) tuples
    for backward compatibility.
    """
    db = get_db()
    
    # Query for user's topics or all topics if no user_id
    if user_id:
        query = db.collection(TOPIC_PROGRESS_COLLECTION).where('user_id', '==', user_id)
    else:
        query = db.collection(TOPIC_PROGRESS_COLLECTION)
        
    results = query.stream()
    
    topic_progress = []
    for doc in results:
        data = doc.to_dict()
        topic_progress.append((
            data.get('topic_code', ''),
            data.get('topic_title', ''),
            data.get('last_studied', ''),
            data.get('proficiency', 0),
            data.get('notes', '')
        ))
    
    return topic_progress

def record_exam_practice(
    topic_code: str, 
    question_type: str, 
    difficulty: int, 
    score: int, 
    max_score: int, 
    user_id: str = None
) -> bool:
    """
    Record a student's exam practice results in Firestore.
    Returns True if the record was created successfully.
    """
    db = get_db()
    
    # Create exam practice document
    exam_ref = db.collection(EXAM_PRACTICE_COLLECTION).document()
    
    exam_data = {
        'topic_code': topic_code,
        'question_type': question_type,
        'difficulty': difficulty,
        'score': score,
        'max_score': max_score,
        'percentage': (score / max_score) * 100 if max_score > 0 else 0,
        'created_at': datetime.now().isoformat()
    }
    
    if user_id:
        exam_data['user_id'] = user_id
        
    exam_ref.set(exam_data)
    
    return True

def get_exam_progress(user_id: str = None) -> List[Tuple[str, str, int, int, int, float, str]]:
    """
    Get a user's exam practice results from Firestore.
    Returns a list of (topic_code, question_type, difficulty, score, max_score, percentage, created_at)
    tuples for backward compatibility.
    """
    db = get_db()
    
    # Query for user's exams or all exams if no user_id
    if user_id:
        query = db.collection(EXAM_PRACTICE_COLLECTION).where('user_id', '==', user_id)
    else:
        query = db.collection(EXAM_PRACTICE_COLLECTION)
        
    results = query.stream()
    
    exam_progress = []
    for doc in results:
        data = doc.to_dict()
        exam_progress.append((
            data.get('topic_code', ''),
            data.get('question_type', ''),
            data.get('difficulty', 1),
            data.get('score', 0),
            data.get('max_score', 0),
            data.get('percentage', 0),
            data.get('created_at', '')
        ))
    
    return exam_progress

def add_pdf_to_database(user_id: str, topic_code: str, topic_title: str, filename: str) -> str:
    """
    DEPRECATED: Add a PDF to the legacy latex_pdfs collection in Firestore.
    This function exists for backward compatibility.
    Returns the document ID of the created PDF record.
    """
    db = get_db()
    
    # Create PDF document
    pdf_ref = db.collection('latex_pdfs').document()
    
    pdf_ref.set({
        'user_id': user_id,
        'topic_code': topic_code,
        'topic_title': topic_title,
        'filename': filename,
        'created_at': datetime.now().isoformat()
    })
    
    return pdf_ref.id

def add_pdf_to_generated_pdfs(
    user_id: str, 
    topic_code: str, 
    title: str, 
    latex_content: str, 
    pdf_path: str,
    storage_url: str = None,
    storage_path: str = None
) -> str:
    """
    Add a PDF to the generated_pdfs collection in Firestore.
    
    Args:
        user_id: ID of the user who owns the PDF
        topic_code: Topic code related to the PDF
        title: Title of the PDF
        latex_content: LaTeX content used to generate the PDF
        pdf_path: Local path to the PDF file (for backward compatibility)
        storage_url: Firebase Storage URL for the PDF (if using Storage)
        storage_path: Firebase Storage path for the PDF (if using Storage)
        
    Returns:
        str: The document ID of the created PDF record
    """
    db = get_db()
    
    # Create PDF document
    pdf_ref = db.collection(GENERATED_PDFS_COLLECTION).document()
    
    pdf_data = {
        'user_id': user_id,
        'topic_code': topic_code,
        'title': title,
        'latex_content': latex_content,
        'pdf_path': pdf_path,
        'created_at': datetime.now().isoformat()
    }
    
    # Add Storage information if available
    if storage_url:
        pdf_data['storage_url'] = storage_url
    
    if storage_path:
        pdf_data['storage_path'] = storage_path
        
    pdf_ref.set(pdf_data)
    
    return pdf_ref.id

def get_pdf_by_id(pdf_id: str, user_id: str) -> Optional[Dict]:
    """
    Get a specific PDF by ID and verify ownership.
    
    Args:
        pdf_id: ID of the PDF document
        user_id: ID of the user
        
    Returns:
        dict: PDF data if found and owned by user, None otherwise
    """
    db = get_db()
    
    # Check generated_pdfs collection
    pdf_ref = db.collection(GENERATED_PDFS_COLLECTION).document(pdf_id)
    pdf = pdf_ref.get()
    
    if pdf.exists and pdf.to_dict().get('user_id') == user_id:
        pdf_data = pdf.to_dict()
        pdf_data['id'] = pdf_id
        return pdf_data
    
    # Check legacy latex_pdfs collection
    legacy_ref = db.collection('latex_pdfs').document(pdf_id)
    legacy_pdf = legacy_ref.get()
    
    if legacy_pdf.exists and legacy_pdf.to_dict().get('user_id') == user_id:
        pdf_data = legacy_pdf.to_dict()
        pdf_data['id'] = pdf_id
        return pdf_data
    
    return None

def get_pdfs_for_user(user_id: str) -> List[Tuple]:
    """
    Get all PDFs created by a user from Firestore.
    Returns a combined list with the format:
    (id, topic_code, title, created_at, pdf_path, storage_url, storage_path)
    """
    db = get_db()
    
    # Get PDFs from generated_pdfs collection
    pdfs_query = db.collection(GENERATED_PDFS_COLLECTION).where('user_id', '==', user_id)
    pdfs = pdfs_query.stream()
    
    result = []
    for pdf in pdfs:
        pdf_data = pdf.to_dict()
        result.append((
            pdf.id,
            pdf_data.get('topic_code', ''),
            pdf_data.get('title', ''),
            pdf_data.get('created_at', ''),
            pdf_data.get('pdf_path', ''),
            pdf_data.get('storage_url', ''),  # Add Storage URL
            pdf_data.get('storage_path', '')  # Add Storage path
        ))
    
    # Get legacy PDFs from latex_pdfs collection
    legacy_query = db.collection('latex_pdfs').where('user_id', '==', user_id)
    legacy_pdfs = legacy_query.stream()
    
    for pdf in legacy_pdfs:
        pdf_data = pdf.to_dict()
        filename = pdf_data.get('filename', '')
        # Convert .tex filename to .pdf path format
        pdf_path = f"temp_latex/{filename.replace('.tex', '.pdf')}" if filename else ''
        
        result.append((
            pdf.id,
            pdf_data.get('topic_code', ''),
            pdf_data.get('topic_title', ''),
            pdf_data.get('created_at', ''),
            pdf_path,
            '',  # Legacy PDFs don't have a storage URL
            ''   # Legacy PDFs don't have a storage path
        ))
    
    # Sort by created_at, newest first
    # Handle both string timestamps and Firestore timestamps
    def get_created_at_key(pdf_tuple):
        created_at = pdf_tuple[3]  # Index 3 is created_at
        # If created_at is a Firestore timestamp object, convert to string
        if hasattr(created_at, 'isoformat'):
            return created_at.isoformat()
        return str(created_at)  # Ensure it's a string for comparison
        
    result.sort(key=get_created_at_key, reverse=True)
    
    return result

def delete_pdf(user_id: str, pdf_id: str) -> bool:
    """
    Delete a PDF created by a user from Firestore.
    Checks both generated_pdfs and latex_pdfs collections.
    Returns True if the PDF was deleted successfully.
    """
    db = get_db()
    
    # Check generated_pdfs collection
    pdf_ref = db.collection(GENERATED_PDFS_COLLECTION).document(pdf_id)
    pdf = pdf_ref.get()
    
    if pdf.exists and pdf.to_dict().get('user_id') == user_id:
        pdf_ref.delete()
        return True
    
    # Check latex_pdfs collection
    legacy_ref = db.collection('latex_pdfs').document(pdf_id)
    legacy_pdf = legacy_ref.get()
    
    if legacy_pdf.exists and legacy_pdf.to_dict().get('user_id') == user_id:
        legacy_ref.delete()
        return True
    
    return False

def track_activity(user_id: str, activity_type: str = 'page_view', session_duration: int = 0) -> bool:
    """
    Track a user's activity in Firestore for streak calculation.
    Returns True if the activity was tracked successfully.
    """
    db = get_db()
    
    # Get current date in YYYY-MM-DD format
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Create document ID combining user_id and date
    doc_id = f"{user_id}_{today}"
    
    # Reference to the activity document
    activity_ref = db.collection(USER_ACTIVITY_COLLECTION).document(doc_id)
    
    # Check if user already has activity for today
    activity = activity_ref.get()
    
    if activity.exists:
        # Update existing activity
        activity_ref.update({
            'session_duration': firestore.Increment(session_duration),
            'last_updated': datetime.now().isoformat()
        })
    else:
        # Create new activity
        activity_ref.set({
            'user_id': user_id,
            'activity_date': today,
            'activity_type': activity_type,
            'session_duration': session_duration,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        })
    
    return True

def get_activity_data(user_id: str, start_date: str, end_date: str) -> List[Tuple[str, str, int]]:
    """
    Get a user's activity data for a date range from Firestore.
    Returns a list of (activity_date, activity_type, session_duration) tuples.
    """
    db = get_db()
    
    # Query for user's activities within date range
    query = (
        db.collection(USER_ACTIVITY_COLLECTION)
        .where('user_id', '==', user_id)
        .where('activity_date', '>=', start_date)
        .where('activity_date', '<=', end_date)
    )
    
    results = query.stream()
    
    activity_data = []
    for doc in results:
        data = doc.to_dict()
        activity_data.append((
            data.get('activity_date', ''),
            data.get('activity_type', ''),
            data.get('session_duration', 0)
        ))
    
    # Sort by date
    activity_data.sort(key=lambda x: x[0])
    
    return activity_data

def calculate_user_streak(user_id: str) -> Dict[str, Any]:
    """
    Calculate a user's current streak from Firestore activity data.
    Returns a dictionary with 'streak' (int) and 'streak_at_risk' (bool) keys.
    """
    db = get_db()
    
    # Get today's date and yesterday's date
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)
    
    # Format dates as strings
    today_str = today.strftime('%Y-%m-%d')
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    two_days_ago_str = two_days_ago.strftime('%Y-%m-%d')
    
    # Check if user has activity for today
    today_doc = db.collection(USER_ACTIVITY_COLLECTION).document(f"{user_id}_{today_str}").get()
    has_activity_today = today_doc.exists
    
    # Check if user has activity for yesterday
    yesterday_doc = db.collection(USER_ACTIVITY_COLLECTION).document(f"{user_id}_{yesterday_str}").get()
    has_activity_yesterday = yesterday_doc.exists
    
    # Check if user has activity for two days ago
    two_days_ago_doc = db.collection(USER_ACTIVITY_COLLECTION).document(f"{user_id}_{two_days_ago_str}").get()
    has_activity_two_days_ago = two_days_ago_doc.exists
    
    # Get all activity dates for this user
    query = db.collection(USER_ACTIVITY_COLLECTION).where('user_id', '==', user_id)
    results = query.stream()
    
    activity_dates = []
    for doc in results:
        data = doc.to_dict()
        activity_date = data.get('activity_date')
        if activity_date:
            try:
                activity_dates.append(datetime.strptime(activity_date, '%Y-%m-%d').date())
            except ValueError:
                continue
    
    # Sort activity dates in descending order
    activity_dates.sort(reverse=True)
    
    # If no activity, streak is 0
    if not activity_dates:
        return {'streak': 0, 'streak_at_risk': False}
    
    # Calculate streak
    streak = 0
    streak_at_risk = False
    
    # If user has activity today, start counting from today
    if has_activity_today:
        streak = 1
        date_to_check = yesterday
    # If user has activity yesterday but not today, start counting from yesterday
    # and mark streak as at risk
    elif has_activity_yesterday:
        streak = 1
        date_to_check = two_days_ago
        streak_at_risk = True
    # If user has activity two days ago but not yesterday or today,
    # streak is 0 (streak was broken)
    else:
        return {'streak': 0, 'streak_at_risk': False}
    
    # Continue counting streak from previous days
    for date in activity_dates:
        if date == today or date == yesterday:
            # Skip today and yesterday as they were already counted
            continue
            
        if date == date_to_check:
            streak += 1
            date_to_check = date_to_check - timedelta(days=1)
        else:
            # Allow for one missed day in the streak
            if date == date_to_check - timedelta(days=1) and not streak_at_risk:
                streak_at_risk = True
                date_to_check = date - timedelta(days=1)
            else:
                # Streak is broken
                break
    
    return {'streak': streak, 'streak_at_risk': streak_at_risk}

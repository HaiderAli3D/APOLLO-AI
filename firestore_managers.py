#!/usr/bin/env python3
"""
Firestore Data Managers

This module provides classes for interacting with Firestore database collections.
Each manager class is responsible for a specific collection or related set of collections.
"""

import time
import datetime
from typing import List, Dict, Any, Optional, Tuple, Union
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import auth

class FirestoreUserManager:
    """Manager for the users collection in Firestore."""
    
    def __init__(self, db: firestore.Client):
        """Initialize with a Firestore client instance."""
        self.db = db
        self.collection = 'users'
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their ID.
        
        Args:
            user_id: The user's document ID
            
        Returns:
            User document as a dictionary or None if not found
        """
        try:
            doc_ref = self.db.collection(self.collection).document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"Error getting user {user_id}: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their email address.
        
        Args:
            email: The user's email address
            
        Returns:
            User document as a dictionary or None if not found
        """
        try:
            query = self.db.collection(self.collection).where(filter=FieldFilter("email", "==", email))
            docs = query.get()
            
            for doc in docs:
                # Return the first matching document
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            print(f"Error getting user by email {email}: {e}")
            return None
    
    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by their Firebase UID.
        
        Args:
            firebase_uid: The user's Firebase UID
            
        Returns:
            User document as a dictionary or None if not found
        """
        try:
            query = self.db.collection(self.collection).where(filter=FieldFilter("firebase_uid", "==", firebase_uid))
            docs = query.get()
            
            for doc in docs:
                # Return the first matching document
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            print(f"Error getting user by Firebase UID {firebase_uid}: {e}")
            return None
    
    def create_user(self, user_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new user document.
        
        Args:
            user_data: Dictionary containing user information
            
        Returns:
            The ID of the created document or None if creation failed
        """
        try:
            # Handle the case where Firebase UID is provided
            firebase_uid = user_data.get('firebase_uid')
            if firebase_uid:
                # Check if user already exists with this Firebase UID
                existing_user = self.get_user_by_firebase_uid(firebase_uid)
                if existing_user:
                    return existing_user.get('id')
                
                # Use Firebase UID as document ID
                doc_ref = self.db.collection(self.collection).document(firebase_uid)
            else:
                # Auto-generate document ID
                doc_ref = self.db.collection(self.collection).document()
            
            # Add created_at timestamp if not provided
            if 'created_at' not in user_data:
                user_data['created_at'] = firestore.SERVER_TIMESTAMP
                
            doc_ref.set(user_data)
            return doc_ref.id
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """
        Update a user document.
        
        Args:
            user_id: The user's document ID
            user_data: Dictionary containing fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            doc_ref = self.db.collection(self.collection).document(user_id)
            doc_ref.update(user_data)
            return True
        except Exception as e:
            print(f"Error updating user {user_id}: {e}")
            return False
    
    def get_or_create_firebase_user(self, uid: str, email: str, full_name: str, 
                                   role: str = 'student', profile_picture_url: str = None, 
                                   decoded_token: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Get existing user by Firebase UID or create a new one.
        
        Args:
            uid: Firebase UID
            email: User's email
            full_name: User's full name
            role: User role (student, admin, developer)
            profile_picture_url: URL to profile picture
            decoded_token: Decoded Firebase token
            
        Returns:
            User document as a dictionary or None if operation failed
        """
        try:
            # First, check if user exists by Firebase UID
            user = self.get_user_by_firebase_uid(uid)
            
            # If picture URL is not provided, try to extract it from token
            if profile_picture_url is None and decoded_token:
                profile_picture_url = decoded_token.get('picture')
                if not profile_picture_url:
                    # Try alternative field for Google auth
                    provider = decoded_token.get('firebase', {}).get('sign_in_provider', '')
                    if provider == 'google.com':
                        profile_picture_url = decoded_token.get('photoURL')
            
            if user:
                # User exists, update profile picture if provided
                if profile_picture_url:
                    self.update_user(user['id'], {'profile_picture_url': profile_picture_url})
                    # Refresh user data
                    user = self.get_user_by_id(user['id'])
                return user
            
            # Check if user exists by email (for migration)
            user = self.get_user_by_email(email)
            
            if user:
                # Update existing user with Firebase UID
                update_data = {
                    'firebase_uid': uid,
                    'account_migrated': True
                }
                
                if profile_picture_url:
                    update_data['profile_picture_url'] = profile_picture_url
                
                self.update_user(user['id'], update_data)
                # Refresh user data
                user = self.get_user_by_id(user['id'])
                return user
            
            # Create new user
            user_data = {
                'firebase_uid': uid,
                'email': email,
                'full_name': full_name,
                'role': role,
                'account_migrated': True,
                'password_hash': "firebase_auth",  # Legacy field
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            if profile_picture_url:
                user_data['profile_picture_url'] = profile_picture_url
            
            user_id = self.create_user(user_data)
            if user_id:
                return self.get_user_by_id(user_id)
            return None
        except Exception as e:
            print(f"Error in get_or_create_firebase_user: {e}")
            return None

class FirestoreSessionManager:
    """Manager for the sessions collection and related message subcollections in Firestore."""
    
    def __init__(self, db: firestore.Client):
        """Initialize with a Firestore client instance."""
        self.db = db
        self.collection = 'sessions'
    
    def start_session(self, topics: List[str], user_id: Optional[str] = None) -> Optional[str]:
        """
        Start a new learning session.
        
        Args:
            topics: List of topics for the session
            user_id: Optional user ID to associate with the session
            
        Returns:
            Session ID or None if creation failed
        """
        try:
            # Create session document
            session_data = {
                'topics': topics,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_active': firestore.SERVER_TIMESTAMP
            }
            
            if user_id:
                session_data['user_id'] = user_id
                
            # Auto-generate document ID
            doc_ref = self.db.collection(self.collection).document()
            doc_ref.set(session_data)
            
            return doc_ref.id
        except Exception as e:
            print(f"Error starting session: {e}")
            return None
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a session by ID.
        
        Args:
            session_id: The session document ID
            
        Returns:
            Session document as a dictionary or None if not found
        """
        try:
            doc_ref = self.db.collection(self.collection).document(session_id)
            doc = doc_ref.get()
            if doc.exists:
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            print(f"Error getting session {session_id}: {e}")
            return None
    
    def add_message(self, session_id: str, role: str, content: str) -> Optional[str]:
        """
        Add a message to a session.
        
        Args:
            session_id: The session document ID
            role: Message role (user or assistant)
            content: Message content
            
        Returns:
            Message ID or None if creation failed
        """
        try:
            # Update session last_active timestamp
            session_ref = self.db.collection(self.collection).document(session_id)
            session_ref.update({'last_active': firestore.SERVER_TIMESTAMP})
            
            # Add message to subcollection
            messages_ref = session_ref.collection('messages')
            
            message_data = {
                'role': role,
                'content': content,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            
            # Auto-generate document ID
            doc_ref = messages_ref.document()
            doc_ref.set(message_data)
            
            return doc_ref.id
        except Exception as e:
            print(f"Error adding message to session {session_id}: {e}")
            return None
    
    def get_session_messages(self, session_id: str, limit: int = 50) -> List[Tuple[str, str, str]]:
        """
        Get messages for a session.
        
        Args:
            session_id: The session document ID
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of tuples (message_id, role, content)
        """
        try:
            messages_ref = self.db.collection(self.collection).document(session_id).collection('messages')
            # Order by timestamp to ensure messages are in chronological order
            query = messages_ref.order_by('timestamp').limit(limit)
            docs = query.get()
            
            messages = []
            for doc in docs:
                data = doc.to_dict()
                messages.append((doc.id, data.get('role', ''), data.get('content', '')))
            
            return messages
        except Exception as e:
            print(f"Error getting messages for session {session_id}: {e}")
            return []
    
    def verify_session_ownership(self, session_id: str, user_id: str) -> bool:
        """
        Check if a session belongs to a user.
        
        Args:
            session_id: The session document ID
            user_id: The user document ID
            
        Returns:
            True if the session belongs to the user, False otherwise
        """
        try:
            session = self.get_session(session_id)
            if not session:
                return False
            
            # If the session has no user_id, assume it's accessible
            if 'user_id' not in session:
                return True
                
            return session.get('user_id') == user_id
        except Exception as e:
            print(f"Error verifying session ownership: {e}")
            return False
    
    def clear_session_messages(self, session_id: str) -> bool:
        """
        Delete all messages for a session.
        
        Args:
            session_id: The session document ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            messages_ref = self.db.collection(self.collection).document(session_id).collection('messages')
            docs = messages_ref.get()
            
            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            
            batch.commit()
            return True
        except Exception as e:
            print(f"Error clearing messages for session {session_id}: {e}")
            return False

class FirestoreProgressManager:
    """Manager for student progress data in Firestore."""
    
    def __init__(self, db: firestore.Client):
        """Initialize with a Firestore client instance."""
        self.db = db
        self.topic_progress_collection = 'topic_progress'
        self.exam_progress_collection = 'exam_practice'
    
    def update_topic_progress(self, topic_code: str, topic_title: str, rating: int, 
                             notes: str = '', user_id: Optional[str] = None,
                             last_studied: Optional[str] = None) -> bool:
        """
        Update progress for a specific topic.
        
        Args:
            topic_code: The topic code (e.g., "1.2.3")
            topic_title: The topic title
            rating: Proficiency rating (1-5)
            notes: Optional notes about the topic
            user_id: The user document ID
            last_studied: Date string in YYYY-MM-DD format
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not user_id:
                print("Warning: No user_id provided for topic progress update")
                return False
                
            # Use user_id/topic_code as the document ID for easy retrieval
            doc_id = f"{user_id}_{topic_code}"
            doc_ref = self.db.collection(self.topic_progress_collection).document(doc_id)
            
            # Set the last_studied date if not provided
            if not last_studied:
                last_studied = datetime.datetime.now().strftime('%Y-%m-%d')
                
            # Check if document exists
            doc = doc_ref.get()
            if doc.exists:
                # Update existing document
                doc_ref.update({
                    'topic_title': topic_title,
                    'rating': rating,
                    'notes': notes,
                    'last_studied': last_studied,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            else:
                # Create new document
                doc_ref.set({
                    'user_id': user_id,
                    'topic_code': topic_code,
                    'topic_title': topic_title,
                    'rating': rating,
                    'notes': notes,
                    'last_studied': last_studied,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            
            return True
        except Exception as e:
            print(f"Error updating topic progress: {e}")
            return False
    
    def get_topic_progress(self, user_id: Optional[str] = None) -> List[Tuple[str, str, str, int, str]]:
        """
        Get topic progress for a user.
        
        Args:
            user_id: The user document ID (optional)
            
        Returns:
            List of tuples (topic_code, topic_title, last_studied, rating, notes)
        """
        try:
            if user_id:
                # Filter by user_id
                query = self.db.collection(self.topic_progress_collection).where(
                    filter=FieldFilter("user_id", "==", user_id))
            else:
                # Get all progress records (not recommended for large datasets)
                query = self.db.collection(self.topic_progress_collection)
                
            docs = query.get()
            
            progress_list = []
            for doc in docs:
                data = doc.to_dict()
                progress_list.append((
                    data.get('topic_code', ''),
                    data.get('topic_title', ''),
                    data.get('last_studied', ''),
                    data.get('rating', 0),
                    data.get('notes', '')
                ))
            
            return progress_list
        except Exception as e:
            print(f"Error getting topic progress: {e}")
            return []
    
    def record_exam_practice(self, topic_code: str, question_type: str, 
                            difficulty: int, score: int, max_score: int,
                            user_id: Optional[str] = None) -> bool:
        """
        Record exam practice results.
        
        Args:
            topic_code: The topic code (e.g., "1.2.3")
            question_type: Type of questions (e.g., "exam", "quiz")
            difficulty: Difficulty level (1-3)
            score: Points scored
            max_score: Maximum possible score
            user_id: The user document ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not user_id:
                print("Warning: No user_id provided for exam practice record")
                return False
                
            # Create a new document with auto-generated ID
            doc_ref = self.db.collection(self.exam_progress_collection).document()
            
            doc_ref.set({
                'user_id': user_id,
                'topic_code': topic_code,
                'question_type': question_type,
                'difficulty': difficulty,
                'score': score,
                'max_score': max_score,
                'percentage': (score / max_score) * 100 if max_score > 0 else 0,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            
            return True
        except Exception as e:
            print(f"Error recording exam practice: {e}")
            return False
    
    def get_exam_progress(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get exam practice results.
        
        Args:
            user_id: The user document ID (optional)
            limit: Maximum number of results to retrieve
            
        Returns:
            List of exam practice records
        """
        try:
            if user_id:
                # Filter by user_id
                query = self.db.collection(self.exam_progress_collection).where(
                    filter=FieldFilter("user_id", "==", user_id))
            else:
                # Get all records (not recommended for large datasets)
                query = self.db.collection(self.exam_progress_collection)
                
            # Order by timestamp (descending) and limit results
            query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.get()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                # Add document ID to data
                data['id'] = doc.id
                results.append(data)
            
            return results
        except Exception as e:
            print(f"Error getting exam progress: {e}")
            return []

class FirestorePDFManager:
    """Manager for generated PDF documents in Firestore."""
    
    def __init__(self, db: firestore.Client):
        """Initialize with a Firestore client instance."""
        self.db = db
        self.collection = 'generated_pdfs'
    
    def add_pdf(self, user_id: str, topic_code: str, title: str, 
                latex_content: str, pdf_path: str) -> Optional[str]:
        """
        Add a generated PDF document.
        
        Args:
            user_id: The user document ID
            topic_code: The topic code (e.g., "1.2.3")
            title: Document title
            latex_content: LaTeX content used to generate the PDF
            pdf_path: Path to the generated PDF file
            
        Returns:
            Document ID or None if creation failed
        """
        try:
            # Create a new document with auto-generated ID
            doc_ref = self.db.collection(self.collection).document()
            
            doc_ref.set({
                'user_id': user_id,
                'topic_code': topic_code,
                'title': title,
                'latex_content': latex_content,
                'pdf_path': pdf_path,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            
            return doc_ref.id
        except Exception as e:
            print(f"Error adding PDF document: {e}")
            return None
    
    def get_pdfs_for_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get PDF documents for a user.
        
        Args:
            user_id: The user document ID
            limit: Maximum number of documents to retrieve
            
        Returns:
            List of PDF document records
        """
        try:
            query = self.db.collection(self.collection).where(
                filter=FieldFilter("user_id", "==", user_id))
                
            # Order by created_at (descending) and limit results
            query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.get()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                # Add document ID to data
                data['id'] = doc.id
                results.append(data)
            
            return results
        except Exception as e:
            print(f"Error getting PDFs for user {user_id}: {e}")
            return []
    
    def delete_pdf(self, pdf_id: str, user_id: str) -> bool:
        """
        Delete a PDF document.
        
        Args:
            pdf_id: The document ID
            user_id: The user document ID (for ownership verification)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            doc_ref = self.db.collection(self.collection).document(pdf_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                print(f"PDF document {pdf_id} not found")
                return False
                
            # Verify ownership
            data = doc.to_dict()
            if data.get('user_id') != user_id:
                print(f"User {user_id} does not own PDF document {pdf_id}")
                return False
                
            # Delete the document
            doc_ref.delete()
            return True
        except Exception as e:
            print(f"Error deleting PDF document {pdf_id}: {e}")
            return False

class FirestoreActivityManager:
    """Manager for user activity data in Firestore."""
    
    def __init__(self, db: firestore.Client):
        """Initialize with a Firestore client instance."""
        self.db = db
        self.collection = 'user_activity'
    
    def track_activity(self, user_id: str, activity_type: str = 'page_view', 
                      session_duration: int = 0) -> bool:
        """
        Track user activity for streak calculation.
        
        Args:
            user_id: The user document ID
            activity_type: Type of activity
            session_duration: Duration of the session in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current date in YYYY-MM-DD format
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            
            # Use user_id/date as the document ID for easy retrieval
            doc_id = f"{user_id}_{today}"
            doc_ref = self.db.collection(self.collection).document(doc_id)
            
            # Check if document exists
            doc = doc_ref.get()
            if doc.exists:
                # Update existing document
                data = doc.to_dict()
                current_duration = data.get('session_duration', 0)
                
                doc_ref.update({
                    'session_duration': current_duration + session_duration,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            else:
                # Create new document
                doc_ref.set({
                    'user_id': user_id,
                    'activity_date': today,
                    'activity_type': activity_type,
                    'session_duration': session_duration,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            
            return True
        except Exception as e:
            print(f"Error tracking activity: {e}")
            return False
    
    def get_activity_data(self, user_id: str, year: int, month: int) -> List[Dict[str, Any]]:
        """
        Get user activity data for a specific month.
        
        Args:
            user_id: The user document ID
            year: Year
            month: Month (1-12)
            
        Returns:
            List of activity records
        """
        try:
            # Calculate first and last day of the month
            if month == 12:
                end_date = datetime.datetime(year + 1, 1, 1) - datetime.timedelta(days=1)
            else:
                end_date = datetime.datetime(year, month + 1, 1) - datetime.timedelta(days=1)
                
            start_date = datetime.datetime(year, month, 1)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # Query for activity records in the date range
            query = self.db.collection(self.collection).where(
                filter=FieldFilter("user_id", "==", user_id)).where(
                filter=FieldFilter("activity_date", ">=", start_date_str)).where(
                filter=FieldFilter("activity_date", "<=", end_date_str))
                
            docs = query.get()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                results.append({
                    'date': data.get('activity_date', ''),
                    'type': data.get('activity_type', ''),
                    'duration': data.get('session_duration', 0)
                })
            
            return results
        except Exception as e:
            print(f"Error getting activity data: {e}")
            return []
    
    def calculate_user_streak(self, user_id: str) -> Dict[str, Any]:
        """
        Calculate a user's current streak and whether it's at risk.
        
        Args:
            user_id: The user document ID
            
        Returns:
            Dictionary with streak info
        """
        try:
            # Get today's date and previous dates
            today = datetime.datetime.now().date()
            yesterday = today - datetime.timedelta(days=1)
            two_days_ago = today - datetime.timedelta(days=2)
            
            # Format dates as strings
            today_str = today.strftime('%Y-%m-%d')
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            two_days_ago_str = two_days_ago.strftime('%Y-%m-%d')
            
            # Check if user has activity for today
            today_doc_id = f"{user_id}_{today_str}"
            today_doc = self.db.collection(self.collection).document(today_doc_id).get()
            has_activity_today = today_doc.exists
            
            # Check if user has activity for yesterday
            yesterday_doc_id = f"{user_id}_{yesterday_str}"
            yesterday_doc = self.db.collection(self.collection).document(yesterday_doc_id).get()
            has_activity_yesterday = yesterday_doc.exists
            
            # Check if user has activity for two days ago
            two_days_ago_doc_id = f"{user_id}_{two_days_ago_str}"
            two_days_ago_doc = self.db.collection(self.collection).document(two_days_ago_doc_id).get()
            has_activity_two_days_ago = two_days_ago_doc.exists
            
            # Get all activity dates for this user in descending order
            query = self.db.collection(self.collection).where(
                filter=FieldFilter("user_id", "==", user_id)).order_by(
                'activity_date', direction=firestore.Query.DESCENDING)
            
            docs = query.get()
            activity_dates = [datetime.datetime.strptime(
                doc.to_dict()['activity_date'], '%Y-%m-%d').date() for doc in docs]
            
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
                    date_to_check = date_to_check - datetime.timedelta(days=1)
                else:
                    # Allow for one missed day in the streak
                    if date == date_to_check - datetime.timedelta(days=1) and not streak_at_risk:
                        streak_at_risk = True
                        date_to_check = date - datetime.timedelta(days=1)
                    else:
                        # Streak is broken
                        break
            
            return {'streak': streak, 'streak_at_risk': streak_at_risk}
        except Exception as e:
            print(f"Error calculating streak: {e}")
            return {'streak': 0, 'streak_at_risk': False}

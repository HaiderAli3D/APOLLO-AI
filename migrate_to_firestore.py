"""
Data Migration Script for SQLite to Firestore

This script transfers data from the existing SQLite databases to Firebase Firestore.
It should be run once to migrate all existing data.
"""

import os
import sqlite3
from datetime import datetime
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
import argparse

# Import Firestore adapter to use the same collection names and structure
from firestore_db_adapter import (
    USERS_COLLECTION, SESSIONS_COLLECTION, MESSAGES_COLLECTION,
    TOPIC_PROGRESS_COLLECTION, EXAM_PRACTICE_COLLECTION,
    GENERATED_PDFS_COLLECTION, USER_ACTIVITY_COLLECTION
)

# SQLite database paths
OCR_CS_TUTOR_DB = 'ocr_cs_tutor.db'
USER_DATABASE_DB = 'user_database.db'
KNOWLEDGE_BASE_DB = 'knowledge_base.db'

# Initialize Firestore
def init_firestore():
    """Initialize Firebase Admin SDK and get Firestore client."""
    try:
        # Check if already initialized
        firebase_admin.get_app()
    except ValueError:
        # Initialize with service account
        cred = credentials.Certificate("apollo-auth-753b5-firebase-adminsdk-fbsvc-6b6d2904d5.json")
        firebase_admin.initialize_app(cred)
    
    return firestore.client()

def migrate_users():
    """Migrate users from SQLite to Firestore."""
    print("Migrating users...")
    
    db = init_firestore()
    conn = sqlite3.connect(USER_DATABASE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all users
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    migrated_count = 0
    for user in users:
        # Convert user data to dict
        user_data = {
            'email': user['email'],
            'password_hash': user['password_hash'],
            'full_name': user['full_name'],
            'role': user['role'],
            'created_at': user.get('created_at', datetime.now().isoformat()),
            'account_migrated': True
        }
        
        # Add firebase_uid if exists
        if 'firebase_uid' in user.keys() and user['firebase_uid']:
            user_data['firebase_uid'] = user['firebase_uid']
            
        # Add profile picture if exists
        if 'profile_picture_url' in user.keys() and user['profile_picture_url']:
            user_data['profile_picture_url'] = user['profile_picture_url']
        
        # Create document with same ID
        user_id = str(user['id'])
        db.collection(USERS_COLLECTION).document(user_id).set(user_data)
        migrated_count += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_count} users")
    return migrated_count

def migrate_sessions():
    """Migrate sessions and messages from SQLite to Firestore."""
    print("Migrating sessions and messages...")
    
    db = init_firestore()
    conn = sqlite3.connect(OCR_CS_TUTOR_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all sessions
    cursor.execute("SELECT * FROM sessions")
    sessions = cursor.fetchall()
    
    migrated_sessions = 0
    migrated_messages = 0
    
    for session in sessions:
        # Convert session data to dict
        session_id = str(session['id'])
        
        # Extract context information from topic field
        topic = session.get('topic', '')
        context_info = topic.split('|') if topic else []
        
        session_data = {
            'context': context_info,
            'started_at': session.get('created_at', datetime.now().isoformat()),
            'last_activity': session.get('last_activity', datetime.now().isoformat())
        }
        
        # Add user_id if exists
        if 'user_id' in session.keys() and session['user_id']:
            session_data['user_id'] = str(session['user_id'])
        
        # Create session document
        db.collection(SESSIONS_COLLECTION).document(session_id).set(session_data)
        migrated_sessions += 1
        
        # Get messages for this session
        cursor.execute(
            "SELECT * FROM conversation_history WHERE session_id = ? ORDER BY timestamp",
            (session['id'],)
        )
        messages = cursor.fetchall()
        
        # Migrate messages
        for message in messages:
            message_data = {
                'role': message['role'],
                'content': message['content'],
                'timestamp': message.get('timestamp', datetime.now().isoformat())
            }
            
            # Create message document in subcollection
            message_ref = db.collection(SESSIONS_COLLECTION).document(session_id) \
                            .collection(MESSAGES_COLLECTION).document()
            message_ref.set(message_data)
            migrated_messages += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_sessions} sessions and {migrated_messages} messages")
    return migrated_sessions, migrated_messages

def migrate_topic_progress():
    """Migrate topic progress data from SQLite to Firestore."""
    print("Migrating topic progress...")
    
    db = init_firestore()
    conn = sqlite3.connect(OCR_CS_TUTOR_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all topic progress entries
    cursor.execute("SELECT * FROM topic_progress")
    progress_entries = cursor.fetchall()
    
    migrated_count = 0
    for entry in progress_entries:
        # Convert data to dict
        progress_data = {
            'topic_code': entry['topic_code'],
            'topic_title': entry['topic_title'],
            'proficiency': entry['proficiency'],
            'notes': entry.get('notes', ''),
            'last_studied': entry.get('last_studied', datetime.now().strftime('%Y-%m-%d')),
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        # Add user_id if exists
        user_id = None
        if 'user_id' in entry.keys() and entry['user_id']:
            user_id = str(entry['user_id'])
            progress_data['user_id'] = user_id
        
        # Create document ID that combines user_id and topic_code
        doc_id = f"{user_id}_{entry['topic_code']}" if user_id else entry['topic_code']
        
        # Create document
        db.collection(TOPIC_PROGRESS_COLLECTION).document(doc_id).set(progress_data)
        migrated_count += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_count} topic progress entries")
    return migrated_count

def migrate_exam_practice():
    """Migrate exam practice data from SQLite to Firestore."""
    print("Migrating exam practice data...")
    
    db = init_firestore()
    conn = sqlite3.connect(OCR_CS_TUTOR_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all exam practice entries
    cursor.execute("SELECT * FROM exam_practice")
    exam_entries = cursor.fetchall()
    
    migrated_count = 0
    for entry in exam_entries:
        # Convert data to dict
        max_score = entry.get('max_score', 0)
        score = entry.get('score', 0)
        
        exam_data = {
            'topic_code': entry['topic_code'],
            'question_type': entry.get('question_type', 'exam'),
            'difficulty': entry.get('difficulty', 2),
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score) * 100 if max_score > 0 else 0,
            'created_at': entry.get('created_at', datetime.now().isoformat())
        }
        
        # Add user_id if exists
        if 'user_id' in entry.keys() and entry['user_id']:
            exam_data['user_id'] = str(entry['user_id'])
        
        # Create document
        db.collection(EXAM_PRACTICE_COLLECTION).document().set(exam_data)
        migrated_count += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_count} exam practice entries")
    return migrated_count

def migrate_generated_pdfs():
    """Migrate generated PDFs data from SQLite to Firestore."""
    print("Migrating generated PDFs data...")
    
    db = init_firestore()
    conn = sqlite3.connect(USER_DATABASE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all PDFs from generated_pdfs table
    cursor.execute("SELECT * FROM generated_pdfs")
    pdfs = cursor.fetchall()
    
    migrated_count = 0
    for pdf in pdfs:
        # Convert data to dict
        pdf_data = {
            'user_id': str(pdf['user_id']),
            'topic_code': pdf.get('topic_code', ''),
            'title': pdf.get('title', 'Generated PDF'),
            'latex_content': pdf.get('latex_content', ''),
            'pdf_path': pdf.get('pdf_path', ''),
            'created_at': pdf.get('created_at', datetime.now().isoformat())
        }
        
        # Create document
        db.collection(GENERATED_PDFS_COLLECTION).document().set(pdf_data)
        migrated_count += 1
    
    # Also migrate legacy PDFs from latex_pdfs table
    cursor.execute("SELECT * FROM latex_pdfs")
    legacy_pdfs = cursor.fetchall()
    
    for pdf in legacy_pdfs:
        # Convert filename to pdf_path
        filename = pdf.get('filename', '')
        pdf_path = f"temp_latex/{filename.replace('.tex', '.pdf')}" if filename else ''
        
        pdf_data = {
            'user_id': str(pdf['user_id']),
            'topic_code': pdf.get('topic_code', ''),
            'topic_title': pdf.get('topic_title', 'Legacy PDF'),
            'filename': filename,
            'pdf_path': pdf_path,
            'created_at': pdf.get('created_at', datetime.now().isoformat())
        }
        
        # Create document in legacy collection
        db.collection('latex_pdfs').document().set(pdf_data)
        migrated_count += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_count} PDF entries")
    return migrated_count

def migrate_user_activity():
    """Migrate user activity data from SQLite to Firestore."""
    print("Migrating user activity data...")
    
    db = init_firestore()
    conn = sqlite3.connect(USER_DATABASE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all activity entries
    cursor.execute("SELECT * FROM user_activity")
    activity_entries = cursor.fetchall()
    
    migrated_count = 0
    for entry in activity_entries:
        # Convert data to dict
        user_id = str(entry['user_id'])
        activity_date = entry['activity_date']
        
        activity_data = {
            'user_id': user_id,
            'activity_date': activity_date,
            'activity_type': entry.get('activity_type', 'page_view'),
            'session_duration': entry.get('session_duration', 0),
            'created_at': entry.get('created_at', datetime.now().isoformat()),
            'last_updated': entry.get('last_updated', datetime.now().isoformat())
        }
        
        # Create document ID combining user_id and date
        doc_id = f"{user_id}_{activity_date}"
        
        # Create document
        db.collection(USER_ACTIVITY_COLLECTION).document(doc_id).set(activity_data)
        migrated_count += 1
    
    conn.close()
    print(f"Successfully migrated {migrated_count} user activity entries")
    return migrated_count

def migrate_all_data():
    """Migrate all data from SQLite to Firestore."""
    print("Starting full data migration...")
    
    # Check if SQLite databases exist
    if not os.path.exists(USER_DATABASE_DB):
        print(f"Error: {USER_DATABASE_DB} not found")
        return False
        
    if not os.path.exists(OCR_CS_TUTOR_DB):
        print(f"Error: {OCR_CS_TUTOR_DB} not found")
        return False
    
    # Migrate in the appropriate order
    users_count = migrate_users()
    sessions_count, messages_count = migrate_sessions()
    topic_progress_count = migrate_topic_progress()
    exam_practice_count = migrate_exam_practice()
    pdfs_count = migrate_generated_pdfs()
    activity_count = migrate_user_activity()
    
    print("\nMigration Summary:")
    print(f"- {users_count} users migrated")
    print(f"- {sessions_count} sessions with {messages_count} messages migrated")
    print(f"- {topic_progress_count} topic progress entries migrated")
    print(f"- {exam_practice_count} exam practice entries migrated")
    print(f"- {pdfs_count} PDF entries migrated")
    print(f"- {activity_count} user activity entries migrated")
    print("\nData migration completed successfully")
    
    return True

def verify_migration():
    """Verify that data was migrated correctly."""
    print("\nVerifying migration...")
    
    db = init_firestore()
    
    # Check counts in Firestore collections
    users = db.collection(USERS_COLLECTION).get()
    sessions = db.collection(SESSIONS_COLLECTION).get()
    topic_progress = db.collection(TOPIC_PROGRESS_COLLECTION).get()
    exam_practice = db.collection(EXAM_PRACTICE_COLLECTION).get()
    generated_pdfs = db.collection(GENERATED_PDFS_COLLECTION).get()
    latex_pdfs = db.collection('latex_pdfs').get()
    user_activity = db.collection(USER_ACTIVITY_COLLECTION).get()
    
    print("\nFirestore Collection Counts:")
    print(f"- {len(users)} users")
    print(f"- {len(sessions)} sessions")
    print(f"- {len(topic_progress)} topic progress entries")
    print(f"- {len(exam_practice)} exam practice entries")
    print(f"- {len(generated_pdfs)} generated PDFs")
    print(f"- {len(latex_pdfs)} legacy PDFs")
    print(f"- {len(user_activity)} user activity entries")
    
    # Compare with SQLite counts
    print("\nComparing with SQLite counts...")
    
    # Users
    conn_user = sqlite3.connect(USER_DATABASE_DB)
    cursor_user = conn_user.cursor()
    cursor_user.execute("SELECT COUNT(*) FROM users")
    sqlite_users_count = cursor_user.fetchone()[0]
    print(f"- Users: Firestore={len(users)}, SQLite={sqlite_users_count}")
    
    # Sessions
    conn_sessions = sqlite3.connect(OCR_CS_TUTOR_DB)
    cursor_sessions = conn_sessions.cursor()
    cursor_sessions.execute("SELECT COUNT(*) FROM sessions")
    sqlite_sessions_count = cursor_sessions.fetchone()[0]
    print(f"- Sessions: Firestore={len(sessions)}, SQLite={sqlite_sessions_count}")
    
    # Topic Progress
    cursor_sessions.execute("SELECT COUNT(*) FROM topic_progress")
    sqlite_topic_count = cursor_sessions.fetchone()[0]
    print(f"- Topic Progress: Firestore={len(topic_progress)}, SQLite={sqlite_topic_count}")
    
    # Exam Practice
    cursor_sessions.execute("SELECT COUNT(*) FROM exam_practice")
    sqlite_exam_count = cursor_sessions.fetchone()[0]
    print(f"- Exam Practice: Firestore={len(exam_practice)}, SQLite={sqlite_exam_count}")
    
    # Generated PDFs
    cursor_user.execute("SELECT COUNT(*) FROM generated_pdfs")
    sqlite_pdf_count = cursor_user.fetchone()[0]
    
    # Legacy PDFs
    cursor_user.execute("SELECT COUNT(*) FROM latex_pdfs")
    sqlite_legacy_pdf_count = cursor_user.fetchone()[0]
    print(f"- PDFs: Firestore={len(generated_pdfs) + len(latex_pdfs)}, SQLite={sqlite_pdf_count + sqlite_legacy_pdf_count}")
    
    # User Activity
    cursor_user.execute("SELECT COUNT(*) FROM user_activity")
    sqlite_activity_count = cursor_user.fetchone()[0]
    print(f"- User Activity: Firestore={len(user_activity)}, SQLite={sqlite_activity_count}")
    
    conn_user.close()
    conn_sessions.close()
    
    print("\nVerification complete")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate SQLite data to Firestore')
    parser.add_argument('--verify-only', action='store_true', help='Only verify migration without migrating data')
    parser.add_argument('--migrate-only', action='store_true', help='Only migrate data without verification')
    
    args = parser.parse_args()
    
    if args.verify_only:
        verify_migration()
    elif args.migrate_only:
        migrate_all_data()
    else:
        # Default: migrate and verify
        if migrate_all_data():
            verify_migration()

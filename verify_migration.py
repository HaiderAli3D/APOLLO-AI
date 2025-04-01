"""
Firestore Migration Verification Script

This script compares the data between SQLite and Firestore to verify the integrity
of the migration. It performs both quantitative (count) and qualitative (content)
checks to ensure data was migrated correctly.
"""

import os
import sqlite3
import json
import random
import argparse
from datetime import datetime
from prettytable import PrettyTable
from colorama import init, Fore, Style
import firebase_admin
from firebase_admin import credentials, firestore

# SQLite database paths
OCR_CS_TUTOR_DB = 'ocr_cs_tutor.db'
USER_DATABASE_DB = 'user_database.db'
KNOWLEDGE_BASE_DB = 'knowledge_base.db'

# Initialize colorama for colored output
init()

# Firestore collection names
USERS_COLLECTION = 'users'
SESSIONS_COLLECTION = 'sessions'
MESSAGES_COLLECTION = 'messages'
TOPIC_PROGRESS_COLLECTION = 'topic_progress'
EXAM_PRACTICE_COLLECTION = 'exam_practice'
GENERATED_PDFS_COLLECTION = 'generated_pdfs'
USER_ACTIVITY_COLLECTION = 'user_activity'

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

def check_databases_exist():
    """Check if required SQLite databases exist."""
    missing_dbs = []
    
    if not os.path.exists(OCR_CS_TUTOR_DB):
        missing_dbs.append(OCR_CS_TUTOR_DB)
    
    if not os.path.exists(USER_DATABASE_DB):
        missing_dbs.append(USER_DATABASE_DB)
    
    return missing_dbs

def get_sqlite_table_count(db_path, table_name):
    """Get the number of records in a SQLite table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_firestore_collection_count(db, collection_name):
    """Get the number of documents in a Firestore collection."""
    try:
        collection_ref = db.collection(collection_name)
        return len(list(collection_ref.stream()))
    except Exception as e:
        print(f"Error getting count for {collection_name}: {e}")
        return 0

def get_session_messages_count(db):
    """Get the total count of all messages across all sessions."""
    sessions = db.collection(SESSIONS_COLLECTION).stream()
    total_messages = 0
    
    for session in sessions:
        messages = session.reference.collection(MESSAGES_COLLECTION).stream()
        message_count = len(list(messages))
        total_messages += message_count
    
    return total_messages

def compare_record_counts(verbose=False):
    """Compare record counts between SQLite and Firestore."""
    print(f"\n{Fore.CYAN}Comparing record counts between SQLite and Firestore...{Style.RESET_ALL}")
    
    db = init_firestore()
    
    # Create a pretty table for results
    table = PrettyTable()
    table.field_names = ["Collection/Table", "SQLite Count", "Firestore Count", "Match", "Difference"]
    table.align = "l"
    
    # Users
    sqlite_users_count = get_sqlite_table_count(USER_DATABASE_DB, "users")
    firestore_users_count = get_firestore_collection_count(db, USERS_COLLECTION)
    users_match = sqlite_users_count == firestore_users_count
    users_diff = firestore_users_count - sqlite_users_count
    
    table.add_row([
        "Users", 
        sqlite_users_count, 
        firestore_users_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if users_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        users_diff
    ])
    
    # Sessions
    sqlite_sessions_count = get_sqlite_table_count(OCR_CS_TUTOR_DB, "sessions")
    firestore_sessions_count = get_firestore_collection_count(db, SESSIONS_COLLECTION)
    sessions_match = sqlite_sessions_count == firestore_sessions_count
    sessions_diff = firestore_sessions_count - sqlite_sessions_count
    
    table.add_row([
        "Sessions", 
        sqlite_sessions_count, 
        firestore_sessions_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if sessions_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        sessions_diff
    ])
    
    # Messages
    sqlite_messages_count = get_sqlite_table_count(OCR_CS_TUTOR_DB, "conversation_history")
    firestore_messages_count = get_session_messages_count(db)
    messages_match = sqlite_messages_count == firestore_messages_count
    messages_diff = firestore_messages_count - sqlite_messages_count
    
    table.add_row([
        "Messages", 
        sqlite_messages_count, 
        firestore_messages_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if messages_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        messages_diff
    ])
    
    # Topic Progress
    sqlite_topic_progress_count = get_sqlite_table_count(OCR_CS_TUTOR_DB, "topic_progress")
    firestore_topic_progress_count = get_firestore_collection_count(db, TOPIC_PROGRESS_COLLECTION)
    topic_progress_match = sqlite_topic_progress_count == firestore_topic_progress_count
    topic_progress_diff = firestore_topic_progress_count - sqlite_topic_progress_count
    
    table.add_row([
        "Topic Progress", 
        sqlite_topic_progress_count, 
        firestore_topic_progress_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if topic_progress_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        topic_progress_diff
    ])
    
    # Exam Practice
    sqlite_exam_practice_count = get_sqlite_table_count(OCR_CS_TUTOR_DB, "exam_practice")
    firestore_exam_practice_count = get_firestore_collection_count(db, EXAM_PRACTICE_COLLECTION)
    exam_practice_match = sqlite_exam_practice_count == firestore_exam_practice_count
    exam_practice_diff = firestore_exam_practice_count - sqlite_exam_practice_count
    
    table.add_row([
        "Exam Practice", 
        sqlite_exam_practice_count, 
        firestore_exam_practice_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if exam_practice_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        exam_practice_diff
    ])
    
    # Generated PDFs
    sqlite_generated_pdfs_count = get_sqlite_table_count(USER_DATABASE_DB, "generated_pdfs")
    firestore_generated_pdfs_count = get_firestore_collection_count(db, GENERATED_PDFS_COLLECTION)
    generated_pdfs_match = sqlite_generated_pdfs_count == firestore_generated_pdfs_count
    generated_pdfs_diff = firestore_generated_pdfs_count - sqlite_generated_pdfs_count
    
    table.add_row([
        "Generated PDFs", 
        sqlite_generated_pdfs_count, 
        firestore_generated_pdfs_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if generated_pdfs_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        generated_pdfs_diff
    ])
    
    # Legacy PDFs
    sqlite_legacy_pdfs_count = get_sqlite_table_count(USER_DATABASE_DB, "latex_pdfs")
    firestore_legacy_pdfs_count = get_firestore_collection_count(db, "latex_pdfs")
    legacy_pdfs_match = sqlite_legacy_pdfs_count == firestore_legacy_pdfs_count
    legacy_pdfs_diff = firestore_legacy_pdfs_count - sqlite_legacy_pdfs_count
    
    table.add_row([
        "Legacy PDFs", 
        sqlite_legacy_pdfs_count, 
        firestore_legacy_pdfs_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if legacy_pdfs_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        legacy_pdfs_diff
    ])
    
    # User Activity
    sqlite_user_activity_count = get_sqlite_table_count(USER_DATABASE_DB, "user_activity")
    firestore_user_activity_count = get_firestore_collection_count(db, USER_ACTIVITY_COLLECTION)
    user_activity_match = sqlite_user_activity_count == firestore_user_activity_count
    user_activity_diff = firestore_user_activity_count - sqlite_user_activity_count
    
    table.add_row([
        "User Activity", 
        sqlite_user_activity_count, 
        firestore_user_activity_count,
        f"{Fore.GREEN}✓{Style.RESET_ALL}" if user_activity_match else f"{Fore.RED}✗{Style.RESET_ALL}",
        user_activity_diff
    ])
    
    print(table)
    
    # Calculate overall match percentage
    total_sqlite = (sqlite_users_count + sqlite_sessions_count + sqlite_messages_count +
                  sqlite_topic_progress_count + sqlite_exam_practice_count +
                  sqlite_generated_pdfs_count + sqlite_legacy_pdfs_count +
                  sqlite_user_activity_count)
    
    total_firestore = (firestore_users_count + firestore_sessions_count + firestore_messages_count +
                     firestore_topic_progress_count + firestore_exam_practice_count +
                     firestore_generated_pdfs_count + firestore_legacy_pdfs_count +
                     firestore_user_activity_count)
    
    if total_sqlite > 0:
        match_percentage = (total_firestore / total_sqlite) * 100
        print(f"\nOverall Match: {match_percentage:.2f}%")
    else:
        print(f"\nNo SQLite records found to compare against.")
    
    # Return True if all counts match
    return (users_match and sessions_match and messages_match and 
            topic_progress_match and exam_practice_match and 
            generated_pdfs_match and legacy_pdfs_match and user_activity_match)

def get_sqlite_sample(db_path, table_name, sample_size=5):
    """Get a random sample of records from a SQLite table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get total count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_count = cursor.fetchone()[0]
    
    # Adjust sample size if needed
    sample_size = min(sample_size, total_count)
    
    if sample_size == 0:
        return []
    
    # Get list of all IDs
    cursor.execute(f"SELECT id FROM {table_name}")
    all_ids = [row['id'] for row in cursor.fetchall()]
    
    # Select random IDs
    sample_ids = random.sample(all_ids, sample_size) if all_ids else []
    
    # Get sample records
    sample = []
    for id_val in sample_ids:
        cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (id_val,))
        row = cursor.fetchone()
        if row:
            sample.append(dict(row))
    
    conn.close()
    return sample

def get_firestore_sample(db, collection_name, sample_size=5):
    """Get a random sample of documents from a Firestore collection."""
    try:
        collection_ref = db.collection(collection_name)
        all_docs = list(collection_ref.stream())
        
        # Adjust sample size if needed
        sample_size = min(sample_size, len(all_docs))
        
        if sample_size == 0:
            return []
        
        # Select random documents
        sample_docs = random.sample(all_docs, sample_size) if all_docs else []
        
        # Convert to dictionaries with ID included
        sample = []
        for doc in sample_docs:
            data = doc.to_dict()
            data['id'] = doc.id
            sample.append(data)
        
        return sample
    except Exception as e:
        print(f"Error getting sample for {collection_name}: {e}")
        return []

def get_sqlite_message_sample(db_path, session_id):
    """Get messages for a specific session from SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM conversation_history WHERE session_id = ? ORDER BY timestamp",
        (session_id,)
    )
    
    messages = []
    for row in cursor.fetchall():
        messages.append(dict(row))
    
    conn.close()
    return messages

def get_firestore_message_sample(db, session_id):
    """Get messages for a specific session from Firestore."""
    try:
        messages_ref = db.collection(SESSIONS_COLLECTION).document(str(session_id)).collection(MESSAGES_COLLECTION)
        messages = list(messages_ref.order_by('timestamp').stream())
        
        # Convert to dictionaries with ID included
        sample = []
        for doc in messages:
            data = doc.to_dict()
            data['id'] = doc.id
            sample.append(data)
        
        return sample
    except Exception as e:
        print(f"Error getting messages for session {session_id}: {e}")
        return []

def compare_record_content(verbose=False):
    """Compare the content of records between SQLite and Firestore."""
    print(f"\n{Fore.CYAN}Comparing record content between SQLite and Firestore...{Style.RESET_ALL}")
    
    db = init_firestore()
    
    # Create a table for results
    table = PrettyTable()
    table.field_names = ["Collection/Table", "Sample Size", "Fields Compared", "Match Percentage", "Status"]
    table.align = "l"
    
    sample_size = 5  # Number of records to compare for each table
    
    # Users
    print(f"\nComparing users...")
    sqlite_users = get_sqlite_sample(USER_DATABASE_DB, "users", sample_size)
    firestore_users = get_firestore_sample(db, USERS_COLLECTION, len(sqlite_users))
    
    # Create a dictionary of Firestore users by ID for easy lookup
    firestore_users_dict = {user['id']: user for user in firestore_users}
    
    user_match_count = 0
    user_total_fields = 0
    user_matched_fields = 0
    
    for sqlite_user in sqlite_users:
        if str(sqlite_user['id']) in firestore_users_dict:
            firestore_user = firestore_users_dict[str(sqlite_user['id'])]
            
            # Compare important fields
            fields_to_compare = ['email', 'full_name', 'role']
            field_matches = 0
            
            for field in fields_to_compare:
                if field in sqlite_user and field in firestore_user:
                    if sqlite_user[field] == firestore_user[field]:
                        field_matches += 1
                        user_matched_fields += 1
                    elif verbose:
                        print(f"  Mismatch in user {sqlite_user['id']} field {field}: {sqlite_user[field]} vs {firestore_user[field]}")
                
                user_total_fields += 1
            
            if field_matches == len(fields_to_compare):
                user_match_count += 1
    
    user_match_percentage = (user_matched_fields / user_total_fields * 100) if user_total_fields > 0 else 0
    user_status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if user_match_percentage >= 90 else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    
    table.add_row([
        "Users", 
        len(sqlite_users), 
        user_total_fields,
        f"{user_match_percentage:.2f}%",
        user_status
    ])
    
    # Sessions
    print(f"\nComparing sessions...")
    sqlite_sessions = get_sqlite_sample(OCR_CS_TUTOR_DB, "sessions", sample_size)
    firestore_sessions = get_firestore_sample(db, SESSIONS_COLLECTION, len(sqlite_sessions))
    
    # Create a dictionary of Firestore sessions by ID for easy lookup
    firestore_sessions_dict = {session['id']: session for session in firestore_sessions}
    
    session_match_count = 0
    session_total_fields = 0
    session_matched_fields = 0
    
    for sqlite_session in sqlite_sessions:
        if str(sqlite_session['id']) in firestore_sessions_dict:
            firestore_session = firestore_sessions_dict[str(sqlite_session['id'])]
            
            # Check user_id field
            if 'user_id' in sqlite_session and 'user_id' in firestore_session:
                # Convert to string for comparison (Firestore uses string IDs)
                sqlite_user_id = str(sqlite_session['user_id']) if sqlite_session['user_id'] is not None else None
                firestore_user_id = firestore_session['user_id']
                
                if sqlite_user_id == firestore_user_id:
                    session_matched_fields += 1
                elif verbose:
                    print(f"  Mismatch in session {sqlite_session['id']} field user_id: {sqlite_user_id} vs {firestore_user_id}")
                
                session_total_fields += 1
            
            # Also compare a random sample of messages for this session
            sqlite_messages = get_sqlite_message_sample(OCR_CS_TUTOR_DB, sqlite_session['id'])
            firestore_messages = get_firestore_message_sample(db, sqlite_session['id'])
            
            # Sort by timestamp for comparison
            sqlite_messages.sort(key=lambda x: x.get('timestamp', ''))
            firestore_messages.sort(key=lambda x: x.get('timestamp', ''))
            
            # Compare message content and roles
            for i in range(min(len(sqlite_messages), len(firestore_messages))):
                sqlite_msg = sqlite_messages[i]
                firestore_msg = firestore_messages[i]
                
                # Compare role
                if sqlite_msg.get('role') == firestore_msg.get('role'):
                    session_matched_fields += 1
                elif verbose:
                    print(f"  Mismatch in message role for session {sqlite_session['id']}")
                
                session_total_fields += 1
                
                # Compare content (allowing for minor differences in whitespace)
                sqlite_content = sqlite_msg.get('content', '').strip()
                firestore_content = firestore_msg.get('content', '').strip()
                
                if sqlite_content == firestore_content:
                    session_matched_fields += 1
                elif verbose:
                    print(f"  Mismatch in message content for session {sqlite_session['id']}")
                
                session_total_fields += 1
    
    session_match_percentage = (session_matched_fields / session_total_fields * 100) if session_total_fields > 0 else 0
    session_status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if session_match_percentage >= 90 else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    
    table.add_row([
        "Sessions & Messages", 
        len(sqlite_sessions), 
        session_total_fields,
        f"{session_match_percentage:.2f}%",
        session_status
    ])
    
    # Topic Progress
    print(f"\nComparing topic progress...")
    sqlite_topics = get_sqlite_sample(OCR_CS_TUTOR_DB, "topic_progress", sample_size)
    
    topic_match_count = 0
    topic_total_fields = 0
    topic_matched_fields = 0
    
    # For topic progress, we need to construct the document ID to look up in Firestore
    for sqlite_topic in sqlite_topics:
        topic_code = sqlite_topic.get('topic_code')
        user_id = str(sqlite_topic.get('user_id')) if 'user_id' in sqlite_topic else None
        
        # Construct Firestore document ID
        doc_id = f"{user_id}_{topic_code}" if user_id else topic_code
        
        # Get the Firestore document
        firestore_topic_doc = db.collection(TOPIC_PROGRESS_COLLECTION).document(doc_id).get()
        
        if firestore_topic_doc.exists:
            firestore_topic = firestore_topic_doc.to_dict()
            
            # Compare important fields
            fields_to_compare = ['topic_code', 'topic_title', 'proficiency']
            field_matches = 0
            
            for field in fields_to_compare:
                sqlite_field_name = field
                firestore_field_name = field
                
                # Rename fields to match Firestore schema (if needed)
                if field == 'proficiency':
                    sqlite_field_name = 'proficiency'
                    
                if sqlite_field_name in sqlite_topic and firestore_field_name in firestore_topic:
                    if str(sqlite_topic[sqlite_field_name]) == str(firestore_topic[firestore_field_name]):
                        field_matches += 1
                        topic_matched_fields += 1
                    elif verbose:
                        print(f"  Mismatch in topic {topic_code} field {field}: {sqlite_topic[sqlite_field_name]} vs {firestore_topic[firestore_field_name]}")
                
                topic_total_fields += 1
            
            if field_matches == len(fields_to_compare):
                topic_match_count += 1
    
    topic_match_percentage = (topic_matched_fields / topic_total_fields * 100) if topic_total_fields > 0 else 0
    topic_status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if topic_match_percentage >= 90 else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    
    table.add_row([
        "Topic Progress", 
        len(sqlite_topics), 
        topic_total_fields,
        f"{topic_match_percentage:.2f}%",
        topic_status
    ])
    
    # Exam Practice
    print(f"\nComparing exam practice...")
    sqlite_exams = get_sqlite_sample(OCR_CS_TUTOR_DB, "exam_practice", sample_size)
    firestore_exams = get_firestore_sample(db, EXAM_PRACTICE_COLLECTION, len(sqlite_exams) * 2)  # Get more to increase chance of finding matches
    
    exam_match_count = 0
    exam_total_fields = 0
    exam_matched_fields = 0
    
    for sqlite_exam in sqlite_exams:
        # Try to find a matching exam in Firestore by topic_code and score
        matching_firestore_exams = [
            exam for exam in firestore_exams 
            if exam.get('topic_code') == sqlite_exam.get('topic_code') and 
               str(exam.get('score')) == str(sqlite_exam.get('score'))
        ]
        
        if matching_firestore_exams:
            # Use the first match
            firestore_exam = matching_firestore_exams[0]
            
            # Compare important fields
            fields_to_compare = ['topic_code', 'score', 'max_score']
            field_matches = 0
            
            for field in fields_to_compare:
                if field in sqlite_exam and field in firestore_exam:
                    if str(sqlite_exam[field]) == str(firestore_exam[field]):
                        field_matches += 1
                        exam_matched_fields += 1
                    elif verbose:
                        print(f"  Mismatch in exam practice field {field}: {sqlite_exam[field]} vs {firestore_exam[field]}")
                
                exam_total_fields += 1
            
            if field_matches == len(fields_to_compare):
                exam_match_count += 1
    
    exam_match_percentage = (exam_matched_fields / exam_total_fields * 100) if exam_total_fields > 0 else 0
    exam_status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if exam_match_percentage >= 90 else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    
    table.add_row([
        "Exam Practice", 
        len(sqlite_exams), 
        exam_total_fields,
        f"{exam_match_percentage:.2f}%",
        exam_status
    ])
    
    # Generated PDFs
    print(f"\nComparing generated PDFs...")
    sqlite_pdfs = get_sqlite_sample(USER_DATABASE_DB, "generated_pdfs", sample_size)
    firestore_pdfs = get_firestore_sample(db, GENERATED_PDFS_COLLECTION, len(sqlite_pdfs) * 2)  # Get more to increase chance of finding matches
    
    pdf_match_count = 0
    pdf_total_fields = 0
    pdf_matched_fields = 0
    
    for sqlite_pdf in sqlite_pdfs:
        # Try to find a matching PDF in Firestore by user_id and title
        matching_firestore_pdfs = [
            pdf for pdf in firestore_pdfs 
            if str(pdf.get('user_id')) == str(sqlite_pdf.get('user_id')) and 
               pdf.get('title') == sqlite_pdf.get('title')
        ]
        
        if matching_firestore_pdfs:
            # Use the first match
            firestore_pdf = matching_firestore_pdfs[0]
            
            # Compare important fields
            fields_to_compare = ['user_id', 'title', 'pdf_path']
            field_matches = 0
            
            for field in fields_to_compare:
                if field in sqlite_pdf and field in firestore_pdf:
                    sqlite_value = str(sqlite_pdf[field]) if sqlite_pdf[field] is not None else None
                    firestore_value = str(firestore_pdf[field]) if firestore_pdf[field] is not None else None
                    
                    if sqlite_value == firestore_value:
                        field_matches += 1
                        pdf_matched_fields += 1
                    elif verbose:
                        print(f"  Mismatch in PDF field {field}: {sqlite_value} vs {firestore_value}")
                
                pdf_total_fields += 1
            
            if field_matches == len(fields_to_compare):
                pdf_match_count += 1
    
    pdf_match_percentage = (pdf_matched_fields / pdf_total_fields * 100) if pdf_total_fields > 0 else 0
    pdf_status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if pdf_match_percentage >= 90 else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    
    table.add_row([
        "Generated PDFs", 
        len(sqlite_pdfs), 
        pdf_total_fields,
        f"{pdf_match_percentage:.2f}%",
        pdf_status
    ])
    
    print(table)
    
    # Calculate overall match percentage
    total_fields = user_total_fields + session_total_fields + topic_total_fields + exam_total_fields + pdf_total_fields
    matched_fields = user_matched_fields + session_matched_fields + topic_matched_fields + exam_matched_fields + pdf_matched_fields
    
    if total_fields > 0:
        overall_match_percentage = (matched_fields / total_fields) * 100
        overall_status = "PASS" if overall_match_percentage >= 90 else "FAIL"
        print(f"\nOverall Field Match Rate: {overall_match_percentage:.2f}% - {Fore.GREEN if overall_status == 'PASS' else Fore.RED}{overall_status}{Style.RESET_ALL}")
    else:
        print(f"\nNo fields were compared.")
    
    # Return True if all percentages are >= 90%
    return (user_match_percentage >= 90 and session_match_percentage >= 90 and 
            topic_match_percentage >= 90 and exam_match_percentage >= 90 and 
            pdf_match_percentage >= 90)

def generate_verification_report(count_result, content_result):
    """Generate a verification report."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_file = f"verification_report_{timestamp}.txt"
    
    with open(report_file, "w") as f:
        f.write("================================================\n")
        f.write("          FIRESTORE MIGRATION VERIFICATION      \n")
        f.write("================================================\n\n")
        f.write(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("VERIFICATION SUMMARY:\n")
        f.write("-------------------\n")
        f.write(f"Record Count Verification: {'PASSED' if count_result else 'FAILED'}\n")
        f.write(f"Content Verification: {'PASSED' if content_result else 'FAILED'}\n")
        f.write(f"Overall Verification: {'PASSED' if count_result and content_result else 'FAILED'}\n\n")
        
        f.write("RECOMMENDATIONS:\n")
        f.write("---------------\n")
        
        if count_result and content_result:
            f.write("✓ Migration appears successful and data integrity is maintained.\n")
            f.write("✓ Proceed with switching to the Firestore implementation.\n")
        else:
            if not count_result:
                f.write("✗ Record count verification failed. This suggests some data was not migrated.\n")
                f.write("  - Run 'python migrate_to_firestore.py' again to attempt re-migration.\n")
                f.write("  - Check Firestore security rules to ensure write access is permitted.\n")
            
            if not content_result:
                f.write("✗ Content verification failed. This suggests data may have been corrupted during migration.\n")
                f.write("  - Run a detailed comparison with the '--verbose' flag to identify specific mismatches.\n")
                f.write("  - Consider modifying 'migrate_to_firestore.py' to address specific field mapping issues.\n")
            
            f.write("\n✗ Please address these issues before proceeding with the switch to Firestore.\n")
    
    print(f"\nVerification report generated: {report_file}")
    return report_file

def main():
    """Main function to run the verification script."""
    parser = argparse.ArgumentParser(description='Verify Firestore migration integrity')
    parser.add_argument('--verbose', action='store_true', help='Show detailed comparison information')
    parser.add_argument('--report', action='store_true', help='Generate a detailed verification report')
    parser.add_argument('--counts-only', action='store_true', help='Only verify record counts')
    parser.add_argument('--content-only', action='store_true', help='Only verify record content')
    
    args = parser.parse_args()
    
    # Check if SQLite databases exist
    missing_dbs = check_databases_exist()
    if missing_dbs:
        print(f"{Fore.RED}Error: The following SQLite databases are missing:{Style.RESET_ALL}")
        for db in missing_dbs:
            print(f"  - {db}")
        print("Verification cannot proceed without the original SQLite databases.")
        return 1
    
    # Run verification
    count_result = True
    content_result = True
    
    if not args.content_only:
        count_result = compare_record_counts(args.verbose)
    
    if not args.counts_only:
        content_result = compare_record_content(args.verbose)
    
    # Generate report if requested
    if args.report:
        generate_verification_report(count_result, content_result)
    
    # Return success if both verifications pass
    return 0 if count_result and content_result else 1

if __name__ == "__main__":
    exit(main())

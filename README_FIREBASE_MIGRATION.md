# SQLite to Firebase Firestore Migration Guide

This guide documents the process of migrating the OCR A-Level Computer Science AI Tutor application from SQLite to Firebase Firestore for data storage, creating a fully cloud-based architecture integrated with the existing Firebase Authentication.

## Table of Contents

1. [Migration Overview](#migration-overview)
2. [Firebase Architecture](#firebase-architecture)
3. [Data Migration Process](#data-migration-process)
4. [Running the Migration](#running-the-migration)
5. [Code Changes](#code-changes)
6. [Security Considerations](#security-considerations)
7. [Performance Optimization](#performance-optimization)
8. [Maintenance and Monitoring](#maintenance-and-monitoring)
9. [Future Enhancements](#future-enhancements)

## Migration Overview

### Why Migrate to Firebase?

The application has been using Firebase Authentication but SQLite for data storage, which creates a hybrid architecture with some limitations:

- **Architecture Consistency**: Unifying authentication and data storage in a single platform
- **Real-time Capabilities**: Leveraging Firebase's real-time database features for chat functionality
- **Cloud Storage**: Eliminating server management and enabling easier scaling
- **Unified Security Model**: Integrating data access controls with authentication
- **Deployment Simplification**: Reducing deployment complexity with a cloud-based database

### Migration Goals

- Maintain all existing functionality during and after migration
- Ensure backward compatibility with existing data
- Implement a phased approach to minimize disruption
- Optimize database structure for Firestore's document model
- Enhance security using Firebase's security rules
- Leverage Firestore features for improved application capabilities

## Firebase Architecture

### Database Structure

The Firestore database is organized into collections that mirror the existing SQLite tables:

- **users**: User profiles and authentication data
  - Document ID: User ID (matches Firebase Auth UID where possible)
  - Fields: email, full_name, role, created_at, firebase_uid, etc.

- **sessions**: Learning sessions between users and AI
  - Document ID: Session ID
  - Fields: context, started_at, last_activity, user_id
  - Subcollection: messages

- **messages**: (Subcollection of sessions)
  - Document ID: Auto-generated
  - Fields: role, content, timestamp

- **topic_progress**: Tracking user understanding of topics
  - Document ID: user_id_topic_code
  - Fields: topic_code, topic_title, proficiency, notes, last_studied

- **exam_practice**: Storing practice test results
  - Document ID: Auto-generated
  - Fields: topic_code, question_type, difficulty, score, max_score, percentage, created_at, user_id

- **generated_pdfs**: References to generated PDF documents
  - Document ID: Auto-generated
  - Fields: user_id, topic_code, title, latex_content, pdf_path, created_at

- **user_activity**: User engagement and streak tracking
  - Document ID: user_id_date
  - Fields: user_id, activity_date, activity_type, session_duration, created_at

### Integration with Firebase Authentication

Firestore and Firebase Authentication are tightly integrated:
- Each user document is linked to a Firebase Authentication UID
- Security rules validate access based on authenticated user
- Token-based authentication is used throughout the application

## Data Migration Process

The migration process happens in several phases:

1. **Adapter Implementation**: Create a Firestore adapter that mimics the SQLite interface
2. **Database Structure Migration**: Design document collections mirroring SQL tables
3. **Data Migration**: Transfer existing data from SQLite to Firestore
4. **Code Adaptation**: Modify application code to use the Firestore adapter
5. **Testing**: Verify all functionality using the new database
6. **Deployment**: Roll out the Firestore-based application

### Data Mapping

| SQLite Table | Firestore Collection | ID Strategy | Notes |
|--------------|---------------------|-------------|-------|
| users | users | Same ID | Maintain same IDs for compatibility |
| sessions | sessions | Same ID | Messages become subcollection |
| conversation_history | sessions/{id}/messages | Auto-generated | Nested under parent session |
| topic_progress | topic_progress | user_id_topic_code | Composite ID for efficient queries |
| exam_practice | exam_practice | Auto-generated | Add user_id field |
| generated_pdfs | generated_pdfs | Auto-generated | Maintain same structure |
| latex_pdfs | latex_pdfs | Auto-generated | Legacy support only |
| user_activity | user_activity | user_id_date | Composite ID for date-based activities |

## Running the Migration

The migration is performed using the `migrate_to_firestore.py` script, which transfers data from the SQLite databases to Firestore collections.

### Prerequisites

- Firebase project with Firestore enabled
- Service account credentials (JSON file)
- Firebase Admin SDK configured
- Existing SQLite databases

### Migration Steps

1. Install required packages:
   ```
   pip install firebase-admin google-cloud-firestore
   ```

2. Ensure the Firebase service account key is in the project directory:
   ```
   apollo-auth-753b5-firebase-adminsdk-fbsvc-6b6d2904d5.json
   ```

3. Run the migration script:
   ```
   python migrate_to_firestore.py
   ```

   The script will:
   - Check for existing SQLite databases
   - Transfer all data to Firestore collections
   - Verify the migration was successful
   - Generate a migration report

4. Verify the migration with the `--verify-only` flag:
   ```
   python migrate_to_firestore.py --verify-only
   ```

### Migration Options

- `--migrate-only`: Only perform data migration without verification
- `--verify-only`: Only verify migration without transferring data

## Code Changes

The migration required several code changes:

1. **Firestore Adapter**: New `firestore_db_adapter.py` file providing SQLite-compatible functions

2. **Import Changes**: Updated imports to use the new adapter:
   ```python
   from firestore_db_adapter import (
       get_db, get_user_by_email, get_user_by_id, create_user, 
       get_or_create_firebase_user, add_pdf_to_database, add_pdf_to_generated_pdfs,
       track_activity, get_activity_data, calculate_user_streak,
       get_pdfs_for_user, delete_pdf
   )
   ```

3. **Schema Migrations**: Removed SQLite-specific schema migrations since Firestore is schemaless

4. **Security Context**: Updated security around database operations to use Firestore security rules

5. **Query Patterns**: Adjusted queries to work with Firestore's document-based model

6. **Error Handling**: Enhanced error handling for Firebase-specific exceptions

## Key Files

1. **migrate_to_firestore.py**
   - Script to migrate existing data from SQLite to Firestore
   - Handles migration of users, sessions, conversations, topic progress, etc.
   - Verifies data integrity between the original and migrated data
   - Provides command-line options for different migration scenarios

2. **firestore_db_adapter.py**
   - Adapter module that provides the same interface as the SQLite functions
   - Implements all required database operations using Firestore
   - Maintains compatibility with existing application code
   - Handles conversion between SQLite tuple format and Firestore documents

3. **app.py** (Modified)
   - Updated to use the Firestore adapter
   - Maintains the same external API and template rendering
   - Implements error handling for Firestore-specific exceptions
   - Seamlessly works with both old and new data formats

## Security Considerations

### Firestore Security Rules

Security in Firestore is implemented through security rules:

```
service cloud.firestore {
  match /databases/{database}/documents {
    // User profiles
    match /users/{userId} {
      allow read: if request.auth != null && (request.auth.uid == resource.data.firebase_uid || isAdmin());
      allow write: if request.auth != null && (request.auth.uid == resource.data.firebase_uid || isAdmin());
    }
    
    // Sessions
    match /sessions/{sessionId} {
      allow read: if request.auth != null && (resource.data.user_id == getUserDocId() || isAdmin());
      allow write: if request.auth != null;
      
      // Messages subcollection
      match /messages/{messageId} {
        allow read: if request.auth != null && (getSessionUserId() == getUserDocId() || isAdmin());
        allow write: if request.auth != null && (getSessionUserId() == getUserDocId() || isAdmin());
      }
    }
    
    // Topic progress
    match /topic_progress/{docId} {
      allow read: if request.auth != null && (docId.split('_')[0] == getUserDocId() || isAdmin());
      allow write: if request.auth != null && (docId.split('_')[0] == getUserDocId() || isAdmin());
    }
    
    // Exam practice 
    match /exam_practice/{docId} {
      allow read: if request.auth != null && (resource.data.user_id == getUserDocId() || isAdmin());
      allow write: if request.auth != null;
    }
    
    // Generated PDFs
    match /generated_pdfs/{docId} {
      allow read: if request.auth != null && (resource.data.user_id == getUserDocId() || isAdmin());
      allow write: if request.auth != null && (request.resource.data.user_id == getUserDocId() || isAdmin());
      allow delete: if request.auth != null && (resource.data.user_id == getUserDocId() || isAdmin());
    }
    
    // User activity
    match /user_activity/{docId} {
      allow read: if request.auth != null && (docId.split('_')[0] == getUserDocId() || isAdmin());
      allow write: if request.auth != null && (docId.split('_')[0] == getUserDocId() || isAdmin());
    }
    
    // Helper functions
    function isAdmin() {
      return get(/databases/$(database)/documents/users/$(getUserDocId())).data.role == 'admin' ||
             get(/databases/$(database)/documents/users/$(getUserDocId())).data.role == 'developer';
    }
    
    function getUserDocId() {
      return get(/databases/$(database)/documents/users).where('firebase_uid', '==', request.auth.uid).limit(1)[0].id;
    }
    
    function getSessionUserId() {
      return get(/databases/$(database)/documents/sessions/$(sessionId)).data.user_id;
    }
  }
}
```

### Authentication Integration

- Users continue to authenticate through Firebase Authentication
- Firestore security rules validate access based on the authenticated user
- Admin and developer roles have expanded access privileges
- Session ownership is enforced through security rules

## Performance Optimization

### Query Optimization

1. **Composite Document IDs**: Using composite IDs like `user_id_topic_code` to enable efficient filtering

2. **Denormalization**: Strategic data duplication to prevent excessive reads
   - Store relevant user information in session documents
   - Cache recent messages in session documents

3. **Pagination**: Implement pagination for large collections
   - Sessions and messages are particularly important to paginate
   - Implement cursor-based pagination using Firestore's `startAfter()` method

4. **Batch Operations**: Use batched writes for multiple operations
   - Use transactions for operations that need to be atomic
   - Consolidate reads and writes to minimize network round trips

### Caching Strategy

1. **Client-Side Caching**: Locally cache frequently accessed data
   - User profile information
   - Current session data
   - Recent topic progress

2. **Offline Persistence**: Enable Firestore offline persistence
   - Configure cache size based on expected data volume
   - Implement cache invalidation strategies

3. **Query Caching**: Cache query results that don't change often
   - Topic lists and resources
   - Historical progress data

### Cost Optimization

1. **Optimize Read/Write Operations**: Firestore charges per operation
   - Batch related operations where possible
   - Use listeners efficiently (detach when not needed)
   - Use local state management to reduce redundant reads

2. **Document Size**: Keep documents under 1MB
   - Store large content (like LaTeX content) efficiently
   - Consider storing very large data in Cloud Storage instead

3. **Index Management**: Only create necessary indexes
   - Remove unused indexes to reduce storage costs
   - Monitor index usage to identify optimization opportunities

## Maintenance and Monitoring

### Monitoring

1. **Firebase Console**: Regular checks of:
   - Authentication usage
   - Firestore read/write operations
   - Security rule evaluation failures
   - Query performance

2. **Error Tracking**:
   - Implement error logging for Firestore operations
   - Set up alerts for critical error patterns
   - Monitor client-side errors through Firebase Crashlytics

3. **Usage Metrics**:
   - Track daily active users
   - Monitor database operation volume
   - Set up cost thresholds and alerts

### Backups and Disaster Recovery

1. **Scheduled Exports**: Set up regular exports to Cloud Storage
   - Configure export frequency based on data change rate
   - Retain backups according to data retention policy

2. **Import Testing**: Regularly test import procedures
   - Validate backup integrity
   - Measure recovery time

3. **Rollback Procedures**: Document steps for:
   - Data recovery from exports
   - Reverting to SQLite if necessary
   - Handling partial data corruption

### Maintenance Tasks

1. **Index Optimization**: Periodically review and optimize indexes
   - Remove unused indexes
   - Add indexes for common queries

2. **Data Cleanup**: Implement policies for:
   - Archiving old sessions
   - Removing orphaned documents
   - Compressing historical data

3. **Version Migration**: Plan for future Firestore changes
   - Document version dependencies
   - Test new Firebase SDK versions before upgrading

## Future Enhancements

With Firestore in place, the application can now implement several enhancements:

1. **Real-time Features**:
   - Live collaboration between students and tutors
   - Real-time progress updates
   - Instant notifications for important events

2. **Offline Support**:
   - Enable users to study without internet connection
   - Automatically sync when connection is restored
   - Cache frequently used resources locally

3. **Advanced Analytics**:
   - Track user engagement patterns
   - Analyze topic difficulty based on student performance
   - Provide personalized learning recommendations

4. **Enhanced Security**:
   - Implement row-level security for shared resources
   - Add custom claims for fine-grained permissions
   - Enable multi-factor authentication for sensitive operations

5. **Scalability Improvements**:
   - Implement sharding for high-volume data
   - Use Cloud Functions for background processing
   - Integrate with other Firebase services (ML Kit, etc.)

## Conclusion

The migration from SQLite to Firebase Firestore represents a significant architectural improvement for the OCR A-Level Computer Science AI Tutor application. By unifying the authentication and data storage platforms, the application can now leverage the full benefits of cloud-based architecture, including real-time features, improved scalability, and simplified deployment.

The migration process was designed to minimize disruption while maximizing compatibility with existing code and data. By using an adapter pattern, most of the application logic remains unchanged, focused on the educational features rather than database implementation details.

With Firestore in place, the application is now well-positioned for future enhancements, including real-time collaboration, offline support, and advanced analytics. These capabilities will further enhance the learning experience for students and provide more powerful tools for educators.

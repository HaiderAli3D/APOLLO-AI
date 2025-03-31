#!/usr/bin/env python3
"""
Database Migration Script for Firebase Authentication

This script adds the firebase_uid column to the users table in user_database.db.
"""

import sqlite3
import os

def run_migration():
    """Add firebase_uid column to users table if it doesn't exist."""
    print("Running migration to add firebase_uid column...")
    
    # Connect to the database
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    try:
        # Check if firebase_uid column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'firebase_uid' not in column_names:
            print("Adding firebase_uid column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT")
            
            # Also add account_migrated column if it doesn't exist
            if 'account_migrated' not in column_names:
                print("Adding account_migrated column to users table...")
                cursor.execute("ALTER TABLE users ADD COLUMN account_migrated BOOLEAN DEFAULT 0")
                
            conn.commit()
            print("Migration successful!")
        else:
            print("firebase_uid column already exists. No changes needed.")
            
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    # Check if database exists
    if not os.path.exists('user_database.db'):
        print("Error: user_database.db not found!")
        exit(1)
        
    run_migration()
    print("Migration process completed.")

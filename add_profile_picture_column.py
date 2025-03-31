#!/usr/bin/env python3
"""
Database Migration Script to Add Profile Picture Support

This script adds the profile_picture_url column to the users table in user_database.db.
"""

import sqlite3
import os

def run_migration():
    """Add profile_picture_url column to users table if it doesn't exist."""
    print("Running migration to add profile_picture_url column...")
    
    # Connect to the database
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    try:
        # Check if profile_picture_url column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'profile_picture_url' not in column_names:
            print("Adding profile_picture_url column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN profile_picture_url TEXT")
            conn.commit()
            print("Migration successful!")
        else:
            print("profile_picture_url column already exists. No changes needed.")
            
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

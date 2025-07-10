#!/usr/bin/env python3
"""
Migration script to add status_message column to users table
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SQLITE_DATABASE_URL, engine
from sqlalchemy import create_engine, text


def run_migration():
    # Use the engine from database.py
    with engine.connect() as connection:
        # For SQLite, check if column exists by querying table info
        try:
            result = connection.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]  # Column names are in index 1
            
            if 'status_message' in columns:
                print("status_message column already exists, skipping migration")
                return
                
        except Exception as e:
            print(f"Error checking column existence: {e}")
            
        # Add the status_message column
        try:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN status_message VARCHAR(200) NULL
            """))
            connection.commit()
            print("Successfully added status_message column to users table")
            
        except Exception as e:
            print(f"Error adding status_message column: {e}")
            connection.rollback()
            raise

if __name__ == "__main__":
    run_migration()

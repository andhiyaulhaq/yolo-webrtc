import sqlite3
import datetime
import os

DB_NAME = "counts.sqlite"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables."""
    if not os.path.exists(DB_NAME):
        print(f"Creating new database: {DB_NAME}")
    else:
        print(f"Using existing database: {DB_NAME}")
        
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create table for crossings
    c.execute('''
        CREATE TABLE IF NOT EXISTS crossings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            direction TEXT NOT NULL,
            track_id INTEGER
        )
    ''')
    
    # Create table for alerts (optional, but good to have based on plan)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            current_count INTEGER,
            threshold INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

def log_crossing(direction, track_id):
    """Log a crossing event."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO crossings (direction, track_id) VALUES (?, ?)', (direction, track_id))
    conn.commit()
    conn.close()

def log_alert(current_count, threshold):
    """Log a threshold alert."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO alerts (current_count, threshold) VALUES (?, ?)', (current_count, threshold))
    conn.commit()
    conn.close()

def get_stats():
    """Get basic statistics (total in/out)."""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM crossings WHERE direction = 'in'")
    total_in = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM crossings WHERE direction = 'out'")
    total_out = c.fetchone()[0]
    
    conn.close()
    return {"total_in": total_in, "total_out": total_out}

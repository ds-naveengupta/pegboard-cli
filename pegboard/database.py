"""This module provides the Pegboard CLI database functionality."""
# pegboard/database.py

from pathlib import Path
from platformdirs import user_data_dir # type: ignore
import sqlite3

from pegboard import __app_name__

APP_NAME = __app_name__

def get_db_path() -> Path:
    # Get the standard data directory for the current OS
    data_dir = Path(user_data_dir(APP_NAME))
    
    # Create the folder if it doesn't exist
    data_dir.mkdir(parents=True, exist_ok=True)
    
    return data_dir / "app.db"

def get_connection():
    """
    Returns a new SQLite connection.
    Always call this instead of creating connections manually.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def create_schema() -> None:
    schema_sql = """
    -- Enable Foreign Key enforcement
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        gender TEXT NOT NULL CHECK(gender IN('M', 'F')),
        type TEXT NOT NULL CHECK(type IN('M', 'G')),
        timestamp TEXT,
        status TEXT NOT NULL DEFAULT 'A' CHECK(status IN('A', 'P', 'E')),
        UNIQUE(name, gender)
    );

    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_nr INTEGER NOT NULL,
        court_nr INTEGER NOT NULL CHECK(court_nr BETWEEN 1 AND 3),
        duration INTEGER NOT NULL,
        UNIQUE(game_nr, court_nr)
    );

    CREATE TABLE IF NOT EXISTS participations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        court_side TEXT NOT NULL CHECK(court_side IN ('Side A', 'Side B')),
        player_1 INTEGER NOT NULL REFERENCES players(id),
        player_2 INTEGER NOT NULL REFERENCES players(id),
        UNIQUE(game_id, court_side),
        -- Prevents a player from being paired with themselves
        CHECK(player_1 != player_2) 
    );
    """
    with get_connection() as conn:
        conn.executescript(schema_sql)
        conn.commit()
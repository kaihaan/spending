"""
File Manager MCP Component
Manages Excel files in the local data folder.
"""

import os
from pathlib import Path
import sqlite3

# Data folder location (configurable)
DATA_FOLDER = Path.home() / 'FinanceData'


def ensure_data_folder_exists():
    """Create data folder if it doesn't exist."""
    if not DATA_FOLDER.exists():
        DATA_FOLDER.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created data folder: {DATA_FOLDER}")
    return DATA_FOLDER


def list_excel_files():
    """
    List all Excel files in the data folder.
    Supports both .xls and .xlsx formats.

    Returns:
        List of file dictionaries with metadata
    """
    ensure_data_folder_exists()

    files = []

    # Find all Excel files (both .xls and .xlsx)
    for extension in ['*.xlsx', '*.xls']:
        for file_path in DATA_FOLDER.glob(extension):
            # Get file stats
            stat = file_path.stat()

            # Check if file has been imported
            imported = check_if_imported(file_path.name)

            files.append({
                'name': file_path.name,
                'size': stat.st_size,
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': stat.st_mtime,
                'modified_readable': format_timestamp(stat.st_mtime),
                'imported': imported,
                'path': str(file_path),
                'format': 'Excel 97-2003 (.xls)' if extension == '*.xls' else 'Excel (.xlsx)'
            })

    # Sort by modified date (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)

    return files


def check_if_imported(filename):
    """
    Check if a file has already been imported into the database.

    Args:
        filename: Name of the Excel file

    Returns:
        Boolean indicating if file has been imported
    """
    try:
        from database import get_db

        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                'SELECT COUNT(*) FROM transactions WHERE source_file = ?',
                (filename,)
            )
            count = c.fetchone()[0]
            return count > 0

    except Exception as e:
        print(f"Error checking import status: {e}")
        return False


def format_timestamp(timestamp):
    """
    Format Unix timestamp to readable date string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted date string (e.g., "2025-01-15 14:30")
    """
    from datetime import datetime
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M')


def get_file_path(filename):
    """
    Get full path to a file in the data folder.

    Args:
        filename: Name of the Excel file

    Returns:
        Full path to the file

    Raises:
        FileNotFoundError if file doesn't exist
    """
    file_path = DATA_FOLDER / filename

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    return file_path


def get_transaction_count(filename):
    """
    Get the number of transactions imported from a specific file.

    Args:
        filename: Name of the Excel file

    Returns:
        Number of transactions
    """
    try:
        from database import get_db

        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                'SELECT COUNT(*) FROM transactions WHERE source_file = ?',
                (filename,)
            )
            return c.fetchone()[0]

    except Exception as e:
        print(f"Error getting transaction count: {e}")
        return 0

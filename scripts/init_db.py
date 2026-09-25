"""
Run once to create all tables in elderly.db.
Safe to re-run — nothing is dropped.
"""

import sys
import os

# Allow this script to import from the parent folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db, DB_PATH


if __name__ == '__main__':
    init_db()
    print(f'Database initialized at: {DB_PATH}')
    print('Tables created (or already present): users, elderly_people, user_elderly_access, logs, devices, doctors, report_shares')
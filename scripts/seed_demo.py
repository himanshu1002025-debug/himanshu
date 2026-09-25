"""
Populate the database with demo data so the app is immediately usable.

Creates:
    - 2 users:       family/1234, sister/abcd
    - 2 elderly:     Kamla Devi, Ramesh Kumar
    - Access links:  family sees both, sister sees only Ramesh
    - 1 device:      demo-device-key-123 → Kamla Devi
    - 5 doctors
    - 30 days of logs for Kamla Devi (days 10 & 22 injected as anomalies)
    - 10 days of baseline-only logs for Ramesh Kumar

Safe to re-run — skips users/people/devices/doctors if they exist,
but does NOT skip logs (so re-running adds more log data).
"""

import sys
import os
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import query_one, query_all, execute, init_db


def random_between(lo, hi):
    return random.randint(lo, hi)


def ensure_user(username, password):
    existing = query_one('SELECT id FROM users WHERE username = ?', (username,))
    if existing:
        return existing['id']
    return execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))


def ensure_elderly(name):
    existing = query_one('SELECT id FROM elderly_people WHERE name = ?', (name,))
    if existing:
        return existing['id']
    return execute('INSERT INTO elderly_people (name) VALUES (?)', (name,))


def ensure_access(user_id, elderly_id):
    existing = query_one(
        'SELECT 1 as x FROM user_elderly_access WHERE userId = ? AND elderlyId = ?',
        (user_id, elderly_id)
    )
    if not existing:
        execute(
            'INSERT INTO user_elderly_access (userId, elderlyId) VALUES (?, ?)',
            (user_id, elderly_id)
        )


def ensure_device(api_key, elderly_id):
    existing = query_one('SELECT id FROM devices WHERE apiKey = ?', (api_key,))
    if existing:
        return existing['id']
    return execute(
        'INSERT INTO devices (apiKey, elderlyId) VALUES (?, ?)',
        (api_key, elderly_id)
    )


def ensure_doctors():
    existing = query_one('SELECT COUNT(*) as c FROM doctors')
    if existing and existing['c'] > 0:
        print(f'Doctors already seeded ({existing["c"]} found). Skipping.')
        return

    doctors = [
        ('Dr. Anjali Sharma',   'Geriatric Medicine', 'Apollo Hospital, Delhi',     'anjali.sharma@example.com', 15),
        ('Dr. Rajesh Verma',    'Cardiology',         'Fortis, Mumbai',             'rajesh.verma@example.com',  22),
        ('Dr. Meera Iyer',      'Neurology',          'AIIMS, Delhi',               'meera.iyer@example.com',    18),
        ('Dr. Suresh Nair',     'General Physician',  'Manipal Hospital, Bangalore','suresh.nair@example.com',   12),
        ('Dr. Priya Deshpande', 'Sleep Medicine',     'Kokilaben, Mumbai',          'priya.d@example.com',        9),
    ]
    for d in doctors:
        execute(
            'INSERT INTO doctors (name, specialty, hospital, email, experience_years) VALUES (?, ?, ?, ?, ?)',
            d
        )
    print(f'Seeded {len(doctors)} doctors.')


def seed_logs(elderly_id, days, inject_anomalies_at=None):
    """
    Generate `days` days of realistic activity data ending today.
    inject_anomalies_at: list of day numbers (1-indexed) that should be "unusual".
    """
    inject_anomalies_at = inject_anomalies_at or []

    # Get the current max day for this elderly person (so re-runs append)
    existing = query_one(
        'SELECT MAX(day) as max_day FROM logs WHERE elderlyId = ?',
        (elderly_id,)
    )
    start_day = (existing['max_day'] or 0) + 1

    today = datetime.now().date()
    # Align first day of this batch to (days - 1) days ago
    first_date = today - timedelta(days=days - 1)

    for i in range(days):
        day_num = start_day + i
        date_str = (first_date + timedelta(days=i)).isoformat()

        is_anomaly_day = i + 1 in inject_anomalies_at

        if is_anomaly_day:
            wake_up = 11
            meals = 0
            movement = 15
            sleep = 3
            wakes = 5
            medicine = 0
        else:
            wake_up = random_between(6, 8)
            meals = random_between(2, 3)
            movement = random_between(80, 120)
            sleep = random_between(6, 8)
            wakes = random_between(0, 2)
            medicine = 1

        execute(
            """INSERT INTO logs
               (elderlyId, day, date, wakeUpTime, mealsEaten, movementCount,
                sleepHours, timesWokenAtNight, medicineTaken)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (elderly_id, day_num, date_str, wake_up, meals, movement, sleep, wakes, medicine)
        )

    print(f'  → {days} days seeded for elderlyId={elderly_id}')


if __name__ == '__main__':
    print('Initializing tables...')
    init_db()

    print('Creating users...')
    family_id = ensure_user('family', '1234')
    sister_id = ensure_user('sister', 'abcd')

    print('Creating elderly people...')
    kamla_id  = ensure_elderly('Kamla Devi')
    ramesh_id = ensure_elderly('Ramesh Kumar')

    print('Linking users to elderly people...')
    ensure_access(family_id, kamla_id)
    ensure_access(family_id, ramesh_id)
    ensure_access(sister_id, ramesh_id)

    print('Creating device...')
    ensure_device('demo-device-key-123', kamla_id)

    print('Seeding doctors...')
    ensure_doctors()

    # Only add logs if Kamla has none yet, so re-runs don't duplicate 30-day sets
    kamla_logs = query_one('SELECT COUNT(*) as c FROM logs WHERE elderlyId = ?', (kamla_id,))
    if kamla_logs['c'] == 0:
        print('Seeding 30 days for Kamla Devi (anomalies on days 10 and 22)...')
        seed_logs(kamla_id, days=30, inject_anomalies_at=[10, 22])
    else:
        print(f'Kamla Devi already has {kamla_logs["c"]} log rows. Skipping.')

    ramesh_logs = query_one('SELECT COUNT(*) as c FROM logs WHERE elderlyId = ?', (ramesh_id,))
    if ramesh_logs['c'] == 0:
        print('Seeding 10 baseline days for Ramesh Kumar...')
        seed_logs(ramesh_id, days=10)
    else:
        print(f'Ramesh Kumar already has {ramesh_logs["c"]} log rows. Skipping.')

    print('')
    print('==================================================')
    print('  Demo credentials:')
    print('    family / 1234   →  sees Kamla Devi + Ramesh Kumar')
    print('    sister / abcd   →  sees Ramesh Kumar only')
    print('  Device API key:  demo-device-key-123')
    print('==================================================')
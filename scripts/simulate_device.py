"""
Fake IoT device simulator.

Sends a movement reading to the Flask backend every 5 seconds,
authenticated with the demo device's API key. The server stores
it as "today's" activity — the same endpoint a real wearable
would POST to.
"""

import sys
import os
import time
import random

# Allow import of nothing from parent — this script only uses requests
# and talks over HTTP, so no sys.path tricks needed.

import requests

API_KEY = 'demo-device-key-123'
SERVER_URL = 'http://localhost:4000/api/sensor-data'


def send_reading():
    movement = random.randint(80, 120)
    try:
        response = requests.post(
            SERVER_URL,
            json={'apiKey': API_KEY, 'movementReading': movement},
            timeout=5
        )
        data = response.json()
        if response.status_code == 200:
            print(f'Sent reading: {movement} | Action: {data.get("action", "?")}')
        else:
            print(f'Server rejected: {data}')
    except requests.exceptions.ConnectionError:
        print('Failed to connect — is the Flask server running on port 4000?')
    except Exception as e:
        print(f'Failed to send: {e}')


if __name__ == '__main__':
    print('Simulated device starting.')
    print(f'Target:  {SERVER_URL}')
    print('Sending a reading every 5 seconds. Press Ctrl+C to stop.')
    print('')
    try:
        while True:
            send_reading()
            time.sleep(5)
    except KeyboardInterrupt:
        print('')
        print('Simulator stopped.')
"""
Family Care — Flask application (Stage 2: auth + home)

At this stage, this file handles:
    - home page
    - login / signup / logout (with real Flask sessions)
    - a placeholder /picker route so login redirect works

Stage 3 will fill in the picker + dashboard.
Stage 4 will add doctors + the share-report feature.
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash
from db import query_one, execute, init_db

app = Flask(__name__)
# Secret key signs the session cookie. Change before any real deployment.
app.secret_key = 'dev-only-change-me-before-deploying'

init_db()


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not username or not password:
        flash('Please enter both username and password.', 'error')
        return redirect(url_for('login'))

    user = query_one(
        'SELECT * FROM users WHERE username = ? AND password = ?',
        (username, password)
    )
    if not user:
        flash('Incorrect username or password.', 'error')
        return redirect(url_for('login'))

    session['user_id'] = user['id']
    session['username'] = user['username']
    flash(f"Welcome back, {user['username']}!", 'success')
    return redirect(url_for('picker'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if len(username) < 3 or len(password) < 3:
        flash('Username and password must be at least 3 characters.', 'error')
        return redirect(url_for('signup'))

    if query_one('SELECT id FROM users WHERE username = ?', (username,)):
        flash('That username is already taken.', 'error')
        return redirect(url_for('signup'))

    user_id = execute(
        'INSERT INTO users (username, password) VALUES (?, ?)',
        (username, password)
    )
    session['user_id'] = user_id
    session['username'] = username
    flash('Account created. Add a family member to monitor.', 'success')
    return redirect(url_for('picker'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('home'))


@app.route('/picker')
def picker():
    """Placeholder — will be replaced in Stage 3."""
    if 'user_id' not in session:
        flash('Please log in first.', 'error')
        return redirect(url_for('login'))

    return """
    <div style="max-width: 480px; margin: 60px auto; padding: 40px; font-family: sans-serif; text-align: center;">
        <h1 style="font-family: Georgia, serif;">Picker page coming in Stage 3</h1>
        <p>You are logged in as <strong>{}</strong>.</p>
        <p style="margin-top: 20px;">
            <a href="/logout" style="color: #6B8F71; font-weight: 600;">Log out</a>
        </p>
    </div>
    """.format(session.get('username', 'unknown'))


if __name__ == '__main__':
    print('Family Care (Flask) running on http://localhost:4000')
    app.run(host='0.0.0.0', port=4000, debug=False)
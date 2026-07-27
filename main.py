import os
import sqlite3
import json
import threading
import re
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect
from Email_Fetcher import EmailFetcher
from GmailFetcher import GmailFetcher
from Assignment_Finder import AssignmentFinder
from LLMClassifier import LLMClassifier

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.urandom(24)

EMAILS_DB = 'emails.db'
ASSIGNMENTS_DB = 'assignments.db'
SETTINGS_FILE = 'settings.json'

FETCH_LIMIT = 150

gmail_fetcher = GmailFetcher(credentials_dir='.', token_name='token.pickle')
gmail_fetcher_2 = GmailFetcher(credentials_dir='.', token_name='token_2.pickle')
email_config = {}
email_config_2 = {}
llm_classifier = LLMClassifier()
llm_download_status = {"status": "idle", "message": ""}


def init_databases():
    conn = sqlite3.connect(EMAILS_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS emails
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         message_id TEXT UNIQUE,
         sender TEXT,
         subject TEXT,
         body TEXT,
         received_date TEXT,
         is_deleted INTEGER DEFAULT 0,
         account INTEGER DEFAULT 1,
         created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_emails_is_deleted ON emails(is_deleted)')
    # Migrations: add columns if not present
    for col_sql in [
        'ALTER TABLE emails ADD COLUMN account INTEGER DEFAULT 1',
        'ALTER TABLE emails ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP',
        'ALTER TABLE emails ADD COLUMN is_dismissed INTEGER DEFAULT 0',
    ]:
        try:
            conn.execute(col_sql)
        except:
            pass
    conn.commit()
    conn.close()

    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS assignments
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         email_id INTEGER,
         sender TEXT,
         subject TEXT,
         body TEXT,
         received_date TEXT,
         status TEXT DEFAULT 'pending',
         created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_assignments_email_id ON assignments(email_id)')
    conn.commit()
    conn.close()


init_databases()


def _load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}


def _save_settings(settings):
    try:
        merged = _load_settings()
        merged.update(settings)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
    except:
        pass


# Auto-load previously downloaded LLM model on startup
_settings = _load_settings()
_llm_model_key = _settings.get('llm_model', 'distilbert')
_llm_downloaded = _settings.get('llm_downloaded_models', [])
if _llm_model_key in _llm_downloaded:
    try:
        llm_classifier.load(_llm_model_key)
    except:
        pass


def extract_email(sender):
    match = re.search(r'<([^>]+)>', sender)
    return (match.group(1) or '').lower().strip() if match else sender.lower().strip()


def is_trusted_sender(sender, trusted_list):
    if not trusted_list:
        return False
    sender_email = extract_email(sender)
    for trusted in trusted_list:
        t = trusted.lower().strip()
        if t in sender_email or t in sender.lower():
            return True
    return False


def get_classifier():
    settings = _load_settings()
    method = settings.get('classification_method', 'keyword')
    if method == 'llm' and llm_classifier.is_ready():
        return lambda s, b: llm_classifier.is_assignment(s, b)
    finder = AssignmentFinder()
    return lambda s, b: finder.is_assignment(s, b)


def store_emails(emails, account=1):
    conn_emails = sqlite3.connect(EMAILS_DB)
    conn_assign = sqlite3.connect(ASSIGNMENTS_DB)
    settings = _load_settings()
    trusted = settings.get('trusted_senders', [])
    classifier = get_classifier()

    new_count = 0
    assignment_count = 0

    for email_data in emails:
        try:
            conn_emails.execute('''INSERT OR IGNORE INTO emails
                (message_id, sender, subject, body, received_date, account)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (email_data['message_id'], email_data['from'],
                 email_data['subject'], email_data['body'],
                 email_data['date'], account))

            is_new = conn_emails.execute('SELECT changes()').fetchone()[0] > 0
            if is_new:
                new_count += 1

            row = conn_emails.execute(
                'SELECT id, is_dismissed FROM emails WHERE message_id = ?',
                (email_data['message_id'],)).fetchone()
            if not row:
                continue
            email_id, is_dismissed = row

            if is_dismissed:
                continue

            if is_trusted_sender(email_data['from'], trusted) or \
               classifier(email_data['subject'], email_data['body']):
                conn_assign.execute('''INSERT OR IGNORE INTO assignments
                    (email_id, sender, subject, body, received_date, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')''',
                    (email_id, email_data['from'], email_data['subject'],
                     email_data['body'], email_data['date']))

                if conn_assign.execute('SELECT changes()').fetchone()[0] > 0:
                    assignment_count += 1
        except Exception as e:
            print(f"Error processing email: {e}")

    conn_emails.commit()
    conn_assign.commit()
    conn_emails.close()
    conn_assign.close()

    return new_count, assignment_count


@app.route('/')
def index():
    settings = _load_settings()
    return render_template('index.html', theme=settings.get('theme', 'dark'))


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify(_load_settings())
    _save_settings(request.json)
    return jsonify({'status': 'ok'})


def _connect_imap(data, config_store, config_save_key=''):
    email = data.get('email', '').strip()
    password = data.get('password', '')
    imap_server = data.get('imap_server', '').strip()
    imap_port = int(data.get('imap_port', 993))

    if not all([email, password, imap_server]):
        return jsonify({'status': 'error', 'message': 'All fields required'}), 400

    fetcher = EmailFetcher(email, password, imap_server, imap_port)
    success, msg = fetcher.test_connection()

    if success:
        config_store.clear()
        config_store.update({
            'email': email, 'password': password,
            'imap_server': imap_server, 'imap_port': imap_port
        })
        if config_save_key:
            _save_settings({
                f'imap_email_{config_save_key}': email,
                f'imap_server_{config_save_key}': imap_server,
                f'imap_port_{config_save_key}': imap_port
            })
        return jsonify({'status': 'connected', 'message': 'Connected'})
    return jsonify({'status': 'error', 'message': msg})


@app.route('/api/connect', methods=['POST'])
def api_connect():
    return _connect_imap(request.json, email_config, '1')


@app.route('/api/connect/2', methods=['POST'])
def api_connect_2():
    return _connect_imap(request.json, email_config_2, '2')


@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    email_config.clear()
    return jsonify({'status': 'ok'})


@app.route('/api/disconnect/2', methods=['POST'])
def api_disconnect_2():
    email_config_2.clear()
    return jsonify({'status': 'ok'})


def _fetch_all():
    all_emails = []
    errors = []

    if gmail_fetcher.is_authenticated():
        s, r = gmail_fetcher.fetch_emails(limit=FETCH_LIMIT)
        if s: all_emails.extend((e, 1) for e in r)
        else: errors.append(f"Account 1: {r}")
    elif email_config:
        f = EmailFetcher(**email_config)
        s, r = f.fetch_emails(limit=FETCH_LIMIT)
        if s: all_emails.extend((e, 1) for e in r)
        else: errors.append(f"Account 1: {r}")

    if gmail_fetcher_2.is_authenticated():
        s, r = gmail_fetcher_2.fetch_emails(limit=FETCH_LIMIT)
        if s: all_emails.extend((e, 2) for e in r)
        else: errors.append(f"Account 2: {r}")
    elif email_config_2:
        f = EmailFetcher(**email_config_2)
        s, r = f.fetch_emails(limit=FETCH_LIMIT)
        if s: all_emails.extend((e, 2) for e in r)
        else: errors.append(f"Account 2: {r}")

    return all_emails, errors


@app.route('/api/fetch', methods=['POST'])
def api_fetch():
    all_emails, errors = _fetch_all()
    if not all_emails:
        msg = '; '.join(errors) if errors else 'No accounts connected. Set up in Settings.'
        return jsonify({'status': 'error', 'message': msg})

    total_new = 0
    total_assign = 0
    for email_data, acct in all_emails:
        n, a = store_emails([email_data], account=acct)
        total_new += n
        total_assign += a

    return jsonify({
        'status': 'success',
        'new_emails': total_new,
        'total_emails': len(all_emails),
        'assignments_found': total_assign,
        'accounts': 2 if (email_config_2 or gmail_fetcher_2.is_authenticated()) else 1
    })


@app.route('/api/fetch/new', methods=['POST'])
def api_fetch_new():
    all_emails, errors = _fetch_all()
    if not all_emails:
        msg = '; '.join(errors) if errors else 'No accounts connected.'
        return jsonify({'status': 'error', 'message': msg})

    total_new = 0
    total_assign = 0
    for email_data, acct in all_emails:
        n, a = store_emails([email_data], account=acct)
        total_new += n
        total_assign += a

    if total_new == 0:
        return jsonify({'status': 'ok', 'message': 'No new emails found', 'new_emails': 0})

    return jsonify({
        'status': 'success',
        'new_emails': total_new,
        'total_emails': len(all_emails),
        'assignments_found': total_assign
    })


@app.route('/api/gmail/auth-url', methods=['GET'])
def api_gmail_auth_url():
    acct = request.args.get('account', '1')
    fetcher = gmail_fetcher_2 if acct == '2' else gmail_fetcher
    try:
        url = fetcher.get_auth_url(state=f'account={acct}')
        if url is None:
            return jsonify({'status': 'error',
                'message': 'client_secret.json not found'})
        return jsonify({'status': 'ok', 'auth_url': url})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/gmail/callback')
def api_gmail_callback():
    code = request.args.get('code')
    state = request.args.get('state', '')
    if not code:
        return 'No code received', 400
    acct = '1'
    if state.startswith('account='):
        acct = state.split('=')[1]
    fetcher = gmail_fetcher_2 if acct == '2' else gmail_fetcher
    try:
        fetcher.exchange_code(request.url)
        return redirect('/')
    except Exception as e:
        return f'OAuth error: {str(e)}', 400


@app.route('/api/gmail/status', methods=['GET'])
def api_gmail_status():
    return jsonify({
        'authenticated': gmail_fetcher.is_authenticated(),
        'authenticated_2': gmail_fetcher_2.is_authenticated(),
        'has_client_secret': os.path.exists(gmail_fetcher.client_secret_path)
    })


@app.route('/api/gmail/logout', methods=['POST'])
def api_gmail_logout():
    acct = request.json.get('account', '1') if request.json else '1'
    if acct == '2':
        gmail_fetcher_2.logout()
    else:
        gmail_fetcher.logout()
    return jsonify({'status': 'ok'})


@app.route('/api/gmail/upload-client-secret', methods=['POST'])
def api_gmail_upload_client_secret():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file provided'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'})
    try:
        content = file.read()
        import json
        data = json.loads(content)
        if 'web' not in data and 'installed' not in data:
            return jsonify({'status': 'error', 'message': 'Invalid client_secret format'})
        save_path = os.path.join(os.getcwd(), 'client_secret.json')
        with open(save_path, 'wb') as f:
            f.write(content)
        return jsonify({'status': 'ok', 'message': 'client_secret.json saved'})
    except json.JSONDecodeError:
        return jsonify({'status': 'error', 'message': 'File is not valid JSON'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/llm/status', methods=['GET'])
def api_llm_status():
    models_status = LLMClassifier.check_all_cached()
    downloaded = [k for k, v in models_status.items() if v]
    return jsonify({
        'ready': llm_classifier.is_ready(),
        'model': llm_classifier.get_current_model(),
        'error': llm_classifier._error,
        'download_status': llm_download_status['status'],
        'download_message': llm_download_status['message'],
        'models': {k: {'cached': v} for k, v in models_status.items()},
        'downloaded_models': downloaded
    })


@app.route('/api/llm/models', methods=['GET'])
def api_llm_models():
    return jsonify(LLMClassifier.MODELS)


@app.route('/api/llm/download', methods=['POST'])
def api_llm_download():
    global llm_download_status

    model_key = (request.json or {}).get('model', 'distilbert')

    if llm_classifier.is_ready() and llm_classifier.get_current_model() == model_key:
        return jsonify({'status': 'ok', 'message': f'{model_key} already ready'})

    if llm_download_status['status'] == 'downloading':
        return jsonify({'status': 'error', 'message': 'Already downloading'})

    model_sizes = LLMClassifier.MODELS
    size = model_sizes.get(model_key, {}).get('size', 'unknown')
    llm_download_status = {"status": "downloading", "message": f"Downloading {model_key} ({size})..."}

    def _download():
        global llm_download_status
        try:
            llm_classifier.load(model_key)
            if llm_classifier.is_ready():
                llm_download_status = {"status": "ready", "message": f"{model_key} ready"}
                downloaded = _load_settings().get('llm_downloaded_models', [])
                if model_key not in downloaded:
                    downloaded.append(model_key)
                    _save_settings({'llm_downloaded_models': downloaded, 'llm_model': model_key})
            else:
                llm_download_status = {"status": "error", "message": llm_classifier._error or "Unknown error"}
        except Exception as e:
            llm_download_status = {"status": "error", "message": str(e)}

    thread = threading.Thread(target=_download, daemon=True)
    thread.start()
    return jsonify({'status': 'downloading', 'message': f'Downloading {model_key}...'})


@app.route('/api/resort', methods=['POST'])
def api_resort():
    conn = sqlite3.connect(EMAILS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM emails WHERE is_deleted = 0 AND is_dismissed = 0').fetchall()
    conn.close()

    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('DELETE FROM assignments')
    conn.commit()
    conn.close()

    settings = _load_settings()
    trusted = settings.get('trusted_senders', [])
    classifier = get_classifier()
    count = 0

    conn_assign = sqlite3.connect(ASSIGNMENTS_DB)
    for row in rows:
        if is_trusted_sender(row['sender'], trusted) or \
           classifier(row['subject'], row['body']):
            conn_assign.execute('''INSERT OR IGNORE INTO assignments
                (email_id, sender, subject, body, received_date, status)
                VALUES (?, ?, ?, ?, ?, 'pending')''',
                (row['id'], row['sender'], row['subject'], row['body'], row['received_date']))
            count += 1
    conn_assign.commit()
    conn_assign.close()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    _save_settings({'last_resort': now})

    return jsonify({'status': 'ok', 'assignments_found': count, 'time': now})


@app.route('/api/emails', methods=['GET'])
def api_get_emails():
    conn = sqlite3.connect(EMAILS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, sender, subject, body, received_date, created_at, account '
        'FROM emails WHERE is_deleted = 0 ORDER BY received_date DESC '
        'LIMIT ?', (FETCH_LIMIT,)).fetchall()
    conn.close()

    return jsonify({
        'emails': [{
            'id': r['id'], 'sender': r['sender'], 'subject': r['subject'],
            'body': r['body'][:300] + ('...' if len(r['body']) > 300 else ''),
            'received_date': r['received_date'], 'created_at': r['created_at'],
            'account': r['account']
        } for r in rows],
        'count': len(rows)
    })


@app.route('/api/assignments', methods=['GET'])
def api_get_assignments():
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, email_id, sender, subject, body, received_date, status '
        'FROM assignments ORDER BY received_date DESC').fetchall()
    conn.close()

    return jsonify({
        'assignments': [{
            'id': r['id'], 'email_id': r['email_id'], 'sender': r['sender'],
            'subject': r['subject'],
            'body': r['body'][:300] + ('...' if len(r['body']) > 300 else ''),
            'received_date': r['received_date'], 'status': r['status']
        } for r in rows],
        'count': len(rows)
    })


@app.route('/api/emails/<int:email_id>/delete', methods=['POST'])
def api_delete_email(email_id):
    conn = sqlite3.connect(EMAILS_DB)
    conn.execute('UPDATE emails SET is_deleted = 1, is_dismissed = 1 WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('DELETE FROM assignments WHERE email_id = ?', (email_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/emails/<int:email_id>/move-to-assignment', methods=['POST'])
def api_move_to_assignment(email_id):
    conn = sqlite3.connect(EMAILS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT id, sender, subject, body, received_date FROM emails WHERE id = ?',
        (email_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('''INSERT OR IGNORE INTO assignments
        (email_id, sender, subject, body, received_date, status)
        VALUES (?, ?, ?, ?, ?, 'pending')''',
        (row['id'], row['sender'], row['subject'], row['body'], row['received_date']))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/assignments/<int:assign_id>/complete', methods=['POST'])
def api_complete_assignment(assign_id):
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT email_id FROM assignments WHERE id = ?', (assign_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    email_id = row['email_id']
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('DELETE FROM assignments WHERE id = ?', (assign_id,))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(EMAILS_DB)
    conn.execute('UPDATE emails SET is_dismissed = 1 WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/assignments/<int:assign_id>/discard', methods=['POST'])
def api_discard_assignment(assign_id):
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT email_id FROM assignments WHERE id = ?', (assign_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    email_id = row['email_id']
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('DELETE FROM assignments WHERE id = ?', (assign_id,))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(EMAILS_DB)
    conn.execute('UPDATE emails SET is_deleted = 1, is_dismissed = 1 WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/assignments/<int:assign_id>/move-to-mail', methods=['POST'])
def api_move_to_mail(assign_id):
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT email_id FROM assignments WHERE id = ?', (assign_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    email_id = row['email_id']
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    conn.execute('DELETE FROM assignments WHERE id = ?', (assign_id,))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(EMAILS_DB)
    conn.execute('UPDATE emails SET is_dismissed = 1 WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/status', methods=['GET'])
def api_status():
    settings = _load_settings()
    return jsonify({
        'connected': bool(email_config) or gmail_fetcher.is_authenticated(),
        'connected_2': bool(email_config_2) or gmail_fetcher_2.is_authenticated(),
        'email': email_config.get('email', '') if email_config else '',
        'email_2': email_config_2.get('email', '') if email_config_2 else '',
        'gmail_authenticated': gmail_fetcher.is_authenticated(),
        'gmail_authenticated_2': gmail_fetcher_2.is_authenticated(),
        'llm_ready': llm_classifier.is_ready(),
        'llm_model': llm_classifier.get_current_model(),
        'llm_downloaded_models': settings.get('llm_downloaded_models', []),
        'classification_method': settings.get('classification_method', 'keyword'),
        'theme': settings.get('theme', 'dark'),
        'last_resort': settings.get('last_resort', ''),
        'trusted_senders': settings.get('trusted_senders', []),
        'fetch_limit': FETCH_LIMIT
    })


@app.route('/api/emails/count', methods=['GET'])
def api_emails_count():
    conn = sqlite3.connect(EMAILS_DB)
    total = conn.execute('SELECT COUNT(*) FROM emails WHERE is_deleted = 0').fetchone()[0]
    conn.close()
    conn = sqlite3.connect(ASSIGNMENTS_DB)
    assignments = conn.execute('SELECT COUNT(*) FROM assignments').fetchone()[0]
    conn.close()
    return jsonify({'total': total, 'assignments': assignments})


if __name__ == '__main__':
    print("=" * 60)
    print("  Assignment Tracker")
    print("=" * 60)
    print(f"  Fetches up to {FETCH_LIMIT} emails per account per fetch")
    print("  Supports 2 email accounts")
    print("  Open: http://127.0.0.1:5000")
    print()
    app.run(debug=True, host='127.0.0.1', port=5000)

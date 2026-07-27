import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import pickle
import base64
import re
import html
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from email.utils import parsedate_to_datetime
from oauthlib import oauth2

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


class GmailFetcher:
    def __init__(self, credentials_dir='.', token_name='token.pickle'):
        self.credentials_dir = credentials_dir
        self.token_path = os.path.join(credentials_dir, token_name)
        self.client_secret_path = os.path.join(credentials_dir, 'client_secret.json')
        self.service = None
        self.creds = None
        self._flow = None
        self._code_verifier = None
        self._load_creds()

    def _load_creds(self):
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, 'rb') as f:
                    self.creds = pickle.load(f)
            except:
                self.creds = None

    def _save_creds(self):
        with open(self.token_path, 'wb') as f:
            pickle.dump(self.creds, f)

    def is_authenticated(self):
        if not self.creds:
            return False
        if self.creds and self.creds.valid:
            return True
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(GoogleRequest())
                self._save_creds()
                return True
            except:
                return False
        return False

    def get_auth_url(self, state=None):
        if not os.path.exists(self.client_secret_path):
            return None

        self._flow = Flow.from_client_secrets_file(
            self.client_secret_path,
            scopes=SCOPES,
            redirect_uri='http://localhost:5000/api/gmail/callback'
        )

        oauth_client = oauth2.WebApplicationClient(self._flow.client_config['client_id'])
        self._code_verifier = oauth_client.create_code_verifier(43)
        code_challenge = oauth_client.create_code_challenge(self._code_verifier, 'S256')

        kwargs = dict(
            prompt='consent',
            access_type='offline',
            code_challenge=code_challenge,
            code_challenge_method='S256'
        )
        if state:
            kwargs['state'] = state

        auth_url, _ = self._flow.authorization_url(**kwargs)
        return auth_url

    def exchange_code(self, authorization_response):
        if not self._flow:
            self._flow = Flow.from_client_secrets_file(
                self.client_secret_path,
                scopes=SCOPES,
                redirect_uri='http://localhost:5000/api/gmail/callback'
            )
        self._flow.fetch_token(
            authorization_response=authorization_response,
            code_verifier=self._code_verifier
        )
        self.creds = self._flow.credentials
        self._save_creds()
        self._build_service()
        self._flow = None
        self._code_verifier = None

    def _build_service(self):
        if self.creds:
            self.service = build('gmail', 'v1', credentials=self.creds)

    def fetch_emails(self, limit=50):
        if not self.is_authenticated():
            return False, "Not authenticated with Gmail API"

        if not self.service:
            self._build_service()

        try:
            results = self.service.users().messages().list(
                userId='me', maxResults=limit, q='in:inbox'
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return False, "Inbox is empty"

            emails = []
            for msg in messages:
                full_msg = self.service.users().messages().get(
                    userId='me', id=msg['id'], format='full'
                ).execute()

                email_data = self._parse_message(full_msg)
                if email_data:
                    emails.append(email_data)

            return True, emails

        except Exception as e:
            return False, f"Gmail API error: {str(e)}"

    def _parse_message(self, msg):
        try:
            headers = {}
            for header in msg['payload'].get('headers', []):
                headers[header['name'].lower()] = header['value']

            message_id = headers.get('message-id', '') or headers.get('message-id', '') or msg.get('id', '')
            subject = headers.get('subject', '(No Subject)')
            sender = headers.get('from', 'Unknown')
            date_str = headers.get('date', '')

            try:
                date_dt = parsedate_to_datetime(date_str)
                date = date_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                date = date_str

            body = self._get_body(msg['payload'])

            return {
                'message_id': message_id.strip(),
                'from': sender,
                'subject': subject,
                'body': body,
                'date': date
            }
        except Exception:
            return None

    def _get_body(self, payload):
        if 'parts' in payload:
            text = ''
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                    try:
                        data = part['body']['data']
                        text += base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    except:
                        pass
                elif part['mimeType'] == 'text/html' and 'data' in part.get('body', {}):
                    try:
                        data = part['body']['data']
                        html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                        if not text:
                            text += self._html_to_text(html_content)
                    except:
                        pass
                elif 'parts' in part:
                    text += self._get_body(part)
            return text.strip() or '(No content)'

        if 'data' in payload.get('body', {}):
            try:
                data = payload['body']['data']
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                if payload['mimeType'] == 'text/html':
                    return self._html_to_text(decoded) or '(No content)'
                return decoded.strip() or '(No content)'
            except:
                pass

        return '(No content)'

    def _html_to_text(self, html_content):
        text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = html.unescape(text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def logout(self):
        if os.path.exists(self.token_path):
            os.remove(self.token_path)
        self.creds = None
        self.service = None

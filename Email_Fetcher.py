import imaplib
import email
import socket
from email.header import decode_header
from email.utils import parsedate_to_datetime
import html
import re


class EmailFetcher:
    def __init__(self, email_address, password, imap_server, imap_port=993):
        self.email_address = email_address
        self.password = password
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.connection = None

    def test_connection(self):
        socket.setdefaulttimeout(15)
        try:
            self.connection = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.connection.login(self.email_address, self.password)
            self.connection.logout()
            self.connection = None
            return True, "Connection successful"
        except imaplib.IMAP4.error as e:
            msg = str(e).strip()
            if '[AUTHENTICATIONFAILED]' in msg:
                return False, (
                    "Authentication failed. For Gmail, use an App Password "
                    "(https://myaccount.google.com/apppasswords). "
                    "For others, check your password."
                )
            return False, f"Login failed: {msg}"
        except socket.timeout:
            return False, (
                f"Connection timed out. Cannot reach {self.imap_server}:{self.imap_port}.\n"
                "Check firewall, VPN, or network - IMAP port 993 may be blocked."
            )
        except socket.gaierror:
            return False, f"Could not resolve server '{self.imap_server}'."
        except ConnectionRefusedError:
            return False, f"Connection refused by {self.imap_server}:{self.imap_port}."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def fetch_emails(self, limit=50):
        socket.setdefaulttimeout(15)
        try:
            self.connection = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.connection.login(self.email_address, self.password)
            self.connection.select('INBOX')

            status, messages = self.connection.search(None, 'ALL')
            if status != 'OK':
                return False, "No emails found"

            email_ids = messages[0].split()
            if not email_ids:
                return False, "Inbox is empty"

            email_ids = email_ids[-limit:]
            emails = []

            for e_id in reversed(email_ids):
                status, msg_data = self.connection.fetch(e_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                email_data = self._parse_email(msg)
                if email_data:
                    emails.append(email_data)

            return True, emails

        except Exception as e:
            return False, f"Fetch failed: {str(e)}"
        finally:
            if self.connection:
                try:
                    self.connection.close()
                    self.connection.logout()
                except:
                    pass
                self.connection = None

    def _parse_email(self, msg):
        try:
            message_id = msg.get('Message-ID', '') or msg.get('Message-Id', '') or ''
            subject = self._decode_str(msg.get('Subject', '(No Subject)'))
            sender = self._decode_str(msg.get('From', 'Unknown'))
            date_str = msg.get('Date', '')

            try:
                date_dt = parsedate_to_datetime(date_str)
                date = date_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                date = date_str

            body = self._get_body(msg)

            return {
                'message_id': message_id.strip(),
                'from': sender,
                'subject': subject,
                'body': body,
                'date': date
            }
        except Exception:
            return None

    def _decode_str(self, text):
        if not text:
            return ''
        try:
            decoded_parts = decode_header(text)
            result = []
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    try:
                        result.append(part.decode(charset or 'utf-8', errors='replace'))
                    except:
                        result.append(part.decode('utf-8', errors='replace'))
                else:
                    result.append(str(part))
            return ' '.join(result)
        except:
            return str(text)

    def _get_body(self, msg):
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))

                if 'attachment' in content_disposition:
                    continue

                if content_type == 'text/plain':
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body += payload.decode(charset, errors='replace')
                    except:
                        pass
                elif content_type == 'text/html' and not body:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html_content = payload.decode(charset, errors='replace')
                            body += self._html_to_text(html_content)
                    except:
                        pass
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    if content_type == 'text/plain':
                        body = payload.decode(charset, errors='replace')
                    elif content_type == 'text/html':
                        html_content = payload.decode(charset, errors='replace')
                        body = self._html_to_text(html_content)
            except:
                pass

        return body.strip() or '(No content)'

    def _html_to_text(self, html_content):
        text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = html.unescape(text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

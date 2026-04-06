from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import os
import pickle
import base64


class GmailClient:
    def __init__(self, user_email):  # 👈 Fixed here
        self.service = None
        self.authenticated = False
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        self.user_email = user_email
        token_dir = os.getenv("TOKEN_STORAGE_DIR", ".")
        os.makedirs(token_dir, exist_ok=True)
        self.token_file = os.path.join(token_dir, f"token_{self.user_email}.pkl")
        self.credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
        self.oauth_redirect_uri = os.getenv(
            "GMAIL_OAUTH_REDIRECT_URI",
            "http://localhost:5000/gmail_oauth_callback",
        )
        self.pending_auth_url = None
        self.pending_auth_state = None

    def _clear_token(self):
        try:
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
        except OSError:
            pass

    def _build_flow(self):
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_file, self.SCOPES
        )
        flow.redirect_uri = self.oauth_redirect_uri
        return flow

    def begin_auth(self):
        flow = self._build_flow()
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="select_account consent",
            include_granted_scopes="true",
        )
        self.pending_auth_url = auth_url
        self.pending_auth_state = state
        return auth_url, state

    def complete_auth(self, state, authorization_response):
        flow = self._build_flow()
        if self.oauth_redirect_uri.startswith("http://localhost") or self.oauth_redirect_uri.startswith("http://127.0.0.1"):
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        flow.fetch_token(authorization_response=authorization_response, state=state)
        creds = flow.credentials
        with open(self.token_file, 'wb') as token:
            pickle.dump(creds, token)
        self.service = build('gmail', 'v1', credentials=creds)
        self.authenticated = True
        return True

    def authenticate(self):
        try:
            creds = None
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except RefreshError:
                        self._clear_token()
                        self.begin_auth()
                        return False
                    except Exception as e:
                        error_text = str(e).lower()
                        if "invalid_grant" in error_text or "expired or revoked" in error_text:
                            self._clear_token()
                            self.begin_auth()
                            return False
                        raise
                else:
                    self._clear_token()
                    self.begin_auth()
                    return False
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)

            try:
                self.service = build('gmail', 'v1', credentials=creds)
            except Exception as e:
                error_text = str(e).lower()
                if "invalid_grant" in error_text or "expired or revoked" in error_text:
                    self._clear_token()
                    self.begin_auth()
                    return False
                raise

            if creds and not getattr(creds, "valid", False):
                if getattr(creds, "refresh_token", None):
                    self._clear_token()
                    self.begin_auth()
                    return False
                else:
                    self._clear_token()
                    self.begin_auth()
                    return False

            self.authenticated = True
            return True
        except Exception as e:
            print(f"Authentication failed: {str(e)}")
            return False

    def get_recent_emails(self, limit=10):
        if not self.authenticated or self.service is None:
            raise Exception("GmailClient is not authenticated")

        try:
            refs = self.get_recent_message_refs(limit=limit)
            emails = self.get_emails_by_ids([msg.get('id') for msg in refs if msg.get('id')])
        except Exception as e:
            print(f"Failed to fetch emails: {e}")
            emails = []

        return emails

    def get_recent_message_refs(self, limit=10):
        if not self.authenticated or self.service is None:
            raise Exception("GmailClient is not authenticated")

        results = self.service.users().messages().list(
            userId='me', maxResults=limit
        ).execute()
        return results.get('messages', [])

    def get_emails_by_ids(self, message_ids):
        if not self.authenticated or self.service is None:
            raise Exception("GmailClient is not authenticated")

        emails = []
        for message_id in message_ids:
            if not message_id:
                continue
            try:
                msg_data = self.service.users().messages().get(
                    userId='me', id=message_id, format='full'
                ).execute()
                emails.append(self._parse_message(msg_data, fallback_id=message_id))
            except Exception as e:
                print(f"Failed to fetch email {message_id}: {e}")
        return emails

    def _parse_message(self, msg_data, fallback_id=None):
        headers = msg_data.get('payload', {}).get('headers', [])
        subject = sender = date = ''

        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            elif header['name'] == 'From':
                sender = header['value']
            elif header['name'] == 'Date':
                date = header['value']

        snippet = msg_data.get('snippet', '')
        body = self._extract_plain_text_body(msg_data.get('payload', {}))

        return {
            'id': msg_data.get('id', fallback_id),
            'thread_id': msg_data.get('threadId'),
            'subject': subject,
            'sender': sender,
            'date': date,
            'content': body or snippet,
            'snippet': snippet,
            'labels': msg_data.get('labelIds', []),
            'attachments': []
        }

    def _extract_plain_text_body(self, payload):
        if not isinstance(payload, dict):
            return ''

        body = payload.get('body', {}) or {}
        data = body.get('data')
        if payload.get('mimeType') == 'text/plain' and data:
            try:
                return base64.urlsafe_b64decode(data).decode('utf-8')
            except Exception:
                return ''

        for part in payload.get('parts', []) or []:
            extracted = self._extract_plain_text_body(part)
            if extracted:
                return extracted
        return ''

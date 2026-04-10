import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class JSMClient:
    def __init__(self):
        self.base = f"https://{settings.CONFLUENCE_DOMAIN}/rest/servicedeskapi"
        self.session = requests.Session()
        self.session.auth = (settings.CONFLUENCE_EMAIL, settings.CONFLUENCE_API_TOKEN)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-ExperimentalApi': 'opt-in',
        })

    def is_customer(self, email: str) -> bool:
        try:
            r = self.session.get(
                f"{self.base}/servicedesk/{settings.JSM_SERVICE_DESK_ID}/customer",
                params={'query': email}
            )
            if r.status_code != 200:
                return False
            customers = r.json().get('values', [])
            return any(c.get('emailAddress', '').lower() == email.lower() for c in customers)
        except Exception as e:
            logger.warning(f"JSM is_customer check failed for {email}: {e}")
            return False

    def create_request(self, user_email: str, request_type_id: str, summary: str, description: str, fields: dict = None):
        payload = {
            'serviceDeskId': settings.JSM_SERVICE_DESK_ID,
            'requestTypeId': request_type_id,
            'requestFieldValues': {
                'summary': summary,
                'description': description,
                **(fields or {}),
            },
            'raiseOnBehalfOf': user_email,
        }
        r = self.session.post(f"{self.base}/request", json=payload)
        r.raise_for_status()
        return r.json()

    def get_customer_requests(self, user_email: str):
        r = self.session.get(
            f"{self.base}/request",
            params={'requestStatus': 'ALL_REQUESTS', 'requestOwnership': 'PARTICIPATED_REQUESTS'}
        )
        r.raise_for_status()
        return r.json().get('values', [])

    def get_request(self, request_id: str):
        r = self.session.get(f"{self.base}/request/{request_id}")
        r.raise_for_status()
        return r.json()

    def get_request_types(self):
        r = self.session.get(
            f"{self.base}/servicedesk/{settings.JSM_SERVICE_DESK_ID}/requesttype"
        )
        r.raise_for_status()
        return r.json().get('values', [])

import os
import requests
import json
import logging
import urllib3

from django.conf import settings
from django.core.cache import cache

from .models import ServiceNowIncident, TDXConfiguration
#from akips.task import update_incident

# Get an instance logger
logger = logging.getLogger(__name__)

# The InCommon intermediate CA is not in the default cert bundle, disable warning.
urllib3.disable_warnings()

class TDX:
    # Class to handle interactions with TeamDynamix
    auth_mode = "user"
    ticket_app_id = 34

    def __init__(self):
        config = TDXConfiguration.get_solo()
        defaults = TDXConfiguration.env_defaults()

        self.enabled = config.enabled
        self.base_url = (config.api_url or defaults['api_url']).rstrip('/')
        self.username = config.username or defaults['username']
        self.password = config.password or defaults['password']
        self.apikey = config.apikey or defaults['apikey']
        self.flow_base = (config.flow_url or defaults['flow_url']).rstrip('/')
        self.session = requests.Session()
        self.token = None

    def _is_enabled(self):
        if not self.enabled:
            logger.info('TDX integration is disabled')
            return False
        return True

    def init_session(self) -> bool:
        ''' Initialize the API session '''
        if not self._is_enabled():
            return False
        if not self.base_url or not self.username or not self.password:
            logger.warning('TDX API settings are incomplete')
            return False

        logger.info(f"Logging into {self.base_url} as {self.username}")
        response = requests.post(
            self.base_url + "/api/auth",
            json={
                "username": self.username,
                "password": self.password
            },
        )
        if response.ok:
            self.token = response.text

        if self.token is None:
            raise RuntimeError("unable to obtain bearer token")
        else:
            logger.info(f"Login was successful, token has been set")

        self.session.headers.update(
            {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.token}",
            }
        )
        return True

    # tdx_method("GET", "/api/applications")
    def get_applications(self):
        ''' get TDX applications '''
        if self.token is None and not self.init_session():
            return None

        logger.info(f"Getting applications")
        response = self.session.get(
            self.base_url + f"/api/applications",
        )
        # logger.info(f"response {response}")
        if response.ok:
            applications = response.json()
            for app in applications:
                if app['Name'] == 'Tickets':
                    self.ticket_app_id = app['AppID']
                    logger.info(f"Found ticket app id {app['AppID']}")
        else:
            logger.error("applications lookup failed")

    # tdx_method("GET", "/api/{appId}/tickets/{id}")
    def get_ticket(self, number):
        ''' get a ticket '''
        if self.token is None and not self.init_session():
            return None

        logger.info(f"Getting ticket {number}")
        response = self.session.get(
            self.base_url + f"/api/{self.ticket_app_id}/tickets/{number}",
        )
        logger.info(f"response {response}")
        if response.ok:
            return response.json()
        else:
            logger.error("ticket lookup failed")
            return None

    # tdx_method("POST", "/api/{appId}/tickets/search")
    def get_ticket_search(self):
        ''' perform a ticket search '''
        if self.token is None and not self.init_session():
            return None

        response = self.session.post(
            self.base_url + f"/api/{self.ticket_app_id}/tickets/search",
            json={
                'RequestorNameSearch': 'Service Account (oc_console) 605000-api-008',
                'StatusClassIDs': [1],
                'MaxResults': 50
            },
        )
        if response.ok:
            return response.json()
        else:
            logger.error("TDX ticket search failed")
            return None

    # tdx_method("POST", "/api/{appId}/tickets")
    def create_ticket(self, group, priority, subject, description):
        ''' create a ticket '''
        if self.token is None and not self.init_session():
            return None

        response = self.session.post(
            self.base_url + f"/api/{self.ticket_app_id}/tickets",
            json={
                'TypeID': 1,        # Int32, required
                'Title': subject,   # String, required
                'AccountID': 967,   # Int32, required
                'StatusID': 1,      # Int32, required
                'PriorityID': 19,   # Int32, required
                'RequesterUid': 'bf4b62f1-c860-ef11-991b-83b4b06ae47d',  # Guid, required
                'Description': description   # String
            },
        )
        if response.ok:
            return response.json()
        else:
            logger.error('TDX create ticket error, response code: %i %s' % (response.status_code, response.reason))
            return None

    # tdx_method("POST", "/api/{appId}/tickets/{id}/feed")
    def update_ticket(self, number, comment):
        ''' update a ticket '''
        if self.token is None and not self.init_session():
            return None

        update_url = self.base_url + f"/api/{self.ticket_app_id}/ticket/{number}/feed"
        logger.info(
            "TDX update attempt: ticket=%s app_id=%s comment_len=%s",
            number,
            self.ticket_app_id,
            len(comment or ''),
        )

        response = self.session.post(
            update_url,
            json={
                'Comments': comment,   # String
                'IsPrivate': False,
                'IsRichHtml': False,
                #'IsCommunication': False,
            },
        )
        if response.ok:
            logger.info(
                "TDX update success: ticket=%s status=%s",
                number,
                response.status_code,
            )
            return response.json()
        else:
            logger.error(
                "TDX update failed: ticket=%s status=%s reason=%s body=%s",
                number,
                response.status_code,
                response.reason,
                (response.text or '')[:500],
            )
            return None

    def create_ticket_flow(self, group, priority, subject, description):
        ''' Use incident_in flow to create incident ticket '''
        ''' https://us1.teamdynamix.com/tdapp/app/flow/api/v1/start/uncchapelhill/incident_in_prod/create_ticket?waitForResults=true '''

        if not self._is_enabled():
            return None
        if not self.flow_base or not self.apikey:
            logger.warning('TDX flow settings are incomplete')
            return None

        response = self.session.post(
            self.flow_base + f"/create_ticket?waitForResults=true",
            json={
                'apikey': self.apikey,
                'assignmentGroup': group,
                'priority': priority,
                'subject': subject,
                'description': description,
                'deptNum': "605000"
            },
        )
        if response.ok:
            data = response.json()
            logger.info(f"Create response {data['data']}")
            return data['data']
        else:
            logger.error('TDX create ticket error, response code: %i %s' % (response.status_code, response.reason))
            return None

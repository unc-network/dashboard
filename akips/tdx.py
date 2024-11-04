import os
import requests
import json
import logging

from django.conf import settings
from django.core.cache import cache

from .models import ServiceNowIncident
#from akips.task import update_incident

# Get an instance logger
logger = logging.getLogger(__name__)

# The InCommon intermediate CA is not in the default cert bundle, disable warning.
requests.packages.urllib3.disable_warnings()

class TDX:
    # Class to handle interactions with TeamDynamix
    auth_mode = "user"
    base_url = os.getenv('TDX_URL', 'https://tdx.unc.edu/TDWebApi/')
    username = os.getenv('TDX_USERNAME', '')
    password = os.getenv('TDX_PASSWORD', '')
    apikey   = os.getenv('TDX_APIKEY', '')
    flow_base = 'https://us1.teamdynamix.com/tdapp/app/flow/api/v1/start/uncchapelhill/incident_in_prod/'
    session = requests.Session()
    token = None
    ticket_app_id = 34

    def init_session(self) -> None:
        ''' Initialize the API session '''
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

    # tdx_method("GET", "/api/applications")
    def get_applications(self):
        ''' get TDX applications '''
        if self.token is None:
            self.init_session()

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
        if self.token is None:
            self.init_session()

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
        if self.token is None:
            self.init_session()

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

    # tdx_method("POST", "/api/{appId}/tickets/search")
    def create_ticket(self):
        ''' create a ticket '''
        if self.token is None:
            self.init_session()

        response = self.session.post(
            self.base_url + f"/api/{self.ticket_app_id}/tickets",
            json={
                'TypeID': 0,        # Int32, required
                'Title': '',        # String, required
                'AccountID': 0,     # Int32, required
                'StatusID': 0,      # Int32, required
                'PriorityID': 0,    # Int32, required
                'RequesterUid': 0,  # Guid, required
                'Description': ''   # String
            },
        )
        if response.ok:
            return response.json()
        else:
            logger.error('TDX create ticket error, response code: %i %s' % (response.status_code, response.reason))
            return None

    def create_ticket_flow(self, group, priority, subject, description):
        ''' Use incident_in flow to create incident ticket '''
        ''' https://us1.teamdynamix.com/tdapp/app/flow/api/v1/start/uncchapelhill/incident_in_prod/create_ticket?waitForResults=true '''

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

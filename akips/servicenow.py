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

class ServiceNow:
    # Class to handle interactions with ServiceNow
    url = os.getenv('SN_URL', '')
    instance = os.getenv('SN_INSTANCE', '')
    username = os.getenv('SN_USERNAME', '')
    password = os.getenv('SN_PASSWORD', '')
    session = requests.Session()

    def create_incident(self, group, description, caller_id=None, severity=None, work_notes=None):
        ''' Create a new SN incident '''
        # Set proper headers
        headers = {
            "Content-Type": "application/json", 
            "Accept": "application/json"
        }

        # populate the details
        body = {
            # servicenow incident table api fields
            'caller_id': self.username,
            # 'business_service': 'Network: IP Services',
            'assignment_group': group,
            'category': 'Network',
            'short_description': "OCNES: {}".format(description),
        }

        if caller_id:
            body['caller_id'] = caller_id

        if severity == 'Critical':
            # "1 - Critical" servicenow priority
            body['impact'] = '1'
            body['urgency'] = '1'
        elif severity == 'High':
            # "2 - High" servicenow priority
            body['impact'] = '1'
            body['urgency'] = '2'
        elif severity == 'Moderate':
            # "3 - Moderate" servicenow priority
            body['impact'] = '2'
            body['urgency'] = '2'
        elif severity == 'Low':
            # "4 - Low" servicenow priority
            body['impact'] = '3'
            body['urgency'] = '2'

        if work_notes:
            body['work_notes'] = work_notes
        
        # Call HTTP POST
        sn_url = "https://{}.service-now.com/api/now/table/incident".format(self.instance)
        logger.debug("url: {}",format(sn_url))
        logger.debug("headers: {}".format(headers))
        logger.debug("data: {}".format(body))
        response = requests.post(sn_url, auth=(self.username,self.password), headers=headers, data=json.dumps(body))

        # All requests return a 201 HTTP status code even if there is an error.  Must check 'status' in result.
        if response.status_code != 201:
            logger.debug('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return None

        # Decode the JSON response and update the database
        result_data = response.json()
        logger.debug("Result: {}".format(result_data))
        sn_incident = ServiceNowIncident.objects.create(
            number=result_data['result']['number'],
            sys_id=result_data['result']['sys_id'],
            instance=self.instance
        )
        return sn_incident

    def get_incident(self, instance, sys_id):
        ''' Refresh a local SN incident '''

        # Set proper headers
        headers = {
            "Content-Type":"application/json", 
            "Accept":"application/json"
        }

        # Call HTTP GET
        sn_url = "https://{}.service-now.com/api/now/table/incident/{}".format(instance,sys_id)
        logger.debug("url: {}".format(sn_url))
        logger.debug("headers: {}".format(headers))
        response = requests.get(sn_url, auth=(self.username, self.password), headers=headers)

        # All requests return a 200 HTTP status code even if there is an error.
        if response.status_code != 200:
            logger.warn('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        logger.debug("Result: {}".format(result_data))

        return result_data['result']

    def get_recent_incidents(self, id='svc-CHG-605000-oc', category='Network', limit=10):
        ''' Find recently created incidents from a group '''

        # Set proper headers
        headers = {
            "Content-Type":"application/json", 
            "Accept":"application/json"
        }
        # Set parameters
        params = {
            #'sysparm_query': "category={}^ORDERBYDESCsys_created_on".format(category),
            # 'sysparm_query': "active=True^category={}^ORDERBYDESCsys_created_on".format(category),
            'sysparm_query': "active=True^sys_created_by={}^ORDERBYDESCsys_created_on".format(id),
            'sysparm_limit': limit
        }

        # Call HTTP GET
        sn_url = "https://{}.service-now.com/api/now/table/incident".format(self.instance)
        logger.debug("url: {}".format(sn_url))
        logger.debug("headers: {}".format(headers))
        logger.debug("params: {}".format(params))
        response = requests.get(sn_url, auth=(self.username, self.password), headers=headers, params=params)

        # All requests return a 200 HTTP status code even if there is an error.
        if response.status_code != 200:
            logger.warn('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        logger.debug("Result: {}".format(result_data))

        return result_data['result']

    def associate_incident(self, number, work_notes=None):
        ''' Search for SN incident by number '''

        # Set proper headers
        headers = {
            "Content-Type":"application/json", 
            "Accept":"application/json"
        }

        # Set parameters
        params = {
            #'sysparm_exclude_reference_link': True,
            'sysparm_query': 'number={}'.format(number),
        }

        # Call HTTP GET
        sn_url = "https://{}.service-now.com/api/now/table/incident".format(self.instance)
        logger.debug("url: {}".format(sn_url))
        logger.debug("headers: {}".format(headers))
        logger.debug("params: {}".format(params))
        response = requests.get(sn_url, auth=(self.username, self.password), headers=headers, params=params)

        # All requests return a 200 HTTP status code even if there is an error.
        if response.status_code != 200:
            logger.warn('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return None

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        logger.debug("Result: {}".format(result_data))

        # Decode the JSON response and update the database
        if len( result_data['result'] ) == 1:
            # result will be a list and should have just one entry
            sn_incident, created = ServiceNowIncident.objects.get_or_create(
                number=result_data['result'][0]['number'],
                sys_id=result_data['result'][0]['sys_id'],
                instance=self.instance
            )
            if created:
                logger.debug("New database entry recorded for incident")
        else:
            logger.warn("Unable to map number to a single instance")
            sn_incident = None

        return sn_incident


    def update_incident(self, number, work_notes):
        ''' Update an existing SN incident '''

        try:
            incident = ServiceNowIncident.objects.get(number=number)
        except ServiceNowIncident.DoesNotExist:
            logger.warning("Unable to find servicenow ticket {} in database".format(number))
            return

        # Set proper headers
        headers = {
            "Content-Type":"application/json", 
            "Accept":"application/json"
        }

        # Define the update data
        body = {
            'work_notes': work_notes,
        }

        # Call HTTP PUT for update
        sn_url = "https://{}.service-now.com/api/now/table/incident/{}".format(incident.instance,incident.sys_id)
        logger.debug("url: {}".format(sn_url))
        logger.debug("headers: {}".format(headers))
        logger.debug("data: {}".format(body))
        response = requests.put(sn_url, auth=(self.username, self.password), headers=headers ,data=json.dumps(body))

        # All requests return a 201 HTTP status code even if there is an error.  Must check 'status' in result.
        if response.status_code != 201:
            logger.debug('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        for entry in result_data['result']:
            logger.debug("Result: {}".format(entry))
            if entry['status'] == 'error':
                logger.error("Failed to update ServiceNow Incident {}".format(entry['error_message']))
                return 
            else:
                return {'number': entry['display_value'], 'link': entry['record_link']}

    def create_incident_import(self, group, description, callerid=None, severity=None, work_notes=None):
        ''' Create a new SN incident with UNC import API '''
        # Set proper headers
        headers = {"Content-Type":"application/json", "Accept":"application/json"}

        data = {
            # Required fields
            'u_assignment_group': group,
            'u_caller_id': self.username,
            'u_short_description': "OCNES: {}".format(description),

            # Optional fields
            #'u_business_service': 'Network: IP Services',
            #'u_impact': '2',        # 1 (Critical), 2 (Significant), 3 (Minor)
            #'u_urgency': '2',       # 1 (High), 2 (Medium), 3 (Low)
            #'u_opened_by': user,             # optional
            #'u_work_notes': '',            # optional

            # u_category is not listed in API doc as supported on create,
            # but it is required to close an incident and can be set here
            'u_category': 'Network',     # optional
        }
        if callerid:
            data['u_caller_id'] = callerid
        if severity == 'Critical':
            # "1 - Critical" servicenow priority
            data['u_impact'] = '1'
            data['u_urgency'] = '1'
        elif severity == 'High':
            # "2 - High" servicenow priority
            data['u_impact'] = '1'
            data['u_urgency'] = '2'
        elif severity == 'Moderate':
            # "3 - Moderate" servicenow priority
            data['u_impact'] = '2'
            data['u_urgency'] = '2'
        elif severity == 'Low':
            # "4 - Low" servicenow priority
            data['u_impact'] = '3'
            data['u_urgency'] = '2'

        if work_notes:
            data['u_work_notes'] = work_notes

        logger.debug("data: {}".format(data))
        # Do the HTTP request
        response = requests.post(self.url, auth=(self.username,self.password), headers=headers ,data=json.dumps(data))

        # All requests return a 201 HTTP status code even if there is an error.  Must check 'status' in result.
        if response.status_code != 201:
            logger.debug('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        for entry in result_data['result']:
            logger.debug("Result: {}".format(entry))
            # Example entry for success
            # {
            #     "display_name": "number",
            #     "display_value": "INC0319066",
            #     "record_link": "https://uncchdev.service-now.com/api/now/table/incident/08bd97cc970ad5502d6274671153af52",
            #     "status": "inserted",
            #     "sys_id": "08bd97cc970ad5502d6274671153af52",
            #     "table": "incident",
            #     "transform_map": "Incident In"
            # }
            if entry['status'] == 'error':
                logger.error("Failed to create ServiceNow Incident {}".format(entry['error_message']))
                return 
            else:
                return {'number': entry['display_value'], 'link': entry['record_link']}

    def update_incident_import(self, number, work_notes):
        ''' Update an existing SN incident '''

        # Set proper headers
        headers = {"Content-Type":"application/json", "Accept":"application/json"}

        # Resolving is not allowed by the API
        data = {
            'u_number': number,
            #'u_category': 'Network',     # optional
            #'u_state': 'In Progress',    # optional: New, In Progress, On Hold, Resolved, Canceled
                                        # resolved requires fields we can't set in the api
            ### create fields below are optional
            #'u_assignment_group': 'IP-Services',
            #'u_caller_id': "wew",
            #'u_short_description': "create test",
            #'u_business_service': 'Network: IP Services',
            #'u_impact': '2',        # 1 (Critical), 2 (Significant), 3 (Minor)
            #'u_urgency': '2',       # 1 (High), 2 (Medium), 3 (Low)
            #'u_opened_by': 'wew',
            'u_work_notes': work_notes,
        }

        # Do the HTTP request
        response = requests.post(self.url, auth=(self.username, self.password), headers=headers ,data=json.dumps(data))

        # All requests return a 201 HTTP status code even if there is an error.  Must check 'status' in result.
        if response.status_code != 201:
            logger.debug('Status: {}, Headers: {}, Error Response: {}'.format(response.status_code, response.headers, response.json()))
            return

        # Decode the JSON response into a dictionary and use the data
        result_data = response.json()
        for entry in result_data['result']:
            logger.debug("Result: {}".format(entry))
            if entry['status'] == 'error':
                logger.error("Failed to update ServiceNow Incident {}".format(entry['error_message']))
                return 
            else:
                return {'number': entry['display_value'], 'link': entry['record_link']}

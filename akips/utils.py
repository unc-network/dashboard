from django.conf import settings
import os
import logging
import requests
import re
import pprint
import ipaddress

# Get an instance logger
logger = logging.getLogger(__name__)


class AKIPS:
    # Class to handle interactions with the NIT database
    akips_server = os.getenv('AKIPS_SERVER', '')
    akips_username = os.getenv('AKIPS_USERNAME', '')
    akips_password = os.getenv('AKIPS_PASSWORD', '')
    session = requests.Session()

    def get_devices(self):
        ''' Pull a list of fields for all devices in akips '''
        params = {
            'cmds': 'mget text * sys /ip.addr|SNMPv2-MIB.sysName|SNMPv2-MIB.sysDescr|SNMPv2-MIB.sysLocation/',
        }
        text = self.get(params=params)
        if text:
            data = {} 
            # Data comes back as 'plain/text' type so we have to parse it
            # Example output, data on each line:
            # 152.19.198.29 sys ip4addr = 152.19.198.29
            # 152.19.198.29 sys SNMPv2-MIB.sysDescr = VMware ESXi 6.5.0 build-8294253 VMware Inc. x86_64
            # 152.19.198.29 sys SNMPv2-MIB.sysName = bc11-n01.isis.unc.edu
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s(\S+)\s(\S+)\s=\s(.*)$", line)
                if match:
                    if match.group(1) not in data:
                        # Populate a default entry for all desired fields
                        data[ match.group(1) ] = {
                            'ip4addr': '',
                            'SNMPv2-MIB.sysName': '',
                            'SNMPv2-MIB.sysDescr': '',
                            'SNMPv2-MIB.sysLocation': '',
                        }
                    # Save this attribute value to data
                    data[ match.group(1) ][ match.group(3) ] = match.group(4)
            logger.debug("Found {} devices in akips".format( len( data.keys() )))
            return data
        return None

    def get_device(self, name):
        ''' Pull the entire configuration for a single device '''
        params = {
            'cmds': 'mget * {} * *'.format(name),
        }
        text = self.get(params=params)
        if text:
            data = {} 
            # Data comes back as 'plain/text' type so we have to parse it.  Example:
            # 152.19.198.29 sys SNMPv2-MIB.sysName = bc11-n01.isis.unc.edu
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s(\S+)\s(\S+)\s=(\s(.*))?$", line)
                if match:
                    name = match.group(1)
                    if match.group(2) not in data:
                       # initialize the dict of attributes
                       data[ match.group(2) ] = {}
                    if match.group(5):
                        # Save this attribute value to data
                        data[ match.group(2) ][ match.group(3) ] = match.group(5)
                    else:
                        # save a blank string if there was nothing after equals
                        data[ match.group(2) ][ match.group(3) ] = ''
            if name:
                data['name'] = name
            logger.debug("Found device {} in akips".format( data ))
            return data
        return None

    def get_unreachable(self):
        ''' Pull a list of unreachable IPv4 ping devices '''
        params = {
            'cmds': 'mget * * ping4 PING.icmpState value /down/',
        }
        text = self.get(params=params)
        if text:
            data = {} 
            # Data comes back as 'plain/text' type so we have to parse it
            # Example output, data on each line:
            # 152.19.198.33 ping4 PING.icmpState = 1,down,1519844016,1646695881,152.19.198.33
            # 152.19.198.37 ping4 PING.icmpState = 1,down,1519844016,1642967467,152.19.198.37
            # 172.22.37.68 ping4 PING.icmpState = 1,down,1443798140,1659405567,172.22.37.68
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s(\S+)\s(\S+)\s=\s(\S+),(\S+),(\S+),(\S+),(\S+)$", line)
                if match:
                    if match.group(1) not in data:
                        # Populate a default entry for all desired fields
                        data[ match.group(1) ] = {
                            'child': match.group(2),
                            'attribute': match.group(3),
                            'index': match.group(4),
                            'state': match.group(5),
                            'device_added': match.group(6), # epoch in local timezone
                            'event_start': match.group(7),  # epoch in local timezone
                            'ip4addr': match.group(8),
                        }
                    # Save this attribute value to data
                    #data[ match.group(1) ][ match.group(3) ] = match.group(4)
            logger.debug("Found {} devices in akips".format( len( data.keys() )))
            return data
        return None

    def get(self, params=None):
        ''' Search and Read Objects: GET Method '''
        url = 'https://' + self.akips_server + '/api-db'
        logger.debug("WAPI GET %s" % (url))
        logger.debug("WAPI GET params: " + pprint.pformat(params))
        params['username'] = self.akips_username
        params['password'] = self.akips_password
        # GET requests have 2 args: URL, HEADERS
        r = self.session.get(url, params=params, verify=False)

        # Return Status/Errors
        # 200	Normal return. Referenced object or result of search in body.
        if r.status_code != 200:
            # Errors come back in the page text and look like below:
            # ERROR: api-db invalid username/password
            logger.warning('WAPI request finished with error, response code: %i %s'
                        % (r.status_code, r.reason))
            #json_object = r.json()
            #logger.warning('Error message: %s' % json_object['Error'])
            return None
        else:
            logger.debug('API request finished successfully, response code: %i %s'
                        % (r.status_code, r.reason))
            return r.text
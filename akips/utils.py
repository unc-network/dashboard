from django.conf import settings
import os
import logging
import requests
import re
import pprint
import json
import ipaddress

# Get an instance logger
logger = logging.getLogger(__name__)

# The InCommon intermediate CA is not in the default cert bundle, disable warning.
requests.packages.urllib3.disable_warnings()

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

    def get_group_membership(self):
        ''' Pull a list of device to group memberships '''
        params = {
            'cmds': 'mgroup device *',
        }
        text = self.get(params=params)
        if text:
            data = {} 
            # Data comes back as 'plain/text' type so we have to parse it
            # Example output, data on each line:
            # 172.28.12.10 = 2-Campus-Services,3-Building-Entrance-Switches,4-Physical-Plant-Maintenance-Shop,admin,Extreme,user
            # 172.28.12.11 = 2-Campus-Services,4-Physical-Plant-Maintenance-Shop,admin,Liebert,poll_oid_20,user
            # 172.28.12.112 = 2-Campus-Services,3-Building-Entrance-Switches,4-Lenoir-Hall,admin,Extreme,user
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s=\s(.*)$", line)
                if match:
                    if match.group(1) not in data:
                        # Populate a default entry for all desired fields
                        data[ match.group(1) ] = match.group(2).split(',')
                    # Save this attribute value to data
                    #data[ match.group(1) ][ match.group(3) ] = match.group(4)
            logger.debug("Found {} device and group mappings in akips".format( len( data.keys() )))
            return data
        return None

    def get_maintenance_mode(self):
        ''' Pull a list of devices in maintenance mode '''
        params = {
            'cmds': 'mget * * any group maintenance_mode',
        }
        text = self.get(params=params)
        if text:
            data = []
            # Data comes back as 'plain/text' type so we have to parse it
            # Example output, data on each line with something at the end:
            # GH-Art_Lab_102
            # GH-Art_Lab_113C
            # HackNC-2
            # ok: mget * * any group maintenance_mode
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)$", line)
                if match:
                    data.append( match.group(1) )
            logger.debug("Found {} devices in maintenance mode".format( len( data )))
            return data
        return None

    def set_maintenance_mode(self, device_name, mode=True):
        ''' Set mantenance mode on or off for a device '''
        params = {
            'function': 'web_manual_grouping',
            'type': 'device',
            'group': 'maintenance_mode',
            'device': device_name
        }
        if mode == 'True':
            params['mode'] = 'assign'
        else:
            params['mode'] = 'clear'
        text = self.get(section='/api-script',params=params)
        if text:
            logger.debug("Maintenance mode update result {}".format( text ))
            return text
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
            #
            # Example child attribute values
            # ping4	PING.icmpState	1,down,1575702020,1662054938,172.29.172.68
            # sys	SNMP.snmpState	1,down,1575702020,1662054911,
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

    def get_threshold_events(self, period='last1h'):
        ''' Pull a list of unreachable IPv4 ping devices '''
        params = {
            'cmds': 'mget event threshold time last1h'
        }
        text = self.get(params=params)
        if text:
            data = []
            # Data comes back as 'plain/text' type so we have to parse it.  Format expected:
            # {epoch} {parent} {child} {attribute} threshold {flags} {rule exceeded} [{child description}]
            # Example output, data on each line:
            # 1662741840 172.29.149.209 cpu.196609 HOST-RESOURCES-MIB.hrProcessorLoad threshold warning,above last5m,avg,90 GenuineIntel: Intel(R) Xeon(R) CPU E5-2658 v2 @ 2.40GHz
            # 1662741900 172.29.170.78 ping4 PING.icmpRtt threshold warning,below last30m,avg,20000 172.29.170.78
            # 1662741960 172.29.149.209 cpu.1.49.2 F5-BIGIP-SYSTEM-MIB.sysMultiHostCpuUsageRatio1m threshold warning,above last5m,avg,90 1
            lines = text.split('\n')
            for line in lines:
                match = re.match(r'^(?P<epoch>\S+)\s(?P<parent>\S+)\s(?P<child>\S+)\s(?P<attribute>\S+)\sthreshold\s(?P<flags>\S+)\s(?P<rule_exceeded>\S+)\s(?P<child_description>.*)$', line)
                if match:
                    entry = {
                        'epoch': match.group('epoch'),
                        'parent': match.group('parent'),
                        'child': match.group('child'),
                        'attribute': match.group('attribute'),
                        'flags': match.group('flags'),
                        'rule_exceeded': match.group('rule_exceeded'),
                    }
                    if match.group('child_description'):
                        entry['child_description'] = match.group('child_description'),
                    data.append(entry)
            logger.debug("Found {} devices in akips".format( len( data )))
            return data
        return None

    def get(self, section='/api-db/', params=None):
        ''' Search and Read Objects: GET Method '''
        #url = 'https://' + self.akips_server + '/api-db'
        url = 'https://' + self.akips_server + section
        logger.debug("WAPI GET %s" % (url))
        logger.debug("WAPI GET params: " + pprint.pformat(params))
        params['username'] = self.akips_username
        params['password'] = self.akips_password
        # GET requests have 2 args: URL, HEADERS
        # Verify is off because the 'certifi' python module is missing the InCommon interim CA
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
            if re.match(r'^ERROR:',r.text):
                logger.warn("AKIPS API failed with {}".format(r.text))
                return r.text
            else:
                return r.text

class NIT:
    # Class to handle interactions with the NIT
    nit_server = os.getenv('NIT_SERVER', '')
    nit_username = os.getenv('NIT_USERNAME', '')
    nit_password = os.getenv('NIT_PASSWORD', '')
    session = requests.Session()

    def get_device_data(self, params=None):
        ''' Search and Read Objects: GET Method '''
        url = 'https://' + self.nit_server + '/json/full_dump_with_aps.json'
        logger.debug("WAPI GET %s" % (url))
        logger.debug("WAPI GET params: " + pprint.pformat(params))
        #params['username'] = self.nit_username
        #params['password'] = self.nit_password
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
            return json.loads(r.text)
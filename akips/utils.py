from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.template.loader import render_to_string

import os
import requests
import re
import pprint
import json
import ipaddress
import logging
import time
from datetime import datetime, timedelta

from .models import Device, Unreachable, Status, Summary, ServiceNowIncident
#from akips.task import update_incident

# Get an instance logger
logger = logging.getLogger(__name__)

# The InCommon intermediate CA is not in the default cert bundle, disable warning.
requests.packages.urllib3.disable_warnings()

class AKIPS:
    # Class to handle interactions with AKiPS instance
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

    def set_maintenance_mode(self, device_name, mode='True'):
        ''' Set maintenance mode on or off for a device '''
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

    def get_device_by_ip(self, ipaddr, use_cache=True):
        # Search for a device by an alternate IP address
        # This makes use of a special site script and not the normal api
        cache_key = 'device_name_' + ipaddr
        cache_timeout = 3600

        # Try cache first.  Doing this since it's an extra akips call.
        device_name = cache.get(cache_key)
        if use_cache and device_name:
            logger.debug("cache hit: {} as {}".format(cache_key, device_name))
            return device_name

        # Hit the akips api
        params = {
            'function': 'web_find_device_by_ip',
            'ipaddr': ipaddr
        }
        text = self.get(section='/api-script/', params=params)
        #logger.debug("api result: {}".format(text))
        if text:
            # Output examples:
            # IP Address 10.194.200.65 is configured on cisco-sw1
            # IP Address 10.194.200.99 is not configured on any devices
            lines = text.split('\n')
            for line in lines:
                match = re.match("IP Address (\S+) is configured on (\S+)", line)
                if match:
                    input = match.group(1)
                    device = match.group(2)
                    logger.debug("found {} on {}".format( input, device ))
                    cache.set(cache_key, device, cache_timeout)
                    return device
        return None

    def get_unreachable(self):
        ''' Pull a list of unreachable IPv4 ping devices '''
        params = {
            #'cmds': 'mget * * ping4 PING.icmpState value /down/',
            #'cmds': 'mget * * /ping4|sys/ * value /down/',
            'cmds': 'mget * * * /PING.icmpState|SNMP.snmpState/ value /down/',
            #'cmds': 'mget * * /ping4|sys/ /PING.icmpState|SNMP.snmpState/ value /down/'
        }
        text = self.get(params=params)
        if text:
            #data = []
            data = {}
            # Data comes back as 'plain/text' type so we have to parse it
            # Example output, data on each line:
            # 172.29.248.54 ping4 PING.icmpState = 1,down,1484685257,1657029502,172.29.248.54
            # 172.29.248.54 sys SNMP.snmpState = 1,down,1484685257,1657029499,
            # CrN-082-SmithCenter-AP_Stats_Table ping4 PING.icmpState = 1,down,1605595895,1656331597,172.29.94.63
            # CrN-082-SmithCenter-AP_Talent_Table ping4 PING.icmpState = 1,down,1641624705,1646101757,172.29.94.112
            #
            # Example child attribute values
            # ping4	PING.icmpState	1,down,1575702020,1662054938,172.29.172.68
            # sys	SNMP.snmpState	1,down,1575702020,1662054911,
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s(\S+)\s(\S+)\s=\s(\S+),(\S+),(\S+),(\S+),(\S+)?$", line)
                if match:
                    name = match.group(1)
                    attribute = match.group(3)
                    # event_start = match.group(7)    # epoch in local timezone
                    event_start = datetime.fromtimestamp(int( match.group(7) ), tz=timezone.get_current_timezone())
                    if name not in data:
                        # populate a starting point for this device
                        data[name] = { 
                            'name': name,
                            'ping_state': 'up',
                            'snmp_state': 'unreported',
                            'event_start': event_start  # epoch in local timezone
                        }
                    if attribute == 'PING.icmpState':
                        data[name]['child'] = match.group(2),
                        data[name]['ping_state'] =  match.group(5)
                        data[name]['index'] = match.group(4)
                        # data[name]['device_added'] = match.group(6) # epoch in local timezone
                        data[name]['device_added'] = datetime.fromtimestamp(int( match.group(6) ), tz=timezone.get_current_timezone())
                        # data[name]['event_start'] = match.group(7)  # epoch in local timezone
                        data[name]['event_start'] = datetime.fromtimestamp(int( match.group(7) ), tz=timezone.get_current_timezone())
                        data[name]['ip4addr'] = match.group(8)
                    elif attribute == 'SNMP.snmpState':
                        data[name]['child'] = match.group(2),
                        data[name]['snmp_state'] =  match.group(5)
                        data[name]['index'] = match.group(4)
                        # data[name]['device_added'] = match.group(6) # epoch in local timezone
                        data[name]['device_added'] = datetime.fromtimestamp(int( match.group(6) ), tz=timezone.get_current_timezone())
                        # data[name]['event_start'] = match.group(7)  # epoch in local timezone
                        data[name]['event_start'] = datetime.fromtimestamp(int( match.group(7) ), tz=timezone.get_current_timezone())
                        data[name]['ip4addr'] = None
                    if event_start < data[name]['event_start']:
                        data[name]['event_start'] = event_start
            logger.debug("Found {} devices in akips".format( len( data )))
            logger.debug("data: {}".format(data))
            return data
        return None

    def get_unreachable_status(self):
        ''' Pull a list of unreachable devices from status tables'''
        data = {}

        list = Status.objects.filter(value='down').filter(attribute__in=['PING.icmpState','SNMP.snmpState'])
        for entry in list:
            name = entry.device.name
            # event_start = str(int(entry.last_change.timestamp()))   # workaround string of timestamp
            event_start = entry.last_change   # workaround string of timestamp
            if name not in data:
                # populate a starting point for this device
                data[ name ] = { 
                    'name': name,
                    'ping_state': 'up',         # default for ping
                    'snmp_state': 'unreported', # default for snmp
                    'event_start': event_start  # epoch in local timezone
                }
            if entry.attribute == 'PING.icmpState':
                data[name]['child'] = entry.child
                data[name]['ping_state'] =  entry.value
                data[name]['index'] = entry.index
                data[name]['device_added'] = entry.device_added
                data[name]['event_start'] = event_start
                data[name]['ip4addr'] = entry.ip4addr
            elif entry.attribute == 'SNMP.snmpState':
                data[name]['child'] = entry.child
                data[name]['snmp_state'] =  entry.value
                data[name]['index'] = entry.index
                data[name]['device_added'] = entry.device_added
                data[name]['event_start'] = event_start
                data[name]['ip4addr'] = entry.ip4addr
            if event_start < data[name]['event_start']: # use earlier of date if ping and snmp
                data[name]['event_start'] = event_start

        return data

    def get_status(self, type='ping'):
        ''' Pull the status values we are most interested in '''
        if type == 'ups':
            params = { 'cmds': 'mget * * ups UPS-MIB.upsOutputSource' }
            # command: mget * * * UPS-MIB.upsOutputSource
            # 172.28.12.11 ups UPS-MIB.upsOutputSource = 3,normal,1473262633,1633441440,
            # 172.28.12.121 ups UPS-MIB.upsOutputSource = 3,normal,1423715292,1632171420,
            # 172.28.12.128 ups UPS-MIB.upsOutputSource = 3,normal,1423715292,1632171420,
        elif type == 'ping':
            params = { 'cmds': 'mget * * ping4 PING.icmpState' }
            # 172.29.248.54 ping4 PING.icmpState = 1,down,1484685257,1657029502,172.29.248.54
            # CrN-082-SmithCenter-AP_Stats_Table ping4 PING.icmpState = 1,down,1605595895,1656331597,172.29.94.63
            # CrN-082-SmithCenter-AP_Talent_Table ping4 PING.icmpState = 1,down,1641624705,1646101757,172.29.94.112
        elif type == 'snmp':
            params = { 'cmds': 'mget * * sys SNMP.snmpState' }
            # 172.29.248.54 sys SNMP.snmpState = 1,down,1484685257,1657029499,
        elif type == 'battery_test':
            params = { 'cmds': 'mget * * battery LIEBERT-GP-POWER-MIB.lgpPwrBatteryTestResult' }
            # 172.28.12.11 battery LIEBERT-GP-POWER-MIB.lgpPwrBatteryTestResult = 2,passed,1473262633,1695182760,
        else:
            logger.warning("Invalid get status type {}".format(type))
            return None

        text = self.get(params=params)
        if text:
            data = []
            lines = text.split('\n')
            for line in lines:
                match = re.match("^(\S+)\s(\S+)\s(\S+)\s=\s(\S*),(\S*),(\S*),(\S*),(\S*)$", line)
                if match:
                    entry = {
                        'device': match.group(1),
                        'child': match.group(2),
                        'attribute':  match.group(3),
                        'index': match.group(4),
                        'state': match.group(5),
                        'device_added': match.group(6), # epoch in local timezone
                        'event_start': match.group(7),  # epoch in local timezone
                        'ipaddr': match.group(8)
                    }
                    data.append( entry )
            logger.debug("Found {} states in akips".format( len( data ) ))
            return data
        return None

    def get_events(self, type='all', period='last1h'):
        ''' Pull a list of events.  Command syntax:
            mget event {all,critical,enum,threshold,uptime}
            time {time filter} [{parent regex} {child regex}
            {attribute regex}] [profile {profile name}]
            [any|all|not group {group name} ...] '''

        params = {
            'cmds': 'mget event {} time {}'.format(type,period)
        }
        text = self.get(params=params)
        if text:
            data = []
            # Data comes back as 'plain/text' type so we have to parse it.  Format expected:
            # {epoch} {parent} {child} {attribute} threshold {flags} {rule exceeded} [{child description}]
            # Example output, data on each line:
            # 1662741900 172.29.170.78 ping4 PING.icmpRtt threshold warning,below last30m,avg,20000 172.29.170.78
            # 1663646539 CrNR-136-HortonRHHJNO-AP_336 ping4 PING.icmpState enum warning down 172.29.69.6
            # 1663661689 MetE-371-CLLCRH-AP_2 ap.168.189.39.203.11.228 WLSX-WLAN-MIB.wlanAPUpTime uptime warning 5053738
            lines = text.split('\n')
            for line in lines:
                #match = re.match(r'^(?P<epoch>\S+)\s(?P<parent>\S+)\s(?P<child>\S+)\s(?P<attribute>\S+)\sthreshold\s(?P<flags>\S+)\s(?P<rule_exceeded>\S+)\s(?P<child_description>.*)$', line)
                match = re.match(r'^(?P<epoch>\S+)\s(?P<parent>\S+)\s(?P<child>\S+)\s(?P<attribute>\S+)\s(?P<type>\S+)\s(?P<flags>\S+)\s(?P<details>.*)$', line)
                if match:
                    entry = {
                        'epoch': match.group('epoch'),
                        'parent': match.group('parent'),
                        'child': match.group('child'),
                        'attribute': match.group('attribute'),
                        'type': match.group('type'),
                        'flags': match.group('flags'),
                        'details': match.group('details'),
                    }
                    #if match.group('child_description'):
                    #    entry['child_description'] = match.group('child_description'),
                    data.append(entry)
            logger.debug("Found {} events of type {} in akips".format( len( data ), type))
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

class Inventory:
    # Class to handle interactions with the NIT
    inventory_url = os.getenv('INVENTORY_URL', '')
    inventory_token = os.getenv('INVENTORY_TOKEN', '')
    session = requests.Session()

    def get_device_data(self, params=None):
        ''' Search and Read Objects: GET Method '''
        headers = {
            'Authorization': self.inventory_token
        }
        logger.debug("WAPI GET %s" % (self.inventory_url))
        logger.debug("WAPI GET params: " + pprint.pformat(params))
        # GET requests have 2 args: URL, HEADERS
        r = self.session.get(self.inventory_url, headers=headers, params=params, verify=False)

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





# Gives a human-readable uptime string
def pretty_duration(seconds):
    total_seconds = int( seconds )
    # Helper vars:
    MINUTE  = 60
    HOUR    = MINUTE * 60
    DAY     = HOUR * 24

    # Get the days, hours, etc:
    days    = int( total_seconds / DAY )
    hours   = int( ( total_seconds % DAY ) / HOUR )
    minutes = int( ( total_seconds % HOUR ) / MINUTE )
    seconds = int( total_seconds % MINUTE )

    # Build up the pretty string (like this: "N days, N hours, N minutes, N seconds")
    string = ""
    if days > 0:
        string += str(days) + " " + (days == 1 and "day" or "days" ) + ", "
    if len(string) > 0 or hours > 0:
        string += str(hours) + " " + (hours == 1 and "hour" or "hours" ) + ", "
    if len(string) > 0 or minutes > 0:
        string += str(minutes) + " " + (minutes == 1 and "minute" or "minutes" ) + ", "
    string += str(seconds) + " " + (seconds == 1 and "second" or "seconds" )

    return string
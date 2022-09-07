from celery import shared_task
import logging
import time
import re
from datetime import datetime

from django.utils import timezone
from django.db.models import Count

from .models import Device, Unreachable, Summary
from akips.utils import AKIPS, NIT

# Get an isntace of a logger
logger = logging.getLogger(__name__)

@shared_task
def example_task():
    logger.info("task is running")

@shared_task
def refresh_akips_devices():
    logger.info("refreshing akips devices")
    now = timezone.now()

    akips = AKIPS()
    devices = akips.get_devices()
    if devices:
        for key, value in devices.items():
            logger.debug("{}: {}".format(key, value))
            name = re.compile(r'^(?P<tier>\w+)-(?P<bldg_id>\w+)-(?P<bldg_name>\w+)-(?P<type>[a-zA-Z0-9]+)[-_](?P<extra>\S+)$')
            match_name = name.match(value['SNMPv2-MIB.sysName'])
            match_location = name.match(value['SNMPv2-MIB.sysLocation'])
            if match_name:
                tier = match_name.group('tier')
                bldg_name = match_name.group('bldg_name')
                type = match_name.group('type').upper()
            elif match_location:
                tier = match_location.group('tier')
                bldg_name = match_location.group('bldg_name')
                type = match_location.group('type').upper()
            else:
                match_snowflake = re.match(r'^(?P<tier>(RC|Micro|VPN))-',value['SNMPv2-MIB.sysName'])
                if match_snowflake:
                    tier = match_snowflake.group('tier')
                else:
                    tier = ''
                bldg_name = ''
                type = ''
            Device.objects.update_or_create(
                #ip4addr = value['ip4addr'],
                name = key,
                defaults = {
                    #'name': key,
                    'ip4addr': value['ip4addr'],
                    'sysName': value['SNMPv2-MIB.sysName'],
                    'sysDescr': value['SNMPv2-MIB.sysDescr'],
                    'sysLocation': value['SNMPv2-MIB.sysLocation'],
                    #'tier': tier,
                    #'building_name': bldg_name,
                    #'type': type,
                    'last_refresh': now
                }
            )
            time.sleep(0.05)

        # Remove stale entries
        Device.objects.exclude(last_refresh__gte=now).delete()

    # Check group membership
    group_membership = akips.get_group_membership()
    if group_membership:
        for key, value in group_membership.items():
            logger.debug("{}: {}".format(key, value))
            device = Device.objects.get(name=key)
            critical = False
            tier = ''
            bldg = ''
            for group_name in value:
                logger.debug("group {} and device {}".format(group_name,device))
                g_match = re.match(r'^(?P<index>\d+)-(?P<label>.+)$',group_name)
                if g_match:
                    logger.debug("matched {} and {}".format(g_match.group('index'),g_match.group('label')))
                    if g_match.group('index') == '0':
                        critical = True
                    elif g_match.group('index') == '1':
                        critical = True
                    elif g_match.group('index') == '2':
                        tier = g_match.group('label')
                    elif g_match.group('index') == '3':
                        pass
                    elif g_match.group('index') == '4':
                        bldg = g_match.group('label')
            device.critical = critical
            device.tier = tier
            device.building_name = bldg
            device.save()
            logger.debug("Set {} to critical {}, tier {}, and building {}".format(device, critical, tier, bldg))

            time.sleep(0.05)

    finish_time = timezone.now()
    logger.info("AKIPS devices updated in {}".format(finish_time - now))


@shared_task
def refresh_nit():
    logger.debug("Refeshing nit device data")
    now = timezone.now()

    nit = NIT()
    device_data = nit.get_device_data()
    #logger.debug("nit data {}".format(device_data))
    if device_data:
        for device in device_data['nodes']:
            logger.debug("Updating device {}".format(device))
            if 'hierarchy' in device and device['hierarchy']:
                hierarcy = device['hierarchy']
                if device['hierarchy'] in ['TIER1','BES','EDGE','SPINE','POD']:
                    type = 'SWITCH'
                else:
                    type = device['hierarchy']
            elif 'type' in device and device['type']:
                hierarcy = ''
                type = device['type'].upper()
            else:
                hierarcy = ''
                type = ''
            if device['building_name'] is None:
                device['building_name'] = ''
            Device.objects.filter(ip4addr=device['ip']).update(
                #tier=device['tier1'],
                #building_name=device['building_name'],
                type=type.upper(),
                hierarcy=hierarcy.upper()
                #type=device['type'].upper()
                #type=device['hierarchy'].upper()
            )
            #logger.debug("Found devices {}".format(devices))
            time.sleep(0.05)

    finish_time = timezone.now()
    logger.info("NIT refreshed in {}".format(finish_time - now))


@shared_task
def refresh_unreachable():
    logger.info("refreshing unreachable")
    now = timezone.now()

    akips = AKIPS()
    devices = akips.get_unreachable()
    if devices:
        for key, value in devices.items():
            logger.debug("{}: {}".format(key, value))
            Unreachable.objects.update_or_create(
                device = Device.objects.get(name=key),
                defaults = {
                    # 'name': key,                        # akips device name
                    'child': value['child'],            # ping4
                    'attribute': value['attribute'],    # PING.icmpState
                    'index': value['index'],            # 1
                    'state': value['state'],            # down
                    'device_added': datetime.fromtimestamp( int(value['device_added']), tz=timezone.get_current_timezone()),
                    'event_start': datetime.fromtimestamp( int(value['event_start']), tz=timezone.get_current_timezone() ),
                    'ip4addr': value['ip4addr'],
                    'last_refresh': now,
                }
            )
            time.sleep(0.05)

        # Remove stale entries
        Unreachable.objects.exclude(last_refresh__gte=now).delete()

        # Calculate Event Updates
        unreachables = Unreachable.objects.all()
        tier_count = {}
        bldg_count = {}
        for entry in unreachables:
            if entry.device.tier:
                tier_name = entry.device.tier
            else:
                tier_name = 'Unknown'
            if entry.device.building_name:
                bldg_name = entry.device.building_name
            else:
                bldg_name = 'Unknown'
            logger.debug("checking {}".format(tier_name))
            if entry.device.tier not in tier_count:
                tier_count[ tier_name ] = {
                    'SWITCH': 0,
                    'AP': 0,
                    'UPS': 0,
                    'TOTAL': 0,
                }
            logger.debug("checking {}".format(bldg_name))
            if entry.device.building_name not in bldg_count:
                bldg_count[ bldg_name ] = {
                    'SWITCH': 0,
                    'AP': 0,
                    'UPS': 0,
                    'TOTAL': 0,
                }
            if entry.device.type in ['SWITCH','AP','UPS']:
                tier_count[ tier_name ][ entry.device.type ] += 1
                tier_count[ tier_name ][ 'TOTAL' ] += 1
                bldg_count[ bldg_name ][ entry.device.type ] += 1
                bldg_count[ bldg_name ][ 'TOTAL' ] += 1
        logger.info("tier count {}".format(tier_count))
        logger.info("bldg count {}".format(bldg_count))

        # Update the Summary Table
        for tier_name in tier_count.keys():
            summary_search = Summary.objects.filter(
                type = 'Distribution',
                name = tier_name,
                status = 'Open'
            )
            if not summary_search:
                event = Summary.objects.create(
                    type = 'Distribution',
                    name = tier_name,
                    status = 'Open',
                    switch_count = tier_count[tier_name]['SWITCH'],
                    ap_count = tier_count[tier_name]['AP'],
                    ups_count = tier_count[tier_name]['UPS'],
                    total_count = tier_count[tier_name]['TOTAL'],
                    #percent_down = tier_count[tier_name]['TOTAL'] / tier_count[tier_name]['SWITCH'],
                    percent_down = 0,
                    first_event = now,
                    last_event = now,
                    trend = 'new',
                    #incident = 'blah'
                )
            else:
                event = summary_search[0]
                event.switch_count = tier_count[tier_name]['SWITCH']
                event.ap_count = tier_count[tier_name]['AP']
                event.ups_count = tier_count[tier_name]['UPS']
                event.last_event = now
                event.save()
        for bldg_name in bldg_count.keys():
            summary_search = Summary.objects.filter(
                type = 'Building',
                name = bldg_name,
                status = 'Open'
            )
            if not summary_search:
                event = Summary.objects.create(
                    type = 'Building',
                    name = bldg_name,
                    status = 'Open',
                    switch_count = bldg_count[bldg_name]['SWITCH'],
                    ap_count = bldg_count[bldg_name]['AP'],
                    ups_count = bldg_count[bldg_name]['UPS'],
                    total_count = bldg_count[bldg_name]['TOTAL'],
                    #percent_down = tier_count[tier_name]['TOTAL'] / tier_count[tier_name]['SWITCH'],
                    percent_down = 0,
                    first_event = now,
                    last_event = now,
                    trend = 'new',
                    #incident = 'blah'
                )
            else:
                event = summary_search[0]
                event.switch_count = bldg_count[bldg_name]['SWITCH']
                event.ap_count = bldg_count[bldg_name]['AP']
                event.ups_count = bldg_count[bldg_name]['UPS']
                event.last_event = now
                event.save()

        # Close events with no devices
        all_open = Summary.objects.filter(status='Open')
        for event in all_open:
            if event.type == 'Distribution' and event.name in tier_count.keys():
                pass
            elif event.type == 'Building' and event.name in bldg_count.keys():
                pass
            else:
                event.status = 'Closed'
                #event.switch_count = 0
                #event.aps_count = 0
                #event.ups_count = 0
                event.save()

    finish_time = timezone.now()
    logger.info("AKIPS unreachable updated in {}".format(finish_time - now))

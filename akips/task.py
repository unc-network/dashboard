from celery import shared_task
import logging
import time
import re
from datetime import datetime

from django.utils import timezone
from django.db.models import Count

from .models import Device, Unreachable
from akips.utils import AKIPS, NIT

# Get an isntace of a logger
logger = logging.getLogger(__name__)

@shared_task
def example_task():
    logger.info("task is running")

@shared_task
def refresh_akips_devices():
    logger.info("refreshing akips devices")

    akips = AKIPS()
    devices = akips.get_devices()
    if devices:
        #now = datetime.now()
        now = timezone.now()
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
                    'tier': tier,
                    #'building_name': bldg_name,
                    #'type': type,
                    'last_refresh': now
                }
            )
            time.sleep(0.05)

        # Remove stale entries
        Device.objects.exclude(last_refresh=now).delete()

        # Update summary totals

@shared_task
def refresh_nit():
    logger.debug("Refeshing nit device data")

    nit = NIT()
    device_data = nit.get_device_data()
    #logger.debug("nit data {}".format(device_data))
    if device_data:
        for device in device_data['nodes']:
            logger.debug("Updating device {}".format(device))
            if 'hierarchy' in device and device['hierarchy']:
                type = device['hierarchy']
            elif 'type' in device and device['type']:
                type = device['type'].upper()
            else:
                type = ''
            if device['building_name'] is None:
                device['building_name'] = ''
            Device.objects.filter(ip4addr=device['ip']).update(
                #tier=device['tier1'],
                building_name=device['building_name'],
                type=type.upper()
                #type=device['type'].upper()
                #type=device['hierarchy'].upper()
            )
            #logger.debug("Found devices {}".format(devices))
            time.sleep(0.05)


@shared_task
def refresh_unreachable():
    logger.info("refreshing unreachable")

    akips = AKIPS()
    devices = akips.get_unreachable()
    if devices:
        now = timezone.now()
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
        Unreachable.objects.exclude(last_refresh=now).delete()

        # Update summary totals
        tier_count = {}
        tier_count['switch'] = Unreachable.objects.filter(device__type='SWITCH').values('device__tier').annotate(total=Count('device__tier')).order_by('device__tier')
        tier_count['ap'] = Unreachable.objects.filter(device__type='AP').values('device__tier').annotate(total=Count('device__tier')).order_by('device__tier')
        tier_count['ups'] = Unreachable.objects.filter(device__type='UPS').values('device__tier').annotate(total=Count('device__tier')).order_by('device__tier')
        logger.info("unreachable tier counts {}".format(tier_count))
        building_count = {}
        building_count['switch'] = Unreachable.objects.filter(device__type='SWITCH').values('device__building_name').annotate(total=Count('device__building_name')).order_by('device__building_name')
        building_count['ap'] = Unreachable.objects.filter(device__type='AP').values('device__building_name').annotate(total=Count('device__building_name')).order_by('device__building_name')
        building_count['ups'] = Unreachable.objects.filter(device__type='UPS').values('device__building_name').annotate(total=Count('device__building_name')).order_by('device__building_name')
        logger.info("unreachable building counts {}".format(building_count))

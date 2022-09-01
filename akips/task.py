from celery import shared_task
import logging
import time
import re
from datetime import datetime

from django.utils import timezone
from django.db.models import Count

from .models import Device, Unresponsive
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
        #now = datetime.now()
        now = timezone.now()
        for key, value in devices.items():
            logger.debug("{}: {}".format(key, value))
            Unresponsive.objects.update_or_create(
                #device = AKIPS_device(name=key),
                name = key,
                defaults = {
                    'name': key,
                    'ip4addr': value['ip4addr'],
                    'device_added': datetime.fromtimestamp( int(value['device_added']), tz=timezone.get_current_timezone()),
                    'event_start': datetime.fromtimestamp( int(value['event_start']), tz=timezone.get_current_timezone() ),
                    'last_refresh': now,
                }
            )
            time.sleep(0.05)

        # Update summary totals
        #tier_switch_count = AKIPS_unresponsive.objects.filter(type='SW').values('tier').annotate(total=Count('tier')).order_by('tier')
        #tier_ap_count = AKIPS_unresponsive.objects.filter(type='AP').values('tier').annotate(total=Count('tier')).order_by('tier')
        #tier_ups_count = AKIPS_unresponsive.objects.filter(type='UPS').values('tier').annotate(total=Count('tier')).order_by('tier')
        #bldg_switch_count = AKIPS_unresponsive.objects.filter(type='SW').values('building_name').annotate(total=Count('building_name')).order_by('building_name')
        #bldg_ap_count = AKIPS_unresponsive.objects.filter(type='AP').values('building_name').annotate(total=Count('building_name')).order_by('building_name')
        #bldg_ups_count = AKIPS_unresponsive.objects.filter(type='UPS').values('building_name').annotate(total=Count('building_name')).order_by('building_name')

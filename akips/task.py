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
    logger.debug("refreshing akips devices")
    now = timezone.now()

    akips = AKIPS()
    devices = akips.get_devices()
    #devices = None
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

            if re.search(r'-(ups[0-9]*)[-_]?',value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                type = 'UPS'
            elif re.search(r'-(ap)[-_]?',value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                type = 'AP'
            elif re.search(r'-(tier1|bes|sw[0-9]*|spine|pod[a-z]*)[-_]?',value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                type = 'SWITCH'
            elif re.search(r'-(legacy|agg|arista)[-]?',value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                type = 'SWITCH'
            else:
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
                    'type': type,
                    'last_refresh': now
                }
            )
            time.sleep(0.05)

        # Remove stale entries
        Device.objects.exclude(last_refresh__gte=now).delete()

    # Identify devices in maintenance mode
    maintenance_list = akips.get_maintenance_mode()
    if maintenance_list:
        Device.objects.filter(name__in=maintenance_list).update(maintenance=True)
        Device.objects.exclude(name__in=maintenance_list).update(maintenance=False)

    # Check group membership
    group_membership = akips.get_group_membership()
    #group_membership = None
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
    logger.info("AKIPS deivce refresh runtime {}".format(finish_time - now))


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
    logger.info("NIT refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_unreachable():
    logger.debug("AKIPS unreachable refresh starting")
    now = timezone.now()

    akips = AKIPS()
    unreachables = akips.get_unreachable()
    if unreachables:
        #for key, value in devices.items():
        for entry in unreachables:
            logger.debug("{}".format(entry))
            Unreachable.objects.update_or_create(
                device = Device.objects.get(name= entry['name']),
                child = entry['child'],
                event_start = datetime.fromtimestamp( int(entry['event_start']), tz=timezone.get_current_timezone() ),
                defaults = {
                    # 'name': key,                        # akips device name
                    #'child': value['child'],            # ping4
                    'attribute': entry['attribute'],    # PING.icmpState
                    'index': entry['index'],            # 1
                    'state': entry['state'],            # down
                    'device_added': datetime.fromtimestamp( int(entry['device_added']), tz=timezone.get_current_timezone()),
                    #'event_start': datetime.fromtimestamp( int(value['event_start']), tz=timezone.get_current_timezone() ),
                    'ip4addr': entry['ip4addr'],
                    'last_refresh': now,
                    'status': 'Open',
                }
            )
            time.sleep(0.05)

        # Remove stale entries
        Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')

    finish_time = timezone.now()
    logger.info("AKIPS unreachable refresh runtime {}".format(finish_time - now))

# @shared_task
# def refresh_summary():
    logger.debug("AKIPS summary refresh starting")
    now = timezone.now()

    unreachables = Unreachable.objects.filter(status='Open',device__maintenance=False)
    for unreachable in unreachables:
        logger.debug("Processing unreachable {}".format(unreachable))

        if unreachable.device.critical:
            # Handle Critical devices
            c_summary, c_created = Summary.objects.get_or_create(
                type='Critical',
                name=unreachable.device.name,
                status='Open',
                defaults = {
                    'first_event': now,
                    'last_event': now,
                    'max_count': 1
                }
            )
            if c_created:
                logger.debug("Crit summary created {}".format(unreachable.device.name))
            else:
                c_summary.last_event = now
                c_summary.save()
            c_summary.unreachables.add( unreachable )

        else:
            # Handle Non-Critical devices

            # Handle blank tier or building names
            if unreachable.device.tier:
                tier_name = unreachable.device.tier
            else:
                tier_name = 'Unknown'
            if unreachable.device.building_name:
                bldg_name = unreachable.device.building_name
            else:
                bldg_name = 'Unknown'

            # Find the tier summary to update
            t_summary, t_created = Summary.objects.get_or_create(
                type='Distribution',
                name=tier_name,
                status='Open',
                defaults = {
                    'first_event': now,
                    'last_event': now,
                    'max_count': Device.objects.filter(tier= unreachable.device.tier ).count()
                }
            )
            if t_created:
                logger.debug("Tier summary created {}".format(tier_name))
            else:
                t_summary.last_event = now
                t_summary.save()
            t_summary.unreachables.add( unreachable )

            # Find the building summary to update
            b_summary, b_created = Summary.objects.get_or_create(
                type='Building',
                name=bldg_name,
                status='Open',
                defaults = {
                    'first_event': now,
                    'last_event': now,
                    'max_count': Device.objects.filter(building_name= unreachable.device.building_name ).count()
                }
            )
            if b_created:
                logger.debug("Building summary created {}".format(bldg_name))
            else:
                b_summary.last_event = now
                b_summary.save()
            b_summary.unreachables.add( unreachable )

        time.sleep(0.05)

    # Calculate summary counts
    summaries = Summary.objects.filter(status='Open')
    for summary in summaries:
        logger.debug("Updating counts on {}".format(summary))

        count = {
            'SWITCH': {},
            'AP': {},
            'UPS': {},
            'UNKNOWN': {},
            'TOTAL':{}, 
        }
        unreachables = summary.unreachables.filter(status='Open')
        for unreachable in unreachables:
            if unreachable.device.maintenance == False:
                if unreachable.device.type in ['SWITCH','AP','UPS']:
                    count[ unreachable.device.type ][ unreachable.device.name ] = True
                else:
                    count[ 'UNKNOWN' ][ unreachable.device.name ] = True
                count[ 'TOTAL' ][ unreachable.device.name ] = True
        logger.debug("Counts {} are {}".format(summary.name,count))

        summary.switch_count = len( count['SWITCH'].keys() )
        summary.ap_count = len( count['AP'].keys() )
        summary.ups_count = len( count['UPS'].keys() )
        total_count = len( count['TOTAL'].keys() )
        percent_down = round( total_count / summary.max_count, 3)

        if summary.total_count == total_count:
            summary.trend = 'Stable'
        elif summary.total_count < total_count:
            summary.trend = 'Increasing'
        elif summary.total_count > total_count:
            summary.trend = 'Decreasing'
        summary.total_count = total_count
        summary.percent_down = percent_down

        summary.save()

        # # Calculate device totals
        # #unreachables = Unreachable.objects.exclude(device__maintenance=True)
        # unreachables = Unreachable.objects.filter(status='Open',device__maintenance=False)
        # crit_count = {}
        # tier_count = {}
        # bldg_count = {}
        # for entry in unreachables:
        #     if entry.device.tier:
        #         tier_name = entry.device.tier
        #     else:
        #         tier_name = 'Unknown'
        #     if entry.device.building_name:
        #         bldg_name = entry.device.building_name
        #     else:
        #         bldg_name = 'Unknown'

        #     # Identify critical devices
        #     if entry.device.critical:
        #         crit_count[ entry.device.name ] = {
        #             'TOTAL': 1,
        #         }

        #     # Identify tier and building devices
        #     logger.debug("checking tier {} for {}".format(tier_name,entry.device.name))
        #     #if entry.device.tier not in tier_count:
        #     if tier_name not in tier_count:
        #         tier_count[ tier_name ] = {
        #             'SWITCH': 0,
        #             'AP': 0,
        #             'UPS': 0,
        #             'TOTAL': 0,
        #         }
        #     logger.debug("checking bldg {} for {}".format(bldg_name,entry.device.name))
        #     #if entry.device.building_name not in bldg_count:
        #     if bldg_name not in bldg_count:
        #         bldg_count[ bldg_name ] = {
        #             'SWITCH': 0,
        #             'AP': 0,
        #             'UPS': 0,
        #             'TOTAL': 0,
        #         }
        #     if entry.device.type in ['SWITCH','AP','UPS']:
        #         tier_count[ tier_name ][ entry.device.type ] += 1
        #         bldg_count[ bldg_name ][ entry.device.type ] += 1
        #     tier_count[ tier_name ][ 'TOTAL' ] += 1
        #     bldg_count[ bldg_name ][ 'TOTAL' ] += 1

        # logger.debug("crit count {}".format(crit_count))
        # logger.debug("tier count {}".format(tier_count))
        # logger.debug("bldg count {}".format(bldg_count))

        # # Update critical type summary events
        # for crit_name in crit_count.keys():
        #     summary_search = Summary.objects.filter(
        #         type = 'Critical',
        #         name = crit_name,
        #         status = 'Open'
        #     )
        #     if not summary_search:
        #         # This is a new event
        #         event = Summary.objects.create(
        #             type = 'Critical',
        #             name = crit_name,
        #             device = Device.objects.get(name=crit_name),
        #             status = 'Open',
        #             max_count = 1,
        #             total_count = 1,
        #             first_event = now,
        #             last_event = now,
        #             trend = 'New',
        #         )
        #         event.unreachables.add( Unreachable.objects.get(device__name=crit_name,last_refresh=now))
        #     else:
        #         # This is a update event
        #         event = summary_search[0]
        #         event.trend = 'Stable'
        #         event.last_event = now
        #         event.save()

        # # Close critical type events open with no down devices
        # Summary.objects.filter(type='Critical',status='Open').exclude(name__in=crit_count.keys()).update(status='Closed')

        # # Update distribution type summary events
        # for tier_name in tier_count.keys():
        #     summary_search = Summary.objects.filter(
        #         type = 'Distribution',
        #         name = tier_name,
        #         status = 'Open'
        #     )
        #     if not summary_search:
        #         # This is a new event
        #         if tier_name == 'Unknown':
        #             tier_device_total = Device.objects.filter(tier='').count()
        #         else:
        #             tier_device_total = Device.objects.filter(tier=tier_name).count()
        #         tier_percent_down = round( tier_count[tier_name]['TOTAL'] / tier_device_total, 3)
        #         event = Summary.objects.create(
        #             type = 'Distribution',
        #             name = tier_name,
        #             status = 'Open',
        #             switch_count = tier_count[tier_name]['SWITCH'],
        #             ap_count = tier_count[tier_name]['AP'],
        #             ups_count = tier_count[tier_name]['UPS'],
        #             total_count = tier_count[tier_name]['TOTAL'],
        #             max_count = tier_device_total,
        #             percent_down = tier_percent_down,
        #             first_event = now,
        #             last_event = now,
        #             trend = 'New',
        #         )
        #     else:
        #         # This is a update event
        #         event = summary_search[0]
        #         event.switch_count = tier_count[tier_name]['SWITCH']
        #         event.ap_count = tier_count[tier_name]['AP']
        #         event.ups_count = tier_count[tier_name]['UPS']
        #         event.percent_down = round( tier_count[tier_name]['TOTAL'] / event.max_count, 3)
        #         if tier_count[tier_name]['TOTAL'] ==  event.total_count:
        #             event.trend = 'Stable'
        #         elif tier_count[tier_name]['TOTAL'] > event.total_count:
        #             event.trend = 'Increasing'
        #         elif tier_count[tier_name]['TOTAL'] < event.total_count:
        #             event.trend = 'Decreasing'
        #         event.total_count = tier_count[tier_name]['TOTAL']
        #         event.last_event = now
        #         event.save()

        # # Close distribution type events open with no down devices
        # Summary.objects.filter(type='Distribution',status='Open').exclude(name__in=tier_count.keys()).update(status='Closed')

        # # Update building type summary events
        # for bldg_name in bldg_count.keys():
        #     summary_search = Summary.objects.filter(
        #         type = 'Building',
        #         name = bldg_name,
        #         status = 'Open'
        #     )
        #     if not summary_search:
        #         # This is a new event
        #         if bldg_name == 'Unknown':
        #             bldg_device_total = Device.objects.filter(building_name='').count()
        #         else:
        #             bldg_device_total = Device.objects.filter(building_name=bldg_name).count()
        #         bldg_percent_down = round( bldg_count[bldg_name]['TOTAL'] / bldg_device_total, 3)
        #         event = Summary.objects.create(
        #             type = 'Building',
        #             name = bldg_name,
        #             status = 'Open',
        #             switch_count = bldg_count[bldg_name]['SWITCH'],
        #             ap_count = bldg_count[bldg_name]['AP'],
        #             ups_count = bldg_count[bldg_name]['UPS'],
        #             total_count = bldg_count[bldg_name]['TOTAL'],
        #             max_count = bldg_device_total,
        #             percent_down = bldg_percent_down,
        #             first_event = now,
        #             last_event = now,
        #             trend = 'New',
        #         )
        #     else:
        #         # This is a update event
        #         event = summary_search[0]
        #         event.switch_count = bldg_count[bldg_name]['SWITCH']
        #         event.ap_count = bldg_count[bldg_name]['AP']
        #         event.ups_count = bldg_count[bldg_name]['UPS']
        #         event.percent_down = round( bldg_count[bldg_name]['TOTAL'] / event.max_count, 3)
        #         if bldg_count[bldg_name]['TOTAL'] ==  event.total_count:
        #             event.trend = 'Stable'
        #         elif bldg_count[bldg_name]['TOTAL'] > event.total_count:
        #             event.trend = 'Increasing'
        #         elif bldg_count[bldg_name]['TOTAL'] < event.total_count:
        #             event.trend = 'Decreasing'
        #         event.total_count = bldg_count[bldg_name]['TOTAL']
        #         event.last_event = now
        #         event.save()

        # # Close building type events open with no down devices
        # Summary.objects.filter(type='Building',status='Open').exclude(name__in=bldg_count.keys()).update(status='Closed')

        time.sleep(0.05)

    # Close building type events open with no down devices
    Summary.objects.filter(status='Open').exclude(last_event__gte=now).update(status='Closed')

    finish_time = timezone.now()
    logger.info("AKIPS summary refresh runtime {}".format(finish_time - now))

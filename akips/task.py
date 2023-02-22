from celery import shared_task, current_app
from django_celery_results.models import TaskResult
import logging
import time
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.db.models import Count

from .models import Device, HibernateRequest, Unreachable, Summary, Trap, Status
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
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    devices = akips.get_devices()
    #devices = None
    if devices:
        for key, value in devices.items():
            logger.debug("{}: {}".format(key, value))
            name = re.compile(
                r'^(?P<tier>\w+)-(?P<bldg_id>\w+)-(?P<bldg_name>\w+)-(?P<type>[a-zA-Z0-9]+)[-_](?P<extra>\S+)$')
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
                match_snowflake = re.match(
                    r'^(?P<tier>(RC|Micro|VPN))-', value['SNMPv2-MIB.sysName'])
                if match_snowflake:
                    tier = match_snowflake.group('tier')
                else:
                    tier = ''
                bldg_name = ''

            defaults = {
                # 'name': key,
                'ip4addr': value['ip4addr'],
                'sysName': value['SNMPv2-MIB.sysName'],
                'sysDescr': value['SNMPv2-MIB.sysDescr'],
                'sysLocation': value['SNMPv2-MIB.sysLocation'],
                # 'tier': tier,
                # 'building_name': bldg_name,
                #'type': type,
                'last_refresh': now
            }
            # Do not set or change type unless we can tell by the name
            if re.search(r'-(ups[0-9]*)[-_]?', value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                defaults['type'] = 'UPS'
            elif re.search(r'-(ap)[-_]?', value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                defaults['type'] = 'AP'
            elif re.search(r'-(tier1|bes|sw[0-9]*|spine|pod[a-z]*)[-_]?', value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                defaults['type'] = 'SWITCH'
            elif re.search(r'-(legacy|agg|arista)[-]?', value['SNMPv2-MIB.sysName'], re.IGNORECASE):
                defaults['type'] = 'SWITCH'
            Device.objects.update_or_create( name=key, defaults=defaults)

            time.sleep(sleep_delay)

        # Remove stale entries
        Device.objects.exclude(last_refresh__gte=now).delete()

    # Identify devices in maintenance mode
    maintenance_list = akips.get_maintenance_mode()
    if maintenance_list:
        Device.objects.filter(
            name__in=maintenance_list).update(maintenance=True)
        Device.objects.exclude(
            name__in=maintenance_list).update(maintenance=False)

    # Check group membership
    group_membership = akips.get_group_membership()
    #group_membership = None
    if group_membership:
        for key, value in group_membership.items():
            logger.debug("{}: {}".format(key, value))
            try:
                device = Device.objects.get(name=key)
            except Device.DoesNotExist:
                logger.warn("Attempting to set group membership for unknown device {}".format(key))
                continue

            critical = False
            tier = ''
            bldg = ''
            for group_name in value:
                logger.debug("group {} and device {}".format(
                    group_name, device))
                g_match = re.match(
                    r'^(?P<index>\d+)-(?P<label>.+)$', group_name)
                if g_match:
                    logger.debug("matched {} and {}".format(
                        g_match.group('index'), g_match.group('label')))
                    if g_match.group('index') == '0':
                        critical = True
                        device.group = 'Critical'
                    elif g_match.group('index') == '1':
                        critical = True
                        device.group = 'Critical'
                    elif g_match.group('index') == '2':
                        tier = g_match.group('label')
                        device.group = 'default'
                    elif g_match.group('index') == '3':
                        device.group = 'default'
                    elif g_match.group('index') == '4':
                        bldg = g_match.group('label')
                        device.group = 'default'
                    elif g_match.group('index') == '5':
                        device.group = g_match.group('label')
                    # elif g_match.group('index') == '5' and g_match.group('label') == 'Servers':
                    #     device.type = 'SERVER'
            device.critical = critical
            device.tier = tier
            device.building_name = bldg
            device.save()
            logger.debug("Set {} to critical {}, tier {}, and building {}".format(
                device, critical, tier, bldg))

            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("AKIPS device refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_ping_status():
    logger.debug("refreshing ping status")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.01
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    data = akips.get_status(type='ping')
    if data:
        for entry in data:
            logger.debug("updating {}".format(entry))
            try:
                device = Device.objects.get(name=entry['device'])
            except Device.DoesNotExist:
                logger.warn("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'value': entry['state'],
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh ping status runtime {}".format(finish_time - now))

@shared_task
def refresh_snmp_status():
    logger.debug("refreshing snmp status")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.01
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    data = akips.get_status(type='snmp')
    if data:
        for entry in data:
            logger.debug("updating {}".format(entry))
            try:
                device = Device.objects.get(name=entry['device'])
            except Device.DoesNotExist:
                logger.warn("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'value': entry['state'],
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh snmp status runtime {}".format(finish_time - now))

@shared_task
def refresh_ups_status():
    logger.debug("refreshing ups status")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.01
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    data = akips.get_status(type='ups')
    if data:
        for entry in data:
            logger.debug("updating {}".format(entry))
            try:
                device = Device.objects.get(name=entry['device'])
            except Device.DoesNotExist:
                logger.warn("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'value': entry['state'],
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh ups status runtime {}".format(finish_time - now))

@shared_task
def refresh_battery_test_status():
    logger.debug("refreshing battery test status")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.01
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    data = akips.get_status(type='battery_test')
    if data:
        for entry in data:
            logger.debug("updating {}".format(entry))
            try:
                device = Device.objects.get(name=entry['device'])
            except Device.DoesNotExist:
                logger.warn("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'value': entry['state'],
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh battery test status runtime {}".format(finish_time - now))

@shared_task
def refresh_nit():
    logger.debug("Refeshing nit device data")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    nit = NIT()
    device_data = nit.get_device_data()
    #logger.debug("nit data {}".format(device_data))
    if device_data:
        for device in device_data['nodes']:
            logger.debug("Updating device {}".format(device))
            if 'hierarchy' in device and device['hierarchy']:
                hierarcy = device['hierarchy']
                if device['hierarchy'] in ['TIER1', 'BES', 'EDGE', 'SPINE', 'POD']:
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
                # tier=device['tier1'],
                # building_name=device['building_name'],
                type=type.upper(),
                hierarcy=hierarcy.upper()
                # type=device['type'].upper()
                # type=device['hierarchy'].upper()
            )
            #logger.debug("Found devices {}".format(devices))
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("NIT refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_unreachable():
    logger.debug("AKIPS unreachable refresh starting")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    akips = AKIPS()
    unreachables = akips.get_unreachable()
    if unreachables:
        for k, v in unreachables.items():
            logger.debug("{}".format(v['name']))
            try:
                device = Device.objects.get(name=v['name'])
            except Device.DoesNotExist:
                logger.warn("Attempting to create unreachable data for unknown device {}".format(v['name']))
                continue

            Unreachable.objects.update_or_create(
                device=device,
                #status='Open',
                #child = entry['child'],
                event_start = datetime.fromtimestamp( int(v['event_start']), tz=timezone.get_current_timezone() ),
                defaults={
                    # 'name': key,                        # akips device name
                    'child': v['child'],            # ping4
                    'ping_state': v['ping_state'],            # down
                    'snmp_state': v['snmp_state'],            # down
                    'index': v['index'],            # 1
                    'device_added': datetime.fromtimestamp(int(v['device_added']), tz=timezone.get_current_timezone()),
                    'event_start': datetime.fromtimestamp(int(v['event_start']), tz=timezone.get_current_timezone()),
                    'ip4addr': v['ip4addr'],
                    'last_refresh': now,
                    'status': 'Open',
                }
            )

            time.sleep(sleep_delay)

        # Remove stale entries
        Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')

    finish_time = timezone.now()
    logger.info("AKIPS unreachable refresh runtime {}".format(finish_time - now))

# @shared_task
# def refresh_summary():

    logger.debug("AKIPS summary refresh starting")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    # Process all current unreachable records
    unreachables = Unreachable.objects.filter(status='Open', device__maintenance=False).exclude(device__hibernate=True)
    for unreachable in unreachables:
        logger.debug("Processing unreachable {}".format(unreachable))

        if unreachable.device.critical:
            # Handle Critical devices
            if unreachable.device.sysName:
                d_name = unreachable.device.sysName
            else:
                d_name = unreachable.device.name
            c_summary, c_created = Summary.objects.get_or_create(
                type='Critical',
                #name=unreachable.device.name,
                name=d_name,
                status='Open',
                defaults={
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    'max_count': 1
                }
            )
            if c_created:
                logger.debug("Crit summary created {}".format(
                    unreachable.device.name))
            else:
                if c_summary.first_event > unreachable.event_start:
                    c_summary.first_event = unreachable.event_start
                if c_summary.last_event < unreachable.event_start:
                    c_summary.last_event = unreachable.event_start
                c_summary.last_refresh = now
                c_summary.save()
            c_summary.unreachables.add(unreachable)

        elif unreachable.device.group == 'default':
            # Handle Non-Critical switch, ap, and ups devices

            # Handle blank tier or building names
            if unreachable.device.tier:
                tier_name = unreachable.device.tier
            else:
                tier_name = 'Other'
            if unreachable.device.building_name:
                bldg_name = unreachable.device.building_name
            else:
                bldg_name = 'Other'

            # Find the tier summary to update
            t_summary, t_created = Summary.objects.get_or_create(
                type='Distribution',
                name=tier_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    'max_count': Device.objects.filter(tier=unreachable.device.tier).count()
                    #'ups_battery': Status.objects.filter(device__tier=unreachable.device.tier,object='UPS-MIB.upsOutputSource',value='battery').count()
                }
            )
            if t_created:
                logger.debug("Tier summary created {}".format(tier_name))
            else:
                t_summary.max_count = Device.objects.filter(tier=unreachable.device.tier).count()
                if t_summary.first_event > unreachable.event_start:
                    t_summary.first_event = unreachable.event_start
                if t_summary.last_event < unreachable.event_start:
                    t_summary.last_event = unreachable.event_start
                t_summary.last_refresh = now
                t_summary.save()
            t_summary.unreachables.add(unreachable)

            # Find the building summary to update
            b_summary, b_created = Summary.objects.get_or_create(
                type='Building',
                name=bldg_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    'max_count': Device.objects.filter(building_name=unreachable.device.building_name).count(),
                    #'ups_battery': Status.objects.filter(device__building_name=unreachable.device.building_name,object='UPS-MIB.upsOutputSource',value='battery').count()
                }
            )
            if b_created:
                logger.debug("Building summary created {}".format(bldg_name))
            else:
                b_summary.max_count = Device.objects.filter(building_name=unreachable.device.building_name).count()
                if b_summary.first_event > unreachable.event_start:
                    b_summary.first_event = unreachable.event_start
                if b_summary.last_event < unreachable.event_start:
                    b_summary.last_event = unreachable.event_start
                b_summary.last_refresh = now
                b_summary.save()
            b_summary.unreachables.add(unreachable)

        else:
            # non critical and non default devices
            logger.debug("Processing special group {}".format( unreachable.device.group ))

            # Find the speciality summary to update
            s_summary, s_created = Summary.objects.get_or_create(
                type='Speciality',
                name= unreachable.device.group,
                status='Open',
                defaults={
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    'max_count': Device.objects.filter(group=unreachable.device.group).count(),
                    #'ups_battery': Status.objects.filter(device__building_name=unreachable.device.building_name,object='UPS-MIB.upsOutputSource',value='battery').count()
                }
            )
            if s_created:
                logger.debug("Speciality summary created {}".format( unreachable.device.group ))
            else:
                s_summary.max_count = Device.objects.filter(group=unreachable.device.group).count()
                if s_summary.first_event > unreachable.event_start:
                    s_summary.first_event = unreachable.event_start
                if s_summary.last_event < unreachable.event_start:
                    s_summary.last_event = unreachable.event_start
                s_summary.last_refresh = now
                s_summary.save()
            s_summary.unreachables.add(unreachable)

        time.sleep(sleep_delay)

    # Process all ups on battery
    ups_on_battery = Status.objects.filter(attribute='UPS-MIB.upsOutputSource',value='battery',device__maintenance=False).exclude(device__hibernate=True)
    for ups in ups_on_battery:
        logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))

        # Find the tier summary to update
        t_summary, t_created = Summary.objects.get_or_create(
            type='Distribution',
            name=ups.device.tier,
            status='Open',
            defaults={
                'tier': ups.device.tier,
                'first_event': ups.last_change,
                'last_event': ups.last_change,
                'max_count': Device.objects.filter(tier=ups.device.tier).count(),
                'ups_battery': Status.objects.filter(device__tier=ups.device.tier,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            }
        )
        if t_created:
            logger.debug("Tier summary created {}".format(ups.device.tier))
        else:
            t_summary.ups_battery = Status.objects.filter(device__tier=ups.device.tier,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            if t_summary.first_event > ups.last_change:
                t_summary.first_event = ups.last_change
            if t_summary.last_event < ups.last_change:
                t_summary.last_event = ups.last_change
            t_summary.last_refresh = now
            t_summary.save()
        t_summary.batteries.add(ups)

        # Find the building summary to update
        b_summary, b_created = Summary.objects.get_or_create(
            type='Building',
            name=ups.device.building_name,
            status='Open',
            defaults={
                'tier': ups.device.tier,
                'first_event': ups.last_change,
                'last_event': ups.last_change,
                'max_count': Device.objects.filter(building_name=unreachable.device.building_name).count(),
                'ups_battery': Status.objects.filter(device__building_name=ups.device.building_name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            }
        )
        if b_created:
            logger.debug("Building summary created {}".format( ups.device.building_name ))
        else:
            b_summary.ups_battery = Status.objects.filter(device__building_name=ups.device.building_name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            if b_summary.first_event > ups.last_change:
                b_summary.first_event = ups.last_change
            if b_summary.last_event < ups.last_change:
                b_summary.last_event = ups.last_change
            b_summary.last_refresh = now
            b_summary.save()
        b_summary.batteries.add(ups)

    # Calculate summary counts
    summaries = Summary.objects.filter(status='Open')
    for summary in summaries:
        logger.debug("Updating counts on {}".format(summary))

        count = {
            'SWITCH': {},
            'AP': {},
            'UPS': {},
            'UNKNOWN': {},
            'TOTAL': {},
        }
        unreachables = summary.unreachables.filter(status='Open')
        for unreachable in unreachables:
            if unreachable.device.maintenance == False:
                if unreachable.device.type in ['SWITCH', 'AP', 'UPS']:
                    count[unreachable.device.type][unreachable.device.name] = True
                else:
                    count['UNKNOWN'][unreachable.device.name] = True
                count['TOTAL'][unreachable.device.name] = True
        logger.debug("Counts {} are {}".format(summary.name, count))

        if summary.type == 'Distribution':
            summary.ups_battery = Status.objects.filter(device__tier=summary.name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
        elif summary.type == 'Building':
            summary.ups_battery = Status.objects.filter(device__building_name=summary.name,attribute='UPS-MIB.upsOutputSource',value='battery').count()

        summary.switch_count = len(count['SWITCH'].keys())
        summary.ap_count = len(count['AP'].keys())
        summary.ups_count = len(count['UPS'].keys())
        total_count = len(count['TOTAL'].keys())
        percent_down = round(total_count / summary.max_count, 3)

        # Moving avg calculation
        # new_average = old_average * (n-1)/n + new_value /n
        # new_average = old_average * 0.80 + new_value * 0.20 
        if summary.moving_avg_count == 0:
            summary.moving_avg_count += 1
            summary.moving_average = total_count
            new_average = total_count
        #elif summary.moving_avg_count < 4:
        else:
            # n = summary.moving_avg_count + 1
            # new_average = ( summary.moving_average * (n-1) + total_count ) / n
            new_average = summary.moving_average * 0.8 + total_count * 0.2
        # else:
        #     n = 4
        #     new_average = summary.moving_average * (n-1)/n + total_count / n
        logger.debug("Moving average: last={}, total={}, new={}".format(summary.moving_average,total_count,new_average))

        new_threshold = now - timedelta(minutes=5)
        if summary.first_event >= new_threshold:
            summary.trend = 'New'
        elif total_count > new_average * 1.05:
            summary.trend = 'Increasing'
        elif total_count < new_average * 0.95:
            summary.trend = 'Decreasing'
        else:
            summary.trend = 'Stable'
        summary.total_count = total_count
        summary.percent_down = percent_down
        summary.moving_average = new_average

        summary.save()

        time.sleep(sleep_delay)

    # Close building type events open with no down devices
    #Summary.objects.filter(status='Open').exclude(last_event__gte=now).update(status='Closed')
    Summary.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')

    finish_time = timezone.now()
    logger.info("AKIPS summary refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_hibernate():
    logger.debug("Refeshing hibernated devices")
    now = timezone.now()
    sleep_delay = 0

    if ( settings.OPENSHIFT_NAMESPACE == 'LOCAL'):
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))


    hibernate_requests = HibernateRequest.objects.filter(status='Open')
    for hibernate in hibernate_requests:
        logger.debug("Checking hibernate status for {}".format( hibernate.device.name ))

        if hibernate.type == 'Auto':
            #status = Status.objects.filter(device=hibernate.device,attribute='PING.icmpState')
            status = Status.objects.filter(device=hibernate.device)
            current_status = 'up'
            for value in status:
                if value.attribute == 'PING.icmpState' and value.value == 'down':
                    current_status = 'down'
                elif value.attribute == 'SNMP.snmpState' and value.value == 'down':
                    current_status = 'down'

            # # Check or an open unreachable on this device
            # unreachable_count = Unreachable.objects.filter(device=hibernate.device,status='Open').count()
            # if unreachable_count == 0:
            if current_status == 'up':
                logger.info("Status is up, clearing hibernate request for {}".format( hibernate.device.name ))

                # # Update AKIPS
                # akips = AKIPS()
                # result = akips.set_maintenance_mode(hibernate.device.name, mode='False')

                # update the local database
                hibernate.device.hibernate = False
                hibernate.device.save()
                hibernate.executed = now
                hibernate.status = 'Closed'
                hibernate.save()

        elif hibernate.type == 'Time' and now >= hibernate.scheduled:
            logger.info("Time is up, clearing hibernate request for {}".format( hibernate.device.name ))

            # # Update AKIPS
            # akips = AKIPS()
            # result = akips.set_maintenance_mode(hibernate.device.name, mode='False')

            # update the local database
            hibernate.device.hibernate = False
            hibernate.device.save()
            hibernate.executed = now
            hibernate.status = 'Closed'
            hibernate.save()

    finish_time = timezone.now()
    logger.info("hibernate refresh runtime {}".format(finish_time - now))

@shared_task
#def clear_traps():
def cleanup_dashboard_data():
    logger.debug("Cleanup dashboard data is starting")
    now = timezone.now()

    # Define the periods we care about
    two_hours_ago = now - timedelta(hours=2)
    one_day_ago = now - timedelta(days=1)
    seven_days_ago = now - timedelta(days=7)

    # Auto clear old traps (1 day)
    Trap.objects.filter(status='Open',tt__lt=one_day_ago).exclude(dup_last__gt=one_day_ago).update(status='Closed', comment='Auto closed due to age')

    # Delete really old traps (7 days)
    Trap.objects.filter(status='Closed',tt__lt=seven_days_ago).delete()

    # Remove old duplicate traps (2 hours)
    Trap.objects.filter(status='Closed',tt__lt=two_hours_ago,comment='Auto-cleared as a duplicate').delete()

    # delete closed summary events based on age
    Summary.objects.filter(status='Closed',first_event__lt=seven_days_ago,last_event__lt=seven_days_ago).delete()

    # delete clsoed unreachables based on age
    Unreachable.objects.filter(status='Closed',event_start__lt=seven_days_ago,last_refresh__lt=seven_days_ago).delete()

    # Status objects
    # Status.objects.filter(child='').delete()

    finish_time = timezone.now()
    logger.info("Cleanup dashboard data runtime {}".format(finish_time - now))


@shared_task
def revoke_duplicate_tasks(task_name, task_args=[], request_id=None):
    ''' Testing duplicate task cleanup'''
    logger.info("Duplicate task check for {}".format(task_name))
    task_args = '"' + str(tuple(task_args)) + '"'
    logger.info(f'Current Task Args - {task_args}')
    logger.info(f'Request ID - {request_id}')
    duplicate_tasks = list(TaskResult.objects.filter(
        task_name=task_name,
        status__in=['PENDING', 'RECEIVED', 'STARTED'],
        task_args=task_args
    ).exclude(
        task_id=request_id
    ).values_list('task_id', flat=True))

    logger.info(f'revoking following duplicate tasks - {duplicate_tasks}')
    current_app.control.revoke(duplicate_tasks, terminate=True, signal='SIGKILL')
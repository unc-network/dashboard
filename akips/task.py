"""
Define tasks to be run in the background
"""
import logging
import time
import re
from datetime import datetime, timedelta

from celery import shared_task, current_app
from django_celery_results.models import TaskResult

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.template.loader import render_to_string

from akips.utils import AKIPS, Inventory
from akips.ocnes import EventManager
from akips.servicenow import ServiceNow

from .models import Device, HibernateRequest, Unreachable, Summary, Trap, Status, ServiceNowIncident

# Get an instance of a logger
logger = logging.getLogger(__name__)


@shared_task
def example_task():
    """
    A simple task example
    """
    logger.info("task is running")


@shared_task
def refresh_akips_devices():
    """
    Refresh local data for devices
    """
    logger.info("refreshing akips devices")
    now = timezone.now()
    sleep_delay = 0

    if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
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
                device_type = match_name.group('type').upper()
            elif match_location:
                tier = match_location.group('tier')
                bldg_name = match_location.group('bldg_name')
                device_type = match_location.group('type').upper()
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
                logger.warning("Attempting to set group membership for unknown device {}".format(key))
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
    logger.info("refreshing ping status")
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
                logger.warning("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'index': entry['index'],
                    'value': entry['state'],
                    'device_added': datetime.fromtimestamp(int(entry['device_added']), tz=timezone.get_current_timezone()),
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                    'ip4addr': entry['ipaddr']
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh ping status runtime {}".format(finish_time - now))

@shared_task
def refresh_snmp_status():
    logger.info("refreshing snmp status")
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
                logger.warning("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'index': entry['index'],
                    'value': entry['state'],
                    'device_added': datetime.fromtimestamp(int(entry['device_added']), tz=timezone.get_current_timezone()),
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                    'ip4addr': entry['ipaddr']
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh snmp status runtime {}".format(finish_time - now))

@shared_task
def refresh_ups_status():
    logger.info("refreshing ups status")
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
                logger.warning("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'index': entry['index'],
                    'value': entry['state'],
                    'device_added': datetime.fromtimestamp(int(entry['device_added']), tz=timezone.get_current_timezone()),
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                    'ip4addr': entry['ipaddr']
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh ups status runtime {}".format(finish_time - now))

@shared_task
def refresh_battery_test_status():
    logger.info("refreshing battery test status")
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
                logger.warning("Attempting to update unknown device {}".format(entry['device']))
                continue

            Status.objects.update_or_create(
                device=device,
                child=entry['child'],
                attribute=entry['attribute'],
                defaults={
                    'index': entry['index'],
                    'value': entry['state'],
                    'device_added': datetime.fromtimestamp(int(entry['device_added']), tz=timezone.get_current_timezone()),
                    'last_change': datetime.fromtimestamp(int(entry['event_start']), tz=timezone.get_current_timezone()),
                    'ip4addr': entry['ipaddr']
                }
            )
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("refresh battery test status runtime {}".format(finish_time - now))

@shared_task
def refresh_inventory():
    logger.info("Refreshing inventory device data")
    now = timezone.now()
    sleep_delay = 0

    if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
        sleep_delay = 0.05
        logger.debug("Delaying database by {} seconds".format(sleep_delay))
    else:
        logger.debug("Delaying database by {} seconds".format(sleep_delay))

    inventory = Inventory()
    device_data = inventory.get_device_data()
    #logger.debug("inventory data {}".format(device_data))
    if device_data:
        for device in device_data['nodes']:
            logger.debug("Updating device {}".format(device))
            if 'hierarchy' in device and device['hierarchy']:
                hierarchy = device['hierarchy']
                if device['hierarchy'] in ['TIER1', 'BES', 'EDGE', 'SPINE', 'POD']:
                    device_type = 'SWITCH'
                else:
                    device_type = device['hierarchy']
            elif 'type' in device and device['type']:
                hierarchy = ''
                device_type = device['type'].upper()
            else:
                hierarchy = ''
                device_type = ''
            if device['building_name'] is None:
                device['building_name'] = ''

            if device['inventory_url']:
                inventory_url = device['inventory_url']
            else:
                inventory_url = ''

            Device.objects.filter(ip4addr=device['ip']).update(
                # tier=device['tier1'],
                # building_name=device['building_name'],
                type=device_type.upper(),
                hierarchy=hierarchy.upper(),
                # type=device['type'].upper()
                # type=device['hierarchy'].upper()
                inventory_url=inventory_url
            )
            #logger.debug("Found devices {}".format(devices))
            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("Inventory refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_incidents():
    ''' Check for any needed updates '''
    logger.debug("Refreshing incidents")
    now = timezone.now()
    servicenow = ServiceNow()

    open_incidents = ServiceNowIncident.objects.filter(active=True)
    for incident in open_incidents:
        # pull the real incident from servicenow
        sn_incident = servicenow.get_incident( incident.instance, incident.sys_id )

        if sn_incident:
            logger.debug("{} state {} is active {}".format( sn_incident['number'], sn_incident['state'], sn_incident['active'] ))

            # State codes for reference
            # New=1
            # Active=2
            # Awaiting Problem=3
            # Awaiting User Info=4
            # Awaiting Evidence=5
            # Resolved=6
            # Closed=7
            if int(sn_incident['state']) == 6 or int(sn_incident['state']) == 7:
                incident.active=False
                incident.save()

    finish_time = timezone.now()
    logger.info("ServiceNow incident refresh runtime {}".format(finish_time - now))

@shared_task
def update_incident(number, message):
    logger.debug("Updating incident {} with text {}".format( number, message ))
    servicenow = ServiceNow()
    servicenow.update_incident(number,message)

@shared_task
def refresh_hibernate():
    logger.info("Refreshing hibernated devices")
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
    logger.info("Cleanup dashboard data is starting")
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

    # delete closed unreachables based on age
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

@shared_task(bind=True)
def refresh_unreachable(self, mode='poll', lock_expire=120):
    ''' Check for locks test '''
    logger.info(f"Task {self.request.id} starting refresh unreachable task")
    lock_id = "refresh_unreachable_task"
    lock_expire = lock_expire


    # cache.add fails if the key already exists
    if cache.add(lock_id, True, lock_expire):
        try:
            logger.info(f"Task {self.request.id} obtained refresh unreachable task lock")
            em = EventManager()

            sn_update_cleared = em.refresh_unreachable(mode=mode)
            for number, u_list in sn_update_cleared.items():
                logger.info("servicenow {} update for cleared {}".format(number,u_list))
                ctx = {
                    'type': 'clear',
                    'u_list': u_list
                }
                message = render_to_string('akips/incident_status_update.txt',ctx)
                update_incident.delay(number, message)

            sn_update_add = em.refresh_summary()
            for number, u_list in sn_update_add.items():
                logger.info("servicenow {} update for new unreachables{}".format(number,u_list))
                context = {
                    'type': 'new',
                    'u_list': u_list
                }
                message = render_to_string('akips/incident_status_update.txt',context)
                update_incident.delay(number, message)

        finally:
            logger.info(f"Task {self.request.id} releasing refresh unreachable task lock")
            cache.delete(lock_id)
    else:
        logger.info(f"Task {self.request.id} failed to get refresh unreachable task lock")

    logger.info(f"Task {self.request.id} finished refresh unreachable task")

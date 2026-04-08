"""
Define tasks to be run in the background
"""
import logging
import time
import re
import os
import gzip
import json
import tempfile
from datetime import datetime, timedelta

from celery import shared_task, current_app
from django_celery_results.models import TaskResult

from django.conf import settings
from django.apps import apps as django_apps
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from django.template.loader import render_to_string
from django.db.transaction import atomic

from akips.utils import AKIPS, Inventory
from akips.ocnes import EventManager
from akips.servicenow import ServiceNow

from .models import Device, HibernateRequest, Unreachable, Summary, Trap, Status, ServiceNowIncident, AKIPSConfiguration

# Get an instance of a logger
logger = logging.getLogger(__name__)

SNAPSHOT_FIXTURE_LABELS = ('akips', 'welcome', 'auth.group', 'auth.user')
SNAPSHOT_IMPORT_EXCLUDED_MODELS = {
    'akips.apiaccesskey',
    'admin.logentry',
    'auth.permission',
    'contenttypes.contenttype',
    'sessions.session',
}
SNAPSHOT_IMPORT_EXCLUDED_MODELS_MERGE_ONLY = {
    'akips.profile',
    'auth.group',
    'auth.user',
}
SNAPSHOT_IMPORT_LOCK_KEY = 'snapshot_import_task'
SNAPSHOT_IMPORT_LOCK_TIMEOUT = 60 * 60 * 4
SNAPSHOT_IMPORT_CACHE_PREFIX = 'snapshot_import_payload'
SNAPSHOT_IMPORT_PAYLOAD_TIMEOUT = SNAPSHOT_IMPORT_LOCK_TIMEOUT


def get_snapshot_import_models(fixture_labels=SNAPSHOT_FIXTURE_LABELS):
    models = []
    seen_labels = set()

    for fixture_label in fixture_labels:
        if '.' in fixture_label:
            candidate_models = [django_apps.get_model(fixture_label)]
        else:
            candidate_models = list(django_apps.get_app_config(fixture_label).get_models())

        for model in candidate_models:
            model_label = model._meta.label_lower
            if model_label in SNAPSHOT_IMPORT_EXCLUDED_MODELS:
                continue
            if model_label in seen_labels:
                continue
            seen_labels.add(model_label)
            models.append(model)

    return models


def clear_snapshot_import_targets(fixture_labels=SNAPSHOT_FIXTURE_LABELS):
    for model in reversed(get_snapshot_import_models(fixture_labels=fixture_labels)):
        model.objects.all().delete()


def is_snapshot_import_in_progress():
    return bool(cache.get(SNAPSHOT_IMPORT_LOCK_KEY))


def skip_task_for_snapshot_import(task_name):
    if not is_snapshot_import_in_progress():
        return False

    logger.warning('Skipping %s because a snapshot import is in progress', task_name)
    return True


def is_akips_enabled():
    return AKIPSConfiguration.get_solo().enabled


def skip_task_for_disabled_akips(task_name):
    if is_akips_enabled():
        return False

    logger.warning('Skipping %s because AKIPS integration is disabled', task_name)
    return True


def sanitize_snapshot_for_import(snapshot_path, clear_existing_data=False):
    opener = gzip.open if snapshot_path.lower().endswith('.gz') else open

    with opener(snapshot_path, 'rt', encoding='utf-8') as snapshot_file:
        snapshot_records = json.load(snapshot_file)

    filtered_records = []
    changed = False

    for record in snapshot_records:
        model_label = record.get('model')
        if model_label in SNAPSHOT_IMPORT_EXCLUDED_MODELS:
            changed = True
            continue
        if not clear_existing_data and model_label in SNAPSHOT_IMPORT_EXCLUDED_MODELS_MERGE_ONLY:
            changed = True
            continue

        fields = dict(record.get('fields', {}))
        if model_label == 'auth.group' and 'permissions' in fields:
            fields.pop('permissions', None)
            changed = True
        if model_label == 'auth.user' and 'user_permissions' in fields:
            fields.pop('user_permissions', None)
            changed = True

        if fields != record.get('fields', {}):
            updated_record = dict(record)
            updated_record['fields'] = fields
            filtered_records.append(updated_record)
        else:
            filtered_records.append(record)

    if not changed:
        return snapshot_path

    with tempfile.NamedTemporaryFile('w', suffix='.json', dir=os.path.dirname(snapshot_path), delete=False) as sanitized_file:
        json.dump(filtered_records, sanitized_file)
        return sanitized_file.name


def materialize_snapshot_import_source(snapshot_source):
    if snapshot_source and os.path.exists(snapshot_source):
        return snapshot_source, None

    cached_snapshot = cache.get(snapshot_source)
    if not cached_snapshot:
        raise FileNotFoundError(f'Snapshot import source not found: {snapshot_source}')

    payload = cached_snapshot.get('payload')
    suffix = cached_snapshot.get('suffix', '.json')
    if payload is None:
        raise FileNotFoundError(f'Snapshot import payload missing for cache key: {snapshot_source}')

    with tempfile.NamedTemporaryFile('wb', suffix=suffix, delete=False) as snapshot_file:
        snapshot_file.write(payload)
        return snapshot_file.name, snapshot_source


@shared_task
def import_snapshot_task(snapshot_source, clear_existing_data=False):
    """Import a snapshot fixture file in the background to avoid request timeouts."""
    snapshot_path = None
    import_path = None
    cached_snapshot_key = None

    if not cache.add(SNAPSHOT_IMPORT_LOCK_KEY, True, SNAPSHOT_IMPORT_LOCK_TIMEOUT):
        raise RuntimeError('A snapshot import is already in progress.')

    try:
        snapshot_path, cached_snapshot_key = materialize_snapshot_import_source(snapshot_source)
        import_path = sanitize_snapshot_for_import(snapshot_path, clear_existing_data=clear_existing_data)
        with atomic():
            if clear_existing_data:
                clear_snapshot_import_targets()
            call_command('loaddata', import_path)
        logger.info('Snapshot import task completed successfully: %s', snapshot_source)
    except Exception:
        logger.exception('Snapshot import task failed: %s', snapshot_source)
        raise
    finally:
        cache.delete(SNAPSHOT_IMPORT_LOCK_KEY)
        if cached_snapshot_key:
            cache.delete(cached_snapshot_key)
        if import_path != snapshot_path and import_path and os.path.exists(import_path):
            os.remove(import_path)
        if snapshot_path and os.path.exists(snapshot_path):
            os.remove(snapshot_path)


# Cache keys used by dashboard cards and chart data.
# Explicitly clear them at the end of refresh_unreachable because parts of
# that workflow use bulk updates and m2m operations that do not emit post_save.
DASHBOARD_CACHE_KEYS = [
    'crit_card_data',
    'tier_card_data',
    'bldg_card_data',
    'spec_card_data',
    'trap_card_data',
    'crit_card_json_data',
    'bldg_card_json_data',
    'spec_card_json_data',
    'trap_card_json_data',
    'chart_data',
]


def invalidate_dashboard_cache(reason=''):
    for key in DASHBOARD_CACHE_KEYS:
        cache.delete(key)
    if reason:
        logger.debug("Dashboard caches invalidated: %s", reason)
    else:
        logger.debug("Dashboard caches invalidated")


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
    if skip_task_for_snapshot_import('refresh_akips_devices'):
        return
    if skip_task_for_disabled_akips('refresh_akips_devices'):
        return

    logger.info("refreshing akips devices")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
            elif re.search(r'[-_]?(ap)[-_]?', value['SNMPv2-MIB.sysName'], re.IGNORECASE):
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
            current_group = 'default'
            notify = True
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
                        current_group = 'Critical'
                    elif g_match.group('index') == '1':
                        critical = True
                        current_group = 'Critical'
                    elif g_match.group('index') == '2':
                        tier = g_match.group('label')
                        current_group = 'default'
                    elif g_match.group('index') == '3':
                        current_group = 'default'
                    elif g_match.group('index') == '4':
                        bldg = g_match.group('label')
                        current_group = 'default'
                    elif g_match.group('index') == '5':
                        current_group = g_match.group('label')
                    elif g_match.group('index') == '6':
                        notify = False
                        current_group = g_match.group('label')
                    else:
                        logger.warning("device {} unhandled group index {} with label {}".format(device, g_match.group('index'), g_match.group('label')))
            device.critical = critical
            device.tier = tier
            device.building_name = bldg
            device.group = current_group
            device.notify = notify
            device.save()
            logger.debug("Set {} to critical {}, tier {}, and building {}".format(
                device, critical, tier, bldg))

            time.sleep(sleep_delay)

    finish_time = timezone.now()
    logger.info("AKIPS device refresh runtime {}".format(finish_time - now))


@shared_task
def refresh_ping_status():
    """
    Refresh local ping data
    """
    if skip_task_for_snapshot_import('refresh_ping_status'):
        return
    if skip_task_for_disabled_akips('refresh_ping_status'):
        return

    logger.info("refreshing ping status")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
    """
    Refresh local snmp data
    """
    if skip_task_for_snapshot_import('refresh_snmp_status'):
        return
    if skip_task_for_disabled_akips('refresh_snmp_status'):
        return

    logger.info("refreshing snmp status")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
    """
    Refresh local ups data
    """
    if skip_task_for_snapshot_import('refresh_ups_status'):
        return
    if skip_task_for_disabled_akips('refresh_ups_status'):
        return

    logger.info("refreshing ups status")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
    """
    Refresh local battery test data
    """
    if skip_task_for_snapshot_import('refresh_battery_test_status'):
        return
    if skip_task_for_disabled_akips('refresh_battery_test_status'):
        return

    logger.info("refreshing battery test status")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
    """
    Refresh external device inventory feed
    """
    if skip_task_for_snapshot_import('refresh_inventory'):
        return

    logger.info("Refreshing inventory device data")
    now = timezone.now()
    sleep_delay = 0

    logger.debug("Settings {}".format(settings.DATABASES))

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
                if device['hierarchy'] in ['TIER1', 'BES', 'EDGE', 'SPINE', 'POD', 'DATACENTER']:
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
    """
    Check for any needed updates
    """
    if skip_task_for_snapshot_import('refresh_incidents'):
        return

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
    """
    Update servicenow incident
    """
    logger.debug("Updating incident {} with text {}".format( number, message ))
    servicenow = ServiceNow()
    servicenow.update_incident(number,message)

@shared_task
def refresh_hibernate():
    """
    Refresh hibernate status
    """
    if skip_task_for_snapshot_import('refresh_hibernate'):
        return

    logger.info("Refreshing hibernated devices")
    now = timezone.now()
    sleep_delay = 0

    #if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
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
def cleanup_dashboard_data():
    """
    Remove old data
    """
    if skip_task_for_snapshot_import('cleanup_dashboard_data'):
        return

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
    """ 
    Testing duplicate task cleanup
    """
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
    """ 
    Check for locks test
    """
    if skip_task_for_snapshot_import('refresh_unreachable'):
        return
    if skip_task_for_disabled_akips('refresh_unreachable'):
        return

    logger.info(f"Task {self.request.id} starting refresh unreachable task")
    lock_id = "refresh_unreachable_task"
    lock_expire = lock_expire


    # cache.add fails if the key already exists
    if cache.add(lock_id, True, lock_expire):
        try:
            logger.debug(f"Task {self.request.id} obtained refresh unreachable task lock")
            em = EventManager()

            em.refresh_unreachable(mode=mode)
            # sn_update_cleared = em.refresh_unreachable(mode=mode)
            # for number, u_list in sn_update_cleared.items():
            #     logger.info("servicenow {} update for cleared {}".format(number,u_list))
            #     ctx = {
            #         'type': 'clear',
            #         'u_list': u_list
            #     }
            #     message = render_to_string('akips/incident_status_update.txt',ctx)
            #     update_incident.delay(number, message)

            em.refresh_summary()
            # sn_update_add = em.refresh_summary()
            # for number, u_list in sn_update_add.items():
            #     logger.info("servicenow {} update for new unreachables{}".format(number,u_list))
            #     context = {
            #         'type': 'new',
            #         'u_list': u_list
            #     }
            #     message = render_to_string('akips/incident_status_update.txt',context)
            #     update_incident.delay(number, message)

        finally:
            invalidate_dashboard_cache(reason=f"refresh_unreachable task {self.request.id}")
            logger.debug(f"Task {self.request.id} releasing refresh unreachable task lock")
            cache.delete(lock_id)
    else:
        logger.warning(f"Task {self.request.id} failed to get refresh unreachable task lock")

    logger.info(f"Task {self.request.id} finished refresh unreachable task")

"""
Module to handle OCNES business logic
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.utils import timezone
from django.template.loader import render_to_string

from .models import Device, Unreachable, Status, Summary
from .utils import AKIPS
#from akips.servicenow import ServiceNow
#from akips.task import update_incident
from akips.tdx import TDX

# Get an instance logger
logger = logging.getLogger(__name__)

class EventManager:
    """ Handle processing for unreachable changes and event summary updates """
    incident_update_add = {}
    update_incident_tickets = True
    tdx = TDX()

    def _record_unreachable_for_incident(self, summary, unreachable):
        """Track new unreachable associations for incident update messages."""
        if summary.tdx_incident:
            if summary.tdx_incident in self.incident_update_add:
                self.incident_update_add[summary.tdx_incident].append(unreachable)
            else:
                self.incident_update_add[summary.tdx_incident] = [unreachable]

    def _build_summary_count_data(self, summary_ids):
        """Return per-summary open device counts by type and total."""
        counts = {
            summary_id: {
                'SWITCH': 0,
                'AP': 0,
                'UPS': 0,
                'UNKNOWN': 0,
                'TOTAL': 0,
            }
            for summary_id in summary_ids
        }
        if not summary_ids:
            return counts

        through_model = Summary.unreachables.through
        base_qs = through_model.objects.filter(
            summary_id__in=summary_ids,
            unreachable__status='Open',
            unreachable__device__maintenance=False,
        )

        type_rows = base_qs.values('summary_id', 'unreachable__device__type').annotate(
            device_count=Count('unreachable__device_id', distinct=True)
        )
        for row in type_rows:
            summary_id = row['summary_id']
            device_type = row['unreachable__device__type']
            bucket = device_type if device_type in ['SWITCH', 'AP', 'UPS'] else 'UNKNOWN'
            counts[summary_id][bucket] += row['device_count']

        total_rows = base_qs.values('summary_id').annotate(
            device_count=Count('unreachable__device_id', distinct=True)
        )
        for row in total_rows:
            counts[row['summary_id']]['TOTAL'] = row['device_count']

        return counts

    def _build_summary_capacity_data(self):
        """Return precomputed max device and UPS battery counts keyed by summary name."""
        tier_max_count = {
            row['tier']: row['total']
            for row in Device.objects.values('tier').annotate(total=Count('id'))
        }
        building_max_count = {
            row['building_name']: row['total']
            for row in Device.objects.values('building_name').annotate(total=Count('id'))
        }
        specialty_max_count = {
            row['group']: row['total']
            for row in Device.objects.values('group').annotate(total=Count('id'))
        }

        tier_ups_battery = {
            row['device__tier']: row['total']
            for row in Status.objects.filter(
                attribute='UPS-MIB.upsOutputSource',
                value='battery',
            ).values('device__tier').annotate(total=Count('id'))
        }
        building_ups_battery = {
            row['device__building_name']: row['total']
            for row in Status.objects.filter(
                attribute='UPS-MIB.upsOutputSource',
                value='battery',
            ).values('device__building_name').annotate(total=Count('id'))
        }

        return {
            'tier_max_count': tier_max_count,
            'building_max_count': building_max_count,
            'specialty_max_count': specialty_max_count,
            'tier_ups_battery': tier_ups_battery,
            'building_ups_battery': building_ups_battery,
        }

    def refresh_unreachable(self,mode='poll'):
        """ Update current data for unreachable devices from AKiPS """
        logger.info("AKIPS unreachable refresh starting")
        now = timezone.now()
        t_start = time.perf_counter()
        sleep_delay = 0

        if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
            sleep_delay = 0.05
            logger.debug("Delaying database by {} seconds".format(sleep_delay))
        else:
            logger.debug("Delaying database by {} seconds".format(sleep_delay))

        # Combine all needed incident updates
        incident_update_cleared = {}
        t_after_setup = time.perf_counter()

        akips = AKIPS()
        if mode == 'status':
            unreachables = akips.get_unreachable_status()
        else:
            unreachables = akips.get_unreachable()

        unreachable_items = unreachables or {}
        logger.debug("unreachables: {}".format(len(unreachable_items)))
        t_after_fetch = time.perf_counter()

        t_after_upsert = t_after_fetch
        t_after_cleared_scan = t_after_fetch
        t_after_cleanup = t_after_fetch

        if unreachables:
            incoming_device_names = [entry.get('name') for entry in unreachable_items.values() if entry.get('name')]
            device_map = {
                device.name: device
                for device in Device.objects.filter(name__in=incoming_device_names)
            }

            for k, v in unreachables.items():
                logger.debug("{}".format(v['name']))
                device = device_map.get(v['name'])
                if not device:
                    logger.warning("Attempting to create unreachable data for unknown device {}".format(v['name']))
                    continue

                if device.maintenance is False:
                    Unreachable.objects.update_or_create(
                        device=device,
                        #status='Open',
                        #child = entry['child'],
                        # event_start = datetime.fromtimestamp( int(v['event_start']), tz=timezone.get_current_timezone() ),
                        event_start = v['event_start'],
                        defaults={
                            # 'name': key,                        # akips device name
                            'child': v['child'],            # ping4
                            'ping_state': v['ping_state'],            # down
                            'snmp_state': v['snmp_state'],            # down
                            'index': v['index'],            # 1
                            # 'device_added': datetime.fromtimestamp(int(v['device_added']), tz=timezone.get_current_timezone()),
                            'device_added': v['device_added'],
                            # 'event_start': datetime.fromtimestamp(int(v['event_start']), tz=timezone.get_current_timezone()),
                            'event_start': v['event_start'],
                            'ip4addr': v['ip4addr'],
                            'last_refresh': now,
                            'status': 'Open',
                        }
                    )
                    time.sleep(sleep_delay)

            t_after_upsert = time.perf_counter()

            # Handle unreachables that have cleared and need notifications
            cleared_unreachables = Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now).prefetch_related(
                Prefetch('summary_set', queryset=Summary.objects.filter(sn_incident__isnull=False))
            )
            for cleared in cleared_unreachables:
                for summary in cleared.summary_set.all():
                    logger.info("unreachable {} has cleared and was part of summary {}".format(cleared,summary))
                    if summary.tdx_incident in incident_update_cleared:
                        # sn_update_cleared[ summary.sn_incident.number ].append( cleared )
                        incident_update_cleared[ summary.tdx_incident ].append( cleared )
                    else:
                        # sn_update_cleared[ summary.sn_incident.number ] = [ cleared ]
                        incident_update_cleared[ summary.tdx_incident ] = [ cleared ]

            t_after_cleared_scan = time.perf_counter()

            # A down device may have moved into AKiPS maintenance mode after the fact.
            # They never clear since AKiPS doesn't poll them. Close the OCNES unreachable.
            Unreachable.objects.filter(status='Open', device__maintenance=True).update(status='Closed',last_refresh=now)

            # Handle unreachables with disabled notifications
            # Unreachable.objects.filter(status='Open', device__notify=False).summary_set.clear()
            ignored_unreachables = Unreachable.objects.filter(status='Open', device__notify=False)
            for ignored in ignored_unreachables:
                logger.info(f"unreachable {ignored} has notifications disabled, removing from all summaries")
                ignored.summary_set.clear()

            # Handle unreachables that have moved to hibernate mode
            # Unreachable.objects.filter(status='Open', device__hibernate=True).summary_set.clear()
            hibernated_unreachables = Unreachable.objects.filter(status='Open', device__hibernate=True)
            for hibernated in hibernated_unreachables:
                logger.info(f"unreachable {hibernated} has been set to hibernate, removing from all summaries")
                hibernated.summary_set.clear()

            # Remove stale entries
            Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')

            t_after_cleanup = time.perf_counter()

        tdx_attempted = []
        tdx_succeeded = []
        tdx_failed = []

        if self.update_incident_tickets:
            # logger.info("incident cleared {}".format(incident_update_cleared))
            for number, u_list in incident_update_cleared.items():
                logger.info("incident {} update for cleared {}".format(number,u_list))
                ctx = {
                    'type': 'clear',
                    'u_list': u_list
                }
                message = render_to_string('akips/incident_status_update.txt',ctx)
                tdx_attempted.append(str(number))
                result = self.tdx.update_ticket(number, message)
                if result is None:
                    tdx_failed.append(str(number))
                    logger.warning(
                        "TDX incident update failed for cleared unreachable set: ticket=%s unreachable_count=%s",
                        number,
                        len(u_list),
                    )
                else:
                    tdx_succeeded.append(str(number))
                    logger.info(f"Updating incident {number} for cleared unreachables {u_list}")

        t_after_incident_updates = time.perf_counter()

        logger.info(
            "TDX update summary (refresh_unreachable): attempted=%s succeeded=%s failed=%s attempted_ids=%s failed_ids=%s",
            len(tdx_attempted),
            len(tdx_succeeded),
            len(tdx_failed),
            ",".join(sorted(set(tdx_attempted))) if tdx_attempted else "none",
            ",".join(sorted(set(tdx_failed))) if tdx_failed else "none",
        )

        logger.info(
            "AKIPS unreachable timing: setup=%.3fs fetch_akips=%.3fs upsert_unreachables=%.3fs scan_cleared=%.3fs cleanup=%.3fs incident_updates=%.3fs total=%.3fs",
            t_after_setup - t_start,
            t_after_fetch - t_after_setup,
            t_after_upsert - t_after_fetch,
            t_after_cleared_scan - t_after_upsert,
            t_after_cleanup - t_after_cleared_scan,
            t_after_incident_updates - t_after_cleanup,
            t_after_incident_updates - t_start,
        )

        finish_time = timezone.now()
        logger.info("AKIPS unreachable refresh runtime {}".format(finish_time - now))

        # return sn_update_cleared
        return

    def refresh_summary(self):
        """ Update the summary data """
        logger.info("AKIPS summary refresh starting")
        now = timezone.now()
        t_start = time.perf_counter()
        sleep_delay = 0

        if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
            sleep_delay = 0.05
            logger.debug("Delaying database by {} seconds".format(sleep_delay))
        else:
            logger.debug("Delaying database by {} seconds".format(sleep_delay))

        # Incident updates
        self.incident_update_add = {}
        t_after_setup = time.perf_counter()

        # Process all current unreachable records
        unreachables = Unreachable.objects.filter(
            status='Open',
            device__maintenance=False,
        ).exclude(
            device__hibernate=True,
        ).exclude(
            device__notify=False,
        ).select_related('device')

        unreachable_count = unreachables.count()
        t_after_unreachable_query = time.perf_counter()

        if settings.MAX_UNREACHABLE and unreachable_count >= settings.MAX_UNREACHABLE:
            # Something may be wrong, stop processing summaries
            logger.error(f"AKiPS is showing an excessive amount of devices down and summary updates are being halted.  {unreachable_count} vs max allowed {settings.MAX_UNREACHABLE}")
            logger.info(
                "AKIPS summary timing (aborted): setup=%.3fs query_unreachables=%.3fs total=%.3fs",
                t_after_setup - t_start,
                t_after_unreachable_query - t_after_setup,
                time.perf_counter() - t_start,
            )
            finish_time = timezone.now()
            logger.info("AKIPS summary refresh runtime {}".format(finish_time - now))
            return None

        for unreachable in unreachables:
            logger.debug("Processing unreachable {}".format(unreachable))
            if unreachable.device.critical:
                # Handle Critical devices
                self.update_critical(now, unreachable)
            elif unreachable.device.group == 'default':
                # Handle Non-Critical switch, ap, and ups devices
                self.update_tier(now, unreachable)
                self.update_building(now, unreachable)
            else:
                # Handle Special device groupings
                self.update_special(now, unreachable)
            time.sleep(sleep_delay)
            t_after_unreachable_processing = time.perf_counter()

        # Process all ups on battery
        ups_on_battery = Status.objects.filter(
            attribute='UPS-MIB.upsOutputSource',
            value='battery',
            device__maintenance=False,
        ).exclude(
            device__hibernate=True,
        ).exclude(
            device__notify=False,
        ).select_related('device')
        for ups in ups_on_battery:
            logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))
            self.update_tier_battery(now, ups)
            self.update_building_battery(now, ups)
        t_after_battery_processing = time.perf_counter()

        # Calculate summary counts using precomputed aggregates to reduce query volume
        summaries = list(Summary.objects.filter(status='Open'))
        summary_ids = [summary.id for summary in summaries]
        summary_count_data = self._build_summary_count_data(summary_ids)
        summary_capacity_data = self._build_summary_capacity_data()
        t_after_summary_precompute = time.perf_counter()
        for summary in summaries:
            self.update_summary_count(
                now,
                summary,
                summary_count_data.get(summary.id),
                summary_capacity_data,
            )
            time.sleep(sleep_delay)
        t_after_summary_updates = time.perf_counter()

        # Close building type events open with no down devices
        #Summary.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')
        five_minutes_ago = now - timedelta(minutes=5)
        Summary.objects.filter(status='Open').exclude(last_refresh__gte=five_minutes_ago).update(status='Closed')
        t_after_close_stale = time.perf_counter()

        tdx_attempted = []
        tdx_succeeded = []
        tdx_failed = []

        if self.update_incident_tickets:
            # logger.info("servicenow new {}".format(sn_update_add))
            for number, u_list in self.incident_update_add.items():
                logger.info("incident {} update for new unreachables{}".format(number,u_list))
                context = {
                    'type': 'new',
                    'u_list': u_list
                }
                message = render_to_string('akips/incident_status_update.txt',context)
                tdx_attempted.append(str(number))
                result = self.tdx.update_ticket(number, message)
                if result is None:
                    tdx_failed.append(str(number))
                    logger.warning(
                        "TDX incident update failed for new unreachable set: ticket=%s unreachable_count=%s",
                        number,
                        len(u_list),
                    )
                else:
                    tdx_succeeded.append(str(number))
                    logger.info(f"Updating incident {number} for new unreachables {u_list}")
        t_after_incident_updates = time.perf_counter()

        logger.info(
            "TDX update summary (refresh_summary): attempted=%s succeeded=%s failed=%s attempted_ids=%s failed_ids=%s",
            len(tdx_attempted),
            len(tdx_succeeded),
            len(tdx_failed),
            ",".join(sorted(set(tdx_attempted))) if tdx_attempted else "none",
            ",".join(sorted(set(tdx_failed))) if tdx_failed else "none",
        )

        logger.info(
            "AKIPS summary timing: setup=%.3fs query_unreachables=%.3fs process_unreachables=%.3fs process_battery=%.3fs precompute_counts=%.3fs update_summaries=%.3fs close_stale=%.3fs incident_updates=%.3fs total=%.3fs",
            t_after_setup - t_start,
            t_after_unreachable_query - t_after_setup,
            t_after_unreachable_processing - t_after_unreachable_query,
            t_after_battery_processing - t_after_unreachable_processing,
            t_after_summary_precompute - t_after_battery_processing,
            t_after_summary_updates - t_after_summary_precompute,
            t_after_close_stale - t_after_summary_updates,
            t_after_incident_updates - t_after_close_stale,
            t_after_incident_updates - t_start,
        )

        finish_time = timezone.now()
        logger.info("AKIPS summary refresh runtime {}".format(finish_time - now))
        # return sn_update_add
        return

    def update_critical(self, now, unreachable):
        ''' Update summary for critical unreachable device '''
        logger.debug("Processing critical {}".format(unreachable))

        if unreachable.device.maintenance is True or unreachable.device.notify is False:
            logger.info(f"Unreachable device {unreachable.device} should be excluded from summary")
            return

        if unreachable.device.sysName:
            device_name = unreachable.device.sysName
        else:
            device_name = unreachable.device.name
        
        try:
            c_summary, c_created = Summary.objects.get_or_create(
                type='Critical',
                #name=unreachable.device.name,
                name=device_name,
                status='Open',
                defaults={
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    'max_count': 1
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            c_summary = Summary.objects.filter(type='Critical',name=device_name,status='Open').first()
            c_created = False
        if c_created:
            logger.debug("Crit summary created {}".format(unreachable.device.name))
        else:
            if c_summary.first_event > unreachable.event_start:
                c_summary.first_event = unreachable.event_start
            if c_summary.last_event < unreachable.event_start:
                c_summary.last_event = unreachable.event_start
            c_summary.last_refresh = now
            c_summary.save()
        if c_summary.unreachables.filter(id=unreachable.id).exists():
            logger.debug("Unreachable {} already associated to summary {}".format(unreachable,c_summary))
        else:
            logger.debug("Unreachable {} is new to summary {}".format(unreachable,c_summary))
            c_summary.unreachables.add(unreachable)
            self._record_unreachable_for_incident(c_summary, unreachable)

    def update_tier(self, now, unreachable):
        ''' Update Tier summary for default unreachable network device '''
        logger.debug("Processing tier for unreachable {}".format( unreachable.device ))

        if unreachable.device.maintenance is True or unreachable.device.notify is False:
            logger.info(f"Unreachable device {unreachable.device} should be excluded from summary")
            return

        # Handle blank tier or building names
        if unreachable.device.tier:
            tier_name = unreachable.device.tier
        else:
            tier_name = 'Other'
        
        # Find the tier summary to update
        try:
            t_summary, t_created = Summary.objects.get_or_create(
                type='Distribution',
                name=tier_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    #'max_count': Device.objects.filter(tier=unreachable.device.tier).count()
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            t_summary = Summary.objects.filter(type='Distribution',name=tier_name,status='Open').first()
            t_created = False
        if t_created:
            logger.debug("Tier summary created {}".format(tier_name))
        else:
            #t_summary.max_count = Device.objects.filter(tier=unreachable.device.tier).count()
            if t_summary.first_event > unreachable.event_start:
                t_summary.first_event = unreachable.event_start
            if t_summary.last_event < unreachable.event_start:
                t_summary.last_event = unreachable.event_start
            t_summary.last_refresh = now
            t_summary.save()
        if t_summary.unreachables.filter(id=unreachable.id).exists():
            logger.debug("Unreachable {} already associated to summary {}".format(unreachable,t_summary))
        else:
            logger.debug("Unreachable {} is new to summary {}".format(unreachable,t_summary))
            t_summary.unreachables.add(unreachable)
            self._record_unreachable_for_incident(t_summary, unreachable)

    def update_building(self, now, unreachable):
        ''' Update summary for building of unreachable device '''
        logger.debug("Processing building for unreachable {}".format( unreachable.device ))

        if unreachable.device.maintenance is True or unreachable.device.notify is False:
            logger.info(f"Unreachable device {unreachable.device} should be excluded from summary")
            return

        # Handle blank tier or building names
        if unreachable.device.tier:
            tier_name = unreachable.device.tier
        else:
            tier_name = 'Other'
        if unreachable.device.building_name:
            bldg_name = unreachable.device.building_name
        else:
            bldg_name = 'Other'
        
        # Find the building summary to update
        try:
            b_summary, b_created = Summary.objects.get_or_create(
                type='Building',
                name=bldg_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    #'max_count': Device.objects.filter(building_name=unreachable.device.building_name).count(),
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            b_summary = Summary.objects.filter(type='Building',name=bldg_name,status='Open').first()
            b_created = False
        if b_created:
            logger.debug("Building summary created {}".format(bldg_name))
        else:
            #b_summary.max_count = Device.objects.filter(building_name=unreachable.device.building_name).count()
            if b_summary.first_event > unreachable.event_start:
                b_summary.first_event = unreachable.event_start
            if b_summary.last_event < unreachable.event_start:
                b_summary.last_event = unreachable.event_start
            b_summary.last_refresh = now
            b_summary.save()
        if b_summary.unreachables.filter(id=unreachable.id).exists():
            logger.debug("Unreachable {} already associated to summary {}".format(unreachable,b_summary))
        else:
            logger.debug("Unreachable {} is new to summary {}".format(unreachable,b_summary))
            b_summary.unreachables.add(unreachable)
            self._record_unreachable_for_incident(b_summary, unreachable)

    def update_special(self, now, unreachable):
        ''' Update summary for non critical and non default unreachable device '''
        logger.debug("Processing special group {}".format( unreachable.device.group ))

        if unreachable.device.maintenance is True or unreachable.device.notify is False:
            logger.info(f"Unreachable device {unreachable.device} should be excluded from summary")
            return

        # Find the specialty summary to update
        try:
            s_summary, s_created = Summary.objects.get_or_create(
                type='Specialty',
                name= unreachable.device.group,
                status='Open',
                defaults={
                    'first_event': unreachable.event_start,
                    'last_event': unreachable.event_start,
                    #'max_count': Device.objects.filter(group=unreachable.device.group).count(),
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            s_summary = Summary.objects.filter(type='Specialty',name=unreachable.device.group,status='Open').first()
            s_created = False
        if s_created:
            logger.debug("Specialty summary created {}".format( unreachable.device.group ))
        else:
            #s_summary.max_count = Device.objects.filter(group=unreachable.device.group).count()
            if s_summary.first_event > unreachable.event_start:
                s_summary.first_event = unreachable.event_start
            if s_summary.last_event < unreachable.event_start:
                s_summary.last_event = unreachable.event_start
            s_summary.last_refresh = now
            s_summary.save()
        if s_summary.unreachables.filter(id=unreachable.id).exists():
            logger.debug("Unreachable {} already associated to summary {}".format(unreachable,s_summary))
        else:
            logger.debug("Unreachable {} is new to summary {}".format(unreachable,s_summary))
            s_summary.unreachables.add(unreachable)
            self._record_unreachable_for_incident(s_summary, unreachable)

    def update_tier_battery(self, now, ups):
        ''' Update tier summary for ups on battery '''
        logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))

        if ups.device.maintenance is True or ups.device.notify is False:
            logger.info(f"Unreachable device {ups.device} should be excluded from summary")
            return

        # Handle blank tier or building names
        if ups.device.tier:
            tier_name = ups.device.tier
        else:
            tier_name = 'Other'

        # Find the tier summary to update
        try:
            t_summary, t_created = Summary.objects.get_or_create(
                type='Distribution',
                name=tier_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': ups.last_change,
                    'last_event': ups.last_change,
                    #'max_count': Device.objects.filter(tier=ups.device.tier).count(),
                    #'ups_battery': Status.objects.filter(device__tier=ups.device.tier,attribute='UPS-MIB.upsOutputSource',value='battery').count()
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            # t_summary = Summary.objects.filter(type='Distribution',name=ups.device.tier,status='Open').first()
            t_summary = Summary.objects.filter(type='Distribution',name=tier_name,status='Open').first()
            t_created = False
            logger.debug("Hit duplicate summary for tier {}".format(tier_name))
        if t_created:
            logger.debug("Tier summary created {}".format(ups.device.tier))
        else:
            #t_summary.ups_battery = Status.objects.filter(device__tier=ups.device.tier,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            if t_summary.first_event > ups.last_change:
                t_summary.first_event = ups.last_change
            if t_summary.last_event < ups.last_change:
                t_summary.last_event = ups.last_change
            t_summary.last_refresh = now
            t_summary.save()
        t_summary.batteries.add(ups)

    def update_building_battery(self, now, ups):
        ''' Update building summary for ups on battery '''
        logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))

        if ups.device.maintenance is True or ups.device.notify is False:
            logger.info(f"Unreachable device {ups.device} should be excluded from summary")
            return

        # Handle blank tier or building names
        if ups.device.tier:
            tier_name = ups.device.tier
        else:
            tier_name = 'Other'
        if ups.device.building_name:
            bldg_name = ups.device.building_name
        else:
            bldg_name = 'Other'
        
        # Find the building summary to update
        try:
            b_summary, b_created = Summary.objects.get_or_create(
                type='Building',
                name=bldg_name,
                status='Open',
                defaults={
                    'tier': tier_name,
                    'first_event': ups.last_change,
                    'last_event': ups.last_change,
                    #'max_count': Device.objects.filter(building_name=ups.device.building_name).count(),
                    #'ups_battery': Status.objects.filter(device__building_name=ups.device.building_name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
                }
            )
        except Summary.MultipleObjectsReturned:
            # if we get more than one, just use the first
            # b_summary = Summary.objects.filter(type='Building',name=ups.device.building_name,status='Open').first()
            b_summary = Summary.objects.filter(type='Building',name=bldg_name,status='Open').first()
            b_created = False
            logger.debug("Hit duplicate summary for building {}".format(bldg_name))
        if b_created:
            logger.debug("Building summary created {}".format( ups.device.building_name ))
        else:
            #b_summary.ups_battery = Status.objects.filter(device__building_name=ups.device.building_name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
            if b_summary.first_event > ups.last_change:
                b_summary.first_event = ups.last_change
            if b_summary.last_event < ups.last_change:
                b_summary.last_event = ups.last_change
            b_summary.last_refresh = now
            b_summary.save()
        b_summary.batteries.add(ups)

    def update_summary_count(self, now, summary, count_data=None, summary_capacity_data=None):
        ''' Calculate overall summary stats '''
        logger.debug("Updating counts on {}".format(summary))

        count_data = count_data or {
            'SWITCH': 0,
            'AP': 0,
            'UPS': 0,
            'UNKNOWN': 0,
            'TOTAL': 0,
        }
        summary_capacity_data = summary_capacity_data or {
            'tier_max_count': {},
            'building_max_count': {},
            'specialty_max_count': {},
            'tier_ups_battery': {},
            'building_ups_battery': {},
        }
        tier_max_count = summary_capacity_data['tier_max_count']
        building_max_count = summary_capacity_data['building_max_count']
        specialty_max_count = summary_capacity_data['specialty_max_count']
        tier_ups_battery = summary_capacity_data['tier_ups_battery']
        building_ups_battery = summary_capacity_data['building_ups_battery']

        logger.debug("Counts {} are {}".format(summary.name, count_data))

        if summary.type == 'Distribution':
            summary.max_count = tier_max_count.get(summary.name, 0)
            summary.ups_battery = tier_ups_battery.get(summary.name, 0)
        elif summary.type == 'Building':
            summary.max_count = building_max_count.get(summary.name, 0)
            summary.ups_battery = building_ups_battery.get(summary.name, 0)
        elif summary.type == 'Specialty':
            summary.max_count = specialty_max_count.get(summary.name, 0)

        summary.switch_count = count_data['SWITCH']
        summary.ap_count = count_data['AP']
        summary.ups_count = count_data['UPS']
        total_count = count_data['TOTAL']
        if summary.max_count == 0:
            percent_down = 0
        else:
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
        if total_count == 0:
            summary.trend = 'Recovered'
        elif summary.first_event >= new_threshold:
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

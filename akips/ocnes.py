"""
Module to handle OCNES business logic
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.template.loader import render_to_string

from .models import Device, Unreachable, Status, Summary
from .utils import AKIPS
#from akips.servicenow import ServiceNow
#from akips.task import update_incident

# Get an instance logger
logger = logging.getLogger(__name__)

class EventManager:
    """ Handle processing for unreachable changes and event summary updates """

    def refresh_unreachable(self,mode='poll'):
        """ Update current data for unreachable devices from AKiPS """
        logger.info("AKIPS unreachable refresh starting")
        now = timezone.now()
        sleep_delay = 0

        if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
            sleep_delay = 0.05
            logger.debug("Delaying database by {} seconds".format(sleep_delay))
        else:
            logger.debug("Delaying database by {} seconds".format(sleep_delay))

        # Combine all needed SN updates
        sn_update_cleared = {}

        akips = AKIPS()
        if mode == 'status':
            unreachables = akips.get_unreachable_status()
        else:
            unreachables = akips.get_unreachable()
        logger.debug("unreachables: {}".format( len(unreachables) ))
        if unreachables:
            for k, v in unreachables.items():
                logger.debug("{}".format(v['name']))
                try:
                    device = Device.objects.get(name=v['name'])
                except Device.DoesNotExist:
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

            # Handle unreachables that have cleared and need notifications
            # cleared_unreachables = Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now)
            # for cleared in cleared_unreachables:
            #     # for summary in cleared.summary_set.all():
            #     for summary in cleared.summary_set.filter(sn_incident__isnull=False):
            #         logger.debug("unreachable {} has cleared and was port of summary {}".format(cleared,summary))
            #         if summary.sn_incident.number in sn_update_cleared:
            #             sn_update_cleared[ summary.sn_incident.number ].append( cleared )
            #         else:
            #             sn_update_cleared[ summary.sn_incident.number ] = [ cleared ]

            # Close unreachables for AKiPS maintenance mode devices, they never clear in AKiPS
            Unreachable.objects.filter(status='Open', device__maintenance=True).update(status='Closed',last_refresh=now)

            # Remove stale entries
            Unreachable.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')

        # logger.info("servicenow cleared {}".format(sn_update_cleared))
        # for number, u_list in sn_update_cleared.items():
        #     logger.info("servicenow {} update for cleared {}".format(number,u_list))
        #     ctx = {
        #         'type': 'clear',
        #         'u_list': u_list
        #     }
        #     message = render_to_string('akips/incident_status_update.txt',ctx)
        #     update_incident.delay(number, message)

        finish_time = timezone.now()
        logger.info("AKIPS unreachable refresh runtime {}".format(finish_time - now))
        return sn_update_cleared

    def refresh_summary(self):
        """ Update the summary data """
        logger.info("AKIPS summary refresh starting")
        now = timezone.now()
        sleep_delay = 0

        if settings.OPENSHIFT_NAMESPACE == 'LOCAL':
            sleep_delay = 0.05
            logger.debug("Delaying database by {} seconds".format(sleep_delay))
        else:
            logger.debug("Delaying database by {} seconds".format(sleep_delay))

        # ServiceNow updates
        sn_update_add = {}

        # Process all current unreachable records
        unreachables = Unreachable.objects.filter(status='Open', device__maintenance=False).exclude(device__hibernate=True).exclude(device__notify=False)

        if settings.MAX_UNREACHABLE and len(unreachables) >= settings.MAX_UNREACHABLE:
            # Something may be wrong, stop processing summaries
            logger.error(f"AKiPS is showing an excessive amount of devices down and summary updates are being halted.  {len(unreachables)} vs max allowed {settings.MAX_UNREACHABLE}")
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

        # Process all ups on battery
        ups_on_battery = Status.objects.filter(attribute='UPS-MIB.upsOutputSource',value='battery',device__maintenance=False).exclude(device__hibernate=True).exclude(device__notify=False)
        for ups in ups_on_battery:
            logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))
            self.update_tier_battery(now, ups)
            self.update_building_battery(now, ups)

        # Calculate summary counts
        summaries = Summary.objects.filter(status='Open')
        for summary in summaries:
            self.update_summary_count(now, summary)
            time.sleep(sleep_delay)

        # Close building type events open with no down devices
        #Summary.objects.filter(status='Open').exclude(last_refresh__gte=now).update(status='Closed')
        five_minutes_ago = now - timedelta(minutes=5)
        Summary.objects.filter(status='Open').exclude(last_refresh__gte=five_minutes_ago).update(status='Closed')

        # logger.info("servicenow new {}".format(sn_update_add))
        # for number, u_list in sn_update_add.items():
        #     logger.info("servicenow {} update for new unreachables{}".format(number,u_list))
        #     context = {
        #         'type': 'new',
        #         'u_list': u_list
        #     }
        #     message = render_to_string('akips/incident_status_update.txt',context)
        #     update_incident.delay(number, message)

        finish_time = timezone.now()
        logger.info("AKIPS summary refresh runtime {}".format(finish_time - now))
        return sn_update_add

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

    def update_tier_battery(self, now, ups):
        ''' Update tier summary for ups on battery '''
        logger.debug("Processing ups on battery {} in {} under {}".format(ups.device,ups.device.building_name,ups.device.tier))

        if ups.maintenance is True or ups.notify is False:
            logger.info(f"Unreachable device {ups} should be excluded from summary")
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

        if ups.maintenance is True or ups.notify is False:
            logger.info(f"Unreachable device {ups} should be excluded from summary")
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

    def update_summary_count(self, now, summary):
        ''' Calculate overall summary stats '''
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
            if unreachable.device.maintenance is False:
                if unreachable.device.type in ['SWITCH', 'AP', 'UPS']:
                    count[unreachable.device.type][unreachable.device.name] = True
                else:
                    count['UNKNOWN'][unreachable.device.name] = True
                count['TOTAL'][unreachable.device.name] = True
        logger.debug("Counts {} are {}".format(summary.name, count))

        if summary.type == 'Distribution':
            summary.max_count = Device.objects.filter(tier=summary.name).count()
            summary.ups_battery = Status.objects.filter(device__tier=summary.name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
        elif summary.type == 'Building':
            summary.max_count = Device.objects.filter(building_name=summary.name).count()
            summary.ups_battery = Status.objects.filter(device__building_name=summary.name,attribute='UPS-MIB.upsOutputSource',value='battery').count()
        elif summary.type == 'Special':
            summary.max_count = Device.objects.filter(group=summary.name).count()

        summary.switch_count = len(count['SWITCH'].keys())
        summary.ap_count = len(count['AP'].keys())
        summary.ups_count = len(count['UPS'].keys())
        total_count = len(count['TOTAL'].keys())
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

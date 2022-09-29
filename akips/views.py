import logging
import json
import re
from datetime import datetime, timedelta
from secrets import compare_digest
import math

from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.views.generic import View
from django.http import Http404, JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
#from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone

from django.db.models import Count
from django.db.models.functions import TruncHour

#from django.utils.decorators import method_decorator
from django.db.transaction import atomic, non_atomic_requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Summary, Unreachable, Device, SNMPTrap, UserAlert
from .forms import IncidentForm
from .task import example_task
from .utils import AKIPS, ServiceNow, pretty_duration

# Get a instance of logger
logger = logging.getLogger(__name__)

# Create your views here.

# def handler403(request, exception):
#     response = render(request, "dashboard/error_pages/403.html")
#     response.status_code = 403

#     return response

# def handler404(request, exception):
#     response = render(request, "dashboard/error_pages/404.html")
#     response.status_code = 404

#     return response

# def handler500(request):
#     response = render(request, "dashboard/error_pages/500.html")
#     response.status_code = 500

#     return response

# def login(request, *args, **kwargs):
#     if request.method == 'POST':
#         if not request.POST.get('remember_me', None):
#             request.session.set_expiry(0)
#     return auth_views.login(request, *args, **kwargs)

class Home(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}
        # now = timezone.now()
        # request.session.set_expiry(0) # If value is 0, the user’s session cookie will expire when the user’s Web browser is closed.
        # age = request.session.get_expiry_age()
        # logger.debug("expiry age {}".format(age))

        context['user_alerts'] = UserAlert.objects.all()

        context['critical'] = Summary.objects.filter(
            type='Critical', status='Open').order_by('name')
        context['tiers'] = Summary.objects.filter(
            type='Distribution', status='Open').order_by('name')
        context['bldgs'] = Summary.objects.filter(
            type='Building', status='Open').order_by('name')

        context['traps'] = SNMPTrap.objects.all().order_by('-tt')[:50]



        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        post_template = 'akips/incident.html'
        context = {}

        return render(request, post_template, context=context)


class CritCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_crit.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['summaries'] = Summary.objects.filter(
            type='Critical', status='Open').order_by('name')
        return render(request, self.template_name, context=context)


class TierCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_tier.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['summaries'] = Summary.objects.filter(
            type='Distribution', status='Open').order_by('name')
        return render(request, self.template_name, context=context)


class BuildingCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_bldg.html'

    def get(self, request, *args, **kwargs):
        context = {}
        #context['summaries'] = Summary.objects.filter(type='Building',status='Open').order_by('name')
        types = ['Distribution', 'Building']
        context['summaries'] = Summary.objects.filter(
            type__in=types, status='Open').order_by('tier', '-type', 'name')
        return render(request, self.template_name, context=context)


class TrapCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_trap.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['traps'] = SNMPTrap.objects.filter(
            status='Open').order_by('-tt')[:50]
        return render(request, self.template_name, context=context)


class UnreachableView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/unreachable.html'

    def get(self, request, *args, **kwargs):
        context = {}

        unreachables = Unreachable.objects.filter(
            status='Open', device__maintenance=False).order_by('device__name')
        context['unreachables'] = unreachables

        return render(request, self.template_name, context=context)


class SummaryView(LoginRequiredMixin, View):
    ''' Generic summary view '''
    template_name = 'akips/summary.html'

    def get(self, request, *args, **kwargs):
        context = {}
        summary_id = self.kwargs.get('id', None)

        summary = get_object_or_404(Summary, id=summary_id)

        context['u_open'] = summary.unreachables.filter(
            status='Open').order_by('device__name')
        context['u_closed'] = summary.unreachables.filter(
            status='Closed').order_by('device__name')
        context['summary'] = summary

        return render(request, self.template_name, context=context)


class TierView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/tier.html'

    def get(self, request, *args, **kwargs):
        context = {}
        tier_name = self.kwargs.get('tier', None)
        if tier_name is None:
            raise Http404("Invalid Tier Name")
        context['tier'] = tier_name

        if tier_name == 'Unknown':
            tier_name = ''
        devices = Unreachable.objects.filter(
            status='Open', device__tier=tier_name).order_by('device__name')
        context['devices'] = devices

        return render(request, self.template_name, context=context)


class BuildingView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/building.html'

    def get(self, request, *args, **kwargs):
        context = {}
        bldg_name = self.kwargs.get('bldg', None)
        if bldg_name is None:
            raise Http404("Invalid Building Name")
        context['bldg'] = bldg_name

        if bldg_name == 'Unknown':
            bldg_name = ''
        #devices = Unreachable.objects.filter(device__building_name=bldg_name)
        devices = Unreachable.objects.filter(
            status='Open', device__building_name=bldg_name).order_by('device__name')
        context['devices'] = devices

        return render(request, self.template_name, context=context)


class RecentSummaryView(LoginRequiredMixin, View):
    ''' Generic recent summary view '''
    template_name = 'akips/recent.html'

    def get(self, request, *args, **kwargs):
        context = {}

        date_from = timezone.now() - timezone.timedelta(days=1)
        # types = ['Critical', 'Building']
        # summaries = Summary.objects.filter( type__in=types, last_event__gte=date_from, status='Closed' ).order_by('-first_event')
        summaries = Summary.objects.filter( last_event__gte=date_from, status='Closed' ).order_by('-first_event')
        context['summaries'] = summaries

        return render(request, self.template_name, context=context)

class RecentTrapsView(LoginRequiredMixin, View):
    ''' Generic recent traps view '''
    template_name = 'akips/recent_traps.html'

    def get(self, request, *args, **kwargs):
        context = {}
        date_from = timezone.now() - timezone.timedelta(days=1)
        traps = SNMPTrap.objects.filter( tt__gte=date_from, status='Closed' ).order_by('-tt')
        context['traps'] = traps
        return render(request, self.template_name, context=context)

class RecentUnreachablesView(LoginRequiredMixin, View):
    ''' Generic recent unreachables view '''
    template_name = 'akips/recent_unreachables.html'

    def get(self, request, *args, **kwargs):
        context = {}
        date_from = timezone.now() - timezone.timedelta(days=1)
        unreachables = Unreachable.objects.filter( event_start__gte=date_from, status='Closed' ).order_by('-event_start')
        context['unreachables'] = unreachables
        return render(request, self.template_name, context=context)


class DeviceView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/device.html'

    def get(self, request, *args, **kwargs):
        context = {}
        device_name = self.kwargs.get('name', None)
        if device_name is None:
            raise Http404("Invalid Device Name")
        context['name'] = device_name

        device = get_object_or_404(Device, name=device_name)
        #device = Device.objects.get(name=device_name)
        context['device'] = device

        #unreachables = Unreachable.objects.filter(device__name=device_name).order_by('-last_refresh')
        unreachables = Unreachable.objects.filter(
            device=device).order_by('-last_refresh')
        context['unreachables'] = unreachables

        traps = SNMPTrap.objects.filter(device=device)
        context['traps'] = traps

        return render(request, self.template_name, context=context)


class TrapView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/trap.html'

    def get(self, request, *args, **kwargs):
        context = {}
        trap_id = self.kwargs.get('trap_id', None)
        if trap_id is None:
            raise Http404("Invalid Device Name")

        trap = get_object_or_404(SNMPTrap, id=trap_id)
        #trap = SNMPTrap.objects.get(id=trap_id)

        trap_oids = json.loads(trap.oids)
        context['trap'] = trap
        context['uptime'] = pretty_duration(trap.uptime)
        context['trap_oids'] = trap_oids

        return render(request, self.template_name, context=context)


class IncidentView(LoginRequiredMixin, View):
    ''' Create Incidents '''
    template_name = 'akips/incident.html'

    def get(self, request, *args, **kwargs):
        context = {}
        checkboxes = request.GET.getlist('event')
        logger.debug("Got list {}".format(checkboxes))

        summary_ids = []
        trap_ids = []
        for check in checkboxes:
            match = re.match(r'^(?P<type>(summary|trap))_(?P<id>\d+)$', check)
            if match and match.group('type') == 'summary':
                summary_ids.append(match.group('id'))
                logger.debug("got summary {}".format(check))
            elif match and match.group('type') == 'trap':
                trap_ids.append(match.group('id'))
                logger.debug("got trap {}".format(check))

        if summary_ids:
            context['summaries'] = Summary.objects.filter(id__in=summary_ids)
        if trap_ids:
            context['traps'] = SNMPTrap.objects.filter(id__in=trap_ids)

        initial = {
            'summary_events': ','.join(summary_ids),
            'trap_events': ','.join(trap_ids)
        }
        context['form'] = IncidentForm(initial=initial)

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        context = {}

        form = IncidentForm(request.POST)
        if form.is_valid():

            # Get the summaries
            summary_ids = []
            if form.cleaned_data.get('summary_events'):
                summary_ids = form.cleaned_data.get(
                    'summary_events').split(',')
                summaries = Summary.objects.filter(id__in=summary_ids)
                dashboard_overview = ''
                for summary in summaries:
                    dashboard_overview += "Unreachable {} {}\n".format(
                        summary.type, summary.name)

            # Get the traps
            trap_ids = []
            if form.cleaned_data.get('trap_events'):
                trap_ids = form.cleaned_data.get('trap_events').split(',')
                traps = SNMPTrap.objects.filter(id__in=trap_ids)
                dashboard_overview = ''
                for trap in traps:
                    dashboard_overview += "Trap {} {}\n".format(
                        trap.device, trap.trap_oid)

            # Create the ServiceNow Incident
            servicenow = ServiceNow()
            incident = servicenow.create_incident(
                form.cleaned_data.get('assignment_group'),
                form.cleaned_data.get('description'),
                severity=form.cleaned_data.get('criticality'),
                work_notes=dashboard_overview
            )
            if incident:
                context['create_message'] = "Incident {} was created.".format(
                    incident['number'])
                logger.debug("created {}".format(incident['number']))
                for id in summary_ids:
                    summary = Summary.objects.get(id=id)
                    summary.incident = incident['number']
                    summary.save()
                for id in trap_ids:
                    trap = SNMPTrap.objects.get(id=id)
                    trap.incident = incident['number']
                    trap.save()
                messages.success(
                    request, "ServiceNow Incident {} was created.".format(incident['number']))
                return HttpResponseRedirect(reverse('home'))
            else:
                messages.error(request, "ServiceNow Incident creation failed.")

            return render(request, self.template_name, context=context)

        else:
            # Form is invalid
            context['form'] = form
        return render(request, self.template_name, context=context)


class SetMaintenanceView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        device_name = request.GET.get(
            'device_name', None)            # Required
        maintenance_mode = request.GET.get(
            'maintenance_mode', None)  # Required
        logger.debug("Got {} and {}".format(device_name, maintenance_mode))
        if device_name is None or maintenance_mode is None:
            raise Http404("Missing device name or maintenance mode setting")

        # Update local database
        device = get_object_or_404(Device, name=device_name)
        #device = Device.objects.get(name=device_name)
        if maintenance_mode == 'True':
            device.maintenance = True
        else:
            device.maintenance = False
        device.save()

        result = {}
        # Get the current device from local database
        akips = AKIPS()
        result['text'] = akips.set_maintenance_mode(
            device_name, maintenance_mode)
        logger.debug(json.dumps(result, indent=4, sort_keys=True))

        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)


class AckView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        summary_id = self.kwargs.get('summary_id', None)
        ack = request.GET.get('ack', None)  # Required
        logger.debug("Got ack for {}".format(summary_id))
        result = {}

        summary = get_object_or_404(Summary, id=summary_id)
        #summary = Summary.objects.get(id=summary_id)
        if ack == 'True':
            summary.ack = True
        else:
            summary.ack = False
        summary.save()

        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)


class ClearTrapView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        trap_id = self.kwargs.get('trap_id', None)
        logger.debug("Got clear for trap {}".format(trap_id))
        result = {"status"}

        user = request.user

        trap = get_object_or_404(SNMPTrap, id=trap_id)
        #trap = SNMPTrap.objects.get(id=trap_id)
        trap.status = 'Closed'
        trap.comment = "Cleared by {}".format(user)
        trap.save()

        result = {"status": trap.status}
        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)


class AckTrapView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        trap_id = self.kwargs.get('trap_id', None)
        ack = request.GET.get('ack', None)  # Required
        logger.debug("Got ack {} for trap {}".format(ack, trap_id))
        result = {}

        trap = get_object_or_404(SNMPTrap, id=trap_id)
        #trap = SNMPTrap.objects.get(id=trap_id)
        if ack == 'True':
            trap.ack = True
        else:
            trap.ack = False
        trap.save()

        result = {"ack": trap.ack}
        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

class UserAlertView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        # logger.debug("Got notification from time {}".format( last_notified ))
        now = timezone.now()
        cutoff_hours = 2
        old_session_time = now - timedelta(hours=cutoff_hours)
        last_notified = request.COOKIES.get('last_notified',None)
        #last_notified_dt = timezone.make_aware(datetime.strftime(last_notified))
        logger.debug("cookie last_notified {}".format(last_notified))

        result = {
            'last_notified': last_notified,
            'messages': []
        }
        if last_notified is None:
            # user has no notification history
            messages = UserAlert.objects.filter(created_at__gt=old_session_time,enabled=True)
            if messages:
                # for message in messages:
                #     result['messages'].append( message.message )
                result['messages'].append( "There has been {} alerts in the last {} hours.".format( len(messages), cutoff_hours))
            else:
                result['messages'].append( "There are no active alerts in the last {} hours.".format(cutoff_hours))

        # elif last_notified_dt < old_session_time:
        #     # user is using an old session
        #     messages = UserAlert.objects.filter(created_at__gt=old_session_time,enabled=True)
        #     if messages:
        #         for message in messages:
        #             result['messages'].append( message.message )
        #     else:
        #         result['messages'].append( "There are no active alerts in the last {} hours.".format(cutoff_hours))

        else:
            # user has a typical active session
            messages = UserAlert.objects.filter(created_at__gt=last_notified,enabled=True)
            # result['messages'].append( "There are {} alerts.".format( len(messages) ))
            for message in messages:
                result['messages'].append( message.message )
            #result['messages'].append( "there are no new messages")

        # result = {"alerts": list( alerts )}

        # Return the results
        if self.pretty_print:
            response = JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            response = JsonResponse(result)
        response.set_cookie('last_notified', now)
        return response

class ChartDataView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True
    hours = 2
    period_minutes = 5

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        oldest = now - timedelta(hours=self.hours)

        # Define graph time periods
        max_label = self.round_dt_down(now, timedelta(minutes= self.period_minutes ))
        min_label = max_label - timedelta(hours=self.hours)
        keyList = [ timezone.localtime(dt).strftime('%H:%M') for dt in self.datetime_range( min_label, max_label, timedelta(minutes= self.period_minutes)) ]
        #logger.debug("time stamps {}".format(keyList))

        # Initalize the graph time periods
        event_data = {}
        trap_data = {}
        for i in keyList:
            event_data[i] = 0
            trap_data[i] = 0

        # Increment sums for unreachable events in each period
        unreachables = Unreachable.objects.filter(event_start__gte=min_label).order_by('event_start')
        for unreachable in unreachables:
            slot = self.round_dt_down( unreachable.event_start, timedelta(minutes= self.period_minutes) ) 
            this_label = timezone.localtime(slot).strftime('%H:%M')
            event_data[this_label] += 1

        # Increment sums for unreachable events in each period
        traps = SNMPTrap.objects.filter(tt__gte=min_label).order_by('tt')
        for trap in traps:
            slot = self.round_dt_down( trap.tt, timedelta(minutes= self.period_minutes) ) 
            this_label = timezone.localtime(slot).strftime('%H:%M')
            trap_data[this_label] += 1

        #logger.debug("periods {}".format(event_data.keys()))
        #logger.debug("event values {}".format(event_data.values()))
        #logger.debug("trap values {}".format(trap_data.values()))
        result = {
            'chart_labels': list( event_data.keys() ),
            'chart_event_data': list( event_data.values() ),
            'chart_trap_data': list( trap_data.values() ),
        }

        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

    def datetime_range(self, start, end, delta):
        ''' return a generator of times at each delta '''
        current = start
        while current <= end:
            yield current
            current += delta

    # def round_dt(self, dt, delta):
    #     ''' Round datetime to nearest 'delta' minutes '''
    #     return datetime.min + round((dt - datetime.min) / delta) * delta

    # def round_dt_up(self, dt, delta):
    #     ''' Round datetime up to nearest 'delta' minutes '''
    #     return datetime.min + math.ceil((dt - datetime.min) / delta) * delta

    def round_dt_down(self, dt, delta):
        ''' Round datetime down to nearest 'delta' minutes '''
        tzinfo, is_dst = dt.tzinfo, bool(dt.dst())
        dt = dt.replace(tzinfo=None)
        f = delta.total_seconds()
        rounded_ordinal_seconds = f * math.floor((dt - dt.min).total_seconds() / f)
        rounded_dt = dt.min + timedelta(seconds=rounded_ordinal_seconds)
        localize = getattr(tzinfo, 'localize', None)
        if localize:
            rounded_dt = localize(rounded_dt, is_dst=is_dst)
        else:
            rounded_dt = rounded_dt.replace(tzinfo=tzinfo)
        return rounded_dt

class SetUserProfileView(LoginRequiredMixin, View):
    ''' API to set user profile settings '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        voice_enabled = request.GET.get('voice_enabled', None)
        user = request.user
        logger.debug("Preference update for {} with voice_enabled {}".format(user,voice_enabled))

        user = request.user
        if voice_enabled is not None:
            if voice_enabled == 'False':
                user.profile.voice_enabled = False
            else:
                user.profile.voice_enabled = True
        user.save()

        result = {"voice_enabled": user.profile.voice_enabled }
        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

### functional views ###

@csrf_exempt
@require_POST
@non_atomic_requests
def akips_webhook(request):
    given_token = request.headers.get("Akips-Webhook-Token", "")
    if not compare_digest(given_token, settings.AKIPS_WEBHOOK_TOKEN):
        logger.debug("expected token {}".format(settings.AKIPS_WEBHOOK_TOKEN))
        logger.debug("got token      {}".format(given_token))
        return HttpResponseForbidden(
            "Incorrect token in Akips-Webhook-Token header.",
            content_type="text/plain",
        )

    payload = json.loads(request.body)
    process_webhook_payload(payload)
    return HttpResponse("Message received.", content_type="text/plain")


@atomic
def process_webhook_payload(payload):
    ''' Add it to the database '''
    try:
        device = Device.objects.get(name=payload['device'])
    except Device.DoesNotExist:
        logger.warn("Trap {} received from unknown device {} with address {}".format(
            payload['trap_oid'], payload['device'], payload['ipaddr']))
        return

    SNMPTrap.objects.create(
        tt=datetime.fromtimestamp(
            int(payload['tt']), tz=timezone.get_current_timezone()),
        device=device,
        ipaddr=payload['ipaddr'],
        trap_oid=payload['trap_oid'],
        uptime=payload['uptime'],
        oids=json.dumps(payload['oids'])
    )

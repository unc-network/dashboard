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
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sessions.models import Session
from django.template.loader import render_to_string
from django.contrib import messages
from django.utils import timezone

#from django.db.models import Count
#from django.db.models.functions import TruncHour

#from django.utils.decorators import method_decorator
from django.db.transaction import atomic, non_atomic_requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import HibernateRequest, Summary, Unreachable, Device, Trap, Status
from .forms import IncidentForm, HibernateForm
from .task import example_task
from .utils import AKIPS, ServiceNow, pretty_duration

# Get a instance of logger
logger = logging.getLogger(__name__)

# Create your views here.

# def handler403(request, exception):
#     response = render(request, "akips/403.html")
#     response.status_code = 403
#     return response

# def handler404(request, exception):
#     response = render(request, "akips/404.html")
#     response.status_code = 404
#     return response

# def handler500(request):
#     response = render(request, "akips/500.html")
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
        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        post_template = 'akips/incident.html'
        context = {}
        return render(request, post_template, context=context)


class Devices(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/devices.html'

    def get(self, request, *args, **kwargs):
        context = {}

        # list = ['SWITCH','AP','UPS','ROUTER']
        # devices = Device.objects.exclude(type__in=list)
        devices = Device.objects.all()
        context['devices'] = devices

        return render(request, self.template_name, context=context)

class Users(LoginRequiredMixin, View):
    ''' Show users logged in recently '''
    template_name = 'akips/recent_users.html'

    def get(self, request, *args, **kwargs):
        context = {}
        date_from = timezone.now() - timedelta(days=7)
        context['recent_users'] = User.objects.filter(last_login__gte=date_from).order_by('-last_login')

        session_list = Session.objects.filter(expire_date__gte=timezone.now()).order_by('-expire_date')
        sessions = []
        for s in session_list:
            s_decoded = s.get_decoded()
            session_start = s.expire_date - timedelta(seconds=settings.SESSION_COOKIE_AGE)
            logger.debug("session {}".format( s.get_decoded() ))
            logger.debug("session expire {}".format( s.expire_date ))
            logger.debug("session start {}".format( session_start ))
            sessions.append({ 
                'user': User.objects.get(id=s_decoded['_auth_user_id']),
                'expire': s.expire_date,
                'start': session_start,
                })
        context['session_list'] = sessions


        return render(request, self.template_name, context=context)

class CritCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_crit.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['summaries'] = Summary.objects.filter(type='Critical', status='Open').order_by('name')
        return render(request, self.template_name, context=context)


class TierCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_tier.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['summaries'] = Summary.objects.filter(type='Distribution', status='Open').order_by('name')
        return render(request, self.template_name, context=context)


class BuildingCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_bldg.html'

    def get(self, request, *args, **kwargs):
        context = {}
        #context['summaries'] = Summary.objects.filter(type='Building',status='Open').order_by('name')
        types = ['Distribution', 'Building']
        context['summaries'] = Summary.objects.filter(type__in=types, status='Open').order_by('tier', '-type', 'name')
        return render(request, self.template_name, context=context)

class SpecialityCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_special.html'

    def get(self, request, *args, **kwargs):
        context = {}
        types = ['Speciality']
        context['summaries'] = Summary.objects.filter(type__in=types, status='Open').order_by('name')
        return render(request, self.template_name, context=context)

class TrapCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_trap.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['traps'] = Trap.objects.filter(
            status='Open').order_by('-tt')[:50]
        return render(request, self.template_name, context=context)


class UnreachableView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/unreachable.html'

    def get(self, request, *args, **kwargs):
        context = {}

        #unreachables = Unreachable.objects.filter(status='Open', device__maintenance=False).order_by('-event_start')
        unreachables = Unreachable.objects.filter(status='Open').order_by('-event_start')
        context['unreachables'] = unreachables

        return render(request, self.template_name, context=context)

class MaintenanceView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/devices_maintenance.html'

    def get(self, request, *args, **kwargs):
        context = {}
        list = []

        devices = Device.objects.filter(maintenance=True)
        context['devices'] = devices

        return render(request, self.template_name, context=context)

class HibernateRequestsView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/hibernate_requests.html'

    def get(self, request, *args, **kwargs):
        context = {}
        list = []

        hibernate_list = HibernateRequest.objects.filter(status='Open')
        for hibernate in hibernate_list:
            status = Status.objects.filter(device=hibernate.device,attribute='PING.icmpState')
            logger.debug("status {}".format(status))
            entry = {
                'hibernate': hibernate,
                'status': status
            }
            list.append(entry)
        context['list'] = list

        return render(request, self.template_name, context=context)

class SummaryView(LoginRequiredMixin, View):
    ''' Generic summary view '''
    template_name = 'akips/summary.html'

    def get(self, request, *args, **kwargs):
        context = {}
        summary_id = self.kwargs.get('id', None)

        summary = get_object_or_404(Summary, id=summary_id)

        context['u_open'] = summary.unreachables.filter(status='Open').order_by('-event_start')
        context['u_closed'] = summary.unreachables.filter(status='Closed').order_by('-event_start')
        context['batteries'] = summary.batteries.all()
        context['summary'] = summary

        context['avg_low'] = summary.moving_average * 0.95
        context['avg_high'] = summary.moving_average * 1.05

        return render(request, self.template_name, context=context)


class RecentSummaryView(LoginRequiredMixin, View):
    ''' Generic recent summary view '''
    template_name = 'akips/recent_events.html'

    def get(self, request, *args, **kwargs):
        context = {}

        date_from = timezone.now() - timezone.timedelta(days=1)
        # types = ['Critical', 'Building']
        summaries = Summary.objects.filter( last_event__gte=date_from, status='Closed' ).order_by('-first_event')
        context['summaries'] = summaries

        return render(request, self.template_name, context=context)

class RecentTrapsView(LoginRequiredMixin, View):
    ''' Generic recent traps view '''
    template_name = 'akips/recent_traps.html'

    def get(self, request, *args, **kwargs):
        context = {}
        date_from = timezone.now() - timezone.timedelta(days=1)
        traps = Trap.objects.filter( tt__gte=date_from, status='Closed' ).order_by('-tt')
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
        unreachables = Unreachable.objects.filter( device=device).order_by('-last_refresh')
        context['unreachables'] = unreachables

        traps = Trap.objects.filter(device=device).order_by('-tt')
        context['traps'] = traps

        status_list = Status.objects.filter(device=device)
        logger.debug("status_list {}".format(status_list))
        context['status_list'] = status_list

        hibernate_list = HibernateRequest.objects.filter(device=device)
        context['hibernate_list'] = hibernate_list

        return render(request, self.template_name, context=context)


class TrapView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/trap.html'

    def get(self, request, *args, **kwargs):
        context = {}
        trap_id = self.kwargs.get('trap_id', None)
        if trap_id is None:
            raise Http404("Invalid Device Name")

        trap = get_object_or_404(Trap, id=trap_id)
        #trap = Trap.objects.get(id=trap_id)

        trap_oids = json.loads(trap.oids)
        context['trap'] = trap
        context['uptime'] = pretty_duration(trap.uptime)
        context['trap_oids'] = trap_oids

        return render(request, self.template_name, context=context)


class HibernateView(LoginRequiredMixin, View):
    ''' Hibernate devices '''
    template_name = 'akips/hibernate.html'

    def get(self, request, *args, **kwargs):
        context = {}
        checkboxes = request.GET.getlist('device')
        logger.debug("Got list {}".format(checkboxes))

        device_ids = checkboxes
        context['devices'] = Device.objects.filter(id__in=device_ids)

        initial = {
            'device_ids': ','.join(device_ids),
        }
        context['form'] = HibernateForm(initial=initial)

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        context = {}
        form = HibernateForm(request.POST)

        if form.is_valid():
            device_ids = form.cleaned_data.get('device_ids').split(',')
            for id in device_ids:
                logger.debug("Hibernating device id {}".format(id))
                device = Device.objects.get(id=id)

                hibernate_request, created = HibernateRequest.objects.update_or_create(
                    device=device,
                    defaults={
                        "type": form.cleaned_data.get('type'),
                        "scheduled": form.cleaned_data.get('clear_time'),
                        "comment": form.cleaned_data.get('comment'),
                        "status": 'Open',
                        "created_by": request.user.username,
                    }
                )
                if created:
                    messages.success(request, "Hibernation request created for device {}".format( device.name ))
                elif hibernate_request:
                    messages.success(request, "Hibernation request updated for device {}".format( device.name ))

                # Update local device record
                device.hibernate = True
                device.save()

                logger.debug("Device {} hibernation request submitted".format(device.name))

            return HttpResponseRedirect(reverse('home'))

        else:
            # Form is invalid
            device_ids = request.POST.get('device_ids').split(',')
            context['devices'] = Device.objects.filter(id__in=device_ids)

            context['form'] = form

        return render(request, self.template_name, context=context)

class CreateIncidentView(LoginRequiredMixin, View):
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
            context['traps'] = Trap.objects.filter(id__in=trap_ids)

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
            ctx = {
                'server_name': "https://ocnes.cloudapps.unc.edu"
            }

            # Get the summaries
            summary_ids = []
            if form.cleaned_data.get('summary_events'):
                summary_ids = form.cleaned_data.get('summary_events').split(',')
                summaries = Summary.objects.filter(id__in=summary_ids)
                ctx['summaries'] = summaries

            # Get the traps
            trap_ids = []
            if form.cleaned_data.get('trap_events'):
                trap_ids = form.cleaned_data.get('trap_events').split(',')
                traps = Trap.objects.filter(id__in=trap_ids)
                ctx['traps'] = traps

            # Create the ServiceNow Incident
            servicenow = ServiceNow()
            incident = servicenow.create_incident(
                form.cleaned_data.get('assignment_group'),
                form.cleaned_data.get('description'),
                severity=form.cleaned_data.get('criticality'),
                work_notes=render_to_string('akips/incident_worknote.txt',ctx),
                callerid=request.user.username
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
                    trap = Trap.objects.get(id=id)
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
        result['text'] = akips.set_maintenance_mode(device_name, maintenance_mode)
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
            summary.ack_by = request.user.username
            summary.ack_at = timezone.now()
        else:
            summary.ack = False
            summary.ack_by = request.user.username
            summary.ack_at = timezone.now()
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

        trap = get_object_or_404(Trap, id=trap_id)
        #trap = Trap.objects.get(id=trap_id)
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

        trap = get_object_or_404(Trap, id=trap_id)
        #trap = Trap.objects.get(id=trap_id)
        if ack == 'True':
            trap.ack = True
            trap.ack_by = request.user.username
            trap.ack_at = timezone.now()
        else:
            trap.ack = False
            trap.ack_by = request.user.username
            trap.ack_at = timezone.now()
        trap.save()

        result = {"ack": trap.ack}
        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

class StatusExportView(View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        result = {}
        status = Status.objects.filter(attribute='PING.icmpState').values('device__name','device__sysName','device__ip4addr','attribute','value','last_change')
        
        result = {"status": list(status)}
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
        last_notified_cookie = request.COOKIES.get('last_notified',None)
        logger.debug("cookie last_notified cookie value {}".format(last_notified_cookie))

        # Define the times we care about
        now = timezone.now()
        cutoff_hours = 2
        old_session_time = now - timedelta(hours=cutoff_hours)

        result = {
            'last_notified': now,
            'messages': []
        }

        if last_notified_cookie is None or datetime.fromisoformat(last_notified_cookie) < old_session_time:
            # user has no notification history or it is an old session
            times = []
            tmp_messages = []
            #result['messages'].append("Greetings, {}.".format( request.user.first_name))

            # unreachables = Unreachable.objects.filter(event_start__gt=old_session_time).order_by('event_start')
            # if unreachables:
            #     result['messages'].append("There have been {} new unreachable devices in the last {} hours.".format( len(unreachables), cutoff_hours))
            #     times.append( unreachables.last().event_start )

            criticals = Summary.objects.filter(type='Critical',first_event__gt=old_session_time).order_by('first_event')
            if criticals:
                critical_count = len(criticals)
                if critical_count == 1:
                    # result['messages'].append("{} new critical alert,".format( len(criticals) ))
                    tmp_messages.append("{} new critical alert".format( len(criticals) ))
                else:
                    # result['messages'].append("{} new critical alerts,".format( len(criticals) ))
                    tmp_messages.append("{} new critical alerts".format( len(criticals) ))
                times.append( criticals.last().first_event )

            buildings = Summary.objects.filter(type='Building',first_event__gt=old_session_time).order_by('first_event')
            if buildings:
                building_count = len(buildings)
                if building_count == 1:
                    # result['messages'].append("{} new building alert,".format( len(buildings) ))
                    tmp_messages.append("{} new building alert".format( len(buildings) ))
                else:
                    # result['messages'].append("{} new building alerts,".format( len(buildings) ))
                    tmp_messages.append("{} new building alerts".format( len(buildings) ))
                times.append( buildings.last().first_event )

            traps = Trap.objects.filter(tt__gt=old_session_time).order_by('tt')
            if traps:
                trap_count = len(traps)
                if trap_count == 1:
                    # result['messages'].append("{} new trap".format( len(traps) ))
                    tmp_messages.append("{} new trap".format( len(traps) ))
                else:
                    # result['messages'].append("{} new traps".format( len(traps) ))
                    tmp_messages.append("{} new traps".format( len(traps) ))
                times.append( traps.last().tt )

            if times:
                result['messages'].insert(0,"In the last {} hours there have been ".format(cutoff_hours))
                # make a nicer sentence
                if len(tmp_messages) == 1:
                    result['messages'].append(tmp_messages)
                elif len(tmp_messages) == 2:
                    result['messages'].append(' and '.join(tmp_messages))
                else:
                    result['messages'].append('{}, and {}'.format(', '.join(tmp_messages[:-1]), tmp_messages[-1]))
                result['level'] = 'info'
                result['last_notified'] = max( times )
            else:
                result['messages'].append("There have been no new alerts in the last {} hours.".format( cutoff_hours))
                result['level'] = 'success'
                result['last_notified'] = now

        else:
            # user has a typical active session
            times = []
            tmp_messages = []
            last_notified = datetime.fromisoformat(last_notified_cookie)
            #result['messages'].append("User has an active session")

            # unreachables = Unreachable.objects.filter(event_start__gt=last_notified,status='Open').order_by('event_start')
            # if unreachables:
            #     result['messages'].append("There are {} new unreachable devices.".format( len(unreachables) ))
            #     times.append( unreachables.last().event_start )

            criticals = Summary.objects.filter(type='Critical',first_event__gt=last_notified,status='Open').order_by('first_event')
            if criticals:
                critical_count = len(criticals)
                if critical_count == 1:
                    # result['messages'].append("{} new critical device alert for {},".format( critical_count, criticals.first().name ))
                    tmp_messages.append("{} critical device alert for {}".format( critical_count, criticals.first().name ))
                else:
                    # result['messages'].append("{} new critical device alerts,".format( critical_count ))
                    tmp_messages.append("{} critical device alerts".format( critical_count ))
                times.append( criticals.last().first_event )

            buildings = Summary.objects.filter(type='Building',first_event__gt=last_notified,status='Open').order_by('first_event')
            if buildings:
                building_count = len(buildings)
                if building_count == 1:
                    # result['messages'].append("{} new alert for {},".format( building_count, buildings.first().name ))
                    tmp_messages.append("{} building alert for {}".format( building_count, buildings.first().name ))
                else:
                    # result['messages'].append("{} new building alerts,".format( len(buildings) ))
                    tmp_messages.append("{} building alerts".format( len(buildings) ))
                times.append( buildings.last().first_event )

            traps = Trap.objects.filter(tt__gt=last_notified,status='Open').order_by('tt')
            if traps:
                trap_count = len(traps)
                if trap_count == 1:
                    # result['messages'].append("{} new trap for {},".format( trap_count, traps.first().ipaddr))
                    # result['messages'].append("{} new trap,".format( trap_count ))
                    tmp_messages.append("{} trap for {}".format( trap_count, traps.first().device.sysName ))
                else:
                    # result['messages'].append("{} new traps,".format( trap_count ))
                    tmp_messages.append("{} traps".format( trap_count ))
                times.append( traps.last().tt )

            if times:
                result['messages'].insert(0,"New:")
                # make a nicer sentence
                if len(tmp_messages) == 1:
                    result['messages'].append(tmp_messages)
                elif len(tmp_messages) == 2:
                    result['messages'].append(' and '.join(tmp_messages))
                else:
                    result['messages'].append('{}, and {}'.format(', '.join(tmp_messages[:-1]), tmp_messages[-1]))
                result['level'] = 'danger'
                result['last_notified'] = max( times )
            else:
                # result['messages'].append( "There are no new alerts.")
                result['level'] = 'success'
                result['last_notified'] = last_notified

        # Return the results
        if self.pretty_print:
            response = JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            response = JsonResponse(result)
        response.set_cookie('last_notified', result['last_notified'])
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
        # keyList = [ timezone.localtime(dt).strftime('%-I:%M') for dt in self.datetime_range( min_label, max_label, timedelta(minutes= self.period_minutes)) ]
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
            # this_label = timezone.localtime(slot).strftime('%-I:%M')
            this_label = timezone.localtime(slot).strftime('%H:%M')
            event_data[this_label] += 1

        # Increment sums for unreachable events in each period
        traps = Trap.objects.filter(tt__gte=min_label).order_by('tt')
        for trap in traps:
            slot = self.round_dt_down( trap.tt, timedelta(minutes= self.period_minutes) ) 
            # this_label = timezone.localtime(slot).strftime('%-I:%M')
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
    logger.info("payload: {}".format( str(payload) ))
    process_webhook_payload(payload)
    return HttpResponse("Message received.", content_type="text/plain")


@atomic
def process_webhook_payload(payload):
    ''' Add it to the database '''
    if 'device' not in payload:
        logger.warn("Trap alert is missing device field")
        return
    elif 'type' not in payload:
        logger.warn("Trap alert is missing type field")
        return

    try:
        device = Device.objects.get(name=payload['device'])
    except Device.DoesNotExist:
        logger.warn("Trap {} received from unknown device {} with address {}".format(
            payload['trap_oid'], payload['device'], payload['ipaddr']))
        return

    if payload['type'] == 'Trap':
        # Check for Open duplicates
        duplicates = Trap.objects.filter( 
            device=device, 
            trap_oid=payload['trap_oid'],
            oids=json.dumps(payload['oids']),
            #ack=True,
            status='Open')

        if duplicates:
            logger.info("Trap has repeated")
            for duplicate in duplicates:
                duplicate.dup_count += 1
                duplicate.dup_last = datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone())
                duplicate.save()
            # Trap.objects.create(
            #     tt=datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone()),
            #     device=device,
            #     ipaddr=payload['ipaddr'],
            #     trap_oid=payload['trap_oid'],
            #     uptime=payload['uptime'],
            #     oids=json.dumps(payload['oids']),
            #     comment="Auto-cleared as a duplicate",
            #     status='Closed',
            # )
        else:
            Trap.objects.create(
                tt=datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone()),
                device=device,
                ipaddr=payload['ipaddr'],
                trap_oid=payload['trap_oid'],
                uptime=payload['uptime'],
                oids=json.dumps(payload['oids'])
            )
    elif payload['type'] == 'Status':
        Status.objects.update_or_create(
            device=device,
            child=payload['child'],
            attribute=payload['attr'],
            defaults={
                'value': payload['state'],
                'last_change': datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone()),
            }
        )
    else:
        logger.warn("Unknown type value {}".format( str(payload) ))

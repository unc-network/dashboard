import logging
import json
import re
import hashlib
from datetime import datetime, timedelta
from secrets import compare_digest
import math

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render, get_object_or_404
from django.views.generic import View
from django.http import Http404, JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse
#from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sessions.models import Session
from django.template.loader import render_to_string
from django.contrib import messages
from django.utils import timezone

from django.db.models import Count, Q
from django.db.models.functions import TruncHour

#from django.utils.decorators import method_decorator
from django.db.transaction import atomic, non_atomic_requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django_celery_results.models import TaskResult

from .models import HibernateRequest, Summary, Unreachable, Device, Trap, Status, ServiceNowIncident
from .forms import IncidentForm, HibernateForm, PreferencesForm
from .task import refresh_ping_status, refresh_snmp_status, refresh_ups_status, refresh_akips_devices
from .utils import AKIPS, pretty_duration
from akips.servicenow import ServiceNow
from akips.tdx import TDX

# Get a instance of logger
logger = logging.getLogger(__name__)

# Create your views here.

# def login(request, *args, **kwargs):
#     if request.method == 'POST':
#         if not request.POST.get('remember_me', None):
#             request.session.set_expiry(0)
#     return auth_views.login(request, *args, **kwargs)

# Testing a remember me
# class UpdatedLoginView(LoginView):
#     form_class = LoginForm
#     def form_valid(self, form):
#         remember_me = form.cleaned_data['remember_me']  # get remember me data from cleaned_data of form
#         if not remember_me:
#             self.request.session.set_expiry(0)  # if remember me is 
#             self.request.session.modified = True
#         return super(UpdatedLoginView, self).form_valid(form)

class Home(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}

        # akips = AKIPS()
        # #device_name = akips.get_device_by_ip('152.19.187.21')
        # device_name = akips.get_device_by_ip('172.29.149.203')
        # logger.debug("Found device name {}".format(device_name))

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        post_template = 'akips/incident.html'
        context = {}
        return render(request, post_template, context=context)

class About(LoginRequiredMixin, View):
    ''' basic about page '''
    template_name = 'akips/about.html'

    def get(self, request, *args, **kwargs):
        context = {}
        now = timezone.now()
        since_24h = now - timedelta(hours=24)
        since_7d = now - timedelta(days=7)

        try:
            last_inventory_sync = TaskResult.objects.filter(task_name='akips.task.refresh_inventory').latest('date_done')
        except TaskResult.DoesNotExist:
            last_inventory_sync = None
        context['last_inventory_sync'] = last_inventory_sync

        try:
            last_device_sync = TaskResult.objects.filter(task_name='akips.task.refresh_akips_devices').latest('date_done')
        except TaskResult.DoesNotExist:
            last_device_sync = None
        context['last_akips_sync'] = last_device_sync

        def get_task_duration(task):
            if not task or not task.date_created or not task.date_done:
                return 'In progress'
            return pretty_duration((task.date_done - task.date_created).total_seconds())

        context['last_akips_sync_duration'] = get_task_duration(last_device_sync)
        context['last_inventory_sync_duration'] = get_task_duration(last_inventory_sync)

        data_points = [
            last_device_sync.date_done if last_device_sync and last_device_sync.date_done else None,
            last_inventory_sync.date_done if last_inventory_sync and last_inventory_sync.date_done else None,
        ]
        latest_data_point = max([d for d in data_points if d is not None], default=None)
        if latest_data_point:
            freshness_seconds = max((now - latest_data_point).total_seconds(), 0)
            context['data_freshness'] = pretty_duration(freshness_seconds)
            if freshness_seconds <= 1800:
                context['freshness_level'] = 'success'
                context['freshness_label'] = 'Fresh'
            elif freshness_seconds <= 7200:
                context['freshness_level'] = 'warning'
                context['freshness_label'] = 'Aging'
            else:
                context['freshness_level'] = 'danger'
                context['freshness_label'] = 'Stale'
            context['last_data_update'] = latest_data_point
        else:
            context['data_freshness'] = 'Unknown'
            context['freshness_level'] = 'secondary'
            context['freshness_label'] = 'Unknown'
            context['last_data_update'] = None

        context['device_total'] = Device.objects.count()
        context['device_active'] = Device.objects.filter(maintenance=False, hibernate=False).count()
        context['open_unreachables'] = Unreachable.objects.filter(status='Open').count()
        context['open_traps'] = Trap.objects.filter(status='Open').count()
        context['open_summaries'] = Summary.objects.filter(status='Open').count()
        context['logged_in_users_7d'] = User.objects.filter(last_login__gte=since_7d).count()

        unreachable_24h = Unreachable.objects.filter(event_start__gte=since_24h).count()
        trap_24h = Trap.objects.filter(created_at__gte=since_24h).count()
        unreachable_7d = Unreachable.objects.filter(event_start__gte=since_7d).count()
        trap_7d = Trap.objects.filter(created_at__gte=since_7d).count()

        context['unreachable_24h'] = unreachable_24h
        context['trap_24h'] = trap_24h
        context['events_processed_24h'] = unreachable_24h + trap_24h
        context['unreachable_7d'] = unreachable_7d
        context['trap_7d'] = trap_7d
        context['events_processed_7d'] = unreachable_7d + trap_7d

        chart_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        unreachable_hourly = {
            row['hour']: row['total']
            for row in (
                Unreachable.objects.filter(event_start__gte=chart_start)
                .annotate(hour=TruncHour('event_start'))
                .values('hour')
                .annotate(total=Count('id'))
                .order_by('hour')
            )
        }
        trap_hourly = {
            row['hour']: row['total']
            for row in (
                Trap.objects.filter(created_at__gte=chart_start)
                .annotate(hour=TruncHour('created_at'))
                .values('hour')
                .annotate(total=Count('id'))
                .order_by('hour')
            )
        }
        chart_hours = [chart_start + timedelta(hours=offset) for offset in range(24)]
        context['events_24h_labels'] = [hour.strftime('%H:%M') for hour in chart_hours]
        context['events_24h_totals'] = [unreachable_hourly.get(hour, 0) + trap_hourly.get(hour, 0) for hour in chart_hours]

        context['top_buildings'] = (
            Unreachable.objects.filter(status='Open')
            .exclude(device__building_name='')
            .values('device__building_name')
            .annotate(total=Count('id'))
            .order_by('-total')[:5]
        )
        context['top_tiers'] = (
            Unreachable.objects.filter(status='Open')
            .exclude(device__tier='')
            .values('device__tier')
            .annotate(total=Count('id'))
            .order_by('-total')[:5]
        )

        return render(request, self.template_name, context=context)

class Devices(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/devices.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['search'] = request.GET.get('search', '').strip()

        # last_device_sync = TaskResult.objects.filter(task_name='akips.task.refresh_akips_devices',status='SUCCESS').latest('date_done')
        # context['last_device_sync'] = last_device_sync

        return render(request, self.template_name, context=context)


class DevicesDataAPI(LoginRequiredMixin, View):
    ''' API view for server-side DataTables device listing '''

    columns = ['name', 'ip4addr', 'sysName', 'group', 'type']
    order_columns = ['ip4addr', 'ip4addr', 'sysName', 'group', 'type']
    total_count_cache_key = 'devices_data_total_count'
    total_count_cache_ttl = 60

    def _parse_int(self, value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get(self, request, *args, **kwargs):
        draw = self._parse_int(request.GET.get('draw'), 1)
        start = max(self._parse_int(request.GET.get('start'), 0), 0)
        length = self._parse_int(request.GET.get('length'), 25)
        if length <= 0:
            length = 25
        length = min(length, 500)

        search_value = request.GET.get('search[value]', '').strip()
        order_index = self._parse_int(request.GET.get('order[0][column]'), 0)
        order_dir = request.GET.get('order[0][dir]', 'asc')
        if order_index < 0 or order_index >= len(self.order_columns):
            order_index = 0

        order_field = self.order_columns[order_index]
        order_by = f'-{order_field}' if order_dir == 'desc' else order_field

        records_total = cache.get(self.total_count_cache_key)
        if records_total is None:
            records_total = Device.objects.count()
            cache.set(self.total_count_cache_key, records_total, self.total_count_cache_ttl)

        base_qs = Device.objects.all()

        if search_value:
            base_qs = base_qs.filter(
                Q(name__icontains=search_value)
                | Q(ip4addr__icontains=search_value)
                | Q(sysName__icontains=search_value)
                | Q(group__icontains=search_value)
                | Q(type__icontains=search_value)
            )

        records_filtered = records_total if not search_value else base_qs.count()

        rows = base_qs.order_by(order_by).values(*self.columns)[start:start + length]
        data = []
        for row in rows:
            row_data = dict(row)
            row_data['device_url'] = reverse('device', args=[row['name']])
            data.append(row_data)

        return JsonResponse({
            'draw': draw,
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'data': data,
        })

class UPSProblems(LoginRequiredMixin, View):
    ''' List UPS current in a problem state '''
    template_name = 'akips/ups_problems.html'

    def get(self, request, *args, **kwargs):
        context = {}

        bad_battery_tests = Status.objects.filter(attribute='LIEBERT-GP-POWER-MIB.lgpPwrBatteryTestResult',value='failed')
        context['bad_battery_tests'] = bad_battery_tests

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

class UserPreferences(LoginRequiredMixin, View):
    ''' Edit user preferences '''
    template_name = 'akips/user_preferences.html'

    def get(self, request, *args, **kwargs):
        context = {}
        initial = {
            'alert_enabled': self.request.user.profile.alert_enabled,
            'voice_enabled': self.request.user.profile.voice_enabled,
        }
        context['form'] = PreferencesForm(initial=initial)

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        context = {}
        form = PreferencesForm(request.POST)
        context['form'] = form

        if form.is_valid():
            user = request.user
            user.profile.alert_enabled = form.cleaned_data.get('alert_enabled')
            user.profile.voice_enabled = form.cleaned_data.get('voice_enabled')
            user.save()
            messages.success(request, "{}'s preferences were saved.".format(user.username))
        else:
            pass

        return render(request, self.template_name, context=context)


CARD_REFRESH_CONFIG = {
    'crit_card': {
        'template_name': 'akips/card_refresh_crit.html',
        'cache_key': 'crit_card_data',
        'data_cache_key': 'crit_card_json_data',
        'queryset': lambda: Summary.objects.filter(type='Critical', status='Open').select_related('sn_incident').prefetch_related('unreachables__device').order_by('name'),
        'context_key': 'summaries',
    },
    'bldg_card': {
        'template_name': 'akips/card_refresh_bldg.html',
        'cache_key': 'bldg_card_data',
        'data_cache_key': 'bldg_card_json_data',
        'queryset': lambda: Summary.objects.filter(type__in=['Distribution', 'Building'], status='Open').select_related('sn_incident').order_by('tier', '-type', 'name'),
        'context_key': 'summaries',
    },
    'spec_card': {
        'template_name': 'akips/card_refresh_special.html',
        'cache_key': 'spec_card_data',
        'data_cache_key': 'spec_card_json_data',
        'queryset': lambda: Summary.objects.filter(type__in=['Specialty'], status='Open').select_related('sn_incident').order_by('name'),
        'context_key': 'summaries',
    },
    'trap_card': {
        'template_name': 'akips/card_refresh_trap.html',
        'cache_key': 'trap_card_data',
        'data_cache_key': 'trap_card_json_data',
        'queryset': lambda: Trap.objects.filter(status='Open').select_related('device', 'sn_incident').order_by('-dup_last', '-tt'),
        'context_key': 'traps',
    },
}


def _fmt_dt(value):
    if not value:
        return ''
    return timezone.localtime(value).strftime('%m-%d %H:%M:%S')


def _summary_incident(summary):
    if summary.tdx_incident:
        return {
            'id': str(summary.tdx_incident),
            'url': f"https://tdx.unc.edu/TDNext/Apps/34/Tickets/TicketDet.aspx?TicketID={summary.tdx_incident}",
        }
    if summary.sn_incident:
        sn_number = str(summary.sn_incident)
        return {
            'id': sn_number,
            'url': f"https://{summary.sn_incident.instance}.service-now.com/nav_to.do?uri=task.do?sysparm_query=number={sn_number}",
        }
    return None


def _serialize_summary_base(summary):
    return {
        'id': summary.id,
        'summary_url': reverse('summary', args=[summary.id]),
        'ack_url': reverse('ack', args=[summary.id]),
        'comment_url': reverse('set_comment', args=[summary.id]),
        'ack': summary.ack,
        'ack_by': summary.ack_by or '',
        'ack_at': _fmt_dt(summary.ack_at),
        'comment': summary.comment or '',
        'last_event': _fmt_dt(summary.last_event),
        'trend': summary.trend or '',
        'incident': _summary_incident(summary),
    }


def _serialize_crit_data(summaries):
    rows = []
    for summary in summaries:
        row = _serialize_summary_base(summary)
        first_unreachable = summary.unreachables.all().first()
        device = first_unreachable.device if first_unreachable else None
        row.update({
            'device_name': device.sysName if device else summary.name,
            'device_ip4addr': device.ip4addr if device else '',
            'device_descr': device.sysDescr if device else '',
        })
        rows.append(row)
    return {
        'rows': rows,
        'has_rows': len(rows) > 0,
    }


def _serialize_bldg_data(summaries):
    rows = []
    for summary in summaries:
        row = _serialize_summary_base(summary)
        row.update({
            'type': summary.type,
            'name': summary.name,
            'switch_count': summary.switch_count,
            'ap_count': summary.ap_count,
            'ups_count': summary.ups_count,
            'ups_battery': summary.ups_battery,
            'percent_down': round((summary.percent_down or 0) * 100),
        })
        rows.append(row)
    return {
        'rows': rows,
        'has_rows': len(rows) > 0,
        'empty_message': 'Tier 1 and Building events are currently clear',
    }


def _serialize_spec_data(summaries):
    rows = []
    for summary in summaries:
        row = _serialize_summary_base(summary)
        row.update({
            'name': summary.name,
            'total_count': summary.total_count,
            'percent_down': round((summary.percent_down or 0) * 100),
        })
        rows.append(row)
    return {
        'rows': rows,
        'has_rows': len(rows) > 0,
    }


def _trap_incident(trap):
    if trap.tdx_incident:
        return {
            'id': str(trap.tdx_incident),
            'url': f"https://tdx.unc.edu/TDNext/Apps/34/Tickets/TicketDet.aspx?TicketID={trap.tdx_incident}",
        }
    if trap.sn_incident:
        sn_number = str(trap.sn_incident)
        return {
            'id': sn_number,
            'url': f"https://{trap.sn_incident.instance}.service-now.com/nav_to.do?uri=task.do?sysparm_query=number={sn_number}",
        }
    return None


def _serialize_trap_data(traps):
    rows = []
    for trap in traps:
        rows.append({
            'id': trap.id,
            'ack': trap.ack,
            'ack_by': trap.ack_by or '',
            'ack_at': _fmt_dt(trap.ack_at),
            'ack_url': reverse('ack_trap', args=[trap.id]),
            'device_name': trap.device.sysName,
            'device_url': reverse('device', args=[trap.device.name]),
            'trap_oid': trap.trap_oid,
            'trap_url': reverse('trap', args=[trap.id]),
            'dup_count': trap.dup_count,
            'dup_last_iso': trap.dup_last.isoformat() if trap.dup_last else '',
            'last_event': _fmt_dt(trap.dup_last or trap.tt),
            'incident': _trap_incident(trap),
            'clear_url': reverse('clear_trap', args=[trap.id]),
        })
    return {
        'rows': rows,
        'has_rows': len(rows) > 0,
        'total_open': len(traps),
    }


CARD_SERIALIZERS = {
    'crit_card': _serialize_crit_data,
    'bldg_card': _serialize_bldg_data,
    'spec_card': _serialize_spec_data,
    'trap_card': _serialize_trap_data,
}


def render_card_fragment(card_id, cache_timeout=60):
    """Render one dashboard card fragment with cache reuse."""
    config = CARD_REFRESH_CONFIG[card_id]
    cached_html = cache.get(config['cache_key'])
    if cached_html is not None:
        logger.debug(f"Cache HIT for {config['cache_key']}")
        return cached_html

    logger.debug(f"Cache MISS for {config['cache_key']}")
    context = {
        config['context_key']: config['queryset'](),
    }
    html = render_to_string(config['template_name'], context)
    cache.set(config['cache_key'], html, cache_timeout)
    return html


def get_card_data(card_id, cache_timeout=15):
    """Return one dashboard card data payload with cache reuse."""
    config = CARD_REFRESH_CONFIG[card_id]
    cached_data = cache.get(config['data_cache_key'])
    if cached_data is not None:
        logger.debug(f"Cache HIT for {config['data_cache_key']}")
        return cached_data

    logger.debug(f"Cache MISS for {config['data_cache_key']}")
    data = CARD_SERIALIZERS[card_id](list(config['queryset']()))
    cache.set(config['data_cache_key'], data, cache_timeout)
    return data


class DashboardCardsView(LoginRequiredMixin, View):
    ''' Return all dashboard cards as JSON in one request '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        result = {'cards': {}, 'signatures': {}}
        for card_id in CARD_REFRESH_CONFIG:
            card_data = get_card_data(card_id)
            result['cards'][card_id] = card_data
            card_json = json.dumps(card_data, sort_keys=True, default=str)
            result['signatures'][card_id] = hashlib.md5(card_json.encode('utf-8')).hexdigest()

        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        return JsonResponse(result)

class CritCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_crit.html'
    cache_key = 'crit_card_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        html = render_card_fragment('crit_card', cache_timeout=self.cache_timeout)
        return HttpResponse(html, content_type='text/html')


class TierCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_tier.html'
    cache_key = 'tier_card_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        # Try to get from cache first
        cached_html = cache.get(self.cache_key)
        if cached_html is not None:
            logger.debug(f"Cache HIT for {self.cache_key}")
            return HttpResponse(cached_html, content_type='text/html')

        logger.debug(f"Cache MISS for {self.cache_key}")
        context = {}
        context['summaries'] = Summary.objects.filter(type='Distribution', status='Open').order_by('name')
        html = render_to_string(self.template_name, context)
        
        # Store in cache
        cache.set(self.cache_key, html, self.cache_timeout)
        return HttpResponse(html, content_type='text/html')


class BuildingCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_bldg.html'
    cache_key = 'bldg_card_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        html = render_card_fragment('bldg_card', cache_timeout=self.cache_timeout)
        return HttpResponse(html, content_type='text/html')

class SpecialtyCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_special.html'
    cache_key = 'spec_card_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        html = render_card_fragment('spec_card', cache_timeout=self.cache_timeout)
        return HttpResponse(html, content_type='text/html')

class TrapCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_trap.html'
    cache_key = 'trap_card_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        html = render_card_fragment('trap_card', cache_timeout=self.cache_timeout)
        return HttpResponse(html, content_type='text/html')


class UnreachableView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/unreachable.html'

    def get(self, request, *args, **kwargs):
        context = {}

        unreachables = Unreachable.objects.filter(status='Open', device__maintenance=False).order_by('-event_start')
        # unreachables = Unreachable.objects.filter(status='Open').order_by('-event_start')
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
        # traps = Trap.objects.filter( tt__gte=date_from, status='Closed' ).order_by('-tt')
        # traps = Trap.objects.filter( tt__gte=date_from ).order_by('-tt')
        traps = Trap.objects.filter( dup_last__gte=date_from ).order_by('-dup_last','-tt')
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
                    messages.success(request, "Hibernation request created for device {}.".format( device.name ))
                elif hibernate_request:
                    messages.success(request, "Hibernation request updated for device {}.".format( device.name ))

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

        tdx = TDX()
        # tdx.init_session()
        #tdx.get_applications()
        #ticket = tdx.get_ticket('64038')
        context['recent'] = tdx.get_ticket_search()

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        context = {}

        form = IncidentForm(request.POST)
        if form.is_valid():
            ctx = {
                'server_name': "https://ocnes.netapps.unc.edu"
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

            # Work with Incident
            tdx = TDX()
            # tdx.init_session()
            if form.cleaned_data.get('number'):
                # Get an existing Incident
                incident = tdx.get_ticket(form.cleaned_data.get('number'))
                if incident:
                    context['create_message'] = "Incident {} was associated.".format(incident['ID'])
            else:
                # Get a new Incident
                # incident = tdx.create_ticket(
                incident = tdx.create_ticket_flow(
                    form.cleaned_data.get('assignment_group'),
                    form.cleaned_data.get('criticality'),
                    form.cleaned_data.get('description'),
                    render_to_string('akips/incident_worknote.txt',ctx)
                )
                if incident:
                    context['create_message'] = "Incident {} was created.".format(incident['ID'])

            if incident:
                # Map selected summaries to this incident
                # context['create_message'] = "Incident {} was created.".format(incident.number)
                logger.debug(f"mapping summaries to incident {incident['ID']}")
                for id in summary_ids:
                    summary = Summary.objects.get(id=id)
                    #summary.incident = incident['number']
                    summary.tdx_incident = incident['ID']
                    summary.save()
                for id in trap_ids:
                    trap = Trap.objects.get(id=id)
                    #trap.incident = incident['number']
                    trap.tdx_incident = incident['ID']
                    trap.save()
                messages.success(request, f"Incident {incident['ID']} was associated.")
                return HttpResponseRedirect(reverse('home'))
            else:
                messages.error(request, "Incident association failed.")

            # Failed to associate incident
            context['form'] = form
            return render(request, self.template_name, context=context)

        else:
            # Form is invalid
            tdx = TDX()
            # tdx.init_session()
            context['recent'] = tdx.get_ticket_search()

            context['form'] = form
        return render(request, self.template_name, context=context)

class DevicesAPI(View):
    ''' API view to export device definitions'''

    def get(self, request, *args, **kwargs):
        pretty_print = request.GET.get('pretty_print', None)
        result = {}
        devices = Device.objects.values('id','name','ip4addr','sysName','sysDescr','group','tier','building_name','critical','type','maintenance','hibernate','inventory_url')
        result = {"result": list(devices)}
        
        try:
            last_inventory_sync = TaskResult.objects.filter(task_name='akips.task.refresh_inventory').latest('date_done')
            result['last_inventory_sync'] = last_inventory_sync.date_done
        except TaskResult.DoesNotExist:
            result['last_inventory_sync'] = None

        try:
            last_device_sync = TaskResult.objects.filter(task_name='akips.task.refresh_akips_devices').latest('date_done')
            result['last_akips_sync'] = last_device_sync.date_done
        except TaskResult.DoesNotExist:
            result['last_akips_sync'] = None

        # Return the results
        if pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

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

class SetNotificationView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        device_name = request.GET.get('device_name', None)            # Required
        notification_mode = request.GET.get('notification_mode', None)  # Required
        logger.debug("Got {} and {}".format(device_name, notification_mode))
        if device_name is None or notification_mode is None:
            raise Http404("Missing device name or notification mode setting")

        # Update local database
        device = get_object_or_404(Device, name=device_name)
        #device = Device.objects.get(name=device_name)

        # Do the update
        result = {}
        akips = AKIPS()
        if notification_mode == 'True':
            device.notify = True
            result['text'] = akips.clear_group(device_name, '6-do-not-notify')
        else:
            device.notify = False
            result['text'] = akips.assign_group(device_name, '6-do-not-notify')
        logger.debug(json.dumps(result, indent=4, sort_keys=True))
        device.save()

        # result = {}
        # # Get the current device from local database
        # akips = AKIPS()
        # result['text'] = akips.set_maintenance_mode(device_name, notification_mode)
        # logger.debug(json.dumps(result, indent=4, sort_keys=True))

        # Return the results
        if self.pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

class UnreachablesAPI(View):
    ''' API view to export unreachable definitions'''

    def get(self, request, *args, **kwargs):
        pretty_print = request.GET.get('pretty_print', None)
        result = {}
        unreachables = Unreachable.objects.filter(status='Open').values('id','ping_state','snmp_state','event_start','device__name','device__ip4addr','device__sysName','device__maintenance','device__hibernate')
        
        result = {"result": list(unreachables)}
        # Return the results
        if pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

class SummariesAPI(LoginRequiredMixin, View):
    ''' API view to export all current summary data'''

    def get(self, request, *args, **kwargs):
        pretty_print = request.GET.get('pretty_print', None)
        type = request.GET.get('type', None)
        status = request.GET.get('status', 'Open')
        logger.debug("Type is {}".format(type))
        result = {}
        result_list = []
        if type:
            summary_list = Summary.objects.filter(type=type,status=status)
        else:
            summary_list = Summary.objects.filter(status=status)
        
        for summary in summary_list:
            unreachables = summary.unreachables.values('device__name','device__sysName','device__ip4addr').order_by('device__name').distinct()
            batteries = summary.batteries.values('device__name','device__sysName','device__ip4addr').order_by('device__name').distinct()
            data = {
                'id': summary.id,
                'type': summary.type,
                'name': summary.name,
                'ack': summary.ack,
                'ack_by': summary.ack_by,
                'ack_at': summary.ack_at,
                'comment': summary.comment,
                'first_event': summary.first_event,
                'last_event': summary.last_event,
                'trend': summary.trend,
                'status': summary.status,
                'unreachables': list(unreachables),
                'batteries': list(batteries)
            }
            if summary.sn_incident:
                data['sn_incident__number'] = summary.sn_incident.number
            else:
                data['sn_incident__number'] = None
            result_list.append(data)

        # logger.debug("result {}".format(result_list))
        result = {"result": result_list}
        if pretty_print:
            return JsonResponse(result, json_dumps_params={'indent': 4})
        else:
            return JsonResponse(result)

class SetComment(LoginRequiredMixin, View):
    ''' API call to set the comment for a summary '''
    pretty_print = True

    def post(self, request, *args, **kwargs):
        summary_id = self.kwargs.get('summary_id', None)
        comment = request.POST.get('comment', '')
        logger.debug("Summary {} set comment".format(summary_id))
    
        response_data = {
            'success': True
        }
        summary = get_object_or_404(Summary, id=summary_id)
        summary.comment = comment
        summary.save()

        return JsonResponse(response_data)

class SetIncident(LoginRequiredMixin, View):
    ''' API call to set (or clear) incident number for a summary '''
    pretty_print = True

    def post(self, request, *args, **kwargs):
        summary_id = self.kwargs.get('summary_id', None)
        incident_str = request.POST.get('incident', None)
        if incident_str:
            incident = int(incident_str)
        else:
            incident = None
        logger.debug(f"Summary {summary_id} set incident {incident}")
    
        response_data = {
            'success': True,
            'incident': incident
        }
        summary = get_object_or_404(Summary, id=summary_id)
        summary.tdx_incident = incident
        summary.save()

        return JsonResponse(response_data)

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
        trap.cleared_by = request.user.username
        trap.cleared_at = timezone.now()
        # trap.comment = "Cleared by {}".format(user)
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

class RequestSync(LoginRequiredMixin,View):
    ''' API view to trigger backend refresh job '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        result = {
            "status": 'submitted',
            "ping_sync_started": True,
            "snmp_sync_started": True,
            "ups_sync_started": True,
            "device_sync_started": True,
        }
        
        ping_tasks_pending = TaskResult.objects.filter(task_name='akips.task.refresh_ping_status',status='PENDING').count()
        ping_tasks_started = TaskResult.objects.filter(task_name='akips.task.refresh_ping_status',status='STARTED').count()
        if (ping_tasks_pending == 0 and ping_tasks_started == 0):
            refresh_ping_status.delay()
        else:
            result['ping_sync_started'] = False
            logger.debug("Ping status sync is already in progress")

        snmp_tasks_pending = TaskResult.objects.filter(task_name='akips.task.refresh_snmp_status',status='PENDING').count()
        snmp_tasks_started = TaskResult.objects.filter(task_name='akips.task.refresh_snmp_status',status='STARTED').count()
        if (snmp_tasks_pending == 0 and snmp_tasks_started == 0):
            refresh_snmp_status.delay()
        else:
            result['snmp_sync_started'] = False
            logger.debug("SNMP status sync is already in progress")

        ups_tasks_pending = TaskResult.objects.filter(task_name='akips.task.refresh_ups_status',status='PENDING').count()
        ups_tasks_started = TaskResult.objects.filter(task_name='akips.task.refresh_ups_status',status='STARTED').count()
        if (ups_tasks_pending == 0 and ups_tasks_started == 0):
            refresh_ups_status.delay()
        else:
            result['ups_sync_started'] = False
            logger.debug("UPS status sync is already in progress")

        device_tasks_pending = TaskResult.objects.filter(task_name='akips.task.refresh_akips_devices',status='PENDING').count()
        device_tasks_started = TaskResult.objects.filter(task_name='akips.task.refresh_akips_devices',status='STARTED').count()
        if (device_tasks_pending == 0 and device_tasks_started == 0):
            refresh_akips_devices.delay()
        else:
            result['device_sync_started'] = False
            logger.debug("Device sync is already in progress")

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

        last_notified = None
        if last_notified_cookie is not None:
            try:
                last_notified = datetime.fromisoformat(last_notified_cookie)
            except ValueError:
                logger.warning("Invalid last_notified cookie value; resetting notification window")

        # Define the times we care about
        now = timezone.now()
        cutoff_hours = 2
        old_session_time = now - timedelta(hours=cutoff_hours)

        result = {
            'last_notified': now,
            'level': 'info',
            'messages': [],
            'alert_enabled': self.request.user.profile.alert_enabled,
            'voice_enabled': self.request.user.profile.voice_enabled,
        }

        if last_notified is None or last_notified < old_session_time:
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
                    # tmp_messages.append("{} trap for {}".format( trap_count, traps.first().device.sysName ))
                    tmp_messages.append("{} trap".format( trap_count ))
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
        response.set_cookie('last_notified', result['last_notified'].isoformat())
        return response

class ChartDataView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True
    hours = 2
    period_minutes = 5
    cache_key = 'chart_data'
    cache_timeout = 60  # seconds

    def get(self, request, *args, **kwargs):
        # Try to get from cache first
        cached_result = cache.get(self.cache_key)
        if cached_result is not None:
            logger.debug(f"Cache HIT for {self.cache_key}")
            if self.pretty_print:
                return JsonResponse(cached_result, json_dumps_params={'indent': 4})
            else:
                return JsonResponse(cached_result)

        logger.debug(f"Cache MISS for {self.cache_key}")
        now = timezone.now()
        oldest = now - timedelta(hours=self.hours)

        # Define graph time periods
        max_label = self.round_dt_down(now, timedelta(minutes= self.period_minutes ))
        min_label = max_label - timedelta(hours=self.hours)
        keyList = [ timezone.localtime(dt).strftime('%H:%M') for dt in self.datetime_range( min_label, max_label, timedelta(minutes= self.period_minutes)) ]

        # Initialize the graph time periods
        event_data = {}
        trap_data = {}
        battery_data = {}
        for i in keyList:
            event_data[i] = 0
            trap_data[i] = 0
            battery_data[i] = 0

        # Increment sums for unreachable events in each period
        unreachables = Unreachable.objects.filter(event_start__gte=min_label).order_by('event_start')
        for unreachable in unreachables:
            slot = self.round_dt_down( unreachable.event_start, timedelta(minutes= self.period_minutes) ) 
            this_label = timezone.localtime(slot).strftime('%H:%M')
            event_data[this_label] += 1

        # Increment sums for unreachable events in each period
        traps = Trap.objects.filter(tt__gte=min_label).order_by('tt')
        for trap in traps:
            slot = self.round_dt_down( trap.tt, timedelta(minutes= self.period_minutes) ) 
            this_label = timezone.localtime(slot).strftime('%H:%M')
            trap_data[this_label] += 1

        # Increment sums for ups battery events in each period
        battery = Status.objects.filter(attribute='UPS-MIB.upsOutputSource',
                                        value='battery',
                                        last_change__gte=min_label,
                                        device__maintenance=False).exclude(device__hibernate=True)
        for ups in battery:
            slot = self.round_dt_down( ups.last_change, timedelta(minutes= self.period_minutes) ) 
            this_label = timezone.localtime(slot).strftime('%H:%M')
            battery_data[this_label] += 1

        result = {
            'chart_labels': list( event_data.keys() ),
            'chart_event_data': list( event_data.values() ),
            'chart_trap_data': list( trap_data.values() ),
            'chart_battery_data': list( battery_data.values() ),
        }

        # Check and notify around MAX_UNREACHABLE
        current_unreachable_count = Unreachable.objects.filter(status='Open', device__maintenance=False).count()
        if settings.MAX_UNREACHABLE and current_unreachable_count >= settings.MAX_UNREACHABLE:
            logger.warning("Unreachables are above acceptable limit")
            result['above_max_unreachable'] = True
        else:
            result['above_max_unreachable'] = False

        # Store in cache
        cache.set(self.cache_key, result, self.cache_timeout)

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
        logger.debug("Preference update for %s", request.user.username)
        alert_enabled = request.GET.get('alert_enabled', None)
        voice_enabled = request.GET.get('voice_enabled', None)

        user = request.user
        changed = False
        if alert_enabled is not None:
            if alert_enabled == 'False':
                user.profile.alert_enabled = False
            else:
                user.profile.alert_enabled = True
            changed = True
        if voice_enabled is not None:
            if voice_enabled == 'False':
                user.profile.voice_enabled = False
            else:
                user.profile.voice_enabled = True
            changed = True

        if changed:
            user.save()

        result = {
            "alert_enabled": user.profile.alert_enabled,
            "voice_enabled": user.profile.voice_enabled,
        }
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
    # Accept webhook calls and authenticate before proceeding
    given_token = request.headers.get("Akips-Webhook-Token", "")
    if not given_token:
        logger.debug("No token provided")
        return HttpResponseBadRequest()
    if not compare_digest(given_token, settings.AKIPS_WEBHOOK_TOKEN):
        logger.debug("expected token {}".format(settings.AKIPS_WEBHOOK_TOKEN))
        logger.debug("got token      {}".format(given_token))
        return HttpResponseForbidden()

    # Extract valid jason data
    response_data = {}
    try:
        payload = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        logger.warn("unable to parse body for json payload: {}".format(request.body))
        return HttpResponseBadRequest()

    logger.info("Trap payload: {}".format( str(payload) ))
    response_data['success'] = process_webhook_payload(payload)
    return JsonResponse(response_data)


@atomic
def process_webhook_payload(payload):
    # Handle the webhook action, return success (True/False)
    if 'device' not in payload:
        logger.warn("Webhook is missing device field")
        return False
    elif 'kind' not in payload:
        logger.warn("Webhook is missing kind field")
        return False

    device = None
    try:
        # The trap data has 'device' and 'ipaddr' but they are always
        # the source ip of the trap.  AKIPS doesn't populate 'device' as
        # expected.  There is a support ticket in for that.
        # Status updates do not have an ipaddr field though and use 'device'.
        if 'ipaddr' in payload:
            device = Device.objects.get(ip4addr=payload['ipaddr'])
        else:
            device = Device.objects.get(name=payload['device'])
    except Device.DoesNotExist:
        logger.warn("Webhook received for unknown device {}".format(payload))
        # logger.warn("Trap {} received from unknown device {} with address {}".format(
        #     payload['trap_oid'], payload['device'], payload['ipaddr']))

    # Check the api for alternate addresses if we don't have a device match
    if not device and 'ipaddr' in payload:
        akips = AKIPS()
        device_name = akips.get_device_by_ip(payload['ipaddr'])
        if device_name:
            try:
                device = Device.objects.get(name=device_name)
            except Device.DoesNotExist:
                logger.warn("Trap from {} could not be mapped to a device record".format(payload['device']))

    # If All attempts at matching a device record fail, stop going forward
    if not device:
        logger.warn("Webhook call from {} could not be mapped to a device record".format(payload['device']))
        return False

    if payload['kind'] == 'status':
        Status.objects.update_or_create(
            device=device,
            child=payload['child'],
            attribute=payload['attr'],
            defaults={
                'value': payload['state'],
                'last_change': datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone()),
            }
        )
        return True

    elif payload['kind'] == 'threshold':
        # no current processing
        return False

    elif payload['kind'] == 'syslog':
        # no current processing
        return False

    elif payload['kind'] == 'trap':
        # process trap data
        if device.maintenance is False and device.notify is True:
            # Check for Open duplicates
            duplicates = Trap.objects.filter( 
                device=device, 
                trap_oid=payload['trap_oid'],
                oids=json.dumps(payload['oids']),
                status='Open')

            if duplicates:
                # Update for duplications
                logger.info("Trap has repeated")
                for duplicate in duplicates:
                    duplicate.dup_count += 1
                    duplicate.dup_last = datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone())
                    duplicate.save()
            else:
                # Update for unique
                Trap.objects.create(
                    tt=datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone()),
                    device=device,
                    ipaddr=payload['ipaddr'],
                    trap_oid=payload['trap_oid'],
                    uptime=payload['uptime'],
                    oids=json.dumps(payload['oids']),
                    dup_count = 0,
                    dup_last = datetime.fromtimestamp(int(payload['tt']), tz=timezone.get_current_timezone())
                )
            return True
        else:
            # ignoring this device
            return True

    else:
        logger.warn("Unknown kind value {}".format( str(payload) ))
        return False

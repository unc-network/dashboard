import logging
import json
from secrets import compare_digest

from django.conf import settings
from django.shortcuts import render
from django.views.generic import View
from django.http import Http404, JsonResponse, HttpResponse, HttpResponseForbidden
from django.contrib.auth.mixins import LoginRequiredMixin
#from django.utils.decorators import method_decorator
from django.db.transaction import atomic, non_atomic_requests
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Summary, Unreachable, Device, WebhookMessage
from .task import example_task
from .utils import AKIPS

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

class Home(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}

        context['critical'] = Summary.objects.filter(type='Critical',status='Open').order_by('name')
        context['tiers'] = Summary.objects.filter(type='Distribution',status='Open').order_by('name')
        context['bldgs'] = Summary.objects.filter(type='Building',status='Open').order_by('name')

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
        context['critical'] = Summary.objects.filter(type='Critical',status='Open').order_by('name')
        return render(request, self.template_name, context=context)

class TierCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_tier.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['tiers'] = Summary.objects.filter(type='Distribution',status='Open').order_by('name')
        return render(request, self.template_name, context=context)

class BuildingCard(LoginRequiredMixin, View):
    ''' Generic card refresh view '''
    template_name = 'akips/card_refresh_bldg.html'

    def get(self, request, *args, **kwargs):
        context = {}
        context['bldgs'] = Summary.objects.filter(type='Building',status='Open').order_by('name')
        return render(request, self.template_name, context=context)

class UnreachableView(LoginRequiredMixin, View):
    ''' Generic first view '''
    template_name = 'akips/unreachable.html'

    def get(self, request, *args, **kwargs):
        context = {}

        #devices = Unreachable.objects.exclude(status='Closed').exclude(device__maintenance=True)
        devices = Unreachable.objects.filter(status='Open',device__maintenance=False)
        context['devices'] = devices

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
        devices = Unreachable.objects.filter(status='Open',device__tier=tier_name).order_by('device__name')
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
        devices = Unreachable.objects.filter(status='Open',device__building_name=bldg_name).order_by('device__name')
        context['devices'] = devices

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

        context['device'] = Device.objects.get(name=device_name)
        #devices = Unreachable.objects.filter(device__name=device_name)
        devices = Unreachable.objects.filter(status='Open',device__name=device_name)
        context['devices'] = devices

        return render(request, self.template_name, context=context)

class IncidentView(LoginRequiredMixin, View):
    ''' Create Incidents '''
    template_name = 'akips/incident.html'

    def get(self, request, *args, **kwargs):
        context = {}
        checkboxes = request.GET.getlist('event')
        logger.debug("Got list {}".format(checkboxes))

        summaries = Summary.objects.filter(id__in=checkboxes)
        context['summaries'] = summaries

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        context = {}

        return render(request, self.template_name, context=context)

class SetMaintenanceView(LoginRequiredMixin, View):
    ''' API view '''
    pretty_print = True

    def get(self, request, *args, **kwargs):
        device_name = request.GET.get('device_name',None)            # Required
        maintenance_mode = request.GET.get('maintenance_mode',None)  # Required
        logger.debug("Got {} and {}".format(device_name,maintenance_mode))
        if device_name is None or maintenance_mode is None:
            raise Http404("Missing device name or maintenance mode setting")

        # Update local database
        device = Device.objects.get(name=device_name)
        if maintenance_mode == 'True':
            device.maintenance = True
        else:
            device.maintenance = False
        device.save()

        result = {}
        # Get the current device from local database
        akips = AKIPS()
        result['text'] = akips.set_maintenance_mode(device_name,maintenance_mode)
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
        ack = request.GET.get('ack',None)  # Required
        logger.debug("Got ack for {}".format(summary_id))
        result = {}

        summary = Summary.objects.get(id=summary_id)
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


### functional views ###

@csrf_exempt
@require_POST
@non_atomic_requests
def akips_webhook(request):
    given_token = request.headers.get("Akips-Webhook-Token", "")
    if not compare_digest(given_token, settings.AKIPS_WEBHOOK_TOKEN):
        logger.debug( "expected token {}".format(settings.AKIPS_WEBHOOK_TOKEN) )
        logger.debug( "got token      {}".format(given_token) )
        return HttpResponseForbidden(
            "Incorrect token in Akips-Webhook-Token header.",
            content_type="text/plain",
        )

    payload = json.loads(request.body)
    WebhookMessage.objects.create( message=payload )
    process_webhook_payload(payload)
    return HttpResponse("Message received.", content_type="text/plain")

@atomic
def process_webhook_payload(payload):
    pass
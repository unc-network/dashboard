from django.shortcuts import render
from django.views.generic import View
from django.http import Http404
import logging

from .models import Summary, Unreachable
from .task import example_task

# Get a instance of logger
logger = logging.getLogger(__name__)

# Create your views here.

class Home(View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}

        context['tiers'] = Summary.objects.filter(type='Distribution',status='Open').order_by('name')
        context['bldgs'] = Summary.objects.filter(type='Building',status='Open').order_by('name')

        return render(request, self.template_name, context=context)

class UnreachableView(View):
    ''' Generic first view '''
    template_name = 'akips/unreachable.html'

    def get(self, request, *args, **kwargs):
        context = {}

        return render(request, self.template_name, context=context)

class TierView(View):
    ''' Generic first view '''
    template_name = 'akips/tier.html'

    def get(self, request, *args, **kwargs):
        context = {}
        tier_name = self.kwargs.get('tier', None)
        if tier_name is None:
            raise Http404("Invalid Tier Name")
        context['tier'] = tier_name

        devices = Unreachable.objects.filter(device__tier=tier_name)
        logger.debug("Found devices {}".format(devices))
        context['devices'] = devices

        return render(request, self.template_name, context=context)

class BuildingView(View):
    ''' Generic first view '''
    template_name = 'akips/building.html'

    def get(self, request, *args, **kwargs):
        context = {}
        bldg_name = self.kwargs.get('bldg', None)
        if bldg_name is None:
            raise Http404("Invalid Building Name")
        context['bldg'] = bldg_name

        devices = Unreachable.objects.filter(device__building_name=bldg_name)
        logger.debug("Found devices {}".format(devices))
        context['devices'] = devices

        return render(request, self.template_name, context=context)

class DeviceView(View):
    ''' Generic first view '''
    template_name = 'akips/device.html'

    def get(self, request, *args, **kwargs):
        context = {}
        device_name = self.kwargs.get('device', None)
        if device_name is None:
            raise Http404("Invalid Device Name")
        context['device'] = device_name

        return render(request, self.template_name, context=context)

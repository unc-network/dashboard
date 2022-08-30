from django.shortcuts import render
from django.views.generic import View
import logging

from .task import example_task

# Get a instance of logger
logger = logging.getLogger(__name__)

# Create your views here.

class Home(View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}

        return render(request, self.template_name, context=context)

class TaskTest(View):
    ''' Generic first view '''
    template_name = 'akips/home.html'

    def get(self, request, *args, **kwargs):
        context = {}

        # Call example task
        example_task.delay()

        return render(request, self.template_name, context=context)
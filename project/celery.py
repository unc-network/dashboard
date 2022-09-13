from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env

# setting the Django settings module.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
app = Celery('project')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Looks up for task modules in Django applications and loads them
app.autodiscover_tasks()
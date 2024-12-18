"""
Django settings for this project.

Generated by 'django-admin startproject' using Django 3,2,4.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

import os
import sys
from datetime import timedelta
import ldap
from django_auth_ldap.config import LDAPSearch, GroupOfNamesType

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# The SECRET_KEY is provided via an environment variable in OpenShift
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    # safe value used for development when DJANGO_SECRET_KEY might not be set
    '9e4@&tw46$l31)zrqe3wi+-slqm(ruvz&se0^%9#6(_w3ui!c0'
)

# SECURITY WARNING: don't run with debug turned on in production!
DJANGO_DEBUG = os.getenv('DJANGO_DEBUG', 'False')
if DJANGO_DEBUG == 'True':
    DEBUG = True
else:
    DEBUG = False

ALLOWED_HOSTS = ['*']

# Openshift Namespace
# Find the namespace this application is running under.
OPENSHIFT_NAMESPACE = os.getenv('OPENSHIFT_BUILD_NAMESPACE', 'LOCAL')

# Application definition
INSTALLED_APPS = [
    #'adminlte3_theme',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'debug_toolbar',
    'welcome',

    'adminlte3',

    # Our Apps
    'akips',

    # Celery
    'django_celery_results',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'

# Added for 4.2 upgrade, was not needed in 3.2
CSRF_TRUSTED_ORIGINS = [
    'https://*.netapps.unc.edu',
    'https://*.cloudapps.unc.edu',
    'https://*.127.0.0.1'
]

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

from . import database

DATABASES = {
    'default': database.config()
}

# https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Django's cache framework
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'my_cache_table',
    }
}

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Base LDAP credentials
LDAP_SERVER = os.getenv('LDAP_SERVER', 'ldaps://ldap.unc.edu:636')
LDAP_USERNAME = os.getenv('LDAP_USERNAME', '')
LDAP_PASSWORD = os.getenv('LDAP_PASSWORD', '')

# LDAP Authentication Configuration
# https://django-auth-ldap.readthedocs.io/en/latest/example.html

# Baseline configuration.
AUTH_LDAP_SERVER_URI = LDAP_SERVER

AUTH_LDAP_BIND_DN = LDAP_USERNAME
AUTH_LDAP_BIND_PASSWORD = LDAP_PASSWORD
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    'ou=people,dc=unc,dc=edu',
    ldap.SCOPE_SUBTREE,
    '(uid=%(user)s)',
)
# Or:
# AUTH_LDAP_USER_DN_TEMPLATE = 'uid=%(user)s,ou=users,dc=example,dc=com'

# Set up the basic group parameters.
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    'ou=groups,dc=unc,dc=edu',
    ldap.SCOPE_SUBTREE,
    '(objectClass=groupOfNames)',
)
AUTH_LDAP_GROUP_TYPE = GroupOfNamesType(name_attr='cn')

# Simple group restrictions
AUTH_LDAP_REQUIRE_GROUP = "cn=unc:app:its:net:routerproxy:users,ou=groups,dc=unc,dc=edu"
#AUTH_LDAP_DENY_GROUP = "cn=disabled,ou=django,ou=groups,dc=example,dc=com"

# Populate the Django user from the LDAP directory.
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}

AUTH_LDAP_USER_FLAGS_BY_GROUP = {
    "is_active": "cn=unc:app:its:net:routerproxy:users,ou=groups,dc=unc,dc=edu",        # Designates whether this user should be treated as active. Unselect this instead of deleting accounts.
    "is_staff": "cn=unc:app:its:net:routerproxy:admins,ou=groups,dc=unc,dc=edu",        # Designates whether the user can log into this admin site.
    "is_superuser": "cn=unc:app:its:net:routerproxy:admins,ou=groups,dc=unc,dc=edu",    # Designates that this user has all permissions without explicitly assigning them.
}

# This is the default, but I like to be explicit.
AUTH_LDAP_ALWAYS_UPDATE_USER = True

# Use LDAP group membership to calculate group permissions.
AUTH_LDAP_FIND_GROUP_PERMS = True

# Cache distinguished names and group memberships for an hour to minimize
# LDAP traffic.
AUTH_LDAP_CACHE_TIMEOUT = 3600

# Keep ModelBackend around for per-user permissions and maybe a local
# superuser.
AUTHENTICATION_BACKENDS = [
    'django_auth_ldap.backend.LDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

#STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

INTERNAL_IPS = ['127.0.0.1']

# Email configuration
EMAIL_HOST = 'relay.unc.edu'
EMAIL_PORT = 25
DEFAULT_FROM_EMAIL = 'devops@office.unc.edu'
# Error emails sent from:
SERVER_EMAIL = 'devops@office.unc.edu'

# Session settings
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 1209600    # default 2 weeks, in seconds

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s',
            'datefmt': '%b %d %Y %H:%M:%S'
        },
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s',
            'datefmt': '%b %d %Y %H:%M:%S'
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {    # This goes to sys.stderr
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler', 
            'formatter': 'simple'
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false']
        },
        'openshift': {
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'propagate': True,
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'akips': {
            'handlers': ['openshift'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    }
}

# Define the admins who should receive error email
ADMINS = [
    #('DevOps', 'devops@office.unc.edu'),
    ('Will Whitaker', 'will.whitaker@unc.edu'),
]

# Define the Grouper prefix
GROUPER_PREFIX='unc:app:its:net:routerproxy'

# CELERY related settings
BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0') 
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'America/New_York'
CELERY_TASK_TRACK_STARTED = True
CELERY_SEND_TASK_ERROR_EMAILS = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# django-celery-results
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_RESULT_EXTENDED = True

# django-celery-beat
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Celery Schedule Defaults
CELERY_BEAT_SCHEDULE = {
    'Refresh AKIPS Devices': {
        'task': 'akips.task.refresh_akips_devices',
        'schedule': timedelta(hours=2),
        'description': 'Update the local cache of devices registered in AKiPS.'
    },
    'Refresh Inventory Feed': {
        'task': 'akips.task.refresh_inventory',
        'schedule': timedelta(hours=4),
        'description': 'Pull device details from the external inventory feed.'
    },
    'Refresh Unreachable': {
        'task': 'akips.task.refresh_unreachable',
        'schedule': timedelta(seconds=30),
        # 'kwargs': {"mode": "status"},
        'description': 'This is the primary job that calculates and updates summary data.'
    },
    'Refresh SNMP Status': {
        'task': 'akips.task.refresh_snmp_status',
        'schedule': timedelta(hours=1),
        'description': 'Synchronize the local SNMP status for all AKiPS devices.'
    },
    'Refresh Ping Status': {
        'task': 'akips.task.refresh_ping_status',
        'schedule': timedelta(hours=1),
        'description': 'Synchronize the local Ping status for all AKiPS devices.'
    },
    'Refresh UPS Status': {
        'task': 'akips.task.refresh_ups_status',
        'schedule': timedelta(hours=1),
        'description': 'Synchronize the local UPS status for all AKiPS devices.'
    },
    'Refresh Battery Test Status': {
        'task': 'akips.task.refresh_battery_test_status',
        'schedule': timedelta(hours=4),
        'description': 'Synchronize the local Battery Test status for all AKiPS devices.'
    },
    'Refresh Hibernate': {
        'task': 'akips.task.refresh_hibernate',
        'schedule': timedelta(minutes=1),
        'description': 'Review hibernate device requests and update device status if needed.'
    },
    'Refresh ServiceNow': {
        'task': 'akips.task.refresh_incidents',
        'schedule': timedelta(minutes=10),
        'description': 'Refresh our ServiceNow incident status if needed.'
    },
    'Cleanup Dashboard Data': {
        'task': 'akips.task.cleanup_dashboard_data',
        'schedule': timedelta(hours=1),
        'description': 'Basic task to remove old data no longer needed or helpful.'
    }
}

# AKiPS settings
AKIPS_CACERT = os.getenv('AKIPS_CACERT', None)
# Incoming Webhook, default to something for testing
AKIPS_WEBHOOK_TOKEN = os.getenv('AKIPS_WEBHOOK_TOKEN', 'Tkjh9P6PlqYQLqVz1fLNMPu4lNv9ac2EBkejAIKt2hgH8D7GtvtA')

# Inventory Feed Settings
INVENTORY_URL = os.getenv('INVENTORY_URL', None)
INVENTORY_TOKEN = os.getenv('INVENTORY_TOKEN', None)

# OCNES Specific
MAX_UNREACHABLE = int(os.getenv('MAX_UNREACHABLE', 2000))

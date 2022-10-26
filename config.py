# Gunicorn configuration file
# https://docs.gunicorn.org/en/stable/configure.html#configuration-file
# https://docs.gunicorn.org/en/stable/settings.html
import os

# This is needed to extend the worker thread timeout for long running tasks
timeout = 600
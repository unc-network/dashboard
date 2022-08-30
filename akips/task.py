from celery import shared_task
import logging

# Get an isntace of a logger
logger = logging.getLogger(__name__)

@shared_task
def example_task(optional_param):
    logger.info("celery task is running")

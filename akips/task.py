from celery import shared_task
import logging

# Get an instace of a logger
logger = logging.getLogger(__name__)

@shared_task
def example_task():
    logger.info("celery task is running")

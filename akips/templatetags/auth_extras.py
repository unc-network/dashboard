from django import template
from django.contrib.auth.models import Group 
import logging

logger = logging.getLogger(__name__)
register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name): 
    try:
        group = Group.objects.get(name=group_name) 
    except Group.DoesNotExist:
        logger.debug("group {} does not exist".format(group_name))
        return False
    return True if group in user.groups.all() else False
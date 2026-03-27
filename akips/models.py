from typing import TYPE_CHECKING
import os
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.


class Device(models.Model):
    ''' Representation of AKiPS device record '''
    name = models.CharField(max_length=255, unique=True)
    ip4addr = models.GenericIPAddressField()
    sysName = models.CharField(max_length=255, blank=True)
    sysDescr = models.CharField(max_length=255, blank=True)
    sysLocation = models.CharField(max_length=255, blank=True)
    group = models.CharField(max_length=255, default='default')
    critical = models.BooleanField(default=False)
    tier = models.CharField(max_length=255, blank=True)
    building_name = models.CharField(max_length=255, blank=True)
    hierarchy = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, blank=True)
    maintenance = models.BooleanField(default=False)
    hibernate = models.BooleanField(default=False)
    comment = models.CharField(max_length=1024, blank=True)
    last_refresh = models.DateTimeField()
    inventory_url = models.URLField(blank=True,default='')
    notify = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        # indexes = [models.Index(fields=['ip4addr'])]

    def __str__(self):
        return str(self.name)

class Unreachable(models.Model):
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    STATE_CHOICES = (
        ('up', 'up'),
        ('down', 'down'),
        ('unreported', 'unreported'),
    )
    # Unreachable devices from akips
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    child = models.CharField(max_length=255)
    attribute = models.CharField(max_length=255)
    ping_state = models.CharField( max_length=32, choices=STATE_CHOICES, default='unreported')
    snmp_state = models.CharField( max_length=32, choices=STATE_CHOICES, default='unreported')
    index = models.CharField(max_length=255,blank=True)    # extracted from value
    # state = models.CharField(max_length=255)    # extracted from value
    device_added = models.DateTimeField( blank=True, null=True)       # extracted from value
    event_start = models.DateTimeField()        # extracted from value
    ip4addr = models.GenericIPAddressField( blank=True, null=True)    # extracted from value
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['-event_start']

    def __str__(self):
        return str(self.device)

class ServiceNowIncident(models.Model):
    number = models.CharField(max_length=10)
    sys_id = models.CharField(max_length=32,blank=True)
    instance = models.CharField(max_length=32,default='uncchdev')
    active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.number)

class Trap(models.Model):
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    tt = models.DateTimeField()
    ipaddr = models.GenericIPAddressField()
    trap_oid = models.CharField(max_length=255)
    uptime = models.CharField(max_length=255)
    oids = models.CharField(max_length=2048)
    ack = models.BooleanField(default=False)
    ack_by = models.CharField(max_length=32, blank=True)
    ack_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Open')
    cleared_by = models.CharField(max_length=32, blank=True)
    cleared_at = models.DateTimeField(null=True, blank=True)
    incident = models.CharField(blank=True, max_length=255)
    sn_incident = models.ForeignKey(ServiceNowIncident, blank=True, null=True, on_delete=models.SET_NULL)
    # tdx_incident = models.ForeignKey(TDXIncident, blank=True, null=True, on_delete=models.SET_NULL)
    tdx_incident = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dup_count = models.IntegerField(default=0)
    dup_last = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-tt']

    def __str__(self):
        return str(self.id)

class Status(models.Model):
    ''' Representation of AKiPS status record '''
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    child = models.CharField(max_length=255)
    attribute = models.CharField(max_length=255)
    index = models.CharField(max_length=255,blank=True)
    value = models.CharField(max_length=255)
    device_added = models.DateTimeField(blank=True,null=True)
    last_change = models.DateTimeField()
    ip4addr = models.GenericIPAddressField(blank=True,null=True)

    class Meta:
        verbose_name_plural = 'statuses'
        ordering = ['device']
        indexes = [ models.Index(fields=['attribute']) ]

    def __str__(self):
        return str(self.id)

class Summary(models.Model):
    ''' Summarized view of unreachable devices '''
    TYPE_CHOICES = (
        ('Distribution', 'Distribution'),
        ('Building', 'Building'),
        ('Critical', 'Critical'),
        ('Specialty', 'Specialty'),
    )
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    tier = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    ack = models.BooleanField(default=False)
    ack_by = models.CharField(max_length=32, blank=True)
    ack_at = models.DateTimeField(null=True, blank=True)
    unreachables = models.ManyToManyField(Unreachable, blank=True)
    batteries = models.ManyToManyField(Status, blank=True)
    switch_count = models.IntegerField(default=0)
    ap_count = models.IntegerField(default=0)
    ups_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    max_count = models.IntegerField(default=0)
    percent_down = models.DecimalField(default=0, max_digits=4, decimal_places=3)
    moving_average = models.FloatField(default=0)
    moving_avg_count = models.IntegerField(default=0)
    ups_battery = models.IntegerField(default=0)
    first_event = models.DateTimeField(help_text="First up/down event in the summary time period")
    last_event = models.DateTimeField(help_text="Last up/down event in the summary time period")
    trend = models.CharField(default='New', max_length=255)
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    incident = models.CharField(blank=True, max_length=255)
    sn_incident = models.ForeignKey(ServiceNowIncident, blank=True, null=True, on_delete=models.SET_NULL)
    # tdx_incident = models.ForeignKey(TDXIncident, blank=True, null=True, on_delete=models.SET_NULL)
    tdx_incident = models.IntegerField(null=True, blank=True)
    last_refresh = models.DateTimeField(auto_now_add=True, help_text="Last time the summary data was refreshed")

    class Meta:
        verbose_name_plural = 'summaries'
        #ordering = ['tier', '-type', 'name', 'first_event']
        ordering = ['-first_event']

    def __str__(self):
        return str(self.name)

# class HibernateWindow(models.Model):
#     CLOSE_CHOICES = (
#         ('Auto', 'Auto'),
#         ('Time', 'Time'),
#         ('Manual', 'Manual'),
#     )
#     STATUS_CHOICES = (
#         ('Planned', 'Planned'),
#         ('Open', 'Open'),
#         ('Closed', 'Closed'),
#     )
#     device = models.ForeignKey(Device, on_delete=models.CASCADE)
#     start = models.DateTimeField(null=True, blank=True)
#     end = models.DateTimeField(null=True, blank=True)
#     end_type = models.CharField(max_length=32, choices=CLOSE_CHOICES)
#     comment = models.CharField(max_length=1024, blank=True)
#     status = models.CharField(max_length=32, choices=STATUS_CHOICES)
#     created_by = models.CharField(max_length=32)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return str(self.device)

class HibernateRequest(models.Model):
    TYPE_CHOICES = (
        ('Auto', 'Auto'),
        ('Time', 'Time'),
        ('Manual', 'Manual'),
    )
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    scheduled = models.DateTimeField(null=True, blank=True)
    executed = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    created_by = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.device)

# class ServiceNowGroup(models.Model):
#     name = models.CharField(max_length=1024)
#     group_name = models.CharField(max_length=1024)

#     def __str__(self):
#         return str(self.id)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    alert_enabled = models.BooleanField(default=True)
    voice_enabled = models.BooleanField(default=True)

    def __str__(self):
        return str(self.user)


class AKIPSConfiguration(models.Model):
    enabled = models.BooleanField(default=False)
    server = models.CharField(max_length=255, blank=True, default='')
    username = models.CharField(max_length=255, blank=True, default='')
    password = models.CharField(max_length=255, blank=True, default='')
    verify_ssl = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AKIPS configuration'
        verbose_name_plural = 'AKIPS configuration'

    @classmethod
    def env_defaults(cls):
        return {
            'enabled': os.getenv('AKIPS_SERVER', '') != '',
            'server': os.getenv('AKIPS_SERVER', ''),
            'username': os.getenv('AKIPS_USERNAME', ''),
            'password': os.getenv('AKIPS_PASSWORD', ''),
            'verify_ssl': os.getenv('AKIPS_CACERT', '').lower() != 'false',
        }

    @classmethod
    def get_solo(cls):
        defaults = cls.env_defaults()
        try:
            obj, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
            return obj
        except (OperationalError, ProgrammingError):
            return cls(pk=1, **defaults)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return 'AKIPS configuration'


class TDXConfiguration(models.Model):
    enabled = models.BooleanField(default=False)
    api_url = models.URLField(blank=True, default='')
    flow_url = models.URLField(blank=True, default='')
    username = models.CharField(max_length=255, blank=True, default='')
    password = models.CharField(max_length=255, blank=True, default='')
    apikey = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'TDX configuration'
        verbose_name_plural = 'TDX configuration'

    @classmethod
    def env_defaults(cls):
        return {
            'enabled': os.getenv('UPDATE_TDX', 'false').lower() == 'true',
            'api_url': os.getenv('TDX_URL', 'https://tdx.unc.edu/TDWebApi/'),
            'flow_url': os.getenv('TDX_FLOW_URL', ''),
            'username': os.getenv('TDX_USERNAME', ''),
            'password': os.getenv('TDX_PASSWORD', ''),
            'apikey': os.getenv('TDX_APIKEY', ''),
        }

    @classmethod
    def get_solo(cls):
        defaults = cls.env_defaults()
        try:
            obj, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
            return obj
        except (OperationalError, ProgrammingError):
            return cls(pk=1, **defaults)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return 'TDX configuration'


class InventoryConfiguration(models.Model):
    enabled = models.BooleanField(default=False)
    inventory_url = models.URLField(blank=True, default='')
    inventory_token = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inventory configuration'
        verbose_name_plural = 'Inventory configuration'

    @classmethod
    def env_defaults(cls):
        return {
            'enabled': bool(os.getenv('INVENTORY_URL')),
            'inventory_url': os.getenv('INVENTORY_URL', ''),
            'inventory_token': os.getenv('INVENTORY_TOKEN', ''),
        }

    @classmethod
    def get_solo(cls):
        defaults = cls.env_defaults()
        try:
            obj, _created = cls.objects.get_or_create(pk=1, defaults=defaults)
            return obj
        except (OperationalError, ProgrammingError):
            return cls(pk=1, **defaults)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return 'Inventory configuration'


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if kwargs.get('raw', False):
        return
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if kwargs.get('raw', False):
        return
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()

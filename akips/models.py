from typing import TYPE_CHECKING
from django.db import models
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
    last_refresh = models.DateTimeField(auto_now_add=True, help_text="Last time the summary data was refreshed")

    class Meta:
        verbose_name_plural = 'summaries'
        #ordering = ['tier', '-type', 'name', 'first_event']
        ordering = ['-first_event']

    def __str__(self):
        return str(self.name)

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


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()

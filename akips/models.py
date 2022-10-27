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
    hierarcy = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, blank=True)
    maintenance = models.BooleanField(default=False)
    hibernate = models.BooleanField(default=False)
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['name']
        # indexes = [models.Index(fields=['ip4addr'])]

    def __str__(self):
        return str(self.name)


class Status(models.Model):
    ''' Representation of AKiPS status record '''
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    child = models.CharField(max_length=255)
    attribute = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    last_change = models.DateTimeField()

    class Meta:
        verbose_name_plural = 'statuses'
        ordering = ['device']
        indexes = [ models.Index(fields=['attribute']) ]

    def __str__(self):
        return str(self.id)


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
    index = models.CharField(max_length=255)    # extracted from value
    # state = models.CharField(max_length=255)    # extracted from value
    device_added = models.DateTimeField()       # extracted from value
    event_start = models.DateTimeField()        # extracted from value
    ip4addr = models.GenericIPAddressField( blank=True, null=True)    # extracted from value
    last_refresh = models.DateTimeField()
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)

    class Meta:
        ordering = ['-event_start']

    def __str__(self):
        return str(self.device)

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
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    comment = models.CharField(max_length=1024, blank=True)

    def __str__(self):
        return str(self.device)

# class BatteryEvent(models.Model):
#     STATUS_CHOICES = (
#         ('Open', 'Open'),
#         ('Closed', 'Closed'),
#     )
#     # UPS battery events
#     device = models.ForeignKey(Device, on_delete=models.CASCADE)
#     child = models.CharField(max_length=255)
#     attribute = models.CharField(max_length=255)
#     value = models.CharField(max_length=255)
#     event_start = models.DateTimeField()
#     last_refresh = models.DateTimeField()
#     comment = models.CharField(max_length=1024, blank=True)

#     class Meta:
#         ordering = ['-event_start']

#     def __str__(self):
#         return str(self.device)


class Summary(models.Model):
    ''' Summarized view of unreachable devices '''
    TYPE_CHOICES = (
        ('Distribution', 'Distribution'),
        ('Building', 'Building'),
        ('Critical', 'Critical'),
        ('Speciality', 'Speciality'),
    )
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    tier = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    ack = models.BooleanField(default=False)
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
    last_refresh = models.DateTimeField(auto_now_add=True, help_text="Last time the summmary data was refreshed")
    trend = models.CharField(default='New', max_length=255)
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    incident = models.CharField(blank=True, max_length=255)

    class Meta:
        verbose_name_plural = 'summaries'
        #ordering = ['tier', '-type', 'name', 'first_event']
        ordering = ['-first_event']

    def __str__(self):
        return str(self.name)


class SNMPTrap(models.Model):
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    tt = models.DateTimeField()
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    ipaddr = models.GenericIPAddressField()
    trap_oid = models.CharField(max_length=255)
    uptime = models.CharField(max_length=255)
    oids = models.CharField(max_length=1024)
    ack = models.BooleanField(default=False)
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Open')
    incident = models.CharField(blank=True, max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    dup_count = models.IntegerField(default=0)
    dup_last = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-tt']

    def __str__(self):
        return str(self.id)


# class ServiceNowGroup(models.Model):
#     name = models.CharField(max_length=1024)
#     group_name = models.CharField(max_length=1024)

#     def __str__(self):
#         return str(self.id)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
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

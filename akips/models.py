from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.


class Device(models.Model):
    # devices from akips
    name = models.CharField(max_length=255, unique=True)
    ip4addr = models.GenericIPAddressField()
    sysName = models.CharField(max_length=255, blank=True)
    sysDescr = models.CharField(max_length=255, blank=True)
    sysLocation = models.CharField(max_length=255, blank=True)
    critical = models.BooleanField(default=False)
    tier = models.CharField(max_length=255, blank=True)
    building_name = models.CharField(max_length=255, blank=True)
    hierarcy = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, blank=True)
    maintenance = models.BooleanField(default=False)
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['ip4addr'])]

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
    index = models.CharField(max_length=255)    # extracted from value
    # state = models.CharField(max_length=255)    # extracted from value
    device_added = models.DateTimeField()       # extracted from value
    event_start = models.DateTimeField()        # extracted from value
    ip4addr = models.GenericIPAddressField( blank=True, null=True)    # extracted from value
    last_refresh = models.DateTimeField()
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)

    class Meta:
        ordering = ['device', 'event_start']

    def __str__(self):
        return str(self.device)


class Summary(models.Model):
    ''' Summarized view of unreachable devices '''
    TYPE_CHOICES = (
        ('Distribution', 'Distribution'),
        ('Building', 'Building'),
        ('Critical', 'Critical')
    )
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    tier = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    ack = models.BooleanField(default=False)
    #device = models.ForeignKey(Device, blank=True, null=True, on_delete=models.CASCADE)
    unreachables = models.ManyToManyField(Unreachable)
    switch_count = models.IntegerField(default=0)
    ap_count = models.IntegerField(default=0)
    ups_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    max_count = models.IntegerField(default=0)
    percent_down = models.DecimalField(
        default=0, max_digits=4, decimal_places=3)
    first_event = models.DateTimeField()
    trend = models.CharField(default='New', max_length=255)
    last_event = models.DateTimeField()
    comment = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    incident = models.CharField(blank=True, max_length=255)

    class Meta:
        ordering = ['tier', '-type', 'name', 'first_event']

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
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default='Open')
    incident = models.CharField(blank=True, max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id)


class UserAlert(models.Model):
    message = models.CharField(max_length=1024)
    sound = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

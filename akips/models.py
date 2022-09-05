from django.db import models

# Create your models here.

class Device(models.Model):
    # devices from akips
    name = models.CharField(max_length=255, unique=True)
    ip4addr = models.GenericIPAddressField()
    sysName = models.CharField(max_length=255)
    sysDescr = models.CharField(max_length=255)
    sysLocation = models.CharField(max_length=255)
    tier = models.CharField(max_length=255)
    building_name = models.CharField(max_length=255)
    hierarcy = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['name']
        indexes = [ models.Index(fields=['ip4addr'])]

    def __str__(self):
        return str(self.name)

class Unreachable(models.Model):
    # Unresponsive devices from akips
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    child = models.CharField(max_length=255)
    attribute = models.CharField(max_length=255)
    index = models.CharField(max_length=255)    # extracted from value
    state = models.CharField(max_length=255)    # extracted from value
    device_added = models.DateTimeField()       # extracted from value
    event_start = models.DateTimeField()        # extracted from value
    ip4addr = models.GenericIPAddressField()    # extracted from value
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['ip4addr']

    def __str__(self):
        return str(self.device)

class Summary(models.Model):
    TYPE_CHOICES = (
        ('Distribution', 'Distribution'),
        ('Building', 'Building')
    )
    STATE_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=32, choices=STATE_CHOICES)
    name = models.CharField(max_length=255)
    switch_count = models.IntegerField()
    ap_count = models.IntegerField()
    ups_count = models.IntegerField()
    total_count = models.IntegerField()
    percent_down = models.DecimalField(max_digits=3,decimal_places=3)
    last_event = models.DateTimeField()
    trend = models.CharField(max_length=255)
    incident = models.CharField(max_length=255,Blank=True)

    def __str__(self):
        return str(self.type)


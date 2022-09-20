from django.db import models

# Create your models here.

class Device(models.Model):
    # devices from akips
    name = models.CharField(max_length=255, unique=True)
    ip4addr = models.GenericIPAddressField()
    sysName = models.CharField(max_length=255,blank=True)
    sysDescr = models.CharField(max_length=255,blank=True)
    sysLocation = models.CharField(max_length=255,blank=True)
    critical = models.BooleanField(default=False)
    tier = models.CharField(max_length=255,blank=True)
    building_name = models.CharField(max_length=255,blank=True)
    hierarcy = models.CharField(max_length=255,blank=True)
    type = models.CharField(max_length=255,blank=True)
    maintenance = models.BooleanField(default=False)
    last_refresh = models.DateTimeField()

    class Meta:
        ordering = ['name']
        indexes = [ models.Index(fields=['ip4addr'])]

    def __str__(self):
        return str(self.name)

class Unreachable(models.Model):
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    )
    STATE_CHOICES = (
        ('up','up'),
        ('down','down'),
        ('unreported','unreported'),
    )
    # Unreachable devices from akips
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    child = models.CharField(max_length=255)
    attribute = models.CharField(max_length=255)
    ping_state = models.CharField(max_length=32,choices=STATE_CHOICES,default='unreported')
    snmp_state = models.CharField(max_length=32,choices=STATE_CHOICES,default='unreported')
    index = models.CharField(max_length=255)    # extracted from value
    #state = models.CharField(max_length=255)    # extracted from value
    device_added = models.DateTimeField()       # extracted from value
    event_start = models.DateTimeField()        # extracted from value
    ip4addr = models.GenericIPAddressField(blank=True,null=True)    # extracted from value
    last_refresh = models.DateTimeField()
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
    name = models.CharField(max_length=255)
    ack = models.BooleanField(default=False)
    #device = models.ForeignKey(Device, blank=True, null=True, on_delete=models.CASCADE)
    unreachables = models.ManyToManyField(Unreachable)
    switch_count = models.IntegerField(default=0)
    ap_count = models.IntegerField(default=0)
    ups_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    max_count = models.IntegerField(default=0)
    percent_down = models.DecimalField(default=0,max_digits=4,decimal_places=3)
    first_event = models.DateTimeField()
    trend = models.CharField(default='New',max_length=255)
    incident = models.CharField(blank=True,max_length=255)
    last_event = models.DateTimeField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)

    class Meta:
        ordering = ['type', 'name', 'first_event']

    def __str__(self):
        return str(self.name)

class WebhookMessage(models.Model):
    message = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    #updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.id
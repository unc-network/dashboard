from django.contrib import admin
from akips.models import Device,Unresponsive,Summary

# Register your models here.

# Register your models here.
@admin.register(Device)
class AKIPS_deviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip4addr', 'tier', 'building_name', 'type', 'sysName', 'last_refresh')
    list_filter = ['tier','building_name', 'type']
    search_fields = ['name', 'sysName','ip4addr']

@admin.register(Unresponsive)
class AKIPS_unresponsiveAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip4addr', 'device_added', 'event_start', 'last_refresh')
    list_filter = ['last_refresh']
    search_fields = ['name', 'ip4addr']

@admin.register(Summary)
class AKIPS_summary(admin.ModelAdmin):
    list_display = ('type', 'name', 'status')
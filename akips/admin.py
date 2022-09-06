from django.contrib import admin
from akips.models import Device,Unreachable,Summary

# Register your models here.

# Register your models here.
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip4addr', 'tier', 'building_name', 'type', 'sysName', 'last_refresh')
    list_filter = ['type', 'hierarcy', 'tier','building_name']
    search_fields = ['name', 'sysName','ip4addr']

@admin.register(Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ('device', 'ip4addr', 'device_added', 'event_start', 'last_refresh')
    list_filter = ['last_refresh']
    search_fields = ['ip4addr']

@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ('type', 'name', 'switch_count', 'ap_count', 'ups_count', 'status', 'first_event', 'last_event')
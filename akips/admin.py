from django.contrib import admin
from akips.models import Device, SNMPTrap, Unreachable, Summary

# Register your models here.

# Register your models here.
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip4addr', 'tier', 'building_name', 'type', 'sysName', 'last_refresh']
    list_filter = ['critical', 'maintenance', 'type', 'tier', 'building_name']
    search_fields = ['name', 'sysName','ip4addr']

@admin.register(Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ['device', 'ping_state', 'snmp_state', 'event_start', 'last_refresh', 'status']
    list_filter = ['status', 'last_refresh']
    search_fields = ['ip4addr']

@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'total_count', 'max_count', 'status', 'first_event', 'last_event']
    list_filter = ['status', 'type']
    search_fields = ['name']

@admin.register(SNMPTrap)
class SNMPTrapAdmin(admin.ModelAdmin):
    list_display = ['trap_oid', 'device', 'ipaddr', 'tt']
    list_filter = ['trap_oid']
    search_fields = ['trap_oid', 'ipaddr']
from django.contrib import admin
from . import models

# Register your models here.


@admin.register(models.Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'sysName', 'ip4addr', 'group', 'type', 'last_refresh']
    list_filter = ['group', 'critical', 'maintenance', 'type', 'tier', 'building_name']
    search_fields = ['name', 'sysName', 'ip4addr']

@admin.register(models.Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'ping_state', 'snmp_state', 'event_start', 'last_refresh', 'status']
    list_filter = ['status', 'last_refresh']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(models.Trap)
class TrapAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'trap_oid', 'ipaddr', 'tt', 'status']
    list_filter = ['status', 'trap_oid']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr', 'trap_oid', 'ipaddr']
    autocomplete_fields = ['device']

@admin.register(models.Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'child', 'attribute', 'value', 'last_change']
    list_filter = ['child', 'attribute']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(models.Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'type', 'total_count', 'status', 'first_event', 'last_event', 'last_refresh']
    list_filter = ['type', 'status']
    search_fields = ['name']
    autocomplete_fields = ['unreachables']

@admin.register(models.HibernateRequest)
class HibernateRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'type', 'scheduled', 'executed', 'status']
    list_filter = ['type', 'status']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(models.ServiceNowIncident)
class ServiceNowIncidentAdmin(admin.ModelAdmin):
    list_display = ['number', 'sys_id', 'active']

@admin.register(models.Profile)
class ProfieleAdmin(admin.ModelAdmin):
    list_display = ['user', 'voice_enabled']

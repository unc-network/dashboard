from django.contrib import admin
from akips.models import Device, Trap, Unreachable, Summary, Profile, Status, HibernateRequest

# Register your models here.


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'sysName', 'ip4addr', 'group', 'type', 'last_refresh']
    list_filter = ['group', 'critical', 'maintenance', 'type', 'tier', 'building_name']
    search_fields = ['name', 'sysName', 'ip4addr']

@admin.register(Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'ping_state', 'snmp_state', 'event_start', 'last_refresh', 'status']
    list_filter = ['status', 'last_refresh']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(Trap)
class TrapAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'trap_oid', 'ipaddr', 'tt', 'status']
    list_filter = ['status', 'trap_oid']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr', 'trap_oid', 'ipaddr']
    autocomplete_fields = ['device']

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'child', 'attribute', 'value', 'last_change']
    list_filter = ['attribute', 'value']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'type', 'total_count', 'status', 'first_event', 'last_event', 'last_refresh']
    list_filter = ['type', 'status']
    search_fields = ['name']
    autocomplete_fields = ['unreachables']

@admin.register(HibernateRequest)
class HibernateRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'device', 'type', 'scheduled', 'executed', 'status']
    list_filter = ['type', 'status']
    search_fields = ['device__name', 'device__sysName', 'device__ip4addr']
    autocomplete_fields = ['device']

@admin.register(Profile)
class ProfieleAdmin(admin.ModelAdmin):
    list_display = ['user', 'voice_enabled']

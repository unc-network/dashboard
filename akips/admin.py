from django.contrib import admin
from akips.models import Device, SNMPTrap, Unreachable, Summary, Profile, Status, HibernateRequest

# Register your models here.


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip4addr', 'sysName', 'group', 'type', 'last_refresh']
    list_filter = ['group', 'critical', 'maintenance', 'type', 'tier', 'building_name']
    search_fields = ['name', 'sysName', 'ip4addr']

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['device', 'child', 'attribute', 'value', 'last_change']
    list_filter = ['attribute', 'value']


@admin.register(HibernateRequest)
class HibernateRequestAdmin(admin.ModelAdmin):
    list_display = ['device', 'type', 'comment']

@admin.register(Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ['id','device', 'ping_state', 'snmp_state', 'event_start', 'last_refresh', 'status']
    list_filter = ['status', 'last_refresh']
    search_fields = ['id', 'ip4addr']


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'total_count', 'max_count', 'status', 'first_event', 'last_event']
    list_filter = ['status', 'type']
    search_fields = ['name']


@admin.register(SNMPTrap)
class SNMPTrapAdmin(admin.ModelAdmin):
    list_display = ['trap_oid', 'device', 'ipaddr', 'tt', 'status']
    list_filter = ['status', 'trap_oid']
    search_fields = ['trap_oid', 'ipaddr']


@admin.register(Profile)
class ProfieleAdmin(admin.ModelAdmin):
    list_display = ['user', 'voice_enabled']

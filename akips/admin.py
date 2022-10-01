from django.contrib import admin
from akips.models import Device, SNMPTrap, Unreachable, Summary, UserAlert, Profile, Status, StatusAlert

# Register your models here.


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip4addr', 'tier',
                    'building_name', 'type', 'sysName', 'last_refresh']
    list_filter = ['critical', 'maintenance', 'type', 'tier', 'building_name']
    search_fields = ['name', 'sysName', 'ip4addr']

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['device', 'object', 'value', 'last_change']
    list_filter = ['object', 'value']
    #search_fields = ['device']

@admin.register(StatusAlert)
class StatusAlertAdmin(admin.ModelAdmin):
    list_display = ['device', 'attr']

@admin.register(Unreachable)
class UnreachableAdmin(admin.ModelAdmin):
    list_display = ['id','device', 'ping_state', 'snmp_state',
                    'event_start', 'last_refresh', 'status']
    list_filter = ['status', 'last_refresh']
    search_fields = ['id', 'ip4addr']


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'total_count',
                    'max_count', 'status', 'first_event', 'last_event']
    list_filter = ['status', 'type']
    search_fields = ['name']


@admin.register(SNMPTrap)
class SNMPTrapAdmin(admin.ModelAdmin):
    list_display = ['tt', 'trap_oid', 'device', 'ipaddr', 'status']
    list_filter = ['status', 'trap_oid']
    search_fields = ['trap_oid', 'ipaddr']


@admin.register(UserAlert)
class UserAlertAdmin(admin.ModelAdmin):
    list_display = ['message', 'created_at']


@admin.register(Profile)
class ProfieleAdmin(admin.ModelAdmin):
    list_display = ['user', 'voice_enabled']

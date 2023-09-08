# AKIPS Setup

Requires configuration

## Site Scripts

Menu: Admin -> API -> Site Scripting

Copy paste into the site script

## Status Alert

Menu: Admin -> Alerting -> Status Alerts

```
# OCNES Alerts
* * ping4 PING.icmpState = call custom_post_status_to_dashboard
* * sys SNMP.snmpState = call custom_post_status_to_dashboard
wait 5m * * ups UPS-MIB.upsOutputSource = call custom_post_status_to_dashboard
* * battery LIEBERT-GP-POWER-MIB.lgpPwrBatteryTestResult = call custom_post_status_to_dashboard
```

## Trap Alert

Menu: Admin -> Alerting -> Trap Alerts

```
# Send all alerts to dashboard
/.*/ = call custom_post_trap_to_dashboard
```
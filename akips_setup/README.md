AKIPS Setup
===

AKIPS is the engine that drives OCNES, so setup is required for them to interoperate.

## AKIPS API Accounts

API access to AKIPS works through either a read-only user account and a read-write user account.
You will need to follow the documenation and enabled the local accounts via **User Settings**.
For purposes of OCNES, the api-rw account is needed since some functions require extra access.

1. api-ro
2. api-rw

## Site Scripts

Menu: Admin -> API -> Site Scripting

![AKIPS Site Scripting configuration page](akips_site_scripting.png)

Copy paste the contents of the [akips_site_scripting.pl](site_scripting.pl) file into the site script.

You will need to set two values based on your enviornment.
1. hostname of your OCNES instance
2. token value to use with POST.

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
# Changelog

All notable changes to OCNES will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries before 2.1.1 were reconstructed from Git tags and commit history.

## [2.1.1] - 2026-09-15

### Fixed

- Handle webhook events from an IP address assigned to multiple device records without raising an internal server error.
- Log the webhook source and matching device details when an IP address is ambiguous.

## [2.1.0] - 2026-04-14

### Added

- Add progressive web app support, offline handling, and installable application icons.
- Add mobile and compact dashboard layouts.
- Add a "Remember me" login option.

### Changed

- Refine navigation, themes, notification icons, and recent-user displays.
- Use sliding activity-based session expiration with clearer login redirects.

## [2.0.1] - 2026-04-08

### Fixed

- Correct device grouping logic and refine the grouping-problems report.

## [2.0.0] - 2026-04-08

### Added

- Add HUD and simulation modes for operations-center displays.
- Add scoped API-key authentication for read-only device, unreachable, and summary exports.
- Add snapshot import and export with size limits and API-key exclusions.
- Add an administrative settings interface for AKiPS, inventory, and TeamDynamix integrations.
- Add a device grouping-problems report and additional operational status information.

### Changed

- Move dashboard card caching to Redis and optimize summary and unreachable processing.
- Refresh the dashboard UI, responsive styling, charts, cards, and dark-theme behavior.
- Improve database, cookie, session-tracking, and background-task locking behavior.

## [1.0.3] - 2025-06-25

### Added

- Add device notification controls backed by AKiPS groups.
- Add TeamDynamix ticket creation, association, and update support.
- Add the School of Medicine ticket assignment group.

### Changed

- Improve UPS status checks, trap handling and sorting, maintenance filtering, and unreachable cleanup.
- Update the GitLab build pipeline and container image tooling.

## [1.0.2] - 2024-08-23

### Added

- Add environment configuration examples and an optional external inventory feed.
- Include inventory URLs and synchronization timestamps in device exports.
- Add a hibernating-device display.

### Changed

- Upgrade to Django 4.2 and update WhiteNoise, AdminLTE, and LDAP configuration.
- Increase the supported SNMP trap OID payload length.

## [1.0.1] - 2024-01-04

### Added

- Add the project license and contribution guide.

### Changed

- Expand Docker documentation and add Celery worker autoscaling configuration.

## [1.0.0] - 2023-11-08

### Added

- Initial OCNES release with AKiPS device synchronization, network event summaries, unreachable-device tracking, and SNMP trap handling.
- Add dashboard cards, charts, recent-event views, device details, acknowledgements, comments, alerts, and user preferences.
- Add LDAP authentication, ServiceNow incident integration, maintenance and hibernation workflows, and scheduled Celery tasks.
- Add Docker, OpenShift, PostgreSQL, Redis, Gunicorn, and static-file deployment support.

[2.1.1]: https://github.com/unc-network/dashboard/compare/2e09b8b...v2.1.1
[2.1.0]: https://github.com/unc-network/dashboard/compare/v2.0.1...2e09b8b
[2.0.1]: https://github.com/unc-network/dashboard/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/unc-network/dashboard/compare/v1.0.3...v2.0.0
[1.0.3]: https://github.com/unc-network/dashboard/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/unc-network/dashboard/compare/1.0.1...v1.0.2
[1.0.1]: https://github.com/unc-network/dashboard/compare/1.0.0...1.0.1
[1.0.0]: https://github.com/unc-network/dashboard/releases/tag/1.0.0

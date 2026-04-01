# OCNES

Operations Center Network Event Summary (OCNES) provides a dashboard view of network health. It is built on top of the [AKiPS Network Monitoring Software](http://akips.com) network monitoring platform, which provides all polling and status data.

![Screenshot of OCNES UI](akips/static/akips/img/dashboard.png "OCNES UI")

## Why?

The AKiPS platform is a powerful tool on its own.  OCNES was developed using the AKiPS API to provide a view summarized for network and device topologies.

## Install

Setup is needed inside AKiPS.  Refer to [Setup Readme](akips_setup/README.md).

## Running

This project was initially designed to run under OpenShift.

It also runs under Docker, refer to [Docker Readme](Docker.md).

Most recently work has been to build a K3s setup..

## Dashboard and HUD Mode

OCNES has two primary viewing modes:

- Dashboard mode: the standard interactive operations view.
- HUD mode: a wall-display oriented view for operations center monitors.

### Dashboard Mode

Open the main dashboard at the app root:

- /

You can also enable HUD styling from the dashboard route with query parameters:

- /?hud=1

### HUD Mode

Open the dedicated HUD route:

- /hud/

HUD mode is optimized for large displays and can be tuned with URL query options.

### HUD Query Options

- scale: controls HUD text scaling.
	- Default on /hud/: 1.9
	- Allowed range: 1.0 to 1.9
	- Example: /hud/?scale=1.9
- simulate: enables simulated card data for testing and demo workflows.
	- Use simulate=1 to enable simulation mode.
	- Effective only for staff users.
	- In simulate mode, acknowledgement and clear actions are disabled.
	- Example: /hud/?simulate=1

You can combine options:

- /hud/?scale=1.9&simulate=1

## Contributing

Contributions are welcome.  The project has been in-house for a while but we recently published the repository to facilitate collaboration with other higher education institutions utilizing AKiPS.  

[CONTRIBUTING.md](https://github.com/unc-network/dashboard/blob/develop/CONTRIBUTING.md)

---
UNC Chapel Hill
ITS Networking
https://github.com/unc-network
https://sc.its.unc.edu/network (campus only)

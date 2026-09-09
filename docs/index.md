# ckanext-cwbi-harvesters

ckanext-cwbi-harvesters is a CKAN extension focused on harvesting.

The package exposes the base CKAN plugin `cwbi_harvesters` and concrete harvest source plugins that delegate to local strategy classes under `ckanext.cwbi_harvesters.harvesters`.

Current built-in strategies:

* `cwbi_esri`: harvests datasets from ArcGIS REST sources.
* `cwbi_esri_rest`: harvests datasets from ArcGIS REST Services directories.

This fork intentionally ships a small runtime surface. The old DCAT endpoints, profile system, structured data helpers, and Croissant features are not part of the packaged extension anymore.

See:

* [Getting started](getting-started.md) for installation and configuration.
* [Harvester](harvester.md) for strategy selection and extension points.
* [Contributing](contributing.md) for repository conventions.

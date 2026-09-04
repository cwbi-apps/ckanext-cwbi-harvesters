## Base harvester

This extension exposes the base runtime plugin, `cwbi_harvesters`, and concrete source plugins that delegate to strategy implementations.

Enable harvesting with:

    ckan.plugins = ... harvest cwbi_harvesters cwbi_esri_rest

Select the built-in ArcGIS strategy in the harvest source configuration:

    {"harvester":"cwbi_esri"}

Select the ArcGIS REST Services directory strategy with:

    {"harvester":"cwbi_esri_rest"}

The strategy uses ckanext-harvest's persisted object report statuses. In the
completed CKAN job report, `added` is created, `updated` is updated, `not
modified` is skipped, and `errored` is failed; their sum is discovered.
For this source type, `harvest_job_show` and the `last_job` object returned by
`harvest_source_show_status` also include the mapped report under
`arcgis_rest_report`.


### Extending strategies

Custom strategies are added directly in this package.

1. Create a strategy class in `ckanext/cwbi_harvesters/harvesters/`.
2. Register the alias in `LOCAL_HARVESTERS` at `ckanext/cwbi_harvesters/harvesters/registry.py` (for example `cwbi_esri`, `cwbi_esri_rest`, `cwbi_rest`).
3. Implement the lifecycle methods you need: `validate_config`, `gather_stage`, `fetch_stage`, and `import_stage`.
4. Select the alias in the source config.

Example source config:

    {"harvester":"my_strategy"}

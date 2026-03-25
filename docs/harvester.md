## Base harvester

This extension exposes a single runtime plugin, `cwbi_harvesters`, which delegates to strategy implementations.

Enable harvesting with:

    ckan.plugins = ... harvest cwbi_harvesters

Select the built-in ArcGIS strategy in the harvest source configuration:

    {"harvester":"cwbi_esri"}


### Extending strategies

Custom strategies are added directly in this package.

1. Create a strategy class in `ckanext/cwbi_harvesters/harvesters/`.
2. Register the alias in `LOCAL_HARVESTERS` at `ckanext/cwbi_harvesters/harvesters/registry.py` (for example `cwbi_esri`, `cwbi_rest`).
3. Implement the lifecycle methods you need: `validate_config`, `gather_stage`, `fetch_stage`, and `import_stage`.
4. Select the alias in the source config.

Example source config:

    {"harvester":"my_strategy"}

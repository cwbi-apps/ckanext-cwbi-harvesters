import importlib
import json

DEFAULT_HARVESTER_ALIAS = "cwbi_esri"

# Add local aliases here as new strategy classes are introduced.
# Example:
# "example": "ckanext.cwbi_harvesters.harvesters.example:ExampleHarvesterStrategy",
LOCAL_HARVESTERS = {
    "cwbi_esri": "ckanext.cwbi_harvesters.harvesters.arcgis:ArcGISHarvesterStrategy",
}


def _load_object(import_path):
    module_name, object_name = import_path.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, object_name)


def available_harvesters():
    return dict(LOCAL_HARVESTERS)


def describe_harvesters():
    descriptions = []

    for alias in sorted(available_harvesters()):
        harvester_class = resolve_harvester_class(alias)
        descriptions.append(
            {
                "alias": alias,
                "class_name": harvester_class.__name__,
                "display_name": getattr(harvester_class, "DISPLAY_NAME", alias),
                "summary": getattr(harvester_class, "SUMMARY", ""),
                "config_schema": getattr(harvester_class, "CONFIG_SCHEMA", []),
            }
        )

    return descriptions


def resolve_harvester_class(alias):
    alias = alias or DEFAULT_HARVESTER_ALIAS

    if ":" in alias:
        return _load_object(alias)

    harvesters = available_harvesters()
    if alias not in harvesters:
        known = ", ".join(sorted(harvesters.keys()))
        raise ValueError(
            "Unknown harvester '{0}'. Available harvesters: {1}".format(alias, known)
        )

    target = harvesters[alias]
    if isinstance(target, str):
        return _load_object(target)
    return target


def get_harvester_alias(source_config):
    if not source_config:
        return DEFAULT_HARVESTER_ALIAS

    config_obj = json.loads(source_config)
    return (
        config_obj.get("harvester")
        or config_obj.get("harvester_type")
        or DEFAULT_HARVESTER_ALIAS
    )

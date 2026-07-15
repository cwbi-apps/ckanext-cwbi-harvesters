import json
import re
from urllib.parse import urlparse


CKAN_NAME_MAX_LENGTH = 100
CKAN_TAG_MAX_LENGTH = 100


def to_array(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def string_value(value):
    if value is None:
        return ""
    return str(value).strip()


def sanitize_package_name(value):
    raw = string_value(value).lower()
    name = re.sub(r"[^a-z0-9_-]+", "-", raw)
    name = re.sub(r"-+", "-", name)
    name = re.sub(r"^[-_]+|[-_]+$", "", name)

    if len(name) < 2:
        name = "dcat-{}".format(name or "record")

    name = re.sub(r"^[-_]+|[-_]+$", "", name[:CKAN_NAME_MAX_LENGTH])
    return name if len(name) >= 2 else "dcat-record"


def sanitize_tag(value):
    tag = string_value(value).lower()
    if not tag:
        return None

    tag = re.sub(r"[^a-z0-9 ._-]+", " ", tag)
    tag = re.sub(r"\s+", " ", tag).strip()
    tag = tag[:CKAN_TAG_MAX_LENGTH].strip()
    return tag if len(tag) >= 2 else None


def normalize_url(value):
    candidate = string_value(value)
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return candidate


def extra_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return json.dumps(value) if value else None
    if isinstance(value, dict):
        return json.dumps(value) if value else None
    text = str(value)
    return text if text else None


def append_extra(extras, key, value):
    normalized = extra_value(value)
    if normalized is not None:
        extras.append({"key": key, "value": normalized})


def build_extras(record):
    extras = []
    publisher = record.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")

    theme_labels = []
    for theme in to_array(record.get("theme")):
        if isinstance(theme, dict):
            label = string_value(theme.get("prefLabel"))
        else:
            label = string_value(theme)
        if label:
            theme_labels.append(label)

    append_extra(extras, "identifier", record.get("identifier"))
    append_extra(extras, "publisher", publisher)
    append_extra(extras, "accessLevel", record.get("accessLevel"))
    append_extra(extras, "accessRights", record.get("accessRights"))
    append_extra(extras, "bureauCode", record.get("bureauCode"))
    append_extra(extras, "programCode", record.get("programCode"))
    append_extra(extras, "issued", record.get("issued"))
    append_extra(extras, "modified", record.get("modified"))
    append_extra(extras, "accrualPeriodicity", record.get("accrualPeriodicity"))
    append_extra(extras, "dcat_type", record.get("@type"))
    append_extra(extras, "theme", record.get("theme"))
    append_extra(extras, "theme_pref_labels", theme_labels)
    return extras


def build_tags(record, report):
    tags = []
    seen = set()
    identifier = string_value(record.get("identifier"))

    for keyword in to_array(record.get("keyword")):
        source = string_value(keyword)
        sanitized = sanitize_tag(keyword)

        if not sanitized:
            if source:
                report["tag_sanitization_changes"].append({
                    "identifier": identifier,
                    "source": source,
                    "sanitized": None,
                    "action": "skipped",
                })
            continue

        if source.lower() != sanitized:
            report["tag_sanitization_changes"].append({
                "identifier": identifier,
                "source": source,
                "sanitized": sanitized,
                "action": "sanitized",
            })

        if sanitized not in seen:
            seen.add(sanitized)
            tags.append({"name": sanitized})

    return tags


def build_service_endpoint_resources(record):
    urls = [url for url in (normalize_url(value) for value in to_array(record.get("endpointURL"))) if url]
    title = string_value(record.get("title")) or "Endpoint URL"
    description = string_value(record.get("description"))
    resources = []

    for index, url in enumerate(urls):
        resource = {
            "name": title if len(urls) == 1 else "{} {}".format(title, index + 1),
            "url": url,
            "format": "DCAT DataService",
        }
        if description:
            resource["description"] = description
        resources.append(resource)

    return resources



def build_dataset_distribution_resources(record):
    dataset_title = string_value(record.get("title")) or "Distribution"
    description = string_value(record.get("description"))
    resources = []

    for distribution in to_array(record.get("distribution")):
        if not isinstance(distribution, dict):
            continue
        urls = [
            url for url in (
                normalize_url(value)
                for value in to_array(distribution.get("accessURL"))
            ) if url
        ]
        title = string_value(distribution.get("title")) or dataset_title
        resource_format = string_value(distribution.get("format"))
        for index, url in enumerate(urls):
            resource = {
                "name": title if len(urls) == 1 else "{} {}".format(title, index + 1),
                "url": url,
            }
            if resource_format:
                resource["format"] = resource_format
            if description:
                resource["description"] = description
            resources.append(resource)

    return resources


def build_resources(record, kind):
    if kind == "dataset":
        return build_dataset_distribution_resources(record)
    return build_service_endpoint_resources(record)
def is_private_package(record):
    access_level = string_value(record.get("accessLevel"))
    access_rights = string_value(record.get("accessRights"))

    if access_level and access_rights:
        return not (
            access_level.lower() == "public"
            and access_rights.lower() == "public"
        )
    if access_level:
        return access_level.lower() != "public"
    return access_rights.lower() != "public"


def contact_point(record):
    contact = record.get("contactPoint")
    if not isinstance(contact, dict):
        return {}

    result = {}
    maintainer = string_value(contact.get("fn"))
    maintainer_email = re.sub(r"^mailto:", "", string_value(contact.get("hasEmail")), flags=re.IGNORECASE)
    if maintainer:
        result["maintainer"] = maintainer
    if maintainer_email:
        result["maintainer_email"] = maintainer_email
    return result


def record_label(record, kind, index):
    return (
        string_value(record.get("identifier"))
        or string_value(record.get("title"))
        or "{}-{}".format(kind, index + 1)
    )


def build_package(record, kind, index, owner_org, report):
    identifier = string_value(record.get("identifier"))
    title = string_value(record.get("title")) or identifier or "{} {}".format(kind, index + 1)
    name_base = sanitize_package_name(identifier or title or "{}-{}".format(kind, index + 1))
    resources = build_resources(record, kind)

    if not resources:
        report[
            "datasets_without_usable_distribution"
            if kind == "dataset" else "records_without_usable_url"
        ].append({
            "identifier": identifier,
            "title": title,
            "dcatType": record.get("@type") or kind,
        })

    package = {
        "name": name_base,
        "title": title,
        "notes": string_value(record.get("description")),
        "owner_org": owner_org,
        "private": is_private_package(record),
        "tags": build_tags(record, report),
        "extras": build_extras(record),
        "resources": resources,
    }
    package.update(contact_point(record))
    return {"name_base": name_base, "package": package}


def assert_unique_name(package_name, identifier, seen_names, collisions):
    previous_identifier = seen_names.get(package_name)
    if previous_identifier is None:
        seen_names[package_name] = identifier
        return

    collision = {
        "name": package_name,
        "identifier": identifier,
        "previousIdentifier": previous_identifier,
    }
    collisions.append(collision)
    raise ValueError(
        "duplicate CKAN package name {0} generated for identifiers {1} and {2}".format(
            package_name,
            previous_identifier,
            identifier,
        )
    )


def catalog_entries(catalog):
    catalog = catalog or {}
    return (
        [
            {"kind": "service", "record": record, "index": index}
            for index, record in enumerate(to_array(catalog.get("service")))
        ]
        + [
            {"kind": "dataset", "record": record, "index": index}
            for index, record in enumerate(to_array(catalog.get("dataset")))
        ]
    )


def build_summary(
    catalog,
    packages,
    accepted_record_kinds,
    skipped_records,
    records_without_usable_url,
    datasets_without_usable_distribution,
    tag_sanitization_changes,
    collisions,
):
    visibility_counts = {"shared": 0, "private": 0}
    for package in packages:
        if package.get("private"):
            visibility_counts["private"] += 1
        else:
            visibility_counts["shared"] += 1

    return {
        "source_service_record_count": len(to_array((catalog or {}).get("service"))),
        "source_dataset_record_count": len(to_array((catalog or {}).get("dataset"))),
        "accepted_service_record_count": accepted_record_kinds.count("service"),
        "accepted_dataset_record_count": accepted_record_kinds.count("dataset"),
        "package_payload_count": len(packages),
        "endpoint_resource_payload_count": sum(
            len(package.get("resources", []))
            for package, kind in zip(packages, accepted_record_kinds)
            if kind == "service"
        ),
        "distribution_resource_payload_count": sum(
            len(package.get("resources", []))
            for package, kind in zip(packages, accepted_record_kinds)
            if kind == "dataset"
        ),
        "visibility_counts": visibility_counts,
        "skipped_record_count": len(skipped_records),
        "services_without_endpoint_url_count": len(records_without_usable_url),
        "datasets_without_usable_distribution_count": len(
            datasets_without_usable_distribution
        ),
        "tag_sanitization_change_count": len(tag_sanitization_changes),
        "duplicate_package_name_collision_count": len(collisions),
    }


def transform_catalog(catalog, owner_org):
    report = {
        "packages": [],
        "skipped_records": [],
        "records_without_usable_url": [],
        "datasets_without_usable_distribution": [],
        "tag_sanitization_changes": [],
        "duplicate_package_name_collisions": [],
    }
    seen_names = {}
    accepted_record_kinds = []

    for entry in catalog_entries(catalog):
        record = entry["record"]
        if not isinstance(record, dict):
            report["skipped_records"].append({
                "kind": entry["kind"],
                "index": entry["index"],
                "reason": "record is not a JSON object",
            })
            continue

        built = build_package(record, entry["kind"], entry["index"], owner_org, report)
        identifier = record_label(record, entry["kind"], entry["index"])
        assert_unique_name(
            built["package"]["name"],
            identifier,
            seen_names,
            report["duplicate_package_name_collisions"],
        )
        report["packages"].append(built["package"])
        accepted_record_kinds.append(entry["kind"])

    report["summary"] = build_summary(
        catalog,
        report["packages"],
        accepted_record_kinds,
        report["skipped_records"],
        report["records_without_usable_url"],
        report["datasets_without_usable_distribution"],
        report["tag_sanitization_changes"],
        report["duplicate_package_name_collisions"],
    )
    return report

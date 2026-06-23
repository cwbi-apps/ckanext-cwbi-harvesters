import copy


def extra_value(package, key):
    for extra in package.get("extras", []) or []:
        if extra.get("key") == key:
            return extra.get("value", "")
    return ""


def identifier_from_package(package):
    return extra_value(package, "identifier")


def package_id_from_action_result(result, fallback=None):
    if isinstance(result, dict):
        return result.get("id") or fallback
    if isinstance(result, str):
        return result
    return fallback


def resource_key(resource):
    return str((resource or {}).get("url") or "").strip()


def escape_solr_phrase(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def apply_existing_resource_ids(payload, existing_package):
    existing_by_url = {}
    for resource in existing_package.get("resources", []) or []:
        key = resource_key(resource)
        if key:
            existing_by_url[key] = resource

    created = 0
    updated = 0
    for resource in payload.get("resources", []) or []:
        existing = existing_by_url.get(resource_key(resource))
        if existing and existing.get("id"):
            resource["id"] = existing["id"]
            updated += 1
        else:
            created += 1

    return {"created": created, "updated": updated}


def package_show_or_none(action_runner, package_name):
    return action_runner("package_show", {"id": package_name})


def search_package_by_identifier(action_runner, identifier):
    if not identifier:
        return None

    result = action_runner("package_search", {
        "fq": 'extras_identifier:"{}"'.format(escape_solr_phrase(identifier)),
        "rows": 1000,
        "include_private": True,
    })
    results = (result or {}).get("results", [])
    exact_matches = []

    for candidate in results:
        candidate_id = candidate.get("id") or candidate.get("name")
        full_package = package_show_or_none(action_runner, candidate_id) if candidate_id else None
        package = full_package or candidate
        if identifier_from_package(package) == identifier:
            exact_matches.append(package)

    if len(exact_matches) > 1:
        raise ValueError("multiple CKAN packages already preserve identifier {}".format(identifier))
    return exact_matches[0] if exact_matches else None


def find_existing_package(action_runner, payload):
    identifier = identifier_from_package(payload)
    by_identifier = search_package_by_identifier(action_runner, identifier)
    by_name = package_show_or_none(action_runner, payload["name"])

    if by_identifier and by_name and by_identifier.get("id") != by_name.get("id"):
        raise ValueError(
            "CKAN package name {} and identifier {} match different packages".format(
                payload["name"],
                identifier,
            )
        )

    if by_identifier:
        return {"match": by_identifier, "matched_by": "identifier"}

    if by_name:
        existing_identifier = identifier_from_package(by_name)
        if existing_identifier and existing_identifier != identifier:
            raise ValueError(
                "CKAN package name {} already belongs to identifier {}".format(
                    payload["name"],
                    existing_identifier,
                )
            )
        return {"match": by_name, "matched_by": "name"}

    return None


def import_package(action_runner, source_payload):
    payload = copy.deepcopy(source_payload)
    existing = find_existing_package(action_runner, payload)

    if existing:
        payload["id"] = existing["match"]["id"]
        resource_counts = apply_existing_resource_ids(payload, existing["match"])
        updated_package = action_runner("package_update", payload)
        return {
            "action": "updated",
            "identifier": identifier_from_package(payload) or payload["name"],
            "package_id": package_id_from_action_result(updated_package, payload["id"]),
            "resource_created_count": resource_counts["created"],
            "resource_updated_count": resource_counts["updated"],
        }

    created_package = action_runner("package_create", payload)
    return {
        "action": "created",
        "identifier": identifier_from_package(payload) or payload["name"],
        "package_id": package_id_from_action_result(created_package, payload.get("id")),
        "resource_created_count": len(payload.get("resources", []) or []),
        "resource_updated_count": 0,
    }
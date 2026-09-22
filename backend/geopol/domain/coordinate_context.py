"""Apply the documented input CRS without inferring it from numeric ranges."""


def documented_crs(config):
    """Only an explicit supported declaration with its source confirms input CRS."""
    evidence = config.get("crs_evidence")
    return (
        config.get("crs") == "EPSG:4326" and isinstance(evidence, str) and 8 <= len(evidence.strip()) <= 500
    )


def apply_coordinate_declaration(normalized, config):
    result = dict(normalized)
    source_crs = result.get("source_crs", result.get("crs"))
    evidence = config.get("crs_evidence")
    confirmed = documented_crs(config)
    declared_crs = config.get("crs") if confirmed else None
    result["source_crs"] = source_crs
    result["crs"] = declared_crs
    result["crs_evidence"] = evidence.strip() if confirmed else None
    if source_crs and declared_crs and source_crs != declared_crs:
        for name in ("warnings", "decision_constraints"):
            result[name] = list(dict.fromkeys([*(result.get(name) or []), "CRS_CONFLICTIVO"]))
    return result

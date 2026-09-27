def overrides(options: dict[str, object]) -> dict[str, object]:
    """Merge the standard defaults with ``options``, letting extras pass through."""
    overrides = {
        key: value
        for key, value in options.items()
        if key not in {"version_property", "kind_property"}
    }
    return {
        "version_property": options.get("version_property", "version"),
        "kind_property": options.get("kind_property", "kind"),
        **overrides,
    }

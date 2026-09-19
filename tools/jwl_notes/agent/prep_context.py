"""Validate saved evidence without fetching sources or manufacturing approval."""
from urllib.parse import urlsplit


def validate_context(context):
    """Return the canonical private context shape; raise ValueError on bad input.

    A locator and evidence make a claim reviewable. They do not prove its truth
    or that an experience really belongs to the operator.
    """
    if context is None:
        return {"research": [], "experiences": []}
    if not isinstance(context, dict) or set(context) - {"research", "experiences"}:
        raise ValueError("Context must contain only research and experiences lists")
    result = {name: context.get(name, []) for name in ("research", "experiences")}
    fields = {"research": ("id", "claim", "source_url", "evidence", "kind"),
              "experiences": ("id", "text", "source")}
    for name, rows in result.items():
        if not isinstance(rows, list):
            raise ValueError(f"context.{name} must be a list")
        ids = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"context.{name} entries must be objects")
            for key in fields[name]:
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f"context.{name}.{key} must be nonempty text")
            if row["id"] in ids:
                raise ValueError(f"Duplicate context.{name} id {row['id']}")
            ids.add(row["id"])
            if name == "research":
                url = urlsplit(row["source_url"])
                if url.scheme not in {"http", "https"} or not url.hostname:
                    raise ValueError("Research source_url must be an HTTP(S) source locator")
                if row["kind"] not in {"quotation", "paraphrase", "inference"}:
                    raise ValueError("Research kind must be quotation, paraphrase, or inference")
    return result

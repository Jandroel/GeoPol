"""Territorial name index and bounded retrieval, preserving competing matches."""

import json
from collections import defaultdict
from functools import lru_cache

from rapidfuzz import fuzz, process
from sqlalchemy import select

from .catalogs import search_key
from .domain.normalization import street_parts
from .models import Feature


class ReferenceSearch:
    def __init__(self, sessions):
        self.sessions = sessions

    @lru_cache(maxsize=16)
    def names(self, catalog_id, ubigeo):
        index = defaultdict(set)
        with self.sessions() as db:
            rows = db.execute(
                select(
                    Feature.search_key,
                    Feature.payload["aliases"],
                    Feature.payload["cross_street"],
                    Feature.payload["cross_aliases"],
                    Feature.payload["urban_core"],
                    Feature.payload["urban_core_aliases"],
                ).where(
                    Feature.catalog_id == catalog_id, Feature.ubigeo == ubigeo, Feature.kind != "boundary"
                )
            )
            for name, aliases, cross, cross_aliases, nucleus, nucleus_aliases in rows:
                index[name].add(name)
                alternate = [cross, nucleus]
                for values in (aliases, cross_aliases, nucleus_aliases):
                    if isinstance(values, list):
                        alternate.extend(values)
                for alias in alternate:
                    if isinstance(alias, str) and alias:
                        index[search_key(street_parts(alias)[1] or alias)].add(name)
        return dict(index)

    @lru_cache(maxsize=64)
    def lookup(self, catalog_id, ubigeo, names, manzana_code=None, extra_kinds=()):
        if not catalog_id or not ubigeo:
            return [], False
        index = self.names(catalog_id, ubigeo)
        keys, truncated = set(), False
        for name in names:
            matches = process.extract(name, index.keys(), scorer=fuzz.ratio, score_cutoff=80, limit=65)
            truncated |= len(matches) > 64
            for alias, _, _ in matches[:64]:
                keys.update(index[alias])
        payloads, size = [], 0
        if len(keys) > 512:
            keys, truncated = set(sorted(keys)[:512]), True
        with self.sessions() as db:
            query = select(Feature.payload).where(Feature.catalog_id == catalog_id, Feature.ubigeo == ubigeo)
            applicable = (Feature.kind == "boundary") | Feature.search_key.in_(keys)
            if extra_kinds:
                applicable |= Feature.kind.in_(extra_kinds)
            if manzana_code:
                applicable |= (Feature.kind == "manzana") & (
                    Feature.payload["manzana_code"].as_string() == str(manzana_code)
                )
            query = query.where(applicable)
            rows = db.scalars(query.order_by(Feature.id).execution_options(yield_per=100))
            for payload in rows:
                size += len(json.dumps(payload, ensure_ascii=False).encode())
                if len(payloads) >= 2000 or size > 24 * 1024 * 1024:
                    truncated = True
                    break
                payloads.append(payload)
            rows.close()
        return payloads, truncated

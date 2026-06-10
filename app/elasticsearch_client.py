from __future__ import annotations

import logging

from elasticsearch import Elasticsearch

from app.config import Settings
from app.models import AskRequest, LogEntry

LOGGER = logging.getLogger(__name__)

# Error-priority terms boosted in the should clause
ERROR_LEVEL_TERMS = ["ERROR", "WARN", "WARNING"]
ERROR_MESSAGE_HINTS = [
    "error",
    "exception",
    "failed",
    "failure",
    "timeout",
    "crash",
    "backoff",
    "connection refused",
    "refused",
    "unavailable",
]

# All text fields that hold the log message payload
LOG_FIELD_CANDIDATES = ["component_message", "message", "log", "msg"]

# Fields to search when an app/service filter is provided
SERVICE_FIELD_CANDIDATES = ["component_name", "component_class"]

# Fields returned in each hit
SOURCE_FIELDS = [
    "@timestamp",
    "timestamp",
    "component_name",
    "component_log_level",
    "component_class",
    "component_message",
    "component_traceId",
    "hostname",
    "siteId",
    "tenantId",
    "userId",
]


class ElasticsearchQueryError(RuntimeError):
    pass


class ElasticsearchLogClient:
    def __init__(self, settings: Settings):
        client_kwargs: dict[str, object] = {
            "hosts": [settings.elasticsearch_url],
            "verify_certs": settings.elasticsearch_verify_certs,
            "request_timeout": settings.request_timeout_seconds,
        }
        if settings.elasticsearch_username:
            client_kwargs["basic_auth"] = (
                settings.elasticsearch_username,
                settings.elasticsearch_password or "",
            )
        if settings.elasticsearch_ca_cert_path:
            client_kwargs["ca_certs"] = settings.elasticsearch_ca_cert_path
        self._client = Elasticsearch(**client_kwargs)
        self._settings = settings

    def search_logs(self, request: AskRequest, effective_max_logs: int) -> list[LogEntry]:
        search_body = self._build_query(request, effective_max_logs)
        LOGGER.debug("Elasticsearch query: %s", search_body)
        try:
            response = self._client.search(
                index=self._settings.elasticsearch_index,
                body=search_body,
            )
        except Exception as exc:
            raise ElasticsearchQueryError(f"Failed to query Elasticsearch: {exc}") from exc

        hits = response.get("hits", {}).get("hits", [])
        return [entry for hit in hits if (entry := self._extract_log_entry(hit.get("_source", {})))]

    def _build_query(self, request: AskRequest, max_logs: int) -> dict:
        # time window is the only mandatory hard filter
        filters: list[dict] = [
            {
                "range": {
                    self._settings.timestamp_field: {
                        "gte": f"now-{request.minutes}m",
                        "lte": "now",
                    }
                }
            }
        ]

        # optional service/component filter — matches on component_name or component_class
        if request.app:
            app_should: list[dict] = []
            for field in SERVICE_FIELD_CANDIDATES:
                app_should.append({"match": {field: {"query": request.app, "operator": "or"}}})
                app_should.append({"prefix": {f"{field}.keyword": request.app.upper()}})
            filters.append({"bool": {"should": app_should, "minimum_should_match": 1}})

        # relevance: question text + error-level boost
        relevance_should: list[dict] = [
            {
                "multi_match": {
                    "query": request.question,
                    "fields": ["component_message^4", "component_name^2", "component_class"],
                    "type": "best_fields",
                    "operator": "or",
                }
            },
            # boost ERROR and WARN level entries
            {"terms": {"component_log_level.keyword": ERROR_LEVEL_TERMS, "boost": 5}},
        ]
        for hint in ERROR_MESSAGE_HINTS:
            relevance_should.append(
                {"match": {"component_message": {"query": hint, "boost": 3}}}
            )

        return {
            "size": max_logs,
            "sort": [
                # primary: error-level first, secondary: newest first
                {"_score": {"order": "desc"}},
                {self._settings.timestamp_field: {"order": "desc", "unmapped_type": "date"}},
            ],
            "query": {
                "bool": {
                    "filter": filters,
                    "should": relevance_should,
                    "minimum_should_match": 0,
                }
            },
            "_source": SOURCE_FIELDS,
        }

    def _extract_log_entry(self, source: dict) -> LogEntry | None:
        message = self._get_first_value(source, LOG_FIELD_CANDIDATES)
        if not message:
            return None
        return LogEntry(
            timestamp=source.get("@timestamp") or source.get("timestamp"),
            component_name=source.get("component_name"),
            component_log_level=source.get("component_log_level"),
            component_class=source.get("component_class"),
            hostname=source.get("hostname"),
            site_id=source.get("siteId"),
            message=message.strip(),
        )

    @staticmethod
    def _get_first_value(source: dict, fields: list[str]) -> str | None:
        for field in fields:
            value = ElasticsearchLogClient._get_source_value(source, field)
            if value:
                return str(value)
        return None

    @staticmethod
    def _get_source_value(source: dict, field: str) -> str | None:
        if field in source and source[field] is not None:
            return str(source[field])

        current: object = source
        for key in field.split("."):
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return None if current is None else str(current)

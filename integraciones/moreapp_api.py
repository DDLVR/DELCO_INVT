"""Cliente HTTP mínimo para la API v1.0 de MoreApp."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from django.conf import settings


class MoreAppApiConfigError(Exception):
    """Configuración faltante o inválida para conectar con MoreApp."""


class MoreAppApiError(Exception):
    """Error al ejecutar una llamada HTTP contra MoreApp."""


def _setting_str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _setting_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_base_url() -> str:
    raw = _setting_str("MOREAPP_API_BASE_URL", "https://api.moreapp.com/api/v1.0")
    return raw.rstrip("/")


def _redact_secrets(text: str) -> str:
    redacted = text or ""
    api_key = _setting_str("MOREAPP_API_KEY")
    webhook_secret = _setting_str("MOREAPP_WEBHOOK_SECRET")
    if api_key:
        redacted = redacted.replace(api_key, "***")
    if webhook_secret:
        redacted = redacted.replace(webhook_secret, "***")
    return redacted


def _ensure_config() -> Dict[str, str]:
    enabled = bool(getattr(settings, "MOREAPP_API_ENABLED", False))
    if not enabled:
        raise MoreAppApiConfigError(
            "MOREAPP_API_ENABLED=false. Activa la integración en variables de entorno."
        )

    api_key = _setting_str("MOREAPP_API_KEY")
    customer_id = _setting_str("MOREAPP_CUSTOMER_ID")
    if not api_key:
        raise MoreAppApiConfigError("Falta MOREAPP_API_KEY en el entorno.")
    if not customer_id:
        raise MoreAppApiConfigError("Falta MOREAPP_CUSTOMER_ID en el entorno.")

    return {"api_key": api_key, "customer_id": customer_id}


def _request_raw(
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    accept: str = "application/json, */*",
) -> tuple:
    cfg = _ensure_config()
    url = f"{_build_base_url()}/{path.lstrip('/')}"
    if query:
        encoded = parse.urlencode({k: v for k, v in query.items() if v is not None})
        if encoded:
            url = f"{url}?{encoded}"

    body: Optional[bytes] = None
    headers = {
        "Accept": accept,
        "X-Api-Key": cfg["api_key"],
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, method=method.upper(), headers=headers, data=body)
    timeout = _setting_int("MOREAPP_API_TIMEOUT_SECONDS", 20)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw_bytes = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            filename = ""
            disposition = response.headers.get("Content-Disposition") or ""
            if "filename=" in disposition:
                filename = disposition.split("filename=")[-1].strip().strip('"')
            return raw_bytes, content_type, filename
    except error.HTTPError as exc:
        response_body = ""
        try:
            response_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            response_body = ""
        raise MoreAppApiError(
            _redact_secrets(
                f"HTTP {exc.code} en MoreApp ({method.upper()} {path}): {response_body or exc.reason}"
            )
        ) from exc
    except error.URLError as exc:
        raise MoreAppApiError(_redact_secrets(f"No se pudo conectar a MoreApp: {exc.reason}")) from exc


def _request_json(
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    raw_bytes, _content_type, _filename = _request_raw(
        method, path, query=query, payload=payload
    )
    if not raw_bytes:
        return {}
    text = raw_bytes.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def get_customer_id() -> str:
    return _ensure_config()["customer_id"]


def list_forms(*, page: int = 0, query_text: str = "") -> Any:
    query: Dict[str, Any] = {"page": page}
    if query_text:
        query["query"] = query_text
    return _request_json(
        "GET",
        f"forms/customer/{get_customer_id()}/forms",
        query=query,
    )


def _forms_from_payload(raw: Any) -> List[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("elements", "content", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        if raw.get("id"):
            return [raw]
    return []


def list_all_forms(*, max_pages: int = 20, query_text: str = "") -> List[Any]:
    collected: List[Any] = []
    seen = set()
    pages = max(1, int(max_pages or 1))
    for page in range(pages):
        items = _forms_from_payload(list_forms(page=page, query_text=query_text))
        if not items:
            break
        added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            form_id = str(item.get("id") or "")
            if form_id and form_id in seen:
                continue
            if form_id:
                seen.add(form_id)
            collected.append(item)
            added += 1
        if added == 0:
            break
    return collected


def get_form(form_id: str) -> Any:
    return _request_json(
        "GET",
        f"forms/customer/{get_customer_id()}/forms/{form_id}",
    )


def list_form_versions(form_id: str, *, page: int = 0, size: int = 10, branding_id: str = "") -> Any:
    query: Dict[str, Any] = {"page": page, "size": size}
    if branding_id:
        query["brandingId"] = branding_id
    return _request_json(
        "GET",
        f"forms/customer/{get_customer_id()}/forms/{form_id}/versions",
        query=query,
    )


def get_form_version(form_id: str, form_version_id: str, *, branding_id: str = "") -> Any:
    query: Dict[str, Any] = {}
    if branding_id:
        query["brandingId"] = branding_id
    return _request_json(
        "GET",
        f"forms/customer/{get_customer_id()}/forms/{form_id}/versions/{form_version_id}",
        query=query,
    )


def list_datasources() -> Any:
    return _request_json("GET", f"customers/{get_customer_id()}/datasources")


def get_datasource(datasource_id: str) -> Any:
    return _request_json(
        "GET",
        f"customers/{get_customer_id()}/datasources/{datasource_id}",
    )


def get_datasource_entries(datasource_id: str) -> Any:
    return _request_json(
        "POST",
        f"customers/{get_customer_id()}/datasources/{datasource_id}/entries",
        payload={},
    )


def get_datasource_entry(datasource_id: str, entry_id: str) -> Any:
    safe_entry = parse.quote(str(entry_id or "").strip(), safe="")
    if not safe_entry:
        raise MoreAppApiConfigError("entryId inválido.")
    return _request_json(
        "GET",
        f"customers/{get_customer_id()}/datasources/{datasource_id}/entries/{safe_entry}",
    )


_MAX_DATASOURCE_ROWS = 250


def list_datasource_entry_rows(
    datasource_id: str,
    *,
    limit: int = _MAX_DATASOURCE_ROWS,
) -> Dict[str, Any]:
    """Lee filas vivas de MoreApp. POST /entries solo trae el conteo; el contenido va por GET /entries/{id}."""
    meta = get_datasource_entries(datasource_id)
    columns: List[Any] = []
    total = 0
    if isinstance(meta, dict):
        columns = meta.get("dataKeyList") or []
        try:
            total = int(meta.get("numberOfEntries") or 0)
        except (TypeError, ValueError):
            total = 0
    cap = max(0, min(int(limit or 0), _MAX_DATASOURCE_ROWS))
    to_fetch = min(total, cap) if total > 0 else 0

    def _row_at(index: int) -> Optional[Dict[str, Any]]:
        try:
            payload = get_datasource_entry(datasource_id, str(index))
        except (MoreAppApiError, MoreAppApiConfigError):
            return None
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return None

    rows: List[Dict[str, Any]] = []
    if to_fetch:
        workers = 8 if to_fetch > 8 else 1
        ordered: List[Optional[Dict[str, Any]]] = [None] * to_fetch
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_row_at, index): index - 1 for index in range(1, to_fetch + 1)}
            for future in as_completed(futures):
                ordered[futures[future]] = future.result()
        rows = [item for item in ordered if isinstance(item, dict)]

    return {
        "total": total,
        "columns": columns if isinstance(columns, list) else [],
        "rows": rows,
        "fetched": len(rows),
        "truncated": bool(total > len(rows)),
        "limit": cap,
    }


def list_submissions(form_id: str, page: int = 0, payload: Optional[Dict[str, Any]] = None) -> Any:
    body = payload if isinstance(payload, dict) else {}
    return _request_json(
        "POST",
        f"customers/{get_customer_id()}/forms/{form_id}/submissions/filter/{int(page)}",
        payload=body,
    )


def get_latest_submission(form_id: str) -> Any:
    return list_submissions(
        form_id,
        page=0,
        payload={
            "pageSize": 1,
            "sort": [{"key": "info.date", "direction": -1}],
        },
    )


def get_submission(submission_id: str) -> Any:
    return _request_json(
        "GET",
        f"customers/{get_customer_id()}/submissions/{submission_id}",
    )


def download_registration_file(file_id: str) -> Dict[str, Any]:
    raw_bytes, content_type, filename = _request_raw(
        "GET",
        f"customers/{get_customer_id()}/registrationFile/{file_id}/download",
        accept="*/*",
    )
    return {
        "content": raw_bytes,
        "content_type": content_type or "application/octet-stream",
        "filename": filename or file_id,
    }


def list_users() -> Any:
    return _request_json("GET", f"customers/{get_customer_id()}/users")


def get_user(user_id: str) -> Any:
    return _request_json("GET", f"customers/{get_customer_id()}/users/{user_id}")


def list_exportable_fields(form_id: str) -> Any:
    return _request_json(
        "GET",
        f"customers/{get_customer_id()}/forms/{form_id}/submissions/export/fields",
    )


def test_connection() -> Dict[str, Any]:
    forms = list_forms(page=0)
    if isinstance(forms, list):
        total = len(forms)
    elif isinstance(forms, dict) and isinstance(forms.get("elements"), list):
        total = len(forms["elements"])
    else:
        total = 0
    return {
        "ok": True,
        "base_url": _build_base_url(),
        "customer_id": _setting_str("MOREAPP_CUSTOMER_ID"),
        "forms_detected_in_first_call": total,
    }

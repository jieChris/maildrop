from dataclasses import dataclass
from typing import Any

import httpx


class SpaceshipDnsError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceshipDnsRecord:
    name: str
    domain: str


class SpaceshipDnsSyncClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        domain: str,
        base_url: str = "https://spaceship.dev/api/v1",
        page_size: int = 100,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.domain = domain.strip().lower().rstrip(".")
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.transport = transport

    def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        skip = 0
        total: int | None = None
        while total is None or skip < total:
            page_records, total = self._fetch_record_page(skip)
            records.extend(page_records)
            if not page_records:
                break
            skip += len(page_records)
        return records

    def openai_verification_subdomains(
        self,
        *,
        parent_domain: str,
        txt_prefix: str,
    ) -> list[SpaceshipDnsRecord]:
        parent = parent_domain.strip().lower().rstrip(".")
        prefix = txt_prefix.strip()
        matches: list[SpaceshipDnsRecord] = []
        seen: set[str] = set()
        for record in self.list_records():
            if self._record_type(record) != "TXT":
                continue
            value = self._record_value(record).strip().strip('"')
            if not value.startswith(prefix):
                continue
            name = self._record_name(record)
            full_domain = self._record_domain(name, parent)
            if full_domain is None or full_domain in seen:
                continue
            seen.add(full_domain)
            matches.append(SpaceshipDnsRecord(name=name, domain=full_domain))
        return matches

    def _fetch_record_page(self, skip: int) -> tuple[list[dict[str, Any]], int]:
        headers = {
            "X-API-Key": self.api_key,
            "X-API-Secret": self.api_secret,
        }
        params = {"take": str(self.page_size), "skip": str(skip)}
        url = f"{self.base_url}/dns/records/{self.domain}"
        try:
            with httpx.Client(transport=self.transport, timeout=20.0) as client:
                response = client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise SpaceshipDnsError(f"Spaceship DNS request failed: {exc}") from exc
        if response.status_code >= 400:
            raise SpaceshipDnsError(
                f"Spaceship DNS request failed with HTTP {response.status_code}"
            )
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], len(payload)
        if not isinstance(payload, dict):
            raise SpaceshipDnsError("Spaceship DNS response is not an object")
        items = payload.get("items") or payload.get("records") or payload.get("data") or []
        if not isinstance(items, list):
            raise SpaceshipDnsError("Spaceship DNS records are not a list")
        total = payload.get("total") or payload.get("totalCount") or payload.get("count")
        if not isinstance(total, int):
            total = skip + len(items)
        return [item for item in items if isinstance(item, dict)], total

    @staticmethod
    def _record_type(record: dict[str, Any]) -> str:
        value = record.get("type") or record.get("recordType")
        return str(value or "").strip().upper()

    @staticmethod
    def _record_name(record: dict[str, Any]) -> str:
        value = record.get("name") or record.get("host") or record.get("hostname")
        return str(value or "").strip().lower().rstrip(".")

    @staticmethod
    def _record_value(record: dict[str, Any]) -> str:
        for key in ("value", "content", "address", "data", "txt", "target"):
            value = record.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return " ".join(str(item) for item in value)
        return ""

    def _record_domain(self, name: str, parent_domain: str) -> str | None:
        clean = name.strip().lower().rstrip(".")
        if not clean or clean == "@":
            return None
        if clean == parent_domain:
            return None
        if clean.endswith(f".{parent_domain}"):
            return clean
        candidate = f"{clean}.{self.domain}"
        if candidate.endswith(f".{parent_domain}"):
            return candidate
        return None

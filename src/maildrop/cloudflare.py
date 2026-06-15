from dataclasses import dataclass
from typing import Any

import httpx


class CloudflareDnsError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudflareDnsRecord:
    name: str
    domain: str


class CloudflareDnsSyncClient:
    def __init__(
        self,
        *,
        api_token: str,
        zone_id: str,
        zone_domain: str,
        base_url: str = "https://api.cloudflare.com/client/v4",
        page_size: int = 100,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_token = api_token.strip()
        self.zone_id = zone_id.strip()
        self.zone_domain = zone_domain.strip().lower().rstrip(".")
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.transport = transport

    def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        total_pages: int | None = None
        while total_pages is None or page <= total_pages:
            page_records, total_pages = self._fetch_record_page(page)
            records.extend(page_records)
            if not page_records:
                break
            page += 1
        return records

    def openai_verification_subdomains(
        self,
        *,
        parent_domain: str,
        txt_prefix: str,
    ) -> list[CloudflareDnsRecord]:
        parent = parent_domain.strip().lower().rstrip(".")
        prefix = txt_prefix.strip()
        matches: list[CloudflareDnsRecord] = []
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
            matches.append(CloudflareDnsRecord(name=name, domain=full_domain))
        return matches

    def _fetch_record_page(self, page: int) -> tuple[list[dict[str, Any]], int]:
        headers = {"Authorization": f"Bearer {self.api_token}"}
        params = {"per_page": str(self.page_size), "page": str(page)}
        url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
        try:
            with httpx.Client(transport=self.transport, timeout=20.0) as client:
                response = client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise CloudflareDnsError(f"Cloudflare DNS request failed: {exc}") from exc
        if response.status_code >= 400:
            raise CloudflareDnsError(
                f"Cloudflare DNS request failed with HTTP {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise CloudflareDnsError("Cloudflare DNS response is not an object")
        if payload.get("success") is False:
            raise CloudflareDnsError("Cloudflare DNS request was not successful")
        items = payload.get("result") or []
        if not isinstance(items, list):
            raise CloudflareDnsError("Cloudflare DNS records are not a list")
        info = payload.get("result_info") or {}
        total_pages = info.get("total_pages") if isinstance(info, dict) else None
        if not isinstance(total_pages, int):
            total_pages = page
        return [item for item in items if isinstance(item, dict)], total_pages

    @staticmethod
    def _record_type(record: dict[str, Any]) -> str:
        return str(record.get("type") or "").strip().upper()

    @staticmethod
    def _record_name(record: dict[str, Any]) -> str:
        return str(record.get("name") or "").strip().lower().rstrip(".")

    @staticmethod
    def _record_value(record: dict[str, Any]) -> str:
        value = record.get("content")
        if isinstance(value, str):
            return value
        return ""

    def _record_domain(self, name: str, parent_domain: str) -> str | None:
        clean = name.strip().lower().rstrip(".")
        if not clean or clean == "@" or clean == parent_domain:
            return None
        if clean.endswith(f".{parent_domain}"):
            return clean
        candidate = f"{clean}.{self.zone_domain}"
        if candidate.endswith(f".{parent_domain}"):
            return candidate
        return None

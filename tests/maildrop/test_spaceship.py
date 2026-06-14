import httpx

from maildrop.spaceship import SpaceshipDnsError, SpaceshipDnsRecord, SpaceshipDnsSyncClient


def test_spaceship_client_extracts_openai_txt_records_under_exa_parent():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-API-Key"] == "key"
        assert request.headers["X-API-Secret"] == "secret"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "type": "TXT",
                        "name": "urxg.exa",
                        "value": "openai-domain-verification=dv-123",
                    },
                    {
                        "type": "TXT",
                        "name": "skip.exa",
                        "value": "not-openai",
                    },
                    {
                        "type": "A",
                        "name": "mail",
                        "value": "203.0.113.10",
                    },
                    {
                        "type": "TXT",
                        "name": "full.exa.aiprot.space",
                        "value": '"openai-domain-verification=dv-456"',
                    },
                ],
                "total": 4,
            },
        )

    client = SpaceshipDnsSyncClient(
        api_key="key",
        api_secret="secret",
        domain="aiprot.space",
        transport=httpx.MockTransport(handler),
    )

    result = client.openai_verification_subdomains(
        parent_domain="exa.aiprot.space",
        txt_prefix="openai-domain-verification=",
    )

    assert result == [
        SpaceshipDnsRecord(name="urxg.exa", domain="urxg.exa.aiprot.space"),
        SpaceshipDnsRecord(name="full.exa.aiprot.space", domain="full.exa.aiprot.space"),
    ]
    assert requests[0].url.path == "/api/v1/dns/records/aiprot.space"
    assert requests[0].url.params["take"] == "100"


def test_spaceship_client_supports_paginated_records():
    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params["skip"])
        if skip == 0:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "type": "TXT",
                            "name": "one.exa",
                            "value": "openai-domain-verification=dv-one",
                        }
                    ],
                    "total": 2,
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "type": "TXT",
                        "name": "two.exa",
                        "value": "openai-domain-verification=dv-two",
                    }
                ],
                "total": 2,
            },
        )

    client = SpaceshipDnsSyncClient(
        api_key="key",
        api_secret="secret",
        domain="aiprot.space",
        transport=httpx.MockTransport(handler),
        page_size=1,
    )

    result = client.openai_verification_subdomains(
        parent_domain="exa.aiprot.space",
        txt_prefix="openai-domain-verification=",
    )

    assert [item.domain for item in result] == [
        "one.exa.aiprot.space",
        "two.exa.aiprot.space",
    ]


def test_spaceship_client_raises_clear_error_for_http_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    client = SpaceshipDnsSyncClient(
        api_key="key",
        api_secret="secret",
        domain="aiprot.space",
        transport=httpx.MockTransport(handler),
    )

    try:
        client.list_records()
    except SpaceshipDnsError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("expected SpaceshipDnsError")

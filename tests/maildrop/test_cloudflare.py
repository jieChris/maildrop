import httpx

from maildrop.cloudflare import CloudflareDnsError, CloudflareDnsSyncClient, CloudflareDnsRecord


def test_cloudflare_client_extracts_openai_txt_records_under_parent():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "type": "TXT",
                        "name": "urxg.xx.xoxo.edu.kg",
                        "content": "openai-domain-verification=dv-123",
                    },
                    {
                        "type": "TXT",
                        "name": "skip.xx.xoxo.edu.kg",
                        "content": "not-openai",
                    },
                    {
                        "type": "A",
                        "name": "mail.xoxo.edu.kg",
                        "content": "203.0.113.10",
                    },
                    {
                        "type": "TXT",
                        "name": "full.exa.xoxo.edu.kg",
                        "content": '"openai-domain-verification=dv-456"',
                    },
                ],
                "result_info": {"page": 1, "total_pages": 1},
            },
        )

    client = CloudflareDnsSyncClient(
        api_token="token",
        zone_id="zone-id",
        zone_domain="xoxo.edu.kg",
        transport=httpx.MockTransport(handler),
    )

    result = client.openai_verification_subdomains(
        parent_domain="xx.xoxo.edu.kg",
        txt_prefix="openai-domain-verification=",
    )

    assert result == [
        CloudflareDnsRecord(name="urxg.xx.xoxo.edu.kg", domain="urxg.xx.xoxo.edu.kg")
    ]
    assert requests[0].url.path == "/client/v4/zones/zone-id/dns_records"
    assert requests[0].url.params["per_page"] == "100"


def test_cloudflare_client_supports_paginated_records():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [
                        {
                            "type": "TXT",
                            "name": "one.xx.xoxo.edu.kg",
                            "content": "openai-domain-verification=dv-one",
                        }
                    ],
                    "result_info": {"page": 1, "total_pages": 2},
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "type": "TXT",
                        "name": "two.xx.xoxo.edu.kg",
                        "content": "openai-domain-verification=dv-two",
                    }
                ],
                "result_info": {"page": 2, "total_pages": 2},
            },
        )

    client = CloudflareDnsSyncClient(
        api_token="token",
        zone_id="zone-id",
        zone_domain="xoxo.edu.kg",
        transport=httpx.MockTransport(handler),
        page_size=1,
    )

    result = client.openai_verification_subdomains(
        parent_domain="xx.xoxo.edu.kg",
        txt_prefix="openai-domain-verification=",
    )

    assert [item.domain for item in result] == [
        "one.xx.xoxo.edu.kg",
        "two.xx.xoxo.edu.kg",
    ]


def test_cloudflare_client_raises_clear_error_for_http_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"success": False, "errors": [{"message": "forbidden"}]})

    client = CloudflareDnsSyncClient(
        api_token="token",
        zone_id="zone-id",
        zone_domain="xoxo.edu.kg",
        transport=httpx.MockTransport(handler),
    )

    try:
        client.list_records()
    except CloudflareDnsError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("expected CloudflareDnsError")

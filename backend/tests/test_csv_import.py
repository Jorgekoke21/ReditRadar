import io


async def test_csv_import_parses_rows_reports_errors_and_dedupes(client, auth_headers):
    csv_content = (
        "url,subreddit,title,body,num_comments,language\n"
        ",agency,Necesitamos CRM barato para priorizar leads,somos 3 personas,2,es\n"
        ",web_design,Any tool for finding businesses with outdated sites?,looking for a tool,1,en\n"
        ",,Missing required fields,should fail,0,en\n"
    )
    files = {"file": ("import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = await client.post("/api/conversations/import", files=files, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 2
    assert body["duplicates"] == 0
    assert len(body["errors"]) == 1
    assert "Fila 4" in body["errors"][0]

    # importing the exact same file again must not create duplicates
    files2 = {"file": ("import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp2 = await client.post("/api/conversations/import", files=files2, headers=auth_headers)
    body2 = resp2.json()
    assert body2["imported"] == 0
    assert body2["duplicates"] == 2

    listing = await client.get("/api/conversations", headers=auth_headers)
    assert len(listing.json()) == 2


async def test_csv_import_conversations_are_analyzed_immediately(client, auth_headers):
    csv_content = (
        "url,subreddit,title,body,num_comments,language\n"
        ",SaaS,Any tool you recommend to prioritize leads?,looking for a tool to score inbound leads,1,en\n"
    )
    files = {"file": ("import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    await client.post("/api/conversations/import", files=files, headers=auth_headers)

    listing = (await client.get("/api/conversations", headers=auth_headers)).json()
    assert len(listing) == 1
    assert listing[0]["score_total"] is not None
    assert listing[0]["state"] in ("recommended", "discarded")

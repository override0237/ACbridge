from urllib.parse import parse_qs, unquote, urlparse


def _match_for(world, customer, request_id, name):
    body = world.client.get(f"/matches/{request_id}", headers=customer.headers).json()
    return next(m for m in body["matches"] if m["full_name"] == name)


def test_matched_artisan_who_opted_in_has_a_whatsapp_link_and_icon(world):
    skill_id = world.skill("Electrical Repair")
    customer = world.user("CUSTOMER")
    john = world.artisan(skill_id, "John Fon")
    res = world.client.patch(f"/artisans/{john.artisan_id}", headers=john.headers,
                             json={"whatsapp_number": "670 123 456"})
    assert res.status_code == 200 and res.json()["whatsapp_available"] is True

    request_id = world.request(customer, skill_id, budget=10000)
    contact = _match_for(world, customer, request_id, "John Fon")["contact"]
    assert contact["channel"] == "WHATSAPP" and contact["icon"] == "whatsapp"
    assert "ACbridge" in contact["tip"]

    url = urlparse(contact["link"])
    assert (url.scheme, url.netloc, url.path) == ("https", "wa.me", "/237670123456")
    message = parse_qs(url.query)["text"][0]
    assert "John" in message and "Electrical Repair" in message and "Small Soppo, Buea" in message
    assert "10,000 FCFA" in message and request_id[:8] in message
    assert customer.phone not in contact["link"] and customer.phone.lstrip("+") not in unquote(contact["link"])


def test_artisan_who_did_not_opt_in_has_no_contact(world):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    world.artisan(skill_id, "Quiet Artisan")
    request_id = world.request(customer, skill_id)
    assert _match_for(world, customer, request_id, "Quiet Artisan")["contact"] is None


def test_inspection_request_message_mentions_inspection_not_a_budget(world):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    john = world.artisan(skill_id, "John Fon")
    world.client.patch(f"/artisans/{john.artisan_id}", headers=john.headers, json={"whatsapp_number": john.phone})
    request_id = world.request(customer, skill_id, budget=None, needs_inspection=True)
    contact = _match_for(world, customer, request_id, "John Fon")["contact"]
    assert "inspect" in unquote(contact["link"])


def test_whatsapp_number_is_never_public(world):
    skill_id = world.skill()
    john = world.artisan(skill_id)
    world.client.patch(f"/artisans/{john.artisan_id}", headers=john.headers, json={"whatsapp_number": "670999888"})
    public = str(world.client.get(f"/artisans/{john.artisan_id}").json())
    assert "670999888" not in public and "whatsapp_available': True" in public


def test_invalid_whatsapp_number_rejected(world):
    john = world.artisan(world.skill())
    res = world.client.patch(f"/artisans/{john.artisan_id}", headers=john.headers, json={"whatsapp_number": "abc"})
    assert res.status_code == 422


def test_whatsapp_link_between_parties_only_after_acceptance(world):
    skill_id = world.skill()
    customer, john = world.user("CUSTOMER"), world.artisan(skill_id, "John Fon")
    job_id = world.job(customer, john, world.request(customer, skill_id))
    assert world.client.get(f"/jobs/{job_id}", headers=customer.headers).json()["counterpart_whatsapp_link"] is None
    world.accept(job_id, john)
    for actor, other in ((customer, john), (john, customer)):
        link = world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()["counterpart_whatsapp_link"]
        assert link.startswith("https://wa.me/237")
    stranger = world.user("CUSTOMER")
    assert world.client.get(f"/jobs/{job_id}", headers=stranger.headers).status_code == 403

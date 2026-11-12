"""Job chat ("connect flexibly"): bargaining in free text; the customer's amount-with-currency sets the price."""
import pytest

from app.services.chat_service import ends_with_bare_number, mask_contacts, parse_amount


# ------------------------------------------------------------------ pure parsing
@pytest.mark.parametrize("text,expected", [
    ("9000 FCFA", 9000),
    ("9000FCFA", 9000),
    ("ok, deal at 9 000 FCFA", 9000),
    ("9.000 fcfa", 9000),
    ("9,000 F CFA", 9000),
    ("9 000 XAF", 9000),
    ("1 250 000 CFA", 1_250_000),
    ("final price 12000 FCFA.", 12000),
    ("12000 FCFA!!", 12000),
])
def test_amount_is_read_when_the_currency_is_at_the_end(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", [
    "9000",                       # no currency
    "FCFA 9000",                  # currency not at the end
    "9000 FCFA is too much, sorry",  # amount is not at the end
    "9.5 FCFA",                   # decimals are not valid francs
    "hello",
    "",
])
def test_no_amount_when_currency_is_missing_or_not_last(text):
    assert parse_amount(text) is None


def test_bare_number_is_detected_so_the_ui_can_remind_about_the_currency():
    assert ends_with_bare_number("ok 9000") is True
    assert ends_with_bare_number("ok 9000 FCFA") is False
    assert ends_with_bare_number("hello") is False


def test_phone_numbers_are_hidden_but_prices_are_not():
    assert mask_contacts("call me 670123456 ok") == "call me [number hidden] ok"
    assert mask_contacts("whatsapp +237 670 123 456 please") == "whatsapp [number hidden] please"
    assert mask_contacts("my price is 1 250 000 FCFA") == "my price is 1 250 000 FCFA"


# ------------------------------------------------------------------ API
def _job(world, price=9000):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "John Fon")
    request_id = world.request(customer, skill_id)
    return customer, artisan, world.job(customer, artisan, request_id, price=price), skill_id


def _say(world, actor, job_id, body):
    return world.client.post(f"/jobs/{job_id}/messages", headers=actor.headers, json={"body": body})


def _job_json(world, actor, job_id):
    return world.client.get(f"/jobs/{job_id}", headers=actor.headers).json()


def test_both_parties_can_talk_and_read_the_conversation_in_order(world):
    customer, artisan, job_id, _ = _job(world)
    assert _say(world, customer, job_id, "Hello, can you do it cheaper?").status_code == 201
    assert _say(world, artisan, job_id, "I can come for 8 000 FCFA, final.").status_code == 201
    for actor in (customer, artisan):
        thread = world.client.get(f"/jobs/{job_id}/messages", headers=actor.headers).json()
        assert [m["sender_role"] for m in thread] == ["CUSTOMER", "ARTISAN"]
        assert thread[0]["body"] == "Hello, can you do it cheaper?"


def test_strangers_cannot_read_or_write(world):
    customer, artisan, job_id, _ = _job(world)
    stranger = world.user("CUSTOMER")
    assert _say(world, stranger, job_id, "hi").status_code == 403
    assert world.client.get(f"/jobs/{job_id}/messages", headers=stranger.headers).status_code == 403
    assert world.client.get(f"/jobs/{job_id}/messages").status_code in (401, 403)


def test_artisan_amount_with_currency_becomes_the_proposed_price_and_shows_the_commission(world):
    customer, artisan, job_id, _ = _job(world, price=9000)
    res = _say(world, artisan, job_id, "Final price: 12 000 FCFA")
    assert res.status_code == 201
    body = res.json()
    assert body["price_status"] == "APPLIED"
    assert body["message"]["proposed_price"] == 12000
    assert body["message"]["commission_if_agreed"] == 600          # 5% of 12 000
    assert body["message"]["artisan_receives_if_agreed"] == 11400
    job = _job_json(world, customer, job_id)
    assert (job["proposed_price"], job["proposed_by"], job["agreed_price"]) == (12000, "ARTISAN", None)
    assert any(e["event_type"] == "PRICE_PROPOSED_IN_CHAT" and e["event_metadata"]["amount"] == 12000
               for e in job["events"])


def test_the_artisans_acceptance_is_still_what_agrees_the_price(world):
    customer, artisan, job_id, _ = _job(world, price=9000)
    _say(world, customer, job_id, "Could you do it for 6 000 FCFA?")      # the customer bargains...
    _say(world, artisan, job_id, "ok, my final price is 7500 FCFA")       # ...the artisan states the final price
    assert _job_json(world, customer, job_id)["proposed_price"] == 7500
    res = world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers)
    assert res.status_code == 200
    job = res.json()
    assert job["agreed_price"] == 7500 and job["artisan_agreed"] is True


def test_an_amount_typed_by_the_customer_or_without_currency_changes_nothing(world):
    customer, artisan, job_id, _ = _job(world, price=9000)
    offer = _say(world, customer, job_id, "I offer 3 000 FCFA")
    assert offer.json()["price_status"] == "NOT_ARTISAN" and offer.json()["message"]["proposed_price"] is None
    assert _say(world, artisan, job_id, "ok 5000").json()["price_status"] == "NONE"     # no currency
    assert _job_json(world, customer, job_id)["proposed_price"] == 9000


def test_out_of_range_amounts_are_rejected_but_the_message_is_kept(world):
    customer, artisan, job_id, _ = _job(world)
    assert _say(world, artisan, job_id, "100 FCFA").json()["price_status"] == "OUT_OF_RANGE"
    assert _say(world, artisan, job_id, "9 000 000 FCFA").json()["price_status"] == "OUT_OF_RANGE"
    assert _job_json(world, customer, job_id)["proposed_price"] == 9000


def test_price_is_locked_once_the_artisan_has_agreed(world):
    customer, artisan, job_id, _ = _job(world, price=9000)
    world.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers)
    res = _say(world, artisan, job_id, "actually 3000 FCFA")
    assert res.status_code == 201 and res.json()["price_status"] == "LOCKED"
    job = _job_json(world, customer, job_id)
    assert job["agreed_price"] == 9000 and job["proposed_price"] == 9000


def test_inspection_jobs_do_not_take_a_price_from_the_chat(world):
    skill_id = world.skill()
    customer = world.user("CUSTOMER")
    artisan = world.artisan(skill_id, "Inspector")
    request_id = world.request(customer, skill_id, needs_inspection=True)
    job_id = world.job(customer, artisan, request_id, price=None)
    assert _say(world, artisan, job_id, "10 000 FCFA").json()["price_status"] == "NOT_APPLICABLE"
    assert _job_json(world, customer, job_id)["proposed_price"] is None


def test_phone_numbers_in_messages_are_hidden(world):
    customer, artisan, job_id, _ = _job(world)
    body = _say(world, artisan, job_id, "call 670123456 then 8000 FCFA").json()
    assert "670123456" not in body["message"]["body"] and "[number hidden]" in body["message"]["body"]
    assert body["price_status"] == "APPLIED" and body["message"]["proposed_price"] == 8000


def test_message_length_is_validated(world):
    customer, artisan, job_id, _ = _job(world)
    assert _say(world, customer, job_id, "").status_code == 422
    assert _say(world, customer, job_id, "x" * 501).status_code == 422
    assert _say(world, customer, job_id, "x" * 500).status_code == 201


def test_chat_closes_with_the_job(world):
    customer, artisan, job_id, _ = _job(world)
    res = world.client.post(f"/jobs/{job_id}/cancel", headers=customer.headers, json={"reason": "changed my mind"})
    assert res.status_code == 200
    res = _say(world, customer, job_id, "hello?")
    assert res.status_code == 409 and "closed" in res.json()["detail"]


def test_messages_cannot_be_edited_or_deleted_even_directly_in_the_database(world, session_factory):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    customer, artisan, job_id, _ = _job(world)
    _say(world, customer, job_id, "evidence")
    with session_factory() as db:
        for statement in ("UPDATE job_messages SET body = 'edited'", "DELETE FROM job_messages"):
            with pytest.raises(DBAPIError):
                db.execute(text(statement))
            db.rollback()

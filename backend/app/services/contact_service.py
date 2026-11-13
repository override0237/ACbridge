"""WhatsApp click-to-chat links.

A https://wa.me/<number>?text=<message> link opens WhatsApp on the user's phone with a prefilled message,
so no WhatsApp Business API or extra infrastructure is needed.

Privacy rules:
  * An artisan's number is only ever used if they OPTED IN by providing `whatsapp_number`.
  * Customers receive the link only for artisans matched to THEIR request (never in public profiles).
  * The customer's number is not shared before a job is accepted; the customer reveals it to the artisan
    only by choosing to start the chat.
"""
import re
from urllib.parse import quote

WHATSAPP_SAFETY_TIP = (
    "Agree the details in WhatsApp, but make the booking and payment through ACbridge: only paid, "
    "confirmed jobs earn reviews and are protected by escrow."
)


def whatsapp_link(phone: str, message: str) -> str:
    digits = re.sub(r"\D", "", phone)  # wa.me wants the international number without '+'
    return f"https://wa.me/{digits}?text={quote(message)}"


def customer_to_artisan_message(artisan_name: str, skill_name: str, location: str, budget: int | None,
                                request_id: str, needs_inspection: bool) -> str:
    first_name = artisan_name.split()[0]
    money = ("Price to be agreed after you inspect the problem" if needs_inspection
             else f"My budget is {budget:,} FCFA" if budget is not None else "Let's discuss the price")
    return (f"Hello {first_name}, I found you on ACbridge. I need {skill_name} help in {location}. "
            f"{money}. Request ref: {request_id[:8]}. Are you available?")


def artisan_to_customer_message(artisan_name: str, job_id: str) -> str:
    return f"Hello, this is {artisan_name} from ACbridge about your job (ref {job_id[:8]})."

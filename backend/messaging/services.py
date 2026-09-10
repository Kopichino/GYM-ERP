"""Sending, receiving, and logging WhatsApp messages.

Every message in either direction lands in the log, whether or not the send
succeeded -- a failed reminder that leaves no trace is worse than one that
failed loudly, because nobody finds out until the member does.
"""

from django.utils import timezone

from .assistant import answer, member_for_phone
from .models import DeliveryStatus, Direction, Message, normalise_phone
from .whatsapp import WhatsAppError, is_configured, send_template, send_text


def log_outbound(phone, body, *, user=None, automated=False):
    return Message(
        user=user,
        phone=phone,
        direction=Direction.OUTBOUND,
        body=body,
        is_automated=automated,
    )


def send(phone, body, *, user=None, automated=False, template=None, parameters=None):
    """Sends one message and records it either way.

    `template` sends a pre-approved template instead of free text, which is what
    Meta requires outside the 24-hour window after a member's last message --
    so unprompted reminders must pass one.
    """
    message = log_outbound(phone, body, user=user or member_for_phone(phone), automated=automated)

    if not is_configured():
        message.status = DeliveryStatus.FAILED
        message.error = "WhatsApp isn't configured."
        message.save()
        return message

    try:
        if template:
            external_id = send_template(message.phone, template, parameters=parameters)
        else:
            external_id = send_text(message.phone, body)
        message.external_id = external_id
        message.status = DeliveryStatus.SENT
    except WhatsAppError as exc:
        message.status = DeliveryStatus.FAILED
        message.error = str(exc)[:300]
    message.save()
    return message


def handle_incoming(phone, text, external_id=""):
    """Logs what a member said and replies.

    Meta redelivers a webhook it thinks we didn't acknowledge, so a message we
    have already seen is recorded once and answered once -- otherwise a member
    gets the same reply three times.
    """
    digits = normalise_phone(phone)
    if external_id and Message.objects.filter(external_id=external_id).exists():
        return None

    member = member_for_phone(digits)
    Message.objects.create(
        user=member,
        phone=digits,
        direction=Direction.INBOUND,
        body=text,
        status=DeliveryStatus.RECEIVED,
        external_id=external_id,
    )

    reply = answer(text, digits)
    # A reply to a message the member just sent is inside the 24-hour window,
    # so free text is allowed here.
    return send(digits, reply, user=member, automated=True)


def send_expiry_reminders(on=None, template=None):
    """WhatsApp counterpart to the email sweep.

    Deliberately reuses the email module's idea of who is due, so the two can't
    disagree about which members are being chased, and writes to the same
    notification log so a member never gets both channels for one nudge.
    """
    from notifications.models import NotificationKind, NotificationLog
    from notifications.services import expiring_members

    on = on or timezone.localdate()
    template = template or "membership_expiring"
    sent = skipped = 0

    for member, payment, days_left in expiring_members(on):
        phone = normalise_phone(getattr(member.profile, "phone", ""))
        if not phone:
            skipped += 1
            continue

        # Same key the email sweep uses, so whichever channel goes first claims
        # the nudge and the member is contacted once.
        _, created = NotificationLog.objects.get_or_create(
            user=member,
            kind=NotificationKind.EXPIRY_SOON,
            subject_date=on,
            defaults={"to_email": member.email or "", "subject": "WhatsApp reminder"},
        )
        if not created:
            skipped += 1
            continue

        send(
            phone,
            f"Your {payment.plan.name} membership ends on {payment.period_end:%d %b} "
            f"({days_left} day{'s' if days_left != 1 else ''} left).",
            user=member,
            automated=True,
            template=template,
            parameters=[member.first_name or member.username, payment.plan.name,
                        f"{payment.period_end:%d %b}"],
        )
        sent += 1

    return sent, skipped

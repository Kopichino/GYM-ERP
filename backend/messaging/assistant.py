"""The assistant that answers members on WhatsApp.

Everything it says about a member -- when their membership ends, what they are
training today, what they owe -- is read live from the same places the app reads
them, so it can never quote a number the portal disagrees with.

The order is deliberate: recognised questions are answered from gym data with no
model in the loop at all. Only what the matcher doesn't recognise is handed to
Claude, and then only with facts already fetched for this member, so the model
is rephrasing known truths rather than being trusted to know them. With no API
key configured the fallback is an honest "here's what I can help with" instead
of a guess.
"""

import json
import re

import requests
from django.conf import settings
from django.utils import timezone

from accounts.models import MemberProfile
from billing.services import get_latest_completed_payment

from .models import normalise_phone

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT = 20

# Enough digits to identify one person without demanding that the country code
# was typed the same way in both places.
MATCH_DIGITS = 10


def member_for_phone(phone):
    """The member whose profile carries this number, or None.

    Profile numbers are stored as the desk typed them, so this compares the
    trailing digits rather than the strings. The scan is over members with a
    number on file -- small for a gym, and the alternative is a second
    normalised column that could drift from the one people edit.
    """
    digits = normalise_phone(phone)
    if len(digits) < MATCH_DIGITS:
        return None
    tail = digits[-MATCH_DIGITS:]
    for profile in MemberProfile.objects.exclude(phone="").select_related("user"):
        if normalise_phone(profile.phone).endswith(tail):
            return profile.user
    return None


def _membership_line(member):
    payment = get_latest_completed_payment(member)
    if payment is None:
        return "You don't have a plan on file yet -- pop into the front desk and we'll sort it."
    days = (payment.period_end - timezone.localdate()).days
    if days < 0:
        return (
            f"Your {payment.plan.name} membership ran out on {payment.period_end:%d %b}. "
            "You can renew from the Billing page or at the desk."
        )
    if days == 0:
        return f"Your {payment.plan.name} membership ends today."
    return (
        f"Your {payment.plan.name} membership is active until {payment.period_end:%d %b} "
        f"-- {days} day{'s' if days != 1 else ''} left."
    )


def _split_line(member):
    from workouts.models import WorkoutSplit

    split = WorkoutSplit.objects.filter(user=member, is_active=True).first()
    if split is None:
        return "You haven't set up a weekly split yet. You can build one on the My Split page."
    day = split.days.filter(weekday=timezone.localdate().weekday()).first()
    if day is None:
        return "Today's a rest day on your split."
    exercises = list(day.exercises.select_related("exercise")[:8])
    if not exercises:
        return f"Today is {day.display_label}, but you haven't added any exercises to it yet."
    listed = ", ".join(e.exercise.name for e in exercises)
    return f"Today is {day.display_label}: {listed}."


def _diet_line(member):
    from nutrition import macros
    from nutrition.models import DietPlan

    plan = DietPlan.objects.filter(user=member, is_active=True).first()
    if plan is None:
        return "You don't have a diet plan set up yet."
    day = plan.days.filter(weekday=timezone.localdate().weekday()).first()
    if day is None:
        return "Nothing is planned to eat today on your diet plan."
    totals = macros.for_day(day)
    meals = ", ".join(meal.get_meal_type_display() for meal in day.meals.all())
    return (
        f"Today's plan is about {int(totals['calories'])} kcal "
        f"({int(totals['protein_g'])}g protein): {meals}."
    )


def _classes_line(_member):
    from schedule_app.models import ClassSession

    upcoming = ClassSession.objects.filter(start_time__gte=timezone.now()).order_by(
        "start_time"
    )[:3]
    if not upcoming:
        return "There's nothing on the class schedule right now."
    lines = [
        f"{session.title} on {timezone.localtime(session.start_time):%a %d %b at %I:%M %p}"
        for session in upcoming
    ]
    return "Coming up: " + "; ".join(lines) + "."


def _referral_line(member):
    from referrals.models import ReferralProgram
    from referrals.services import ReferralError, code_for

    try:
        code = code_for(member)
    except ReferralError:
        return "Referrals aren't set up on your account -- ask at the desk."
    program = ReferralProgram.current()
    if program is None:
        return f"Your referral code is {code}. There's no reward running at the moment."
    return (
        f"Your referral code is {code}. When someone joins with it and pays, "
        f"you get {program.reward_days} free days."
    )


def _visits_line(member):
    from attendance.models import CheckInOut

    open_visit = CheckInOut.objects.filter(user=member, check_out_time__isnull=True).first()
    if open_visit:
        return (
            "You're checked in right now, since "
            f"{timezone.localtime(open_visit.check_in_time):%I:%M %p}."
        )
    last = CheckInOut.objects.filter(user=member).first()
    if last is None:
        return "We don't have any visits on record for you yet."
    return f"Your last visit was {timezone.localtime(last.check_in_time):%a %d %b}."


# Question -> answer. Ordered, first match wins, so the more specific patterns
# come first: "when does my plan expire" must not be caught by the plan-agnostic
# "class" pattern.
INTENTS = [
    (r"\b(expire|expiry|expires|renew|membership|my plan|due|valid)\b", _membership_line),
    (r"\b(split|workout|training|train today|what.*train)\b", _split_line),
    (r"\b(diet|meal|eat|food|macro|calorie)\b", _diet_line),
    (r"\b(class|schedule|timetable|session|yoga|zumba)\b", _classes_line),
    (r"\b(refer|referral|friend|invite)\b", _referral_line),
    (r"\b(check.?in|checked in|visit|attendance)\b", _visits_line),
]

HELP = (
    "Hi! I can tell you about:\n"
    "- your membership and when it expires\n"
    "- today's workout split\n"
    "- today's diet plan\n"
    "- upcoming classes\n"
    "- your referral code\n"
    "- your last visit\n"
    "Just ask in your own words."
)

STRANGER = (
    "Thanks for messaging {gym}! I couldn't find a membership against this "
    "number. If you're a member, ask the front desk to add this number to your "
    "profile. If you're thinking of joining, reply with your name and we'll "
    "call you back."
)


def _facts_for(member):
    """Everything the model is allowed to state, fetched before it is asked.

    Handing the model facts rather than database access is what keeps it from
    inventing an expiry date.
    """
    return {
        "membership": _membership_line(member),
        "today_split": _split_line(member),
        "today_diet": _diet_line(member),
        "classes": _classes_line(member),
        "referral": _referral_line(member),
        "visits": _visits_line(member),
    }


def _ask_claude(question, facts, member):
    """Rephrases the known facts into an answer, or returns None.

    Returns None -- rather than raising -- on any failure, so a model outage
    degrades to the help text instead of leaving a member with silence.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    system = (
        "You are the assistant for {gym}, a gym, replying to a member on "
        "WhatsApp. Answer ONLY from the facts given. If the facts do not cover "
        "the question, say you'll pass it to the front desk -- never guess a "
        "date, price, or timing. Keep it to two or three short sentences, "
        "friendly and plain. The member's name is {name}."
    ).format(gym=getattr(settings, "GYM_NAME", "the gym"), name=member.first_name or member.username)

    try:
        response = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": getattr(settings, "ASSISTANT_MODEL", "claude-sonnet-5"),
                "max_tokens": 300,
                "system": system,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Facts about this member:\n{json.dumps(facts, indent=2)}\n\n"
                            f"Their message: {question}"
                        ),
                    }
                ],
            },
            timeout=TIMEOUT,
        )
        if response.status_code >= 400:
            return None
        blocks = response.json().get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return text or None
    except (requests.RequestException, ValueError):
        return None


def answer(text, phone):
    """The reply to send back, given what a member said and the number it came
    from. Never raises: a member who asks something odd gets the help text."""
    member = member_for_phone(phone)
    if member is None:
        return STRANGER.format(gym=getattr(settings, "GYM_NAME", "the gym"))

    question = (text or "").strip()
    if not question:
        return HELP

    lowered = question.lower()
    for pattern, handler in INTENTS:
        if re.search(pattern, lowered):
            return handler(member)

    # Nothing recognised: let the model try, with facts already in hand.
    drafted = _ask_claude(question, _facts_for(member), member)
    return drafted or HELP

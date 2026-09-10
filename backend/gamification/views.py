from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from attendance.services import streaks, visit_dates
from core.permissions import access, IsAdminOrReadOnly

from . import awards, celebrations, leaderboard, records
from .models import Badge, GamificationProfile
from .serializers import (
    BadgeProgressSerializer,
    BadgeSerializer,
    GamificationProfileSerializer,
    LeaderboardRowSerializer,
    PersonalRecordSerializer,
    PRCelebrationSerializer,
    StandingSerializer,
)


class BadgeViewSet(ModelViewSet):
    """The badge catalogue. Members read it so they can see what is worth
    chasing; only an admin defines one."""

    serializer_class = BadgeSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        queryset = Badge.objects.all()
        if not access(self.request).is_admin:
            return queryset.filter(is_active=True)
        return queryset


class MyAchievementsView(APIView):
    """Everything the member's achievements screen needs, in one call.

    Badges are evaluated on read rather than hooked into the check-in and
    workout write paths -- earning something should never be able to make
    logging a set fail.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = request.user
        # Records first: one of the badge criteria counts them.
        records.sync_records(member)
        awarded = awards.evaluate(member)

        dates = visit_dates(member)
        current, longest = streaks(member, dates)
        rows = awards.progress(member)
        profile, _ = GamificationProfile.objects.get_or_create(user=member)

        return Response(
            {
                "current_streak": current,
                "longest_streak": longest,
                "total_visits": len(dates),
                "earned_count": sum(1 for row in rows if row["earned"]),
                "badge_count": len(rows),
                # So the screen can celebrate what was just unlocked rather
                # than quietly adding it to a grid.
                "newly_awarded": [award.badge.code for award in awarded],
                "badges": BadgeProgressSerializer(rows, many=True).data,
                "leaderboard_opt_in": profile.leaderboard_opt_in,
            }
        )


class MyRecordsView(APIView):
    """The member's own PRs, rebuilt from their logs on read."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        found = records.sync_records(request.user)
        return Response(
            PersonalRecordSerializer(
                found.order_by("exercise__name", "-achieved_on"), many=True
            ).data
        )


class LeaderboardView(APIView):
    """Ranked by weight lifted per kilo of bodyweight, this month.

    Opt-in only, and the ratio comes from the bodyweight recorded at the time
    of each lift -- see `leaderboard.py` for why that matters.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # The caller's own records are refreshed so a PR set this morning is on
        # the board they are looking at.
        records.sync_records(request.user)

        exercise = request.query_params.get("exercise")
        month = request.query_params.get("month")
        year = request.query_params.get("year")
        data = leaderboard.board(
            exercise_id=int(exercise) if exercise else None,
            year=int(year) if year else None,
            month=int(month) if month else None,
        )
        return Response(
            {
                "month_start": data["month_start"],
                "results": LeaderboardRowSerializer(data["rows"], many=True).data,
            }
        )


class GamificationProfileView(APIView):
    """The member's own leaderboard opt-in."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = GamificationProfile.objects.get_or_create(user=request.user)
        return Response(GamificationProfileSerializer(profile).data)

    def patch(self, request):
        profile, _ = GamificationProfile.objects.get_or_create(user=request.user)
        form = GamificationProfileSerializer(profile, data=request.data, partial=True)
        form.is_valid(raise_exception=True)
        form.save()
        return Response(form.data)


class PRCelebrationView(APIView):
    """Personal records the member has not been shown yet.

    GET lists them (syncing first, so a set logged a minute ago counts);
    POST marks them seen. Kept separate from the achievements call because the
    portal asks for this on every page, and it has to stay a single indexed
    lookup once there is nothing to celebrate.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            PRCelebrationSerializer(celebrations.pending(request.user), many=True).data
        )

    def post(self, request):
        ids = request.data.get("ids") or None
        if ids is not None and not isinstance(ids, list):
            ids = [ids]
        return Response({"seen": celebrations.mark_seen(request.user, ids)})


class MyStandingView(APIView):
    """Where the member sits, privately.

    The "just for me" mode: someone who wants nothing to do with a public board
    can still see whether they are moving. Nothing returned here identifies
    another member -- only a pool size and a position -- and it refuses to
    place anyone at all when the pool is small enough that a percentile would
    give people away.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        exercise = request.query_params.get("exercise")
        if not exercise:
            return Response(
                {"detail": "Name an exercise to be placed against."}, status=400
            )
        records.sync_records(request.user)
        standing = leaderboard.my_standing(request.user, int(exercise))
        return Response(StandingSerializer(standing).data)

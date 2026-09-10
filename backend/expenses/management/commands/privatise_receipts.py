"""Move receipts already in Cloudinary from public to authenticated delivery.

Pointing the field at a private storage backend only changes what happens to
the *next* upload. Every receipt uploaded before that change is still sitting
at its public address, and will stay there until something moves it -- so
without this command the exposure is closed going forward and left open
backwards, which is the worse half.

Cloudinary's rename API takes a `to_type`, so the move happens server-side: no
download, no re-upload, no bytes crossing the network, and the public id is
unchanged so nothing in the database has to be rewritten. What changes is that
the old public URL stops resolving.

Dry run by default. `--apply` is required to touch anything, because this is
not reversible from here -- moving back would be another rename, and any URL
handed out in the meantime is already invalid either way.

`--limit N` takes the N oldest, which is how to prove the run against a handful
before committing to the whole set. It is worth using at least once: every test
below mocks Cloudinary, so the first `--apply` is the first time this code
meets the real API.
"""

from django.core.management.base import BaseCommand, CommandError

from expenses.models import Expense


class Command(BaseCommand):
    help = (
        "Move existing expense receipts from Cloudinary's public delivery type "
        "to authenticated. Dry run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually perform the move. Without it, only report what would change.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            help=(
                "Process at most N receipts, oldest first. For proving the run "
                "against a handful before committing to the whole set."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not getattr(settings, "CLOUDINARY_CLOUD_NAME", ""):
            raise CommandError(
                "Cloudinary is not configured, so there is nothing hosted to move. "
                "Local uploads live on disk and are not publicly addressable."
            )

        import cloudinary.uploader

        apply = options["apply"]
        # `all_objects`: receipts belong to every branch, and this is platform
        # maintenance rather than one tenant's work. The scoped manager would
        # need a tenant in scope and would only ever move that gym's files.
        manager = getattr(Expense, "all_objects", Expense.objects)
        # Ordered by primary key so a limited run is repeatable and a later,
        # larger limit picks up where the last one left off -- the receipts
        # already moved report as "already private" rather than being redone.
        receipts = manager.exclude(receipt="").exclude(receipt=None).order_by("pk")

        limit = options["limit"]
        if limit is not None:
            if limit < 1:
                raise CommandError("--limit has to be at least 1.")
            total = receipts.count()
            receipts = receipts[:limit]
            self.stdout.write(
                f"Limited to the {min(limit, total)} oldest of {total} receipt(s)."
            )

        moved = skipped = failed = 0
        for expense in receipts:
            public_id = expense.receipt.name
            if not public_id:
                continue

            if not apply:
                self.stdout.write(f"  would move {public_id}")
                moved += 1
                continue

            try:
                cloudinary.uploader.rename(
                    public_id,
                    public_id,
                    type="upload",
                    to_type="authenticated",
                    invalidate=True,
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                # Already authenticated: a re-run, which must be harmless.
                if "not found" in message.lower():
                    skipped += 1
                    continue
                failed += 1
                self.stderr.write(f"  {public_id}: {message}")
                continue
            moved += 1

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {moved} receipt(s) would move to authenticated delivery. "
                    "Re-run with --apply to do it."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Moved {moved}, already private {skipped}, failed {failed}."
            )
        )
        if failed:
            raise CommandError(
                f"{failed} receipt(s) could not be moved and are still public."
            )

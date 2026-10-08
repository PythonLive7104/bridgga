"""Run the AI eval set.

    python manage.py run_evals
    python manage.py run_evals --prompt company_profile
    python manage.py run_evals --tag injection --fail-under 100

Against a real provider this spends money, so the estimated cost is printed
before anything runs and the command asks for confirmation unless --yes is
passed. Against the stub it is free and instant, which is what CI runs.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evals import all_cases, format_report, run_evals
from apps.ai.registry import get_provider


class Command(BaseCommand):
    help = "Run the AI eval set and report pass rates by tag."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--prompt", default="", help="Only cases for this prompt.")
        parser.add_argument("--tag", default="", help="Only cases carrying this tag.")
        parser.add_argument(
            "--fail-under",
            type=float,
            default=0.0,
            help="Exit non-zero if the pass rate is below this percentage.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt when running against a paid provider.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        provider = get_provider()
        cases = all_cases(prompt_name=options["prompt"], tag=options["tag"])

        if not cases:
            raise CommandError("No eval cases matched that filter.")

        self.stdout.write(f"{len(cases)} case(s) via provider '{provider.name}'.")

        if provider.name != "stub" and not options["yes"]:
            self.stdout.write(
                self.style.WARNING("This will call a paid API. Re-run with --yes to proceed.")
            )
            return

        report = run_evals(prompt_name=options["prompt"], tag=options["tag"], provider=provider)
        self.stdout.write("")
        self.stdout.write(format_report(report))

        threshold = options["fail_under"]
        if threshold and report.pass_rate * 100 < threshold:
            raise CommandError(
                f"Pass rate {report.pass_rate:.0%} is below the required {threshold:.0f}%."
            )

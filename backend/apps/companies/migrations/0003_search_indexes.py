"""Indexes behind prospect discovery (PRD sections 29, 103).

Two kinds, for two different query shapes:

* **GIN trigram on the company name**, so a fuzzy or partial name match is an
  index lookup rather than a sequential scan. This is what makes the search
  in `apps.companies.search` meet the two-second target in section 103 once
  there is real data behind it.
* **Composite B-tree indexes** on the filter combinations section 29 names
  and a prospect list actually uses together -- country with industry, status
  with country -- because a filter on one column after another is two index
  scans and a merge, where one composite is a single range read.

The trigram index needs the `pg_trgm` extension and has no SQLite equivalent,
so both are wrapped to skip on anything but Postgres (ADR 0006).
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations, models

from apps.common.db_operations import PostgresOnlyIndex


class Migration(migrations.Migration):
    dependencies = [("companies", "0002_remove_company_one_company_per_domain_per_org_and_more")]

    operations = [
        # Django's CreateExtension subclasses already no-op off Postgres.
        TrigramExtension(),
        PostgresOnlyIndex(
            model_name="company",
            index=GinIndex(
                fields=["name"],
                name="company_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        PostgresOnlyIndex(
            model_name="company",
            index=GinIndex(
                fields=["industry"],
                name="company_industry_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(
                fields=["organization", "country", "industry"],
                name="company_org_geo_industry_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(
                fields=["organization", "status", "country"],
                name="company_org_status_geo_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="companyevent",
            index=models.Index(
                fields=["company", "event_type", "-occurred_at"],
                name="event_company_type_date_idx",
            ),
        ),
    ]

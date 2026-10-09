"""Importing a prospect list (PRD sections 51, 110).

Real exports are messy: byte-order marks from Excel, semicolons instead of
commas, three spellings of one company, blank rows at the end, an address with
a space in it. The suite is mostly about those, because a pipeline that only
handles a clean file is a pipeline that fails on every real one.

The governing rule is that **partial success is the normal case**. A list of
four thousand prospects with nine bad rows must import three thousand nine
hundred and ninety-one of them, and say which nine it did not.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.companies.models import Company
from apps.contacts.models import Person
from apps.leads import importing
from apps.leads import services as lead_services
from apps.leads.import_models import ImportJob, ImportStatus
from apps.leads.import_pipeline import RowSkipped, clean_row, run_import, validate_row
from apps.leads.models import Lead, SourceKind
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

IMPORTS_URL = "/api/v1/leads/imports"

CSV_BODY = (
    "Company Name,Website,Contact Name,Job Title,Email,Country,Industry\r\n"
    "Harmattan Fleet,https://www.harmattanfleet.example,Ada Obi,Fleet Manager,"
    "ada@harmattanfleet.example,NG,Logistics\r\n"
    "LedgerLite,ledgerlite.example,Grace Wanjiru,CFO,grace@ledgerlite.example,Kenya,Fintech\r\n"
)


def make_csv(body: str = CSV_BODY, *, bom: bool = False) -> io.BytesIO:
    raw = body.encode("utf-8")
    if bom:
        raw = b"\xef\xbb\xbf" + raw
    return io.BytesIO(raw)


def make_xlsx(rows: list[list[Any]]) -> io.BytesIO:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


@pytest.fixture
def source(organization: Any) -> Any:
    return lead_services.get_or_create_source(
        organization=organization, name="Q4 list", kind=SourceKind.IMPORT
    )


@pytest.fixture
def make_job(organization: Any, source: Any) -> Callable[..., ImportJob]:
    def _make(body: bytes = CSV_BODY.encode(), *, filename: str = "list.csv", **fields: Any):
        with tenant_context(organization=organization):
            job = ImportJob.objects.create(
                organization=organization,
                file=SimpleUploadedFile(filename, body, content_type="text/csv"),
                original_filename=filename,
                source=source,
                column_mapping=fields.pop(
                    "column_mapping",
                    {
                        "company": "Company Name",
                        "website": "Website",
                        "full_name": "Contact Name",
                        "job_title": "Job Title",
                        "email": "Email",
                        "country": "Country",
                        "industry": "Industry",
                    },
                ),
                **fields,
            )
        return job

    return _make


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_csv_headers_and_rows_are_read() -> None:
    headers, rows = importing.read_csv(make_csv())

    assert headers[0] == "Company Name"
    assert len(list(rows)) == 2


def test_an_excel_byte_order_mark_does_not_corrupt_the_first_header() -> None:
    """Excel writes one, and without utf-8-sig the first column matches nothing."""
    headers, _ = importing.read_csv(make_csv(bom=True))

    assert headers[0] == "Company Name"


def test_semicolon_separated_files_are_read() -> None:
    """A locale using the comma as a decimal separator exports semicolons."""
    body = "Company;Email\r\nAcme;ada@acme.example\r\n"
    headers, rows = importing.read_csv(io.BytesIO(body.encode()))

    assert headers == ["Company", "Email"]
    assert next(iter(rows))["Email"] == "ada@acme.example"


def test_xlsx_is_read() -> None:
    stream = make_xlsx([["Company", "Email"], ["Acme", "ada@acme.example"]])

    headers, rows = importing.read_xlsx(stream)

    assert headers == ["Company", "Email"]
    assert next(iter(rows))["Company"] == "Acme"


def test_trailing_blank_rows_in_a_spreadsheet_are_ignored() -> None:
    """iter_rows pads to the used range, so these arrive as empty dicts."""
    stream = make_xlsx([["Company"], ["Acme"], [None], [""]])

    _, rows = importing.read_xlsx(stream)

    assert len(list(rows)) == 1


def test_a_file_with_no_header_row_is_refused() -> None:
    with pytest.raises(importing.ImportFileError, match="header"):
        importing.read_csv(io.BytesIO(b""))


def test_an_unsupported_extension_is_refused() -> None:
    with pytest.raises(importing.ImportFileError, match="Unsupported"):
        importing.open_file(io.BytesIO(b"x"), filename="prospects.pdf")


# --------------------------------------------------------------------------- #
# Column mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("header", "field"),
    [
        ("Company Name", "company"),
        ("company_name", "company"),
        ("ORGANISATION", "company"),
        ("Work Email", "email"),
        ("E-mail Address", "email"),
        ("Job Title", "job_title"),
        ("Website URL", "website"),
        ("Mobile", "phone"),
        ("LinkedIn Profile", "linkedin_url"),
    ],
)
def test_headers_are_recognised_however_they_are_punctuated(header: str, field: str) -> None:
    assert importing.suggest_mapping([header]).get(field) == header


def test_a_more_specific_header_wins(header: str = "") -> None:
    """A file with both "Name" and "First Name" should not map both to one field."""
    mapping = importing.suggest_mapping(["First Name", "Last Name", "Name"])

    assert mapping["first_name"] == "First Name"
    assert mapping["full_name"] == "Name"


def test_unknown_headers_are_left_unmapped() -> None:
    assert importing.suggest_mapping(["Lead Score", "Notes"]) == {}


def test_preview_shows_a_few_real_rows_beside_the_guess() -> None:
    """A mapping that looks right in the abstract is obviously wrong beside data."""
    found = importing.preview(make_csv(), filename="list.csv")

    assert found["suggested_mapping"]["email"] == "Email"
    assert len(found["sample_rows"]) == 2


# --------------------------------------------------------------------------- #
# Row validation
# --------------------------------------------------------------------------- #


def test_a_bad_address_is_dropped_but_the_row_survives(countries: Any = None) -> None:
    """Refusing the row would discard a good company over one typo."""
    values, notes = validate_row({"company": "Acme", "email": "not an address"})

    assert "email" not in values
    assert values["company"] == "Acme"
    assert notes


def test_a_row_with_nothing_to_match_on_is_skipped() -> None:
    with pytest.raises(RowSkipped):
        validate_row({"job_title": "CFO"})


def test_a_country_name_is_translated_to_its_code(organization: Any) -> None:
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_countries", stdout=StringIO())

    values, _ = validate_row({"company": "Acme", "country": "Kenya"})

    assert values["country"] == "KE"


def test_an_alpha_two_code_passes_through() -> None:
    values, _ = validate_row({"company": "Acme", "country": "ng"})

    assert values["country"] == "NG"


def test_an_unrecognised_country_is_dropped_with_a_note() -> None:
    values, notes = validate_row({"company": "Acme", "country": "Atlantis"})

    assert "country" not in values
    assert any("Atlantis" in note for note in notes)


def test_only_mapped_columns_are_read() -> None:
    cleaned = clean_row(
        {"Company Name": "Acme", "Internal Notes": "do not import"},
        {"company": "Company Name"},
    )

    assert cleaned == {"company": "Acme"}


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


def test_a_clean_file_imports_every_row(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    job = make_job()

    run_import(job=job)

    assert job.status == ImportStatus.COMPLETED
    assert job.total_rows == 2
    assert job.companies_created == 2
    assert job.people_created == 2
    assert job.leads_created == 2


def test_the_same_company_twice_in_one_file_is_one_record(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    """Three spellings of one company is what a real export looks like."""
    body = (
        "Company Name,Website,Email\r\n"
        "Harmattan Fleet,https://www.harmattanfleet.example/,ada@harmattanfleet.example\r\n"
        "Harmattan Fleet Ltd,http://harmattanfleet.example,bola@harmattanfleet.example\r\n"
    )
    job = make_job(
        body.encode(),
        column_mapping={"company": "Company Name", "website": "Website", "email": "Email"},
    )

    run_import(job=job)

    with tenant_context(organization=organization):
        assert Company.objects.count() == 1
        assert Person.objects.count() == 2  # two people at one company
        assert Lead.objects.count() == 1


def test_a_bad_row_does_not_stop_the_run(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    body = (
        "Company Name,Email\r\n"
        "Good Co,ada@good.example\r\n"
        ",\r\n"
        "Another Co,grace@another.example\r\n"
    )
    job = make_job(body.encode(), column_mapping={"company": "Company Name", "email": "Email"})

    run_import(job=job)

    assert job.leads_created == 2
    assert job.rows_skipped == 1


def test_a_dropped_field_is_reported_without_failing_the_row(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    body = "Company Name,Email\r\nGood Co,not-an-address\r\n"
    job = make_job(body.encode(), column_mapping={"company": "Company Name", "email": "Email"})

    run_import(job=job)

    assert job.leads_created == 1
    assert job.rows_failed == 0
    assert job.errors  # the dropped address is still reported


def test_errors_are_capped_but_the_count_is_not(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    """Past the cap the file is structurally wrong and the messages repeat."""
    rows = "\r\n".join(f"Co {n},bad-address-{n}" for n in range(1, 260))
    job = make_job(
        f"Company Name,Email\r\n{rows}\r\n".encode(),
        column_mapping={"company": "Company Name", "email": "Email"},
    )

    run_import(job=job)

    assert len(job.errors) == ImportJob.MAX_STORED_ERRORS
    assert job.total_rows == 259


def test_a_file_that_cannot_be_opened_fails_the_job_not_the_worker(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    job = make_job(b"", filename="empty.csv")

    run_import(job=job)

    assert job.status == ImportStatus.FAILED
    assert job.error_message


def test_a_run_without_a_mapping_is_refused(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    job = make_job(column_mapping={})

    run_import(job=job)

    assert job.status == ImportStatus.FAILED
    assert "mapping" in job.error_message


def test_imported_records_carry_their_provenance(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    """Section 61: the origin must stay answerable after the fact."""
    job = make_job()

    run_import(job=job)

    with tenant_context(organization=organization):
        company = Company.objects.first()
    assert company.source == "import:Q4 list"
    assert company.collected_at is not None


def test_an_import_cannot_resurrect_an_unsubscribed_contact(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    """The most consequential rule in the pipeline (section 63)."""
    job = make_job()
    run_import(job=job)

    with tenant_context(organization=organization):
        person = Person.objects.get(email="ada@harmattanfleet.example")
    person.mark_unsubscribed()

    second = make_job()
    run_import(job=second)

    person.refresh_from_db()
    assert person.email_status == ContactStatus.UNSUBSCRIBED
    assert not person.can_be_emailed


def test_a_single_name_column_is_split_but_the_original_is_kept(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    job = make_job()

    run_import(job=job)

    with tenant_context(organization=organization):
        person = Person.objects.get(email="ada@harmattanfleet.example")
    assert person.full_name == "Ada Obi"
    assert person.first_name == "Ada"
    assert person.last_name == "Obi"


def test_a_row_with_no_company_name_is_labelled_by_its_domain(
    organization: Any, make_job: Callable[..., ImportJob]
) -> None:
    """A blank is less useful than "acme.example" in a prospect list."""
    body = "Website,Email\r\nhttps://acme.example,ada@acme.example\r\n"
    job = make_job(body.encode(), column_mapping={"website": "Website", "email": "Email"})

    run_import(job=job)

    with tenant_context(organization=organization):
        assert Company.objects.first().name == "acme.example"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_uploading_returns_headers_and_a_suggested_mapping(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")

    response = auth_client(owner, organization).post(
        IMPORTS_URL, {"file": upload}, format="multipart"
    )

    assert response.status_code == 201
    assert response.data["status"] == ImportStatus.PENDING
    assert response.data["column_mapping"]["email"] == "Email"
    assert len(response.data["sample_rows"]) == 2


def test_an_oversized_file_is_refused_before_it_is_stored(
    organization: Any, owner: Any, auth_client: Callable[..., Any], settings: Any
) -> None:
    settings.IMPORT_MAX_BYTES = 10
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")

    response = auth_client(owner, organization).post(
        IMPORTS_URL, {"file": upload}, format="multipart"
    )

    assert response.status_code == 400
    assert not ImportJob.objects.filter(organization=organization).exists()


def test_an_executable_disguised_as_a_spreadsheet_is_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """Section 110: the extension and the declared type must both be acceptable."""
    upload = SimpleUploadedFile(
        "prospects.exe", b"MZ\x90\x00", content_type="application/x-msdownload"
    )

    response = auth_client(owner, organization).post(
        IMPORTS_URL, {"file": upload}, format="multipart"
    )

    assert response.status_code == 400


def test_the_stored_file_is_not_named_by_the_uploader(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """A filename is attacker-controlled; it is kept for display only."""
    upload = SimpleUploadedFile("../../etc/passwd.csv", CSV_BODY.encode(), content_type="text/csv")

    response = auth_client(owner, organization).post(
        IMPORTS_URL, {"file": upload}, format="multipart"
    )

    assert response.status_code == 201
    job = ImportJob.objects.get(public_id=response.data["id"])
    assert ".." not in job.file.name
    assert str(organization.public_id) in job.file.name


def test_starting_requires_a_mapping_that_can_match_rows(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    client = auth_client(owner, organization)
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")
    created = client.post(IMPORTS_URL, {"file": upload}, format="multipart")

    response = client.post(
        f"{IMPORTS_URL}/{created.data['id']}/start",
        {"column_mapping": {"job_title": "Job Title"}},
        format="json",
    )

    assert response.status_code == 400


def test_an_unknown_target_field_is_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    client = auth_client(owner, organization)
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")
    created = client.post(IMPORTS_URL, {"file": upload}, format="multipart")

    response = client.post(
        f"{IMPORTS_URL}/{created.data['id']}/start",
        {"column_mapping": {"salary": "Email"}},
        format="json",
    )

    assert response.status_code == 400


def test_starting_runs_the_import(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """Celery runs eagerly in tests, so the queued task completes inline."""
    client = auth_client(owner, organization)
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")
    created = client.post(IMPORTS_URL, {"file": upload}, format="multipart")

    response = client.post(
        f"{IMPORTS_URL}/{created.data['id']}/start",
        {"column_mapping": {"company": "Company Name", "email": "Email"}},
        format="json",
    )

    assert response.status_code == 202
    job = ImportJob.objects.get(public_id=created.data["id"])
    assert job.status == ImportStatus.COMPLETED
    assert job.leads_created == 2


def test_a_viewer_cannot_upload(
    organization: Any, make_member: Callable[..., Any], auth_client: Callable[..., Any]
) -> None:
    viewer = make_member(organization, role=Role.VIEWER)
    upload = SimpleUploadedFile("list.csv", CSV_BODY.encode(), content_type="text/csv")

    response = auth_client(viewer.user, organization).post(
        IMPORTS_URL, {"file": upload}, format="multipart"
    )

    assert response.status_code == 403


def test_one_tenant_never_sees_another_import(
    organization: Any,
    other_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
) -> None:
    other_source = lead_services.get_or_create_source(
        organization=other_organization, name="Theirs", kind=SourceKind.IMPORT
    )
    with tenant_context(organization=other_organization):
        ImportJob.objects.create(
            organization=other_organization,
            file=SimpleUploadedFile("x.csv", b"a,b\r\n1,2\r\n"),
            original_filename="x.csv",
            source=other_source,
        )

    response = auth_client(owner, organization).get(IMPORTS_URL)

    assert response.status_code == 200
    assert response.data["results"] == []

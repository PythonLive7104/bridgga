"""Reading an uploaded prospect list (PRD section 51).

Parsing is kept apart from the pipeline that stores rows, because the two fail
for different reasons and want different handling: a file that cannot be
opened is one error for the whole job, while a row with a broken address is
one error among thousands of good ones.

Both formats are read as a stream. A prospect list is routinely tens of
thousands of rows, and a parser that builds the whole thing in memory first
turns a large upload into a worker outage.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from typing import Any, BinaryIO

from django.conf import settings

#: The fields PRD section 51 names, plus the few the data model needs to
#: deduplicate on. Order is the order a mapping UI should offer them in.
CANONICAL_FIELDS: dict[str, str] = {
    "company": "Company name",
    "website": "Website",
    "industry": "Industry",
    "country": "Country",
    "city": "City",
    "employee_range": "Employee range",
    "full_name": "Contact name",
    "first_name": "First name",
    "last_name": "Last name",
    "job_title": "Job title",
    "email": "Email",
    "phone": "Phone",
    "linkedin_url": "LinkedIn",
}

#: Header spellings seen in real exports, lowercased and stripped of anything
#: that is not a letter or a digit. Matching on that normalised form is what
#: lets "Company Name", "company_name" and "COMPANY-NAME" all land together.
HEADER_ALIASES: dict[str, str] = {
    "company": "company",
    "companyname": "company",
    "organisation": "company",
    "organization": "company",
    "account": "company",
    "accountname": "company",
    "business": "company",
    "website": "website",
    "url": "website",
    "domain": "website",
    "companywebsite": "website",
    "websiteurl": "website",
    "companyurl": "website",
    "companydomain": "website",
    "homepage": "website",
    "web": "website",
    "industry": "industry",
    "sector": "industry",
    "vertical": "industry",
    "industrysector": "industry",
    "category": "industry",
    "country": "country",
    "countrycode": "country",
    "countryname": "country",
    "hq": "country",
    "city": "city",
    "town": "city",
    "location": "city",
    "employees": "employee_range",
    "employeecount": "employee_range",
    "companysize": "employee_range",
    "size": "employee_range",
    "name": "full_name",
    "fullname": "full_name",
    "contact": "full_name",
    "contactname": "full_name",
    "firstname": "first_name",
    "givenname": "first_name",
    "lastname": "last_name",
    "surname": "last_name",
    "familyname": "last_name",
    "title": "job_title",
    "jobtitle": "job_title",
    "position": "job_title",
    "role": "job_title",
    "jobrole": "job_title",
    "designation": "job_title",
    "email": "email",
    "emailaddress": "email",
    "workemail": "email",
    "workemailaddress": "email",
    "businessemail": "email",
    "contactemail": "email",
    "primaryemail": "email",
    "mail": "email",
    "phone": "phone",
    "phonenumber": "phone",
    "telephone": "phone",
    "mobile": "phone",
    "tel": "phone",
    "mobilenumber": "phone",
    "officephone": "phone",
    "contactnumber": "phone",
    "linkedin": "linkedin_url",
    "linkedinurl": "linkedin_url",
    "linkedinprofile": "linkedin_url",
}


class ImportFileError(ValueError):
    """The file as a whole cannot be read. Not a per-row problem."""


def normalise_header(value: str) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Guess which column holds which field.

    A suggestion, never a decision: the caller confirms it. Silently guessing
    is how a phone column ends up in the email field for four thousand people,
    and nobody notices until the first send.

    First match wins, so a file with both "name" and "first name" maps
    `first_name` from the more specific header rather than the looser one.
    """
    mapping: dict[str, str] = {}
    for header in headers:
        field = HEADER_ALIASES.get(normalise_header(header))
        if field and field not in mapping:
            mapping[field] = header
    return mapping


def _decode_csv(stream: BinaryIO) -> io.TextIOWrapper:
    """Wrap bytes as text, tolerating the encodings spreadsheets actually emit.

    ``utf-8-sig`` rather than ``utf-8``: Excel writes a byte-order mark, and
    without this the first header arrives as ``\\ufeffCompany`` and matches
    nothing. ``errors="replace"`` keeps one bad byte from failing a whole file.
    """
    return io.TextIOWrapper(stream, encoding="utf-8-sig", errors="replace", newline="")


def read_csv(stream: BinaryIO) -> tuple[list[str], Iterator[dict[str, Any]]]:
    text = _decode_csv(stream)
    sample = text.read(8192)
    text.seek(0)

    try:
        # Comma, semicolon and tab all appear in the wild; a locale that uses
        # the comma as a decimal separator usually exports semicolons.
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(text, dialect=dialect)
    headers = [header for header in (reader.fieldnames or []) if header]
    if not headers:
        raise ImportFileError("The file has no header row.")

    def rows() -> Iterator[dict[str, Any]]:
        for row in reader:
            yield {key: value for key, value in row.items() if key}

    return headers, rows()


def read_xlsx(stream: BinaryIO) -> tuple[list[str], Iterator[dict[str, Any]]]:
    from openpyxl import load_workbook

    try:
        # read_only streams row by row; data_only takes the cached value of a
        # formula rather than the formula text, which is what a human sees.
        workbook = load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises a wide variety here
        raise ImportFileError(f"The spreadsheet could not be opened: {exc}") from exc

    sheet = workbook.worksheets[0]
    iterator = sheet.iter_rows(values_only=True)

    try:
        header_row = next(iterator)
    except StopIteration as exc:
        raise ImportFileError("The spreadsheet is empty.") from exc

    headers = [str(cell).strip() if cell is not None else "" for cell in header_row]
    if not any(headers):
        raise ImportFileError("The spreadsheet has no header row.")

    def rows() -> Iterator[dict[str, Any]]:
        for values in iterator:
            row = {
                header: ("" if value is None else str(value).strip())
                for header, value in zip(headers, values, strict=False)
                if header
            }
            # iter_rows pads to the sheet's used range, so trailing blank rows
            # arrive as dicts of empty strings rather than stopping iteration.
            if any(row.values()):
                yield row
        workbook.close()

    return headers, rows()


def open_file(
    stream: BinaryIO, *, filename: str, content_type: str = ""
) -> tuple[list[str], Iterator[dict[str, Any]]]:
    """Pick a parser from the extension, cross-checked against the declared type.

    The extension decides, because that is what the uploader meant and what a
    customer will recognise in an error message. The declared content type is
    validated separately on upload; neither is trusted on its own, since both
    are supplied by the client.
    """
    lowered = filename.lower()
    if lowered.endswith(".xlsx"):
        return read_xlsx(stream)
    if lowered.endswith((".csv", ".txt", ".tsv")):
        return read_csv(stream)

    allowed = sorted(set(settings.IMPORT_ALLOWED_TYPES.values()))
    raise ImportFileError(f"Unsupported file type. Accepted: {', '.join(allowed)}.")


def preview(stream: BinaryIO, *, filename: str, limit: int = 5) -> dict[str, Any]:
    """Headers, a suggested mapping, and a few rows to check it against.

    The sample is the point: a mapping that looks right in the abstract is
    obviously wrong the moment it is shown beside three real rows.
    """
    headers, rows = open_file(stream, filename=filename)

    sample: list[dict[str, Any]] = []
    for row in rows:
        sample.append(row)
        if len(sample) >= limit:
            break

    return {
        "headers": headers,
        "suggested_mapping": suggest_mapping(headers),
        "sample_rows": sample,
    }


__all__ = [
    "CANONICAL_FIELDS",
    "HEADER_ALIASES",
    "ImportFileError",
    "normalise_header",
    "open_file",
    "preview",
    "suggest_mapping",
]

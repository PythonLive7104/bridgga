"""Rewriting compose service names for a process outside the network.

This quietly changes where the application connects, so the tests are mostly
about where it must *not* fire.
"""

from __future__ import annotations

import pytest

from config import compose_hosts
from config.compose_hosts import localise_environment, localise_url


@pytest.fixture(autouse=True)
def nothing_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for a machine outside the compose network."""
    monkeypatch.setattr(compose_hosts, "resolves", lambda host: False)


def test_a_compose_host_is_swapped_for_localhost() -> None:
    assert (
        localise_url("postgresql://bridgga:bridgga@db:5432/bridgga")
        == "postgresql://bridgga:bridgga@localhost:5432/bridgga"
    )


def test_credentials_and_port_survive() -> None:
    """The port is how the rewritten URL still reaches the same service."""
    result = localise_url("postgresql://user:p%40ss@db:5433/name")
    assert result == "postgresql://user:p%40ss@localhost:5433/name"


def test_a_password_containing_the_hostname_is_not_mangled() -> None:
    """The reason this parses the URL instead of replacing a substring."""
    result = localise_url("postgresql://db:db@db:5432/db")
    assert result == "postgresql://db:db@localhost:5432/db"


def test_redis_and_scheme_are_preserved() -> None:
    assert localise_url("redis://redis:6379/0") == "redis://localhost:6379/0"


def test_a_host_that_is_not_ours_is_left_alone() -> None:
    """An unresolvable host that is not a compose service is a real failure."""
    url = "postgresql://user:pass@db.production.example:5432/app"
    assert localise_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@prod-db.internal:5432/app",
        "redis://cache.example.com:6379/0",
        "sqlite:///local.sqlite3",
        "",
    ],
)
def test_real_destinations_are_never_rewritten(url: str) -> None:
    assert localise_url(url) == url


def test_nothing_changes_inside_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Where the name resolves, it is already correct."""
    monkeypatch.setattr(compose_hosts, "resolves", lambda host: True)
    url = "postgresql://bridgga:bridgga@db:5432/bridgga"
    assert localise_url(url) == url


def test_the_environment_is_corrected_and_the_changes_reported() -> None:
    environ = {
        "DATABASE_URL": "postgresql://u:p@db:5432/app",
        "REDIS_URL": "redis://redis:6379/0",
        "EMAIL_HOST": "mailhog",
        "SOMETHING_ELSE": "postgresql://u:p@db:5432/app",
    }

    changed = localise_environment(environ)

    assert sorted(changed) == ["DATABASE_URL", "EMAIL_HOST", "REDIS_URL"]
    assert environ["DATABASE_URL"] == "postgresql://u:p@localhost:5432/app"
    assert environ["EMAIL_HOST"] == "localhost"
    # Only the variables this knows about; it does not rewrite the world.
    assert environ["SOMETHING_ELSE"] == "postgresql://u:p@db:5432/app"


def test_an_unset_variable_is_left_unset() -> None:
    environ: dict[str, str] = {}
    assert localise_environment(environ) == []
    assert environ == {}

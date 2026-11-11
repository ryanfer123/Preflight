"""Package and test infrastructure checks."""

import socket

import pytest

import preflight


def test_package_imports() -> None:
    assert preflight.__doc__


def test_network_guard() -> None:
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("example.com", 443))

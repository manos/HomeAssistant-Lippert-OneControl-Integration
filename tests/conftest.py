"""Pytest configuration for Lippert OneControl tests."""
import sys
from pathlib import Path

import pytest

# Add the custom_components directory to the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def mock_onecontrol_host():
    """Return a mock host address."""
    return "192.168.1.1"


@pytest.fixture
def mock_onecontrol_port():
    """Return the standard port."""
    return 6969

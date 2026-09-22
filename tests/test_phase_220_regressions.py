from market.version import __version__
from market.backtest.version import __version__ as backtest_version
from market.research.version import __version__ as research_version


def test_versions_are_consistent():
    assert __version__ == "2.57.0"
    assert backtest_version == __version__
    assert research_version == __version__

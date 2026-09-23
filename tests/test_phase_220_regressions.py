from market.version import __release__, __version__


def test_project_version_consistency():
    assert __version__ == "2.61.0"
    assert __release__ == "Forward Evidence Engine"
    from market.backtest.version import __version__ as backtest_version
    from market.research.version import __version__ as research_version
    assert backtest_version == __version__
    assert research_version == __version__

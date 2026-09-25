def test_project_version_consistency():
    from market.version import __version__
    assert __version__ == "2.69.0"

import owaw


def test_version_is_exposed():
    assert isinstance(owaw.__version__, str)
    assert owaw.__version__

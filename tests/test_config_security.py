from soft_floyd_core.config import Settings


def test_settings_repr_does_not_expose_credentials():
    settings = Settings(
        openai_api_key="test-openai-secret",
        google_client_secret="test-google-secret",
        jwt_secret="test-jwt-secret",
        origin_verify_secret="test-origin-secret",
    )

    rendered = repr(settings)

    assert "test-openai-secret" not in rendered
    assert "test-google-secret" not in rendered
    assert "test-jwt-secret" not in rendered
    assert "test-origin-secret" not in rendered

from django.conf import settings


def test_vehicle_constants():
    assert settings.VEHICLE_RANGE_MILES == 500.0
    assert settings.VEHICLE_MPG == 10.0


def test_ors_base_url_has_no_trailing_slash():
    assert not settings.ORS_BASE_URL.endswith("/")

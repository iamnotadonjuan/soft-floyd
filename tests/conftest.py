from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def road_fit_path():
    return FIXTURES_DIR / "sample_road.fit"


@pytest.fixture(scope="session")
def mtb_fit_path():
    return FIXTURES_DIR / "sample_mtb.fit"


@pytest.fixture(scope="session")
def indoor_fit_path():
    return FIXTURES_DIR / "sample_indoor.fit"


@pytest.fixture(scope="session")
def road_parsed(road_fit_path):
    from coach.ingest.fit_parser import parse_fit

    return parse_fit(road_fit_path)


@pytest.fixture(scope="session")
def mtb_parsed(mtb_fit_path):
    from coach.ingest.fit_parser import parse_fit

    return parse_fit(mtb_fit_path)


@pytest.fixture(scope="session")
def indoor_parsed(indoor_fit_path):
    from coach.ingest.fit_parser import parse_fit

    return parse_fit(indoor_fit_path)

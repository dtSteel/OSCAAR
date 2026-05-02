import structlog
from pathlib import Path
from app.core.config import settings

log = structlog.get_logger()

COUNTRY_TO_LANGUAGE = {
    "US": "en", "GB": "en", "AU": "en", "CA": "en", "NZ": "en", "IE": "en",
    "FR": "fr", "BE": "fr", "CH": "fr", "LU": "fr",
    "DE": "de", "AT": "de",
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es",
    "JP": "ja",
    "CN": "zh", "TW": "zh", "HK": "zh",
    "BR": "pt", "PT": "pt",
    "IT": "it",
    "NL": "nl",
    "KR": "ko",
    "IN": "en",
    "NG": "en",
    "ZA": "en",
}


def detect_language_from_ip(ip_address: str) -> str:
    if not ip_address or ip_address in ("127.0.0.1", "::1"):
        return "en"

    db_path = Path(settings.GEOIP_DB_PATH)
    if not db_path.exists():
        log.warning("geoip_db_not_found", path=str(db_path))
        return "en"

    try:
        import geoip2.database
        with geoip2.database.Reader(str(db_path)) as reader:
            response = reader.country(ip_address)
            country_code = response.country.iso_code
            language = COUNTRY_TO_LANGUAGE.get(country_code, "en")
            log.info("geoip_detected", ip=ip_address, country=country_code, language=language)
            return language
    except Exception as e:
        log.warning("geoip_lookup_failed", ip=ip_address, error=str(e))
        return "en"

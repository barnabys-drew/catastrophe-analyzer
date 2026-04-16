"""
Shared settings loader/validator for runtime safety.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


class SettingsValidationError(ValueError):
    """Raised when settings.json is missing or invalid for runtime use."""


def load_settings(config_path: str) -> Dict[str, Any]:
    """Load settings JSON from disk with explicit failures."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise SettingsValidationError(f"Settings file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SettingsValidationError(
            f"Invalid JSON in settings file {config_path}: {exc.msg} (line {exc.lineno}, col {exc.colno})"
        ) from exc

    if not isinstance(data, dict):
        raise SettingsValidationError("settings.json must contain a top-level JSON object")
    return data


def _require_dict(settings: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = settings.get(key)
    if not isinstance(value, dict) or not value:
        raise SettingsValidationError(f"Missing or invalid settings section: '{key}'")
    return value


def _require_positive_number(section: Dict[str, Any], key: str, section_name: str) -> float:
    value = section.get(key)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: expected positive number, got {value!r}"
        ) from exc
    if numeric <= 0:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: must be > 0, got {numeric}"
        )
    return numeric


def _require_score(section: Dict[str, Any], key: str, section_name: str) -> float:
    value = section.get(key)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: expected number in [0, 100], got {value!r}"
        ) from exc
    if numeric < 0 or numeric > 100:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: must be within [0, 100], got {numeric}"
        )
    return numeric


def _require_non_negative_number(section: Dict[str, Any], key: str, section_name: str) -> float:
    value = section.get(key)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: expected non-negative number, got {value!r}"
        ) from exc
    if numeric < 0:
        raise SettingsValidationError(
            f"Invalid {section_name}.{key}: must be >= 0, got {numeric}"
        )
    return numeric


def _optional_dict(settings: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = settings.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SettingsValidationError(f"Invalid settings section '{key}': expected object")
    return value


def _enabled_categories(event_categories: Dict[str, Any]) -> List[str]:
    enabled = []
    for name, cfg in event_categories.items():
        if not isinstance(cfg, dict):
            continue
        if bool(cfg.get("enabled", False)):
            enabled.append(name)
    return enabled


def _validate_event_categories(event_categories: Dict[str, Any]) -> None:
    enabled = _enabled_categories(event_categories)
    if not enabled:
        raise SettingsValidationError("No enabled event categories in settings.event_categories")
    for category in enabled:
        cfg = event_categories.get(category, {})
        keywords = cfg.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise SettingsValidationError(
                f"Enabled category '{category}' requires non-empty keywords list"
            )


def _validate_news_sources(news_sources: Dict[str, Any], valid_categories: Iterable[str]) -> None:
    enabled_sources = 0
    category_set = set(valid_categories)
    for source_name, source_cfg in news_sources.items():
        if not isinstance(source_cfg, dict):
            raise SettingsValidationError(f"Invalid news source config for '{source_name}'")
        if not bool(source_cfg.get("enabled", False)):
            continue
        enabled_sources += 1
        url = str(source_cfg.get("url", "")).strip()
        category = str(source_cfg.get("event_category", "")).strip()
        if not url:
            raise SettingsValidationError(f"Enabled source '{source_name}' is missing url")
        if category not in category_set:
            raise SettingsValidationError(
                f"Enabled source '{source_name}' references unknown/disabled event_category '{category}'"
            )
    if enabled_sources == 0:
        raise SettingsValidationError("No enabled news sources in settings.news_sources")


def validate_runtime_settings(settings: Dict[str, Any]) -> None:
    """
    Validate required runtime contract for live monitoring mode.
    Raises SettingsValidationError when invalid.
    """
    event_categories = _require_dict(settings, "event_categories")
    news_sources = _require_dict(settings, "news_sources")
    scraping = _require_dict(settings, "scraping")
    triage = _require_dict(settings, "triage")
    monitoring_schedule = _require_dict(settings, "monitoring_schedule")
    distress_model = _require_dict(settings, "distress_model")
    signals = _require_dict(settings, "signals")

    _validate_event_categories(event_categories)
    _validate_news_sources(news_sources, _enabled_categories(event_categories))

    _require_positive_number(scraping, "timeout", "scraping")
    _require_positive_number(scraping, "hours_back", "scraping")
    if scraping.get("max_results_per_source") is None and scraping.get("max_results") is None:
        raise SettingsValidationError(
            "scraping must define max_results_per_source or max_results"
        )
    if scraping.get("max_results_per_source") is not None:
        _require_positive_number(scraping, "max_results_per_source", "scraping")
    if scraping.get("max_results") is not None:
        _require_positive_number(scraping, "max_results", "scraping")
    if scraping.get("max_article_age_hours") is not None:
        _require_positive_number(scraping, "max_article_age_hours", "scraping")

    _require_positive_number(monitoring_schedule, "scan_interval_minutes", "monitoring_schedule")

    min_alert_impact = _require_score(triage, "min_impact_score_for_alert", "triage")
    min_alert_distress = _require_score(triage, "min_distress_score_for_alert", "triage")
    min_signal_impact = _require_score(triage, "min_impact_score_for_signal", "triage")
    min_signal_distress = _require_score(triage, "min_distress_score_for_signal", "triage")
    if min_signal_impact < min_alert_impact or min_signal_distress < min_alert_distress:
        raise SettingsValidationError(
            "triage signal thresholds must be >= alert thresholds"
        )
    if triage.get("duplicate_alert_suppression_hours") is not None:
        _require_non_negative_number(
            triage,
            "duplicate_alert_suppression_hours",
            "triage",
        )

    _require_score(distress_model, "min_score_for_watch_default", "distress_model")

    if not isinstance(signals.get("confidence_levels"), dict):
        raise SettingsValidationError("signals.confidence_levels must be an object")
    if signals.get("min_price_for_signal") is not None:
        _require_positive_number(signals, "min_price_for_signal", "signals")
    if signals.get("min_avg_volume_for_signal") is not None:
        _require_positive_number(signals, "min_avg_volume_for_signal", "signals")
    by_category = signals.get("by_category", {})
    if isinstance(by_category, dict):
        for category, category_cfg in by_category.items():
            if not isinstance(category_cfg, dict):
                continue
            if category_cfg.get("min_price_for_signal") is not None:
                _require_positive_number(
                    category_cfg,
                    "min_price_for_signal",
                    f"signals.by_category.{category}",
                )
            if category_cfg.get("min_avg_volume_for_signal") is not None:
                _require_positive_number(
                    category_cfg,
                    "min_avg_volume_for_signal",
                    f"signals.by_category.{category}",
                )

    dashboard_readiness = _optional_dict(settings, "dashboard_readiness")
    if dashboard_readiness:
        if dashboard_readiness.get("window_days") is not None:
            _require_positive_number(
                dashboard_readiness,
                "window_days",
                "dashboard_readiness",
            )
        if dashboard_readiness.get("required_consecutive_passes") is not None:
            _require_positive_number(
                dashboard_readiness,
                "required_consecutive_passes",
                "dashboard_readiness",
            )
        for key in (
            "min_total_signals",
            "min_categories_with_signals",
            "min_event_to_signal_rate_pct",
            "min_analysis_to_signal_rate_pct",
        ):
            if dashboard_readiness.get(key) is not None:
                _require_non_negative_number(dashboard_readiness, key, "dashboard_readiness")


def load_and_validate_runtime_settings(config_path: str) -> Dict[str, Any]:
    """Load settings file and enforce runtime validation contract."""
    settings = load_settings(config_path)
    validate_runtime_settings(settings)
    return settings

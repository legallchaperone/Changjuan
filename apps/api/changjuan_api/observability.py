from __future__ import annotations

import os
from dataclasses import dataclass

import structlog
from fastapi import FastAPI
from sentry_sdk.transport import Transport

from .settings import Settings


@dataclass(frozen=True)
class ObservabilityState:
    environment: str
    service_name: str
    sentry_configured: bool
    otel_configured: bool
    sls_configured: bool

    def health_payload(self) -> dict[str, str]:
        return {
            "environment": self.environment,
            "service_name": self.service_name,
            "sentry": _status(self.sentry_configured),
            "otel": _status(self.otel_configured),
            "sls": _status(self.sls_configured),
        }


class _NoopSentryTransport(Transport):
    def capture_event(self, event: dict) -> None:
        return None

    def capture_envelope(self, envelope) -> None:
        return None


def configure_observability(app: FastAPI, settings: Settings) -> ObservabilityState:
    configure_structlog()
    state = ObservabilityState(
        environment=settings.app_env,
        service_name=settings.otel_service_name,
        sentry_configured=_configure_sentry(settings),
        otel_configured=_configure_otel(app, settings),
        sls_configured=all(
            [
                settings.aliyun_sls_endpoint,
                settings.aliyun_sls_project,
                settings.aliyun_sls_logstore,
            ]
        ),
    )
    app.state.observability = state
    app.state.observability_logger = structlog.get_logger(settings.otel_service_name).bind(
        environment=settings.app_env,
        sls_endpoint=settings.aliyun_sls_endpoint,
        sls_project=settings.aliyun_sls_project,
        sls_logstore=settings.aliyun_sls_logstore,
    )
    return state


def report_exception(app: FastAPI, error: Exception, *, path: str, method: str) -> None:
    logger = getattr(app.state, "observability_logger", structlog.get_logger("changjuan-api"))
    logger.error(
        "api.unhandled_exception",
        path=path,
        method=method,
        error_type=type(error).__name__,
        error_message=str(error),
    )
    if getattr(getattr(app.state, "observability", None), "sentry_configured", False):
        import sentry_sdk

        sentry_sdk.capture_exception(error)


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=True,
    )


def _configure_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    init_options = {
        "dsn": settings.sentry_dsn,
        "environment": settings.app_env,
        "traces_sample_rate": 0.0,
        "send_default_pii": False,
    }
    if "PYTEST_CURRENT_TEST" in os.environ:
        init_options["transport"] = _NoopSentryTransport
    sentry_sdk.init(**init_options)
    return True


def _configure_otel(app: FastAPI, settings: Settings) -> bool:
    if not settings.otel_exporter_otlp_endpoint:
        return False

    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_exporter_otlp_endpoint)

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    tracer_provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment": settings.app_env,
            }
        )
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(tracer_provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="/healthz",
    )
    return True


def _status(configured: bool) -> str:
    return "configured" if configured else "missing"

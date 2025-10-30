from celery import Celery

from ..configs.setup import get_backend_settings


def get_celery_app(name):
    settings = get_backend_settings()
    broker_url = settings.celery_broker_url
    result_backend = settings.celery_result_backend
    if not broker_url or not result_backend:
        raise ValueError(
            "CELERY_BROKER_URL and CELERY_RESULT_BACKEND must be set in environment variables."
        )

    app = Celery(
        name,
        broker=broker_url,
        backend=result_backend,
    )
    app.conf.update(
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Ho_Chi_Minh",
        enable_utc=True,
        worker_max_tasks_per_child=1,
        worker_concurrency=2,
        task_acks_late=True,
        worker_hijack_root_logger=False,
        worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
        worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s",
    )
    return app

"""Prometheus metrics exposition.

Renders a text/plain Prometheus exposition document from live UCM state:
certificate / CA inventory, scheduler task health, and webhook delivery queue.
Each metric group is isolated so one failing query never blanks the scrape.
"""
import logging
from datetime import timedelta

from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _esc(v) -> str:
    return str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


class _Doc:
    def __init__(self):
        self._lines = []
        self._declared = set()

    def metric(self, name, value, mtype='gauge', help_text=None, **labels):
        if name not in self._declared:
            if help_text:
                self._lines.append(f"# HELP {name} {help_text}")
            self._lines.append(f"# TYPE {name} {mtype}")
            self._declared.add(name)
        if labels:
            label_str = ','.join(f'{k}="{_esc(v)}"' for k, v in labels.items())
            self._lines.append(f"{name}{{{label_str}}} {value}")
        else:
            self._lines.append(f"{name} {value}")

    def render(self) -> str:
        return '\n'.join(self._lines) + '\n'


def _certificates(doc):
    from utils.cert_status import (
        expired_condition, expiring_condition, issued_certificates,
        revoked_condition, valid_condition,
    )
    now = utc_now()
    # Live certificates only: a superseded copy kept for the record and a row
    # holding only a signing request are neither of them a served certificate
    certs = issued_certificates(include_archived=False)
    total = certs.count()
    revoked = certs.filter(revoked_condition()).count()
    expired = certs.filter(expired_condition(now)).count()
    # Lifecycle state: the expiry windows below overlap the valid ones on
    # purpose, they answer "what needs renewing", not "what state is it in"
    valid = certs.filter(valid_condition(now, exclude_expiring=False)).count()
    exp30 = certs.filter(expiring_condition(now, days=30)).count()
    exp7 = certs.filter(expiring_condition(now, days=7)).count()
    h = "Certificates by status"
    doc.metric('ucm_certificates', valid, help_text=h, status='valid')
    doc.metric('ucm_certificates', revoked, status='revoked')
    doc.metric('ucm_certificates', expired, status='expired')
    doc.metric('ucm_certificates_expiring', exp30, help_text="Active certs expiring within a window", days='30')
    doc.metric('ucm_certificates_expiring', exp7, days='7')


def _cas(doc):
    from models import CA
    now = utc_now()
    total = CA.query.count()
    offline = CA.query.filter_by(offline=True).count()
    expired = CA.query.filter(CA.valid_to.isnot(None), CA.valid_to < now).count()
    doc.metric('ucm_certificate_authorities', total, help_text="Certificate authorities by status", status='total')
    doc.metric('ucm_certificate_authorities', offline, status='offline')
    doc.metric('ucm_certificate_authorities', expired, status='expired')


def _scheduler(doc):
    from services.scheduler_service import get_scheduler
    statuses = get_scheduler().get_all_tasks_status()
    doc_help_runs = "Total executions of a scheduler task"
    doc_help_dur = "Last execution duration of a scheduler task (ms)"
    doc_help_fail = "1 if the task's last run errored, else 0"
    for name, st in statuses.items():
        doc.metric('ucm_scheduler_task_runs_total', st.get('run_count', 0),
                   mtype='counter', help_text=doc_help_runs, task=name)
        doc.metric('ucm_scheduler_task_last_duration_milliseconds', st.get('last_duration_ms', 0),
                   help_text=doc_help_dur, task=name)
        doc.metric('ucm_scheduler_task_failed', 1 if st.get('last_error') else 0,
                   help_text=doc_help_fail, task=name)


def _webhooks(doc):
    from models import WebhookDelivery, db
    from sqlalchemy import func
    rows = (db.session.query(WebhookDelivery.status, func.count())
            .group_by(WebhookDelivery.status).all())
    counts = {s: 0 for s in ('pending', 'delivered', 'failed')}
    for status, n in rows:
        counts[status] = n
    for status, n in counts.items():
        doc.metric('ucm_webhook_deliveries', n, help_text="Webhook deliveries by status", status=status)


def _acme(doc):
    from models import AcmeAccount, AcmeOrder, db
    from sqlalchemy import func
    accounts = AcmeAccount.query.count()
    doc.metric('ucm_acme_accounts', accounts, help_text="ACME accounts")
    rows = db.session.query(AcmeOrder.status, func.count()).group_by(AcmeOrder.status).all()
    for status, n in rows:
        doc.metric('ucm_acme_orders', n, help_text="ACME orders by status", status=status)


def _build_info(doc):
    try:
        from services.updates import get_current_version
        version = get_current_version()
    except Exception:
        version = 'unknown'
    doc.metric('ucm_build_info', 1, help_text="UCM build information", version=version)


def render_metrics() -> str:
    doc = _Doc()
    for fn in (_build_info, _certificates, _cas, _scheduler, _webhooks, _acme):
        try:
            fn(doc)
        except Exception as e:
            logger.error(f"Metrics group {fn.__name__} failed: {e}")
    return doc.render()

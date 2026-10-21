"""Shared machinery of the read-only preflights (FIPS readiness, compliance profiles).

A detector reads and names the objects it objects to; ``run_detectors`` collects
them into findings. ``read_only_app`` opens the database without being able to write.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, List

from flask import Flask
from sqlalchemy import event

from config.settings import get_config
from models import db

logger = logging.getLogger(__name__)

BLOCKER, WARNING, INFO = 'blocker', 'warning', 'info'
SEVERITIES = (BLOCKER, WARNING, INFO)
MAX_EXAMPLES = 5


@dataclass(frozen=True)
class Detector:
    id: str
    severity: str
    title: str
    remedy: str
    find: Callable[..., List[str]]  # one name per affected object


def registry_detector(registry: List[Detector]):
    """A ``detector(id, severity, title, remedy)`` decorator that appends to *registry*."""
    def detector(id: str, severity: str, title: str, remedy: str):
        def register(find):
            registry.append(Detector(id, severity, title, remedy, find))
            return find
        return register
    return detector


def run_detectors(detectors: Iterable[Detector], *args, label: str) -> dict:
    """Findings (blockers first), errors and checked ids; ``find(*args)`` is called per detector.

    A detector that raises is listed in errors, never fatal.
    """
    findings, errors, checked = [], [], []
    for item in detectors:
        checked.append(item.id)
        try:
            names = item.find(*args)
        except Exception as exc:
            logger.warning('%s check %s failed: %s', label, item.id, exc)
            db.session.rollback()
            errors.append({'id': item.id, 'error': f'{type(exc).__name__}: {exc}'[:300]})
            continue
        if names:
            findings.append({'id': item.id, 'severity': item.severity, 'title': item.title,
                             'count': len(names), 'examples': names[:MAX_EXAMPLES],
                             'remedy': item.remedy})
    findings.sort(key=lambda f: SEVERITIES.index(f['severity']))
    summary = {s: sum(1 for f in findings if f['severity'] == s) for s in SEVERITIES}
    return {'summary': summary, 'findings': findings, 'errors': errors, 'checked': checked}


def read_only_app(name: str, config=None) -> Flask:
    """The database the service uses, opened read-only; no migration, no scheduler."""
    app = Flask(name)
    app.config.from_object(config or get_config())
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('sqlite:///') and ':memory:' not in uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f"sqlite:///file:{uri[len('sqlite:///'):]}?mode=ro&uri=true")
    db.init_app(app)
    with app.app_context():
        if db.engine.dialect.name == 'postgresql':
            @event.listens_for(db.engine, 'connect')
            def _read_only(dbapi_connection, _record):
                with dbapi_connection.cursor() as cursor:
                    cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
                dbapi_connection.commit()  # a rolled-back SET would be undone
    return app

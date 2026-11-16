"""A UCM process for tests/test_redis_events.py, started in the sandbox of redis_support.

`web PORT`: the application served over HTTP with Socket.IO (threading mode), its
relay reader started as the gunicorn worker starts it, plus /zz-node (state) and
/zz-emit/<name> (emits ca.created from a request). `scheduler`: the application
with the relay publisher started as scheduler_main starts it; each line read on
stdin is a name it emits, without any web server; its answers on stdout start with `NODE `.
"""
import json
import sys

from config.settings import TestingConfig

TestingConfig.SQLALCHEMY_DATABASE_URI = sys.argv[2]

from app import create_app  # noqa: E402
from models import User, db  # noqa: E402
from websocket import events  # noqa: E402
from websocket.emitters import ROOM_CAS  # noqa: E402
from websocket.event_types import EventType  # noqa: E402

app = create_app('testing')
with app.app_context():
    User.query.filter_by(username='admin').update({'force_password_change': False})
    db.session.commit()
    db.session.remove()


def _emit(name):
    events.emit_to_scope(ROOM_CAS, EventType.CA_CREATED, {'name': name})


if sys.argv[1] == 'web':
    from services.ws_relay import start_reader
    reader = start_reader(app)

    @app.route('/zz-node')
    def zz_node():
        return {'reader': reader is not None, 'queue': events.message_queue_in_use()}

    @app.route('/zz-emit/<name>', methods=['POST'])
    def zz_emit(name):
        _emit(name)
        return {'ok': True}

    events.socketio.run(app, host='127.0.0.1', port=int(sys.argv[3]), use_reloader=False,
                        log_output=False, allow_unsafe_werkzeug=True)
else:
    from services.ws_relay import start_publisher
    publisher = start_publisher(app)
    print('NODE', json.dumps({'publisher': publisher is not None, 'queue': events.message_queue_in_use()}),
          flush=True)
    for line in sys.stdin:
        _emit(line.strip())
        print('NODE emitted', flush=True)

"""WSGI guard for the test app: refuses a response header the real server refuses.

gevent's pywsgi raises UnicodeError on a header that does not encode to Latin-1;
Flask's test client lets it through, so the guard makes every test request fail alike.
"""


class Latin1HeaderGuard:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        def checked_start_response(status, headers, exc_info=None):
            for name, value in headers:
                for part in (name, value):
                    try:
                        part.encode('latin-1')
                    except UnicodeEncodeError:
                        raise UnicodeError('Non-latin1 header', repr(name), repr(value)) from None
            return start_response(status, headers, exc_info)
        return self.wsgi_app(environ, checked_start_response)


def guard_latin1_headers(application):
    # Under the peer normalizer, which must stay the outermost layer and passes
    # start_response through untouched: the guard still sees every header the server would.
    from listen_address import PeerAddressNormalizer
    outer = application.wsgi_app
    if isinstance(outer, PeerAddressNormalizer):
        outer.app = Latin1HeaderGuard(outer.app)
    else:
        application.wsgi_app = Latin1HeaderGuard(outer)

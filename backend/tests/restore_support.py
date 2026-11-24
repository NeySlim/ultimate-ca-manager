"""A restore route's answer once its job is final, whatever the route's bounded wait.

The route waits at most JOB_WAIT_SECONDS before answering 202; a loaded test host passes it.
Asked asynchronously and run once the route has answered, the job ends before the test reads.
"""
import pytest
from werkzeug.test import TestResponse

from tests.job_dispatch_support import DeferredDispatch

JOIN_SECONDS = 300


def post_to_the_end(client, url, headers=None, **kwargs):
    """POST ``url`` with ``Prefer: respond-async``, run its job to the end and return the answer
    the route gives for that final job; a refusal before any job comes back as answered."""
    from api.v2.system.jobs import final_response
    from services import jobs
    from services.jobs import runner
    app = client.application
    with pytest.MonkeyPatch.context() as patch:
        deferred = DeferredDispatch(app, patch)
        response = client.post(url, headers={**(headers or {}), 'Prefer': 'respond-async'}, **kwargs)
        if response.status_code != 202:
            deferred.release()
            return response
        job_id = response.headers['Location'].rsplit('/', 1)[1]
        runner.join_local(job_id, JOIN_SECONDS)
    with app.test_request_context():
        # A job run by another executor (a cluster node) is read from the database
        row = runner.wait_for_job(job_id, JOIN_SECONDS)
        assert row['state'] in jobs.FINAL_STATES, f'job {job_id} still {row["state"]} after {JOIN_SECONDS} s'
        body, status = final_response(row)
    body.status_code = status
    return TestResponse(body.response, body.status, body.headers, request=response.request)

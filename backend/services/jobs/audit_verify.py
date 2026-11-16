"""The audit chain verification as a background job: no secret, no file, no audit line."""
from services.jobs import SLOT_AUDIT_VERIFY, JobOutcome, JobType, register

KIND = 'audit_verify'


def message_for(result):
    return {
        'intact': 'Integrity check passed',
        'unprotected': 'No violation found, but the chain is not protected by the master key',
        'broken': f"Chain broken at entry #{result['first_error_id']}",
    }[result['status']]


def params_of(start_id, end_id):
    return {'start_id': start_id, 'end_id': end_id}


def run(ctx):
    from services.audit_service import AuditService
    start_id, end_id = ctx.params.get('start_id'), ctx.params.get('end_id')
    ctx.progress(done=0, total=AuditService.count_entries(start_id, end_id), phase='verifying')
    result = AuditService.verify_integrity(start_id=start_id, end_id=end_id,
                                           on_page=lambda done: ctx.progress(done=done))
    ctx.progress(done=result['checked'])
    return JobOutcome(code=200, message=message_for(result), data=result)


register(JobType(
    kind=KIND, slot=SLOT_AUDIT_VERIFY, permission='read:audit', run=run,
    label='Audit chain verification',
    messages={'executor_lost': 'The verification stopped before the end: run it again',
              'not_taken': 'The verification was never started: run it again',
              'cancelled': 'The verification was cancelled',
              'error': 'Audit chain verification failed'}))

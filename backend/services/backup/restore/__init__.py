"""Restoring an archive, in phases that cannot half-happen.

The restore used to interleave reading, deciding and writing: entities were
committed before the sections that depend on them were even parsed, so a bad
row in a late section left the instance half-restored, and the numeric ids of
the source were written as if they meant something here.

The phases are now separate, and in this order:

1. decrypt and check what the archive says about itself (container, schema)
2. validate every section and every row, touching nothing
3. build the plan: which target row each archived row is, which target id
   each reference resolves to
4. apply, in one transaction, which advances the files generation and lists the
   paths the rows no longer name; no file is written
5. invalidate what the restore made stale; each node's reconciliation then makes
   its files match the rows (services/file_regen_service)

Phases 1 to 3 write nothing, so anything they refuse leaves the instance
exactly as it was.
"""
from .plan import RestorePlan, RestoreValidationError
from .transaction import single_transaction

__all__ = ['RestorePlan', 'RestoreValidationError', 'single_transaction']

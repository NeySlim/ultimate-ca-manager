"""What a restore has to tell the operator, beyond that it worked.

Two facts an archive can carry are useless in a log and necessary in the
answer: a record whose stored private key is not its certificate's, which the
export records deliberately rather than refusing to be taken, and sections the
archive holds that this version does not apply.

Written once because there are two ways to ask for a restore, and each time
the two drifted apart it was the operator who lost: the same archive, restored
from one page or the other, said different things about itself.
"""
from typing import Any, Dict


def with_restore_warnings(message: str, results: Dict[str, Any]) -> str:
    """`message`, followed by what the archive had to warn about.

    The joining is here rather than at each caller because the two messages
    are punctuated differently: one ends with a full stop and the other does
    not, so appending a clause that begins with one produced `again.. 1
    record(s)...` on one side and read correctly on the other.

    Only one full stop is removed, and only a full stop. Stripping every
    trailing one turned an ellipsis into a single dot, and adding one
    unconditionally gave `Did it work?.` to anything ending in a question or
    an exclamation mark. No caller writes either today; this is the joint
    every future one goes through.
    """
    message = message.rstrip()
    if message.endswith('.') and not message.endswith('..'):
        message = message[:-1]
    ends_a_sentence = message.endswith(('.', '?', '!'))

    def _clause(text: str) -> str:
        nonlocal ends_a_sentence
        joiner = ' ' if ends_a_sentence else '. '
        ends_a_sentence = False
        return joiner + text if message else text

    not_restored = (results or {}).get('sections_not_restored') or []
    if not_restored:
        # The archive carries more than this version applies; saying so is
        # the difference between a restore and a restore that looked fine.
        # Bounded like the list below it: an archive from a much newer
        # version can name every section it has.
        shown = not_restored[:5]
        subject = 'a section' if len(not_restored) == 1 else 'sections'
        listing = ', '.join(shown)
        if len(not_restored) > len(shown):
            listing += f' and {len(not_restored) - len(shown)} more'
        message += _clause(f'The archive also holds {subject} this version '
                           f'does not restore: {listing}')

    mismatches = (results or {}).get('key_mismatches') or []
    if mismatches:
        # Recorded when the archive was written. An authority whose key is
        # not its certificate's signs certificates nobody can verify, and the
        # operator has to hear it now rather than from the first client that
        # refuses the chain.
        shown = mismatches[:5]
        record = 'record' if len(mismatches) == 1 else 'records'
        carries = 'carries' if len(mismatches) == 1 else 'carry'
        listing = ', '.join(shown)
        if len(mismatches) > len(shown):
            listing += f' and {len(mismatches) - len(shown)} more'
        message += _clause(
            f'{len(mismatches)} {record} {carries} a private key that is not '
            f"their certificate's and cannot sign: {listing}")

    fallbacks = (results or {}).get('chain_variant_fallbacks') or []
    if fallbacks:
        message += _clause(
            f'{len(fallbacks)} deploy binding(s) pinned to a cross-certificate '
            'absent from this installation were reset to the automatic chain')

    if (results or {}).get('admin_allowlist_cleared'):
        message += _clause('The admin access allowlist from the archive would '
                           'have locked out this session and was cleared; set '
                           'it again in Settings > Security')

    if not message:
        return message
    return message if message.endswith(('.', '?', '!')) else message + '.'

"""Names that must be unique: DNS providers, ACME CA accounts, webhooks.

A clash is resolved by suffixing " (2)", " (3)"... to the later row, the same
way in migration 124, at restore time and for an account UCM creates itself.
"""

# The three columns share this length (String(100)).
NAME_MAX_LENGTH = 100


def suffixed(name, number, max_length=NAME_MAX_LENGTH):
    suffix = f' ({number})'
    return name[:max_length - len(suffix)] + suffix


def first_free(name, taken, max_length=NAME_MAX_LENGTH):
    """`name` if it is not in `taken`, else its first suffixed form that is not."""
    if name not in taken:
        return name
    number = 2
    while suffixed(name, number, max_length) in taken:
        number += 1
    return suffixed(name, number, max_length)


def dedupe(rows, max_length=NAME_MAX_LENGTH):
    """[(id, new_name)] for every row but the first of each name; `rows` in id order."""
    taken = {name for _, name in rows}
    seen = set()
    renames = []
    for row_id, name in rows:
        if name not in seen:
            seen.add(name)
            continue
        new_name = first_free(name, taken, max_length)
        taken.add(new_name)
        renames.append((row_id, new_name))
    return renames

"""The sections of a v4 archive, kept on disk while a restore reads them.

Each section is written to its own JSON file as its chunks are decrypted, and
loaded again only when the restore asks for it. The store answers what the
restore reads of a payload dict, so the restore code is the same for v1 to v4.
"""
import json
import logging
import os
import shutil
import sys
import tempfile
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sections kept loaded at once, unless still referenced elsewhere
DEFAULT_CAPACITY = 2
# Held whole in memory and never written to disk
PINNED = ('metadata',)
_MISSING = object()


def store_directory() -> Optional[str]:
    """`DATA_DIR/tmp`, where uploads already spool; the system temp dir otherwise."""
    try:
        from flask import current_app
        spool = current_app.config.get('UPLOAD_SPOOL_DIR')
        if spool:
            os.makedirs(spool, 0o700, exist_ok=True)
            return spool
    except (RuntimeError, OSError):
        pass
    try:
        from config.settings import Config
        path = os.path.join(str(Config.DATA_DIR), 'tmp')
        os.makedirs(path, 0o700, exist_ok=True)
        return path
    except (AttributeError, OSError):
        return None


def section_kind(payload: Any, name: str) -> Optional[str]:
    """'list', 'mapping', 'other', or None when absent; a store answers without loading."""
    if isinstance(payload, SectionStore):
        return payload.kind(name)
    value = payload.get(name, _MISSING)
    if value is _MISSING:
        return None
    return 'list' if isinstance(value, list) else 'mapping' if isinstance(value, dict) else 'other'


def section_length(payload: Any, name: str) -> int:
    """Entries a list or mapping section holds, 0 for anything else or absent."""
    if isinstance(payload, SectionStore):
        return payload.length(name)
    value = payload.get(name)
    return len(value) if isinstance(value, (list, dict)) else 0


class SectionStore:
    """A payload whose sections live in files of a private directory, loaded on demand.

    A loaded section is dropped again once more than `capacity` are loaded,
    and only when nothing outside the store references it or its rows: what
    the restore still holds keeps its identity and the changes made to it.
    """

    def __init__(self, directory: Optional[str] = None, capacity: int = DEFAULT_CAPACITY):
        self._dir = tempfile.mkdtemp(prefix='.ucm_restore_', dir=directory or store_directory())
        self._capacity = max(1, capacity)
        self._order: List[str] = []
        self._files: Dict[str, str] = {}
        self._shape: Dict[str, Tuple[str, int]] = {}
        self._pinned: Dict[str, Any] = {}
        self._loaded: 'OrderedDict[str, Any]' = OrderedDict()
        self._writing = None    # (name, file, kind, rows written)

    # -- filling, from the chunk reader -----------------------------------

    def add_part(self, name: str, part: int, rows: Any) -> None:
        """Append one decrypted part; parts of a section arrive in order."""
        if self._writing is not None and self._writing[0] != name:
            self._close_section()
        if name in PINNED:
            self._register(name)
            self._pinned[name] = rows
            return
        if self._writing is None:
            self._register(name)
            handle = self._open_for_write(name)
            kind = 'mapping' if isinstance(rows, dict) else 'list'
            handle.write('{' if kind == 'mapping' else '[')
            self._writing = [name, handle, kind, 0]
        _name, handle, kind, written = self._writing
        if kind == 'mapping':
            handle.write(json.dumps(rows, separators=(',', ':'))[1:-1])
            self._writing[3] = len(rows)
            return
        for row in rows:
            if written:
                handle.write(',')
            json.dump(row, handle, separators=(',', ':'))
            written += 1
        self._writing[3] = written

    def seal(self) -> None:
        """Close the section being written; the store is then read-only until changed."""
        if self._writing is not None:
            self._close_section()

    def _close_section(self) -> None:
        name, handle, kind, written = self._writing
        self._writing = None
        handle.write('}' if kind == 'mapping' else ']')
        handle.close()
        self._shape[name] = (kind, written)

    def _register(self, name: str) -> None:
        if name in self._files or name in self._pinned:
            raise ValueError(f"Section '{name}' appears twice")
        self._order.append(name)

    def _open_for_write(self, name: str):
        # Files are named by position: a section name never reaches the filesystem
        path = os.path.join(self._dir, f'{len(self._files)}.json')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._files[name] = path
        return os.fdopen(fd, 'w', encoding='utf-8')

    # -- what a restore reads ---------------------------------------------

    def __getitem__(self, name: str) -> Any:
        if name in self._pinned:
            return self._pinned[name]
        if name in self._loaded:
            self._loaded.move_to_end(name)
            return self._loaded[name]
        if name not in self._files:
            raise KeyError(name)
        with open(self._files[name], 'r', encoding='utf-8') as handle:
            value = json.load(handle)
        self._loaded[name] = value
        self._shrink()
        return value

    def __setitem__(self, name: str, value: Any) -> None:
        if name in PINNED:
            if name not in self._pinned:
                self._register(name)
            self._pinned[name] = value
            return
        if name not in self._files:
            self._register(name)
            self._files[name] = os.path.join(self._dir, f'{len(self._files)}.json')
        self._loaded[name] = value
        self._loaded.move_to_end(name)
        self._shrink()

    def __contains__(self, name: object) -> bool:
        return name in self._pinned or name in self._files

    def __iter__(self) -> Iterator[str]:
        return iter(list(self._order))

    def __len__(self) -> int:
        return len(self._order)

    def keys(self) -> List[str]:
        return list(self._order)

    def get(self, name: str, default: Any = None) -> Any:
        return self[name] if name in self else default

    def items(self) -> Iterator[Tuple[str, Any]]:
        """Each section in archive order, loaded as the iteration reaches it."""
        for name in list(self._order):
            yield name, self[name]

    def values(self) -> Iterator[Any]:
        for _name, value in self.items():
            yield value

    def kind(self, name: str) -> Optional[str]:
        if name in self._pinned or name in self._loaded:
            value = self._pinned[name] if name in self._pinned else self._loaded[name]
            return ('list' if isinstance(value, list)
                    else 'mapping' if isinstance(value, dict) else 'other')
        shape = self._shape.get(name)
        return shape[0] if shape else None

    def length(self, name: str) -> int:
        if name in self._pinned or name in self._loaded:
            value = self._pinned[name] if name in self._pinned else self._loaded[name]
            return len(value) if isinstance(value, (list, dict)) else 0
        shape = self._shape.get(name)
        return shape[1] if shape else 0

    def to_dict(self) -> Dict[str, Any]:
        """Every section loaded at once: for inspection, never on the restore path."""
        return {name: self[name] for name in self._order}

    # -- keeping memory to a few sections ---------------------------------

    def _shrink(self) -> None:
        if len(self._loaded) <= self._capacity:
            return
        for name in list(self._loaded)[:-1]:
            if len(self._loaded) <= self._capacity:
                return
            if self._released(name):
                self._evict(name)

    def _released(self, name: str) -> bool:
        """Whether only the store holds this section and each of its rows."""
        value = self._loaded[name]
        # The store's own reference, this frame's, and getrefcount's argument
        if sys.getrefcount(value) > 3:
            return False
        children = value.values() if isinstance(value, dict) else value
        for child in children:
            # The container's reference, the loop's, and getrefcount's argument
            if isinstance(child, (dict, list)) and sys.getrefcount(child) > 3:
                return False
        return True

    def _evict(self, name: str) -> None:
        """Write the section back, changes included, then let it go."""
        value = self._loaded[name]
        path = self._files[name]
        fd, temp = tempfile.mkstemp(dir=self._dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(value, handle, separators=(',', ':'))
            os.replace(temp, path)
        except (TypeError, ValueError, OSError) as exc:
            # A value JSON cannot carry: the section stays loaded rather than lose it
            logger.debug("Restore: section %s kept in memory (%s)", name, exc)
            try:
                os.unlink(temp)
            except OSError:
                pass
            return
        kind = 'list' if isinstance(value, list) else 'mapping' if isinstance(value, dict) else 'other'
        self._shape[name] = (kind, len(value) if isinstance(value, (list, dict)) else 0)
        del value
        del self._loaded[name]

    # -- lifetime -----------------------------------------------------------

    def close(self) -> None:
        if self._writing is not None:
            try:
                self._writing[1].close()
            except OSError:
                pass
            self._writing = None
        self._loaded.clear()
        self._pinned.clear()
        shutil.rmtree(self._dir, ignore_errors=True)

    def __enter__(self) -> 'SectionStore':
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

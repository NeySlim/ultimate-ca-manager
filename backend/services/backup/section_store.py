"""The sections of a v4 archive, kept on disk while a restore reads them.

Each section is written to its own file as its chunks are decrypted, sealed
with AES-GCM under a key that lives only in this process, and loaded again
only when the restore asks for it. The store answers what the
restore reads of a payload dict, so the restore code is the same for v1 to v4.
"""
import hashlib
import json
import logging
import os
import shutil
import stat
import struct
from sys import getrefcount
import tempfile
import time
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Sections kept loaded at once, unless still referenced elsewhere
DEFAULT_CAPACITY = 2
# Held whole in memory and never written to disk
PINNED = ('metadata',)
_MISSING = object()
STORE_PREFIX = '.ucm_restore_'
# Plaintext sealed per frame; a frame is `len(uint32) || nonce(12) || ciphertext`
FRAME_BYTES = 1024 * 1024
_FRAME_LEN = struct.Struct('>I')
_NONCE_SIZE = 12
# A store left by a killed worker; a live restore holds the backup lock anyway
STALE_AFTER_SECONDS = 3600


def store_directory(spool: Optional[str] = None) -> Optional[str]:
    """The upload spool dir, else `DATA_DIR/tmp` if the upload spool probe accepts it.

    None means the system temp dir: stores are created and swept in the same place.
    """
    try:
        from flask import current_app
        spool = spool or current_app.config.get('UPLOAD_SPOOL_DIR')
        if spool:
            os.makedirs(spool, 0o700, exist_ok=True)
            return spool
    except (RuntimeError, OSError):
        pass
    try:
        from config.settings import Config
        from utils import upload_spool
        return upload_spool.prepare_spool_dir(Config.DATA_DIR)
    except (AttributeError, ImportError):
        return None


def fallback_directory() -> Optional[str]:
    """This instance's own directory in the system temp dir, named after its DATA_DIR,
    so instances sharing that dir never sweep each other's stores; None if unusable."""
    try:
        from config.settings import Config
        digest = hashlib.sha256(os.path.realpath(str(Config.DATA_DIR)).encode()).hexdigest()
        path = os.path.join(tempfile.gettempdir(), f'ucm-restore-{digest[:12]}')
        os.makedirs(path, 0o700, exist_ok=True)
        info = os.lstat(path)
    except (AttributeError, OSError):
        return None
    # Another user's directory could remove or swap the stores under us
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        return None
    return path


def sweep_stale_stores(directory: Optional[str] = None, spool: Optional[str] = None) -> None:
    """Remove stores a killed worker left behind, in the directory `store_directory()` gives.

    Closed rule: nothing is removed unless the backup lock was taken, so a restore
    still applying its plan is never swept.
    """
    directory = directory or store_directory(spool) or fallback_directory()
    if not directory or not os.path.isdir(directory):
        return
    from .locking import BackupBusyError, backup_operation_lock
    try:
        with backup_operation_lock(timeout=0, purpose='sweeping restore leftovers',
                                   fail_open=False):
            limit = time.time() - STALE_AFTER_SECONDS
            for entry in os.scandir(directory):
                if (entry.name.startswith(STORE_PREFIX)
                        and entry.is_dir(follow_symlinks=False)
                        and entry.stat(follow_symlinks=False).st_mtime < limit):
                    shutil.rmtree(entry.path, ignore_errors=True)
    except (BackupBusyError, OSError) as exc:
        logger.info("Restore leftovers not swept: %s", exc)


class _SealedWriter:
    """Text written to it lands in its file as AES-GCM frames, never in clear."""

    def __init__(self, store: 'SectionStore', fd: int, label: str):
        self._store = store
        self._file = os.fdopen(fd, 'wb')
        self._label = label
        self._index = 0
        self._parts: List[bytes] = []
        self._size = 0

    def write(self, text: str) -> None:
        data = text.encode('utf-8')
        self._parts.append(data)
        self._size += len(data)
        if self._size >= FRAME_BYTES:
            self._flush()

    def _flush(self) -> None:
        if not self._parts:
            return
        plaintext = b''.join(self._parts)
        self._parts, self._size = [], 0
        nonce, sealed = self._store._seal(self._label, self._index, plaintext)
        self._file.write(_FRAME_LEN.pack(len(sealed)) + nonce + sealed)
        self._index += 1

    def close(self) -> None:
        try:
            self._flush()
        finally:
            self._file.close()

    def discard(self) -> None:
        self._parts = []
        self._file.close()


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
        self._dir = tempfile.mkdtemp(
            prefix=STORE_PREFIX, dir=directory or store_directory() or fallback_directory())
        # Held only in memory: files a killed worker leaves behind stay unreadable
        self._aead = AESGCM(AESGCM.generate_key(bit_length=256))
        self._nonces = 0
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
        try:
            handle.write('}' if kind == 'mapping' else ']')
        finally:
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
        return _SealedWriter(self, fd, os.path.basename(path))

    def _seal(self, label: str, index: int, plaintext: bytes) -> Tuple[bytes, bytes]:
        # A counter never repeats a nonce under this store's key; the AAD pins
        # each frame to its file and position
        self._nonces += 1
        nonce = self._nonces.to_bytes(_NONCE_SIZE, 'big')
        return nonce, self._aead.encrypt(nonce, plaintext, _frame_aad(label, index))

    def _read_sealed(self, path: str) -> Any:
        label = os.path.basename(path)
        plaintext = bytearray()
        with open(path, 'rb') as handle:
            index = 0
            while True:
                head = handle.read(_FRAME_LEN.size)
                if not head:
                    break
                if len(head) != _FRAME_LEN.size:
                    raise ValueError('Truncated restore section file')
                (length,) = _FRAME_LEN.unpack(head)
                nonce = handle.read(_NONCE_SIZE)
                sealed = handle.read(length)
                if len(nonce) != _NONCE_SIZE or len(sealed) != length:
                    raise ValueError('Truncated restore section file')
                plaintext += self._aead.decrypt(nonce, sealed, _frame_aad(label, index))
                index += 1
        return json.loads(plaintext)

    # -- what a restore reads ---------------------------------------------

    def __getitem__(self, name: str) -> Any:
        if name in self._pinned:
            return self._pinned[name]
        if name in self._loaded:
            self._loaded.move_to_end(name)
            return self._loaded[name]
        if name not in self._files:
            raise KeyError(name)
        value = self._read_sealed(self._files[name])
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
        section, row = _reference_counts(self._loaded, name)
        return section <= _BASELINE[0] and row <= _BASELINE[1]

    def _evict(self, name: str) -> None:
        """Write the section back, changes included, then let it go."""
        value = self._loaded[name]
        path = self._files[name]
        fd, temp = tempfile.mkstemp(dir=self._dir, suffix='.tmp')
        writer = _SealedWriter(self, fd, os.path.basename(path))
        try:
            try:
                json.dump(value, writer, separators=(',', ':'))
            except BaseException:
                writer.discard()
                raise
            writer.close()
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
                self._writing[1].discard()
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


def _reference_counts(loaded: Dict[str, Any], name: str) -> Tuple[int, int]:
    """References to a loaded section and to its most referenced row."""
    value = loaded[name]
    section = getrefcount(value)
    row = 0
    for child in (value.values() if isinstance(value, dict) else value):
        if isinstance(child, (dict, list)):
            row = max(row, getrefcount(child))
    return section, row


def _baseline() -> Tuple[int, int]:
    # Measured on an unheld probe through the same code: interpreters differ
    # in what getrefcount reports (3.14 borrows references 3.13 counted)
    return _reference_counts(OrderedDict(probe=[{}]), 'probe')


def _frame_aad(label: str, index: int) -> bytes:
    return label.encode('ascii') + b'#' + index.to_bytes(8, 'big')


_BASELINE = _baseline()

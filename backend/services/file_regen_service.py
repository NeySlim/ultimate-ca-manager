"""The certificate, CSR and key files on disk, as a function of the database.

CA_DIR, CERT_DIR and PRIVATE_DIR are mirrors for external tools; the application never
reads them back. `reconcile_files` makes each node's copy match the rows, any number of
times, in any order; a restore only advances the files generation and lists what it removed.
"""
import base64
import contextvars
import errno
import hashlib
import logging
import os
import secrets
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from config.settings import Config
from utils.file_naming import (
    ca_cert_path,
    ca_key_path,
    cert_cert_path,
    cert_key_path,
    cert_csr_path,
)

logger = logging.getLogger(__name__)


_INSERT_WRITES_SUSPENDED = contextvars.ContextVar('ucm_insert_file_writes_suspended', default=False)


@contextmanager
def insert_file_writes_suspended():
    """Rows inserted in the block get no files from the insert listeners: a restore's
    files are written by the reconciliation, from the rows once they are committed."""
    token = _INSERT_WRITES_SUSPENDED.set(True)
    try:
        yield
    finally:
        _INSERT_WRITES_SUSPENDED.reset(token)


def insert_file_writes_enabled() -> bool:
    return not _INSERT_WRITES_SUSPENDED.get()


def mirror_private_key(path: Path, key_pem: bytes, *, context: str) -> bool:
    """Mirror a plaintext key only while values are stored in the clear (encryption off,
    or being disabled and in its grace period). While new values are encrypted, any stale
    mirror at ``path`` is removed.

    The write is atomic: the content goes to a temporary file in the same
    directory, is fsynced and chmoded there, and only then replaces the
    mirror. Writing in place truncated the file first, so a failure partway --
    a full disk, a read-only mount -- destroyed the key that was there while
    the caller went on to report a success. A mirror half-written is a key
    nothing can read.

    Failures are logged and reported through the return value rather than
    raised: a mirror is a convenience for tools that read keys off disk, and
    the key itself is in the database. The caller decides what to do with a
    False.
    """
    from security.encryption import key_encryption

    temp_path = None
    try:
        if key_encryption.is_encrypting:
            path.unlink(missing_ok=True)
            logger.debug("Skipped plaintext key mirror for %s", context)
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix='.ucm_key_', suffix='.tmp')
        temp_path = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as key_file:
                fd = -1
                key_file.write(key_pem)
                key_file.flush()
                os.fsync(key_file.fileno())
        finally:
            if fd >= 0:
                os.close(fd)
        os.replace(temp_path, path)
        temp_path = None
        return True
    except Exception as e:
        logger.warning("Could not mirror private key for %s: %s", context, e)
        return False
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                logger.warning(
                    "Could not remove the temporary key mirror %s", temp_path)


def write_cert_files(cert) -> None:
    """Write certificate, key, and CSR files for a Certificate object.

    While new values are encrypted the key is neither decrypted nor mirrored."""
    from security.encryption import key_encryption
    from utils.key_codec import load_pem_bytes

    Config.CERT_DIR.mkdir(parents=True, exist_ok=True)
    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    cert_path = cert_cert_path(cert)
    if not cert_path.exists() and cert.crt:
        try:
            cert_path.write_bytes(base64.b64decode(cert.crt))
        except Exception as e:
            logger.warning(f"Could not write cert file for {cert.descr}: {e}")

    if cert.prv and not key_encryption.is_encrypting:
        try:
            key_pem = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
            mirror_private_key(
                cert_key_path(cert), key_pem, context=f"certificate {cert.id}"
            )
        except Exception as e:
            logger.warning(f"Could not write key file for {cert.descr}: {e}")

    csr_path = cert_csr_path(cert)
    if not csr_path.exists() and cert.csr:
        try:
            csr_data = cert.csr
            csr_bytes = (
                csr_data.encode()
                if csr_data.startswith('-----BEGIN')
                else base64.b64decode(csr_data)
            )
            csr_path.write_bytes(csr_bytes)
        except Exception as e:
            logger.warning(f"Could not write CSR file for {cert.descr}: {e}")


def write_ca_files(ca) -> None:
    """Write certificate and key files for a CA object.

    While new values are encrypted the key is neither decrypted nor mirrored."""
    from security.encryption import key_encryption
    from utils.key_codec import load_pem_bytes

    Config.CA_DIR.mkdir(parents=True, exist_ok=True)
    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    cert_path = ca_cert_path(ca)
    if not cert_path.exists() and ca.crt:
        try:
            cert_path.write_bytes(base64.b64decode(ca.crt))
        except Exception as e:
            logger.warning(f"Could not write CA cert file for {ca.descr}: {e}")

    if ca.prv and not key_encryption.is_encrypting:
        try:
            key_pem = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
            mirror_private_key(ca_key_path(ca), key_pem, context=f"CA {ca.id}")
        except Exception as e:
            logger.warning(f"Could not write CA key file for {ca.descr}: {e}")




def _holds(column):
    """An empty value is no content, as everywhere else in the code (a '' key is no key)."""
    from sqlalchemy import and_
    return and_(column.isnot(None), column != '')


def purge_private_key_files() -> dict:
    """Remove plaintext key mirrors while new values are encrypted (not during a disable's grace).

    A mirror named by a row that holds no key is kept: it may be the only copy.
    """
    from models import CA, Certificate
    from security.encryption import key_encryption

    stats = {'removed': 0, 'kept_no_db_key': 0, 'errors': 0}
    if not key_encryption.is_encrypting:
        return stats

    keyless = set()
    for model, path_of, legacy in ((CA, ca_key_path, 'ca_{}.key'),
                                   (Certificate, cert_key_path, 'cert_{}.key')):
        for row in _pages(model, (model.refid, model.subject, model.descr),
                          where=~_holds(model.prv)):
            keyless.add(path_of(row).name)
            keyless.add(legacy.format(row.refid))

    for path in Config.PRIVATE_DIR.glob('*.key'):
        if path.name in keyless:
            stats['kept_no_db_key'] += 1
            logger.error(
                "Kept plaintext key mirror %s because its database row has no key",
                path,
            )
            continue
        try:
            path.unlink()
            stats['removed'] += 1
        except Exception as e:
            stats['errors'] += 1
            logger.error("Could not purge plaintext key mirror %s: %s", path, e)

    if stats['removed']:
        try:
            from services.audit_service import AuditService

            AuditService.log_action(
                action='private_key_files_purged',
                resource_type='system',
                resource_name='Private Key Files',
                details=(
                    f"{stats['removed']} plaintext key files removed from "
                    "the private directory"
                ),
                success=True,
            )
        except Exception as e:
            logger.warning("Could not audit private-key file purge: %s", e)

    return stats


# --- Files generation and the removal list, written in a restore's transaction ---------

GENERATION_KEY = 'files.generation'
MARKER_NAME = '.ucm-files-generation'
DIR_ID_NAME = '.ucm-files-id'
LOCK_NAME = '.ucm-files.lock'
PAGE_SIZE = 500
_ADVISORY_NAMESPACE = b'ucm-files-reconcile:'


def _pages(model, columns, where=None, ids=None):
    """Rows of ``model`` with only ``columns`` (and id), PAGE_SIZE at a time, by id."""
    from models import db
    last = None
    while True:
        query = db.session.query(model.id, *columns)
        if where is not None:
            query = query.filter(where)
        if ids is not None:
            query = query.filter(model.id.in_(ids))
        if last is not None:
            query = query.filter(model.id > last)
        page = query.order_by(model.id).limit(PAGE_SIZE).all()
        if not page:
            return
        yield from page
        if ids is not None or len(page) < PAGE_SIZE:
            return
        last = page[-1].id


def current_generation() -> str:
    """``"<number>:<random>"``: the random part tells two databases at the same number apart."""
    from models import SystemConfig, db
    value = db.session.query(SystemConfig.value).filter_by(key=GENERATION_KEY).scalar()
    return value or '0'


def generation_number(value) -> int:
    try:
        return int(str(value).split(':', 1)[0])
    except ValueError:
        return 0


def advance_generation() -> int:
    """The next files generation's number, in the caller's transaction (committed with its rows)."""
    from models import SystemConfig, db
    if db.session.connection().dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.session.execute(insert(SystemConfig.__table__).values(
        key=GENERATION_KEY, value='0', encrypted=False,
        description='Advanced by each restore: every node reconciles its files to it',
    ).on_conflict_do_nothing(index_elements=['key']))
    row = (SystemConfig.query.filter_by(key=GENERATION_KEY)
           .with_for_update().populate_existing().one())
    number = generation_number(row.value) + 1
    row.value = f"{number}:{secrets.token_hex(8)}"
    db.session.flush()
    return number


def _named_paths(kind, row):
    if kind == 'ca':
        return (ca_cert_path(row), ca_key_path(row))
    return (cert_cert_path(row), cert_csr_path(row), cert_key_path(row))


def record_removal_candidates(generation: int) -> None:
    """Every file the rows have content for now, listed under ``generation``.

    Called before a restore writes; `keep_named_paths` then strikes what the rows
    still name, which leaves the exact list of files the restore removed.
    """
    from models import CA, Certificate, FileRemoval, db
    batch = []

    def flush():
        if batch:
            db.session.execute(FileRemoval.__table__.insert(), batch)
            batch.clear()

    for row in _pages(CA, (CA.refid, CA.subject, CA.descr, _holds(CA.crt).label('has_crt'),
                           _holds(CA.prv).label('has_prv'))):
        if row.has_crt:
            batch.append({'generation': generation, 'path': str(ca_cert_path(row))})
        if row.has_prv:
            batch.append({'generation': generation, 'path': str(ca_key_path(row))})
        if len(batch) >= PAGE_SIZE:
            flush()
    for row in _pages(Certificate, (
            Certificate.refid, Certificate.subject, Certificate.descr,
            _holds(Certificate.crt).label('has_crt'),
            _holds(Certificate.csr).label('has_csr'),
            _holds(Certificate.prv).label('has_prv'))):
        for present, path in ((row.has_crt, cert_cert_path), (row.has_csr, cert_csr_path),
                              (row.has_prv, cert_key_path)):
            if present:
                batch.append({'generation': generation, 'path': str(path(row))})
        if len(batch) >= PAGE_SIZE:
            flush()
    flush()


def keep_named_paths() -> None:
    """Strike from the list, whatever its generation, every path a row names now
    (a key path too when the row holds no key: such a copy is never removed)."""
    from models import CA, Certificate, FileRemoval, db
    db.session.flush()
    table = FileRemoval.__table__
    for kind, model in (('ca', CA), ('cert', Certificate)):
        paths = []
        for row in _pages(model, (model.refid, model.subject, model.descr)):
            paths.extend(str(p) for p in _named_paths(kind, row))
            if len(paths) >= PAGE_SIZE:
                db.session.execute(table.delete().where(table.c.path.in_(paths)))
                paths = []
        if paths:
            db.session.execute(table.delete().where(table.c.path.in_(paths)))


def removals_listed(generation: int) -> int:
    from models import FileRemoval, db
    return db.session.query(FileRemoval.id).filter_by(generation=generation).count()


# --- The reconciliation ---------------------------------------------------------------


class _Unwritable(Exception):
    """A managed directory this process cannot write to; the message is for operators."""


def managed_dirs():
    """CA_DIR, CERT_DIR and PRIVATE_DIR, each once even when two are the same directory."""
    seen, dirs = set(), []
    for directory in (Config.CA_DIR, Config.CERT_DIR, Config.PRIVATE_DIR):
        real = os.path.realpath(directory)
        if real not in seen:
            seen.add(real)
            dirs.append(Path(directory))
    return dirs


def unwritable_dirs():
    """The managed directories (or their nearest existing parent) this process cannot write.

    Read without writing anything: a restore checks it before its transaction.
    """
    refused = []
    for directory in managed_dirs():
        probe = Path(directory)
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        if not os.access(probe, os.W_OK | os.X_OK):
            refused.append(str(directory))
    return refused


class _Dir:
    """A managed directory opened once: every name is resolved under its descriptor."""

    def __init__(self, path: Path):
        self.path = path
        self.real = os.path.realpath(path)
        self.fd = None
        self.failed = 0
        self.marker = None

    def open(self):
        self.path.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.marker = _read_marker(self.fd)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def _lstat(dfd, name):
    try:
        return os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _read_regular(dfd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
    try:
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _read_marker(dfd):
    try:
        return _read_regular(dfd, MARKER_NAME).decode('ascii').strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def _anonymous_file(dfd, dir_path):
    """A file with no name yet in ``dir_path``: a killed writer leaves nothing behind."""
    try:
        return os.open(str(dir_path), os.O_TMPFILE | os.O_WRONLY | os.O_CLOEXEC, 0o600), None
    except (AttributeError, OSError):
        name = f'.ucm-files-{secrets.token_hex(8)}.tmp'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=dfd)
        return fd, name


def _replace(directory: _Dir, name: str, data: bytes, previous, default_mode: int,
             durable: bool = False) -> None:
    """``name`` holds ``data`` afterwards, by the rename of a complete file.

    The mode and owner of the file replaced are kept, set through the descriptor; when
    the owner cannot be kept nothing is replaced. Never written through a symbolic link.
    """
    dfd = directory.fd
    fd, temp = _anonymous_file(dfd, directory.path)
    try:
        if previous is not None:
            mode = stat.S_IMODE(previous.st_mode)
            if (previous.st_uid, previous.st_gid) != (os.geteuid(), os.getegid()):
                os.fchown(fd, previous.st_uid, previous.st_gid)
        else:
            mode = default_mode
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        if durable:
            os.fsync(fd)
        if temp is None:
            temp = f'.ucm-files-{secrets.token_hex(8)}.tmp'
            os.link(f'/proc/self/fd/{fd}', temp, dst_dir_fd=dfd, follow_symlinks=True)
        os.rename(temp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        temp = None
    finally:
        os.close(fd)
        if temp is not None:
            try:
                os.unlink(temp, dir_fd=dfd)
            except OSError:
                pass


def _decode_csr(csr):
    return csr.encode('utf-8') if csr.startswith('-----BEGIN') else base64.b64decode(csr)


def _wanted(kind, row, encrypting):
    """``[(path, bytes, default mode)]`` the row says should be on disk; unreadable ones logged."""
    from utils.key_codec import load_pem_bytes
    files = []
    label = f"{'CA' if kind == 'ca' else 'certificate'} {row.id}"
    paths = _named_paths(kind, row)
    try:
        if row.crt:
            files.append((paths[0], base64.b64decode(row.crt), 0o644))
    except (ValueError, TypeError) as exc:
        logger.warning("Files: the stored certificate of %s cannot be decoded (%s)", label, exc)
    if kind == 'cert' and row.csr:
        try:
            files.append((paths[1], _decode_csr(row.csr), 0o644))
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning("Files: the stored CSR of %s cannot be decoded (%s)", label, exc)
    if row.prv and not encrypting:
        try:
            files.append((paths[-1], load_pem_bytes(row.prv, context=label), 0o600))
        except ValueError as exc:
            logger.warning("Files: the stored key of %s cannot be read (%s); not mirrored",
                           label, exc)
    return files


def _row_columns(kind, model):
    columns = [model.refid, model.subject, model.descr, model.crt, model.prv]
    return columns + [model.csr] if kind == 'cert' else columns


def _wanted_of(kind, row, encrypting):
    if kind == 'ca':
        row = _CaRow(row)
    return _wanted(kind, row, encrypting)


class _CaRow:
    """A CA row read by columns, with the ``csr`` a certificate row has."""
    __slots__ = ('_row',)

    def __init__(self, row):
        self._row = row

    def __getattr__(self, name):
        return None if name == 'csr' else getattr(self._row, name)


class _Pass:
    """One reconciliation: the generation it read first, its directories, its counts."""

    def __init__(self, dirs, full, encrypting):
        self.dirs = {d.real: d for d in dirs}
        self.full = full
        self.encrypting = encrypting
        self.stats = {'ca_certs': 0, 'ca_keys': 0, 'certs': 0, 'cert_keys': 0, 'csrs': 0,
                      'removed': 0, 'failed': 0, 'refused': 0}

    def directory_of(self, path):
        return self.dirs.get(os.path.realpath(os.path.dirname(str(path))))

    def _count(self, kind, path):
        name = Path(path).name
        if name.endswith('.key'):
            self.stats['ca_keys' if kind == 'ca' else 'cert_keys'] += 1
        elif name.endswith('.csr'):
            self.stats['csrs'] += 1
        else:
            self.stats['ca_certs' if kind == 'ca' else 'certs'] += 1

    def put(self, kind, path, data, default_mode):
        """Write ``path`` when it is absent or (full pass) differs; True when written."""
        directory = self.directory_of(path)
        if directory is None or directory.fd is None:
            return False
        name = Path(path).name
        try:
            previous = _lstat(directory.fd, name)
            if previous is not None:
                if not stat.S_ISREG(previous.st_mode):
                    self.stats['refused'] += 1
                    logger.warning("Files: %s is not a regular file (a link?); left as it is",
                                   path)
                    return False
                if not self.full or _read_regular(directory.fd, name) == data:
                    return False
            _replace(directory, name, data, previous, default_mode)
        except OSError as exc:
            directory.failed += 1
            self.stats['failed'] += 1
            logger.error("Files: %s could not be written (%s); retried at the next pass",
                         path, exc)
            return False
        self._count(kind, path)
        return True

    def undo_creation(self, path, data):
        directory = self.directory_of(path)
        name = Path(path).name
        try:
            if _read_regular(directory.fd, name) == data:
                os.unlink(name, dir_fd=directory.fd)
        except OSError:
            pass

    def write_rows(self, kind, model):
        columns = _row_columns(kind, model)
        page = []
        for row in _pages(model, columns):
            page.append(row)
            if len(page) >= PAGE_SIZE:
                self._write_page(kind, model, columns, page)
                page = []
        if page:
            self._write_page(kind, model, columns, page)

    def _write_page(self, kind, model, columns, rows):
        from models import db
        written = {}
        for row in rows:
            for path, data, mode in _wanted_of(kind, row, self.encrypting):
                existed = self.directory_of(path) is not None and \
                    _lstat(self.directory_of(path).fd, path.name) is not None
                if self.put(kind, path, data, mode):
                    written.setdefault(row.id, []).append((path, data, mode, not existed))
        # Read again after the renames: a writer that committed meanwhile wins over this page
        for _round in range(3):
            if not written:
                break
            db.session.commit()
            fresh = {row.id: row for row in _pages(model, columns, ids=list(written))}
            again = {}
            for row_id, files in written.items():
                row = fresh.get(row_id)
                if row is None:
                    for path, data, _mode, created in files:
                        if created:
                            self.undo_creation(path, data)
                    continue
                now = {str(p): (d, m) for p, d, m in _wanted_of(kind, row, self.encrypting)}
                for path, data, mode, created in files:
                    current = now.get(str(path))
                    if current is not None and current[0] != data and \
                            self._overwrite(kind, path, current[0], current[1]):
                        again.setdefault(row_id, []).append((path, current[0], mode, created))
            written = again

    def _overwrite(self, kind, path, data, mode):
        full, self.full = self.full, True
        try:
            return self.put(kind, path, data, mode)
        finally:
            self.full = full

    def remove_listed(self, generation):
        """Delete the regular files the list names up to this generation; stops if a restore
        commits meanwhile (its own pass follows)."""
        from models import FileRemoval, db
        query = db.session.query(FileRemoval.id, FileRemoval.path).filter(
            FileRemoval.generation <= generation_number(generation))
        last = 0
        while True:
            page = query.filter(FileRemoval.id > last).order_by(FileRemoval.id) \
                .limit(PAGE_SIZE).all()
            if not page:
                return True
            if current_generation() != generation:
                return False
            db.session.commit()
            for entry in page:
                self._remove(entry.path)
            last = page[-1].id

    def _remove(self, path):
        directory = self.directory_of(path)
        if directory is None or directory.fd is None:
            return  # outside the managed directories: never touched
        name = Path(path).name
        try:
            found = _lstat(directory.fd, name)
            if found is None or not stat.S_ISREG(found.st_mode):
                return
            os.unlink(name, dir_fd=directory.fd)
            self.stats['removed'] += 1
        except FileNotFoundError:
            pass
        except OSError as exc:
            directory.failed += 1
            self.stats['failed'] += 1
            logger.error("Files: %s could not be removed (%s); retried at the next pass",
                         path, exc)


def _write_marker(directory: _Dir, generation: str) -> None:
    previous = _lstat(directory.fd, MARKER_NAME)
    if previous is not None and not stat.S_ISREG(previous.st_mode):
        raise OSError(errno.EEXIST, f"{MARKER_NAME} is not a regular file")
    _replace(directory, MARKER_NAME, f"{generation}\n".encode('ascii'), previous, 0o644,
             durable=True)
    os.fsync(directory.fd)


def _directory_id(directory: _Dir) -> str:
    """A random id written once in the directory: nodes sharing it share the id."""
    try:
        return _read_regular(directory.fd, DIR_ID_NAME).decode('ascii').strip()
    except FileNotFoundError:
        pass
    fd, temp = _anonymous_file(directory.fd, directory.path)
    try:
        os.write(fd, secrets.token_hex(16).encode('ascii'))
        os.fsync(fd)
        if temp is None:
            temp = f'.ucm-files-{secrets.token_hex(8)}.tmp'
            os.link(f'/proc/self/fd/{fd}', temp, dst_dir_fd=directory.fd, follow_symlinks=True)
        try:
            os.link(temp, DIR_ID_NAME, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
        except FileExistsError:
            pass  # another node wrote it first: that one is the id
    finally:
        os.close(fd)
        if temp is not None:
            os.unlink(temp, dir_fd=directory.fd)
    return _read_regular(directory.fd, DIR_ID_NAME).decode('ascii').strip()


def advisory_keys(dirs):
    """One PostgreSQL advisory lock key per directory id, sorted: shared directories collide."""
    return sorted({int.from_bytes(hashlib.sha256(
        _ADVISORY_NAMESPACE + _directory_id(d).encode()).digest()[:8], 'big', signed=True)
        for d in dirs})


class FilesBusy(Exception):
    """Another reconciliation holds a managed directory."""


@contextmanager
def _exclusive(dirs):
    """Yields whether every directory is held; never fails open."""
    from models import db
    from utils.ha import ha_enabled
    if ha_enabled() and db.engine.dialect.name == 'postgresql':
        from sqlalchemy import text
        keys = advisory_keys(dirs)
        conn = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        held = []
        try:
            for key in keys:
                if not conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar():
                    break
                held.append(key)
            yield len(held) == len(keys)
        finally:
            for key in held:
                try:
                    conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
                except Exception:
                    pass  # closing the session frees it
            conn.close()
        return
    from utils.process_lock import process_lock
    try:
        lock = process_lock(Path(Config.DATA_DIR) / LOCK_NAME, purpose='the file reconciliation',
                            subject='files', busy_error=FilesBusy, fail_open=False)
        lock.__enter__()
    except FilesBusy:
        yield False
        return
    try:
        yield True
    finally:
        lock.__exit__(None, None, None)


_RETRY = {'after': 0.0, 'delay': 0.0}
_RETRY_FIRST, _RETRY_MAX = 60.0, 3600.0


def reconcile_files(*, full=None) -> dict:
    """Make this node's managed directories match the rows.

    ``full`` (default: when a directory's marker is not the database's generation) compares
    every file and applies the removal list; otherwise only absent files are written.
    Returns the counts and ``status``: 'done', 'busy' (nothing done) or 'incomplete'.
    """
    from models import CA, Certificate, FileRemoval, db
    from security.encryption import key_encryption
    from utils.ha import ha_enabled

    dirs = [_Dir(path) for path in managed_dirs()]
    try:
        opened = []
        for directory in dirs:
            try:
                directory.open()
                opened.append(directory)
            except OSError as exc:
                logger.error("Files: %s cannot be opened (%s); retried at the next pass",
                             directory.path, exc)
        if not opened:
            return {'status': 'incomplete', 'failed': len(dirs)}
        with _exclusive(opened) as held:
            if not held:
                logger.info("Files: another reconciliation holds the directories; retried later")
                return {'status': 'busy'}
            generation = current_generation()
            for directory in opened:
                directory.marker = _read_marker(directory.fd)
            if full is None:
                full = any(d.marker != generation for d in dirs)
            encrypting = key_encryption.is_encrypting
            purged = purge_private_key_files() if encrypting else None
            if full:
                # A row created since the restore may name a listed path again: strike it first
                keep_named_paths()
                db.session.commit()
            run = _Pass(opened, full, encrypting)
            run.write_rows('ca', CA)
            run.write_rows('cert', Certificate)
            complete = len(opened) == len(dirs)
            if full:
                complete = run.remove_listed(generation) and complete
            if run.stats['ca_certs'] + run.stats['certs'] + run.stats['csrs'] + \
                    run.stats['ca_keys'] + run.stats['cert_keys'] + run.stats['removed']:
                os.sync()
            if full and complete:
                for directory in opened:
                    if directory.failed:
                        complete = False
                        continue
                    try:
                        _write_marker(directory, generation)
                    except OSError as exc:
                        complete = False
                        logger.error("Files: the marker of %s could not be written (%s)",
                                     directory.path, exc)
                if complete and not ha_enabled():
                    # One node consumes the list; in HA every node may still need it
                    db.session.query(FileRemoval).filter(
                        FileRemoval.generation <= generation_number(generation)
                    ).delete(synchronize_session=False)
            db.session.commit()
            stats = dict(run.stats, generation=generation, full=full,
                         keys_purged=purged['removed'] if purged else 0)
            stats['status'] = 'done' if complete and not run.stats['failed'] else 'incomplete'
            _note_outcome(stats)
            return stats
    except Exception:
        db.session.rollback()
        raise
    finally:
        for directory in dirs:
            directory.close()


def _note_outcome(stats):
    written = sum(stats[k] for k in ('ca_certs', 'ca_keys', 'certs', 'cert_keys', 'csrs'))
    if stats['status'] == 'done':
        _RETRY.update(after=0.0, delay=0.0)
        if written or stats['removed']:
            logger.info("Files: generation %s, %s written, %s removed", stats['generation'],
                        written, stats['removed'])
        return
    delay = min(max(_RETRY['delay'] * 2, _RETRY_FIRST), _RETRY_MAX)
    _RETRY.update(after=time.monotonic() + delay, delay=delay)
    logger.error("Files: generation %s not reached on this node (%s failed); next try in %ss",
                 stats['generation'], stats['failed'], int(delay))


def reconcile_if_behind() -> dict:
    """Per-node task: one query when every marker holds the database's generation."""
    from models import db
    generation = current_generation()
    db.session.commit()
    markers = []
    for path in managed_dirs():
        try:
            fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError:
            markers.append(None)
            continue
        try:
            markers.append(_read_marker(fd))
        finally:
            os.close(fd)
    if all(marker == generation for marker in markers):
        return {'status': 'current', 'generation': generation}
    if time.monotonic() < _RETRY['after']:
        return {'status': 'waiting', 'generation': generation}
    return reconcile_files(full=True)


def regenerate_all_files():
    """Absent files written from the rows (a full pass when this node is behind)."""
    stats = reconcile_files()
    return {key: stats.get(key, 0) for key in (
        'ca_certs', 'ca_keys', 'certs', 'cert_keys', 'csrs', 'removed', 'keys_purged')}

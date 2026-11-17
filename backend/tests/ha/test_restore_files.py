"""After a restore on A, node B's certificate files follow the database by themselves (a PEM
of the same path rewritten, the file of a removed row deleted), and the node that did not make
the archive serves its HTTPS pair. Two nodes sharing a directory (B's certificate directory
is A's) reconcile it at the same time."""
import base64
import ssl
from types import SimpleNamespace

import pytest
from cryptography import x509

from tests.ha.cluster import READY_TIMEOUT, create_ca, issue, wait_until

pytestmark = pytest.mark.ha

PASSWORD = 'ha-bench-restore-files-2026'


def _cert_names(cluster):
    """{file name: PEM bytes} the certificate rows name, as utils.file_naming builds them."""
    from utils.file_naming import _get_cn, cert_filename
    names = {}
    for refid, subject, descr, crt in cluster.sql(
            'SELECT refid, subject, descr, crt FROM certificates WHERE crt IS NOT NULL'):
        row = SimpleNamespace(refid=refid, subject=subject, descr=descr)
        cn = _get_cn(row.subject) or row.descr or ''
        names[cert_filename(refid, cn, 'crt')] = base64.b64decode(crt)
    return names


def _crt_files(node):
    return {p.name: p.read_bytes() for p in (node.data_dir / 'certs').glob('*.crt')}


def _served(node):
    pem = ssl.get_server_certificate(('127.0.0.1', node.port), timeout=10)
    return x509.load_pem_x509_certificate(pem.encode())


def _matches(node, cluster):
    files, wanted = _crt_files(node), _cert_names(cluster)
    return all(files.get(name) == data for name, data in wanted.items()) and \
        set(files) <= set(wanted)


def test_after_a_restore_on_a_every_node_holds_the_files_of_the_database(cluster, admin):
    a, b = cluster.nodes[:2]
    on_b = admin.on(b)
    ca = create_ca(admin, 'HA restore files CA')
    kept = issue(on_b, ca['id'], 'kept.restore-files.ucm-ha.test')    # B writes its file
    other = issue(on_b, ca['id'], 'other.restore-files.ucm-ha.test')
    r = admin.post('/api/v2/system/backup', {'password': PASSWORD})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']
    archive = admin.get(f'/api/v2/system/backup/{name}/download')
    assert archive.status_code == 200, archive.text[:300]
    # The archive carries the HTTPS pair of the node that made it: the leader, whichever was asked
    listed = admin.get('/api/v2/system/backups?per_page=100').json()['data']['items']
    (maker,) = [i['node'] for i in listed if i['filename'] == name]
    writer = next(node for node in cluster.nodes if node.name == maker)
    other_node = b if writer is a else a
    archived_https = (writer.data_dir / 'https_cert.pem').read_bytes()

    # The database moves on: KEPT holds another PEM on B, REMOVED is issued after the archive
    (kept_crt,) = cluster.sql('SELECT crt FROM certificates WHERE id = %s', (kept['id'],))[0]
    (other_crt,) = cluster.sql('SELECT crt FROM certificates WHERE id = %s', (other['id'],))[0]
    cluster.sql('UPDATE certificates SET crt = %s WHERE id = %s', (other_crt, kept['id']))
    kept_name = next(n for n, d in _cert_names(cluster).items()
                     if d == base64.b64decode(other_crt) and 'kept' in n)
    (b.data_dir / 'certs' / kept_name).write_bytes(base64.b64decode(other_crt))
    removed = issue(on_b, ca['id'], 'removed.restore-files.ucm-ha.test')
    removed_name = next(n for n in _crt_files(b) if n.startswith('removed.restore-files'))
    assert _served(other_node) != x509.load_pem_x509_certificate(archived_https)

    # B's certificate directory becomes A's: a directory both nodes share
    b.stop()
    shared = b.data_dir / 'certs-own'
    (b.data_dir / 'certs').rename(shared)
    (b.data_dir / 'certs').symlink_to(a.data_dir / 'certs')
    for path in shared.iterdir():
        target = a.data_dir / 'certs' / path.name
        if not target.exists():
            target.write_bytes(path.read_bytes())
    (a.data_dir / 'certs' / kept_name).write_bytes(base64.b64decode(other_crt))
    b.start()
    wait_until(b.ready, READY_TIMEOUT, 'B ready on the shared directory')

    def restore():
        # B's scheduler process acknowledges once its start is done: refused until then
        found = admin.http.post(a.url('/api/v2/system/restore'), headers=admin._headers(),
                                files={'file': (name, archive.content)},
                                data={'password': PASSWORD}, timeout=300)
        if found.status_code == 409 and 'maintenance_not_acknowledged' in found.text:
            return None
        return [found]
    (r,) = wait_until(restore, 240, 'the restore acknowledged by every node')
    assert r.status_code == 200, r.text[:1000]
    assert r.json()['data']['files']['removals'] >= 1
    assert (a.data_dir / 'certs' / kept_name).read_bytes() == base64.b64decode(other_crt), \
        'the restore wrote a file itself'

    # A's turn of the rolling restart comes first; both nodes restart then at once, as two
    # pods would, and reconcile the shared directory together
    wait_until(lambda: (a.data_dir / '.restart_requested').exists() or not a.alive(),
               READY_TIMEOUT, 'node A is asked to restart')
    for node in cluster.nodes:
        node.stop()
        (node.data_dir / '.restart_requested').unlink(missing_ok=True)
    for node in cluster.nodes:
        node.start()
    for node in cluster.nodes:
        wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')

    assert base64.b64decode(kept_crt) == _cert_names(cluster)[kept_name]
    for node in cluster.nodes:
        wait_until(lambda: _matches(node, cluster), 120, f'{node.name} files match the database')
        assert removed_name not in _crt_files(node)
        assert (node.data_dir / 'https_cert.pem').read_bytes() == archived_https, node.name
        assert _served(node) == x509.load_pem_x509_certificate(archived_https), node.name
        log = node.app_log_text()
        assert 'could not be written' not in log and 'could not be removed' not in log, node.name
    # The pair stays in the database for every node, as a regenerated one does
    assert cluster.sql("SELECT count(*) FROM shared_files WHERE name = 'https.restored'")[0][0] == 1
    assert removed['id']

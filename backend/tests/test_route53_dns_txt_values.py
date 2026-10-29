"""Route 53: UPSERT replaces the whole RRset, so create_txt_record must merge the existing TXT values."""
import pytest

from services.acme.dns_providers.route53 import Route53DnsProvider

NAME = '_acme-challenge.example.com.'


class FakeRoute53:
    """boto3 route53 client: list starts at the first name >= StartRecordName (not an exact lookup)."""

    def __init__(self):
        self.sets = {}
        self.calls = []
        self.list_error = None

    def list_hosted_zones(self):
        return {'HostedZones': [{'Id': '/hostedzone/Z1', 'Name': 'example.com.'}]}

    def list_resource_record_sets(self, HostedZoneId, StartRecordName, StartRecordType, MaxItems):
        self.calls.append('list')
        if self.list_error:
            raise self.list_error
        found = [rs for key, rs in sorted(self.sets.items()) if key[0] >= StartRecordName]
        return {'ResourceRecordSets': found[:int(MaxItems)]}

    def change_resource_record_sets(self, HostedZoneId, ChangeBatch):
        self.calls.append('change')
        for change in ChangeBatch['Changes']:
            rs = change['ResourceRecordSet']
            key = (rs['Name'], rs['Type'])
            if change['Action'] == 'UPSERT':
                self.sets[key] = {**rs, 'ResourceRecords': list(rs['ResourceRecords'])}
            elif change['Action'] == 'DELETE':
                if self.sets.get(key) != rs:
                    raise RuntimeError('InvalidChangeBatch: but it was not found')
                del self.sets[key]
        return {'ChangeInfo': {'Id': '/change/C1'}}

    def values(self, name=NAME):
        return [r['Value'] for r in self.sets[(name, 'TXT')]['ResourceRecords']]


@pytest.fixture
def api():
    fake = FakeRoute53()
    provider = Route53DnsProvider({'aws_access_key_id': 'k', 'aws_secret_access_key': 's'})
    provider._client = fake
    return provider, fake


def test_first_call_creates_quoted_value(api):
    provider, fake = api
    assert provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1', 120)[0]
    assert fake.values() == ['"tok1"']
    assert fake.sets[(NAME, 'TXT')]['TTL'] == 120


def test_second_value_keeps_the_first_and_the_existing_ttl(api):
    provider, fake = api
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1', 120)
    assert provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok2', 300)[0]
    assert fake.values() == ['"tok1"', '"tok2"']
    assert fake.sets[(NAME, 'TXT')]['TTL'] == 120


def test_other_names_are_not_mistaken_for_the_set(api):
    provider, fake = api
    fake.sets[('_acme-challenge.zzz.example.com.', 'TXT')] = {
        'Name': '_acme-challenge.zzz.example.com.', 'Type': 'TXT', 'TTL': 60,
        'ResourceRecords': [{'Value': '"other"'}]}
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')
    assert fake.values() == ['"tok1"']


def test_value_already_present_is_not_rewritten(api):
    provider, fake = api
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')
    fake.calls.clear()
    assert provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')[0]
    assert 'change' not in fake.calls
    assert fake.values() == ['"tok1"']


def test_read_failure_does_not_overwrite(api):
    provider, fake = api
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')
    fake.list_error = RuntimeError('Throttling: Rate exceeded')
    fake.calls.clear()
    ok, _ = provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok2')
    assert not ok
    assert 'change' not in fake.calls
    assert fake.values() == ['"tok1"']


def test_cleanup_removes_the_set_and_second_call_succeeds(api):
    provider, fake = api
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')
    provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok2')
    assert provider.delete_txt_record('example.com', NAME.rstrip('.'))[0]
    assert (NAME, 'TXT') not in fake.sets
    assert provider.delete_txt_record('example.com', NAME.rstrip('.'))[0]


def test_key_without_list_permission_still_writes_its_value(api):
    provider, fake = api
    fake.list_error = RuntimeError('An error occurred (AccessDenied) when calling ListResourceRecordSets')
    ok, msg = provider.create_txt_record('example.com', NAME.rstrip('.'), 'tok1')
    assert ok, msg
    assert fake.values() == ['"tok1"']

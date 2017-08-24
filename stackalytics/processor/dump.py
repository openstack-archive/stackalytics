# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pickle
import re
import sys

import memcache
from oslo_config import cfg
from oslo_log import log as logging
import six

from stackalytics.processor import config
from stackalytics.processor import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

OPTS = [
    cfg.BoolOpt('restore',
                short='r',
                help='Restore data into memcached'),
    cfg.StrOpt('file',
               short='f',
               help='The name of file to store data'),
    cfg.StrOpt('min-compress-len', default=0,
               short='m',
               help='The threshold length to kick in auto-compression'),
]


SINGLE_KEYS = ['module_groups', 'project_types', 'repos', 'releases',
               'companies', 'last_update_members_date', 'last_member_index',
               'runtime_storage_update_time']
ARRAY_KEYS = ['record', 'user']
BULK_READ_SIZE = 64
MEMCACHED_URI_PREFIX = r'^memcached:\/\/'


def read_records_from_fd(fd):
    while True:
        try:
            record = pickle.load(fd)
        except EOFError:
            break
        yield record


def store_bucket(memcached_inst, bucket):
    LOG.debug('Store bucket of records into memcached')
    res = memcached_inst.set_multi(bucket,
                                   min_compress_len=CONF.min_compress_len)
    if res:
        LOG.critical('Failed to set values in memcached: %s', res)
        raise Exception('memcached set_multi operation is failed')


def import_data(memcached_inst, fd):
    LOG.info('Importing data into memcached')
    bucket = {}
    for key, value in read_records_from_fd(fd):
        LOG.debug('Reading record key %s, value %s', key, value)
        if len(bucket) == BULK_READ_SIZE:
            store_bucket(memcached_inst, bucket)
            bucket = {}
        bucket[key] = value
    if bucket:
        store_bucket(memcached_inst, bucket)


def get_repo_keys(memcached_inst):
    for repo in (memcached_inst.get('repos') or []):
        uri = repo['uri']
        quoted_uri = six.moves.urllib.parse.quote_plus(uri)

        yield 'bug_modified_since-%s' % repo['module']

        branches = {repo.get('default_branch', 'master')}
        for release in repo.get('releases'):
            if 'branch' in release:
                branches.add(release['branch'])

        for branch in branches:
            yield 'vcs:%s:%s' % (quoted_uri, branch)
            yield 'rcs:%s:%s' % (quoted_uri, branch)


def export_data(memcached_inst, fd):
    LOG.info('Exporting data from memcached')

    for key in SINGLE_KEYS:
        pickle.dump((key, memcached_inst.get(key)), fd)

    for key in get_repo_keys(memcached_inst):
        pickle.dump((key, memcached_inst.get(key)), fd)

    for key in ARRAY_KEYS:
        key_count = key + ':count'
        count = memcached_inst.get(key_count) or 0
        pickle.dump((key_count, memcached_inst.get(key_count)), fd)

        key_prefix = key + ':'

        for record_id_set in utils.make_range(0, count + 1, BULK_READ_SIZE):
            # memcache limits the size of returned data to specific yet unknown
            # chunk size, the code should verify that all requested records are
            # returned an be able to fall back to one-by-one retrieval

            chunk = memcached_inst.get_multi(record_id_set, key_prefix)
            if len(chunk) < len(record_id_set):
                # retrieve one-by-one
                for record_id in record_id_set:
                    key = key_prefix + str(record_id)
                    pickle.dump((key, memcached_inst.get(key)), fd)
            else:
                # dump the whole chunk
                for k, v in six.iteritems(chunk):
                    pickle.dump((key_prefix + str(k), v), fd)

    for user_seq in range((memcached_inst.get('user:count') or 0) + 1):
        user = memcached_inst.get('user:%s' % user_seq)
        if user:
            if user.get('user_id'):
                pickle.dump((('user:%s' % user['user_id']).encode('utf8'),
                             user), fd)
            if user.get('launchpad_id'):
                pickle.dump(('user:%s' % user['launchpad_id'], user), fd)
            if user.get('gerrit_id'):
                pickle.dump(('user:gerrit:%s' % user['gerrit_id'], user), fd)
            if user.get('member_id'):
                pickle.dump(('user:member:%s' % user['member_id'], user), fd)
            for email in user.get('emails') or []:
                pickle.dump((('user:%s' % email).encode('utf8'), user), fd)


def _connect_to_memcached(uri):
    stripped = re.sub(MEMCACHED_URI_PREFIX, '', uri)
    if stripped:
        storage_uri = stripped.split(',')
        return memcache.Client(storage_uri)
    else:
        raise Exception('Invalid storage uri %s' % uri)


def main():
    utils.init_config_and_logging(config.CONNECTION_OPTS + OPTS)

    memcached_inst = _connect_to_memcached(CONF.runtime_storage_uri)

    filename = CONF.file

    if CONF.restore:
        if filename:
            fd = open(filename, 'r')
        else:
            fd = sys.stdin
        import_data(memcached_inst, fd)
    else:
        if filename:
            fd = open(filename, 'w')
        else:
            fd = sys.stdout
        export_data(memcached_inst, fd)


if __name__ == '__main__':
    main()

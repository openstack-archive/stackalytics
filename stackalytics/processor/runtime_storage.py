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

import re

import memcache
from oslo_log import log as logging
import six

from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

BULK_READ_SIZE = 64
BULK_DELETE_SIZE = 4096
RECORD_ID_PREFIX = 'record:'
UPDATE_ID_PREFIX = 'update:'
MEMCACHED_URI_PREFIX = r'^memcached:\/\/'


class RuntimeStorage(object):
    def __init__(self, uri):
        pass

    def set_records(self, records_iterator):
        pass

    def apply_corrections(self, corrections_iterator):
        pass

    def get_by_key(self, key):
        pass

    def set_by_key(self, key, value):
        pass

    def get_update(self, pid):
        pass

    def active_pids(self, pids):
        pass

    def get_all_records(self):
        pass


class MemcachedStorage(RuntimeStorage):
    def __init__(self, uri):
        super(MemcachedStorage, self).__init__(uri)

        stripped = re.sub(MEMCACHED_URI_PREFIX, '', uri)
        if stripped:
            storage_uri = stripped.split(',')
            self.memcached = memcache.Client(storage_uri)
            self._init_user_count()
            self.record_index = {}
        else:
            raise Exception('Invalid storage uri %s' % uri)

    def _build_index_lazily(self):
        if self.record_index:
            return
        for record in self.get_all_records():
            self.record_index[record['primary_key']] = record['record_id']

    def set_records(self, records_iterator, merge_handler=None):
        self._build_index_lazily()
        for record in records_iterator:
            if record['primary_key'] in self.record_index:
                # update
                record_id = self.record_index[record['primary_key']]
                if not merge_handler:
                    record['record_id'] = record_id
                    LOG.debug('Update record %s', record)
                    self.set_by_key(self._get_record_name(record_id), record)
                else:
                    original = self.get_by_key(self._get_record_name(
                        record_id))
                    if merge_handler(original, record):
                        LOG.debug('Update record with merge %s', record)
                        self.set_by_key(self._get_record_name(record_id),
                                        original)
            else:
                # insert record
                record_id = self._get_record_count()
                record['record_id'] = record_id
                self.record_index[record['primary_key']] = record_id
                LOG.debug('Insert new record %s', record)
                self.set_by_key(self._get_record_name(record_id), record)
                self._set_record_count(record_id + 1)

            self._commit_update(record_id)

    def apply_corrections(self, corrections_iterator):
        self._build_index_lazily()
        for correction in corrections_iterator:
            if correction['primary_key'] not in self.record_index:
                continue

            record_id = self.record_index[correction['primary_key']]
            original = self.get_by_key(self._get_record_name(record_id))
            need_update = False

            for field, value in six.iteritems(correction):
                if (field not in original) or (original[field] != value):
                    need_update = True
                    original[field] = value

            if need_update:
                self.set_by_key(self._get_record_name(record_id), original)
                self._commit_update(record_id)

    def inc_user_count(self):
        return self.memcached.incr('user:count')

    def get_all_users(self):
        for n in six.moves.range(0, self.get_by_key('user:count') + 1):
            user = self.get_by_key('user:%s' % n)
            if user:
                yield user

    def get_by_key(self, key):
        if six.PY2:
            key = key.encode('utf8')
        return self.memcached.get(key)

    def set_by_key(self, key, value):
        if six.PY2:
            key = key.encode('utf8')
        if not self.memcached.set(key, value):
            LOG.critical('Failed to store data in memcached: '
                         'key %(key)s, value %(value)s',
                         {'key': key, 'value': value})
            raise Exception('Memcached set failed')

    def delete_by_key(self, key):
        if six.PY2:
            key = key.encode('utf8')
        if not self.memcached.delete(key):
            LOG.critical('Failed to delete data from memcached: key %s', key)
            raise Exception('Memcached delete failed')

    def get_update(self, pid):
        last_update = self.get_by_key('pid:%s' % pid)
        update_count = self._get_update_count()

        self.set_by_key('pid:%s' % pid, update_count)
        self._set_pids(pid)

        if not last_update:
            for i in self.get_all_records():
                yield i
        else:
            for update_id_set in utils.make_range(last_update, update_count,
                                                  BULK_READ_SIZE):
                update_set = self.memcached.get_multi(
                    update_id_set, UPDATE_ID_PREFIX).values()
                for i in self.memcached.get_multi(
                        update_set, RECORD_ID_PREFIX).values():
                    yield i

    def active_pids(self, pids):
        stored_pids = self.get_by_key('pids') or set()
        for pid in stored_pids:
            if pid not in pids:
                LOG.debug('Purge dead uwsgi pid %s from pids list', pid)
                self.delete_by_key('pid:%s' % pid)

        self.set_by_key('pids', pids)

        # remove unneeded updates
        min_update = self._get_update_count()
        for pid in pids:
            n = self.get_by_key('pid:%s' % pid)
            if n:
                if n < min_update:
                    min_update = n

        first_valid_update = self.get_by_key('first_valid_update') or 0
        LOG.debug('Purge polled updates from %(first)s to %(min)s',
                  {'first': first_valid_update, 'min': min_update})

        for delete_id_set in utils.make_range(first_valid_update, min_update,
                                              BULK_DELETE_SIZE):
            if not self.memcached.delete_multi(delete_id_set,
                                               key_prefix=UPDATE_ID_PREFIX):
                LOG.critical('Failed to delete_multi from memcached')
                raise Exception('Failed to delete_multi from memcached')

        self.set_by_key('first_valid_update', min_update)

    def _get_update_count(self):
        return self.get_by_key('update:count') or 0

    def _set_pids(self, pid):
        pids = self.get_by_key('pids') or set()
        if pid in pids:
            return
        pids.add(pid)
        self.set_by_key('pids', pids)

    def _get_record_name(self, record_id):
        return RECORD_ID_PREFIX + str(record_id)

    def _get_record_count(self):
        return self.get_by_key('record:count') or 0

    def _set_record_count(self, count):
        self.set_by_key('record:count', count)

    def get_all_records(self):
        for record_id_set in utils.make_range(0, self._get_record_count(),
                                              BULK_READ_SIZE):
            for i in self.memcached.get_multi(
                    record_id_set, RECORD_ID_PREFIX).values():
                yield i

    def _commit_update(self, record_id):
        count = self._get_update_count()
        self.set_by_key(UPDATE_ID_PREFIX + str(count), record_id)
        self.set_by_key('update:count', count + 1)

    def _init_user_count(self):
        if not self.get_by_key('user:count'):
            self.set_by_key('user:count', 1)


def get_runtime_storage(uri):
    LOG.debug('Runtime storage is requested for uri %s', uri)
    match = re.search(MEMCACHED_URI_PREFIX, uri)
    if match:
        return MemcachedStorage(uri)
    else:
        raise Exception('Unknown runtime storage uri %s' % uri)

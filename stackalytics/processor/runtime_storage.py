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
import six

from stackalytics.openstack.common import log as logging
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
            self._build_index()
            self._init_user_count()
        else:
            raise Exception('Invalid storage uri %s' % uri)

    def _build_index(self):
        self.record_index = {}
        for record in self.get_all_records():
            self.record_index[record['primary_key']] = record['record_id']

    def set_records(self, records_iterator, merge_handler=None):
        for record in records_iterator:
            if record['primary_key'] in self.record_index:
                # update
                record_id = self.record_index[record['primary_key']]
                if not merge_handler:
                    record['record_id'] = record_id
                    LOG.debug('Update record %s', record)
                    self.memcached.set(self._get_record_name(record_id),
                                       record)
                else:
                    original = self.memcached.get(self._get_record_name(
                        record_id))
                    if merge_handler(original, record):
                        LOG.debug('Update record with merge %s', record)
                        self.memcached.set(self._get_record_name(record_id),
                                           original)
            else:
                # insert record
                record_id = self._get_record_count()
                record['record_id'] = record_id
                self.record_index[record['primary_key']] = record_id
                LOG.debug('Insert new record %s', record)
                self.memcached.set(self._get_record_name(record_id), record)
                self._set_record_count(record_id + 1)

            self._commit_update(record_id)

    def apply_corrections(self, corrections_iterator):
        for correction in corrections_iterator:
            if correction['primary_key'] not in self.record_index:
                continue

            record_id = self.record_index[correction['primary_key']]
            original = self.memcached.get(self._get_record_name(record_id))
            need_update = False

            for field, value in six.iteritems(correction):
                if (field not in original) or (original[field] != value):
                    need_update = True
                    original[field] = value

            if need_update:
                self.memcached.set(self._get_record_name(record_id), original)
                self._commit_update(record_id)

    def inc_user_count(self):
        return self.memcached.incr('user:count')

    def get_all_users(self):
        for n in xrange(0, self.get_by_key('user:count') + 1):
            user = self.get_by_key('user:%s' % n)
            if user:
                yield user

    def get_by_key(self, key):
        return self.memcached.get(key.encode('utf8'))

    def set_by_key(self, key, value):
        self.memcached.set(key.encode('utf8'), value)

    def delete_by_key(self, key):
        self.memcached.delete(key.encode('utf8'))

    def get_update(self, pid):
        last_update = self.memcached.get('pid:%s' % pid)
        update_count = self._get_update_count()

        self.memcached.set('pid:%s' % pid, update_count)
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
        stored_pids = self.memcached.get('pids') or set()
        for pid in stored_pids:
            if pid not in pids:
                LOG.debug('Purge dead uwsgi pid %s from pids list', pid)
                self.memcached.delete('pid:%s' % pid)

        self.memcached.set('pids', pids)

        # remove unneeded updates
        min_update = self._get_update_count()
        for pid in pids:
            n = self.memcached.get('pid:%s' % pid)
            if n:
                if n < min_update:
                    min_update = n

        first_valid_update = self.memcached.get('first_valid_update') or 0
        LOG.debug('Purge polled updates from %(first)s to %(min)s',
                  {'first': first_valid_update, 'min': min_update})

        for delete_id_set in utils.make_range(first_valid_update, min_update,
                                              BULK_DELETE_SIZE):
            if not self.memcached.delete_multi(delete_id_set,
                                               key_prefix=UPDATE_ID_PREFIX):
                raise Exception('Failed to delete from memcache')

        self.memcached.set('first_valid_update', min_update)

    def _get_update_count(self):
        return self.memcached.get('update:count') or 0

    def _set_pids(self, pid):
        pids = self.memcached.get('pids') or set()
        if pid in pids:
            return
        pids.add(pid)
        self.memcached.set('pids', pids)

    def _get_record_name(self, record_id):
        return RECORD_ID_PREFIX + str(record_id)

    def _get_record_count(self):
        return self.memcached.get('record:count') or 0

    def _set_record_count(self, count):
        self.memcached.set('record:count', count)

    def get_all_records(self):
        for record_id_set in utils.make_range(0, self._get_record_count(),
                                              BULK_READ_SIZE):
            for i in self.memcached.get_multi(
                    record_id_set, RECORD_ID_PREFIX).values():
                yield i

    def _commit_update(self, record_id):
        count = self._get_update_count()
        self.memcached.set(UPDATE_ID_PREFIX + str(count), record_id)
        self.memcached.set('update:count', count + 1)

    def _init_user_count(self):
        if not self.memcached.get('user:count'):
            self.memcached.set('user:count', 1)


def get_runtime_storage(uri):
    LOG.debug('Runtime storage is requested for uri %s' % uri)
    match = re.search(MEMCACHED_URI_PREFIX, uri)
    if match:
        return MemcachedStorage(uri)
    else:
        raise Exception('Unknown runtime storage uri %s' % uri)

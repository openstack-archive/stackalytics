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

import logging
import re

import pymongo

LOG = logging.getLogger(__name__)

PRIMARY_KEYS = {
    'companies': 'company_name',
    'repos': 'uri',
    'users': 'user_id',
    'releases': 'release_name',
}


class PersistentStorage(object):
    def __init__(self, uri):
        pass

    def reset(self, default_data):
        pass

    def find(self, table, **criteria):
        pass

    def insert(self, table, inst):
        pass

    def update(self, table, inst):
        pass


class MongodbStorage(PersistentStorage):
    def __init__(self, uri):
        super(MongodbStorage, self).__init__(uri)

        self.client = pymongo.MongoClient(uri)
        self.mongo = self.client.stackalytics

        for table, primary_key in PRIMARY_KEYS.iteritems():
            self.mongo[table].create_index([(primary_key, pymongo.ASCENDING)])

        LOG.debug('Mongodb storage is created')

    def reset(self, default_data):
        LOG.debug('Clear all tables')
        for table in PRIMARY_KEYS.keys():
            self.mongo[table].remove()
            if table in default_data:
                for item in default_data[table]:
                    self.insert(table, item)

    def find(self, table, **criteria):
        return self.mongo[table].find(criteria)

    def insert(self, table, inst):
        self.mongo[table].insert(inst)

    def update(self, table, inst):
        primary_key = PRIMARY_KEYS[table]
        self.mongo[table].update({primary_key: inst[primary_key]}, inst)


def get_persistent_storage(uri):
    LOG.debug('Persistent storage is requested for uri %s' % uri)
    match = re.search(r'^mongodb:\/\/', uri)
    if match:
        return MongodbStorage(uri)
    else:
        raise Exception('Unknown persistent storage uri %s' % uri)

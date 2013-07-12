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

import json
import logging
import re

import pymongo

from stackalytics.processor import user_utils

LOG = logging.getLogger(__name__)


class PersistentStorage(object):
    def __init__(self, uri):
        pass

    def sync(self, default_data_file_name, force=False):
        if force:
            self.clean_all()

        default_data = self._read_default_persistent_storage(
            default_data_file_name)

        self._build_index(default_data['repos'], 'uri',
                          self.get_repos, self.insert_repo)
        self._build_index(default_data['companies'], 'company_name',
                          self.get_companies, self.insert_company)
        self._build_index(default_data['users'], 'launchpad_id',
                          self.get_users, self.insert_user)
        self._build_index(default_data['releases'], 'release_name',
                          self.get_releases, self.insert_release)

    def _build_index(self, default_data, primary_key, getter, inserter):
        # loads all items from persistent storage
        existing_items = set([item[primary_key] for item in getter()])
        # inserts items from default storage that are not in persistent storage
        map(inserter, [item for item in default_data
                       if item[primary_key] not in existing_items])

    def get_companies(self, **criteria):
        pass

    def insert_company(self, company):
        pass

    def get_repos(self, **criteria):
        pass

    def insert_repo(self, repo):
        pass

    def get_users(self, **criteria):
        pass

    def insert_user(self, user):
        pass

    def update_user(self, user):
        pass

    def get_releases(self, **criteria):
        pass

    def insert_release(self, release):
        pass

    def clean_all(self):
        pass

    def _read_default_persistent_storage(self, file_name):
        try:
            with open(file_name, 'r') as content_file:
                content = content_file.read()
                return json.loads(content)
        except Exception as e:
            LOG.error('Error while reading config: %s' % e)


class MongodbStorage(PersistentStorage):
    def __init__(self, uri):
        super(MongodbStorage, self).__init__(uri)

        self.client = pymongo.MongoClient(uri)
        self.mongo = self.client.stackalytics

        self.mongo.companies.create_index([("company", pymongo.ASCENDING)])
        self.mongo.repos.create_index([("uri", pymongo.ASCENDING)])
        self.mongo.users.create_index([("launchpad_id", pymongo.ASCENDING)])
        self.mongo.releases.create_index([("releases", pymongo.ASCENDING)])

        LOG.debug('Mongodb storage is created')

    def clean_all(self):
        LOG.debug('Clear all tables')
        self.mongo.companies.remove()
        self.mongo.repos.remove()
        self.mongo.users.remove()
        self.mongo.releases.remove()

    def get_companies(self, **criteria):
        return self.mongo.companies.find(criteria)

    def insert_company(self, company):
        self.mongo.companies.insert(company)

    def get_repos(self, **criteria):
        return self.mongo.repos.find(criteria)

    def insert_repo(self, repo):
        self.mongo.repos.insert(repo)

    def get_users(self, **criteria):
        return self.mongo.users.find(criteria)

    def insert_user(self, user):
        self.mongo.users.insert(user_utils.normalize_user(user))

    def update_user(self, user):
        user_utils.normalize_user(user)
        launchpad_id = user['launchpad_id']
        self.mongo.users.update({'launchpad_id': launchpad_id}, user)

    def get_releases(self, **criteria):
        return self.mongo.releases.find(criteria)

    def insert_release(self, release):
        self.mongo.releases.insert(release)


def get_persistent_storage(uri):
    LOG.debug('Persistent storage is requested for uri %s' % uri)
    match = re.search(r'^mongodb:\/\/', uri)
    if match:
        return MongodbStorage(uri)
    else:
        raise Exception('Unknown persistent storage uri %s' % uri)

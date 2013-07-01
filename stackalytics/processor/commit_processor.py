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

from launchpadlib import launchpad
from oslo.config import cfg

LOG = logging.getLogger(__name__)


COMMIT_PROCESSOR_DUMMY = 0
COMMIT_PROCESSOR_CACHED = 1


class CommitProcessor(object):
    def __init__(self, persistent_storage):
        self.persistent_storage = persistent_storage

    def process(self, commit_iterator):
        pass


class DummyProcessor(CommitProcessor):
    def __init__(self, persistent_storage):
        super(DummyProcessor, self).__init__(persistent_storage)

    def process(self, commit_iterator):
        return commit_iterator


class CachedProcessor(CommitProcessor):
    def __init__(self, persistent_storage):
        super(CachedProcessor, self).__init__(persistent_storage)

        companies = persistent_storage.get_companies()
        self.domains_index = {}
        for company in companies:
            for domain in company['domains']:
                self.domains_index[domain] = company['company_name']

        users = persistent_storage.get_users()
        self.users_index = {}
        for user in users:
            for email in user['emails']:
                self.users_index[email] = user

        LOG.debug('Cached commit processor is instantiated')

    def _find_company(self, companies, date):
        for r in companies:
            if date < r['end_date']:
                return r['company_name']
        return companies[-1]['company_name']

    def _get_company_by_email(self, email):
        name, at, domain = email.partition('@')
        if domain:
            parts = domain.split('.')
            for i in range(len(parts), 1, -1):
                m = '.'.join(parts[len(parts) - i:])
                if m in self.domains_index:
                    return self.domains_index[m]
        return None

    def _unknown_user_email(self, email):

        lp_profile = None
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            LOG.debug('User email is not valid %s' % email)
        else:
            LOG.debug('Lookup user email %s at Launchpad' % email)
            lp = launchpad.Launchpad.login_anonymously(cfg.CONF.launchpad_user)
            try:
                lp_profile = lp.people.getByEmail(email=email)
            except Exception as error:
                LOG.warn('Lookup of email %s failed %s' %
                         (email, error.message))
        if not lp_profile:
            # user is not found in Launchpad, create dummy record for commit
            # update
            LOG.debug('Email is not found at Launchpad, mapping to nobody')
            user = {
                'launchpad_id': None,
                'companies': [{
                    'company_name': self.domains_index[''],
                    'end_date': 0
                }]
            }
        else:
            # get user's launchpad id from his profile
            launchpad_id = lp_profile.name
            LOG.debug('Found user %s' % launchpad_id)

            # check if user with launchpad_id exists in persistent storage
            persistent_user_iterator = self.persistent_storage.get_users(
                launchpad_id=launchpad_id)

            for persistent_user in persistent_user_iterator:
                break
            else:
                persistent_user = None

            if persistent_user:
                # user already exist, merge
                LOG.debug('User exists in persistent storage, add new email')
                persistent_user_email = persistent_user['emails'][0]
                if persistent_user_email not in self.users_index:
                    raise Exception('User index is not valid')
                user = self.users_index[persistent_user_email]
                user['emails'].append(email)
                self.persistent_storage.update_user(user)
            else:
                # add new user
                LOG.debug('Add new user into persistent storage')
                company = (self._get_company_by_email(email) or
                           self.domains_index[''])
                user = {
                    'launchpad_id': launchpad_id,
                    'user_name': lp_profile.display_name,
                    'emails': [email],
                    'companies': [{
                        'company_name': company,
                        'end_date': 0,
                    }],
                }
                self.persistent_storage.insert_user(user)

        # update local index
        self.users_index[email] = user
        return user

    def _update_commit_with_user_data(self, commit):
        email = commit['author_email'].lower()
        if email in self.users_index:
            user = self.users_index[email]
        else:
            user = self._unknown_user_email(email)
        commit['launchpad_id'] = user['launchpad_id']
        company = self._get_company_by_email(email)
        if not company:
            company = self._find_company(user['companies'], commit['date'])
        commit['company_name'] = company

    def process(self, commit_iterator):

        for commit in commit_iterator:
            self._update_commit_with_user_data(commit)

            yield commit


class CommitProcessorFactory(object):
    @staticmethod
    def get_processor(commit_processor_type, persistent_storage):
        LOG.debug('Factory is asked for commit processor type %s' %
                  commit_processor_type)
        if commit_processor_type == COMMIT_PROCESSOR_DUMMY:
            return DummyProcessor(persistent_storage)
        elif commit_processor_type == COMMIT_PROCESSOR_CACHED:
            return CachedProcessor(persistent_storage)
        else:
            raise Exception('Unknown commit processor type %s' %
                            commit_processor_type)

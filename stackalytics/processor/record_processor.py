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

import bisect
import re

from launchpadlib import launchpad
from oslo.config import cfg
from stackalytics.openstack.common import log as logging
from stackalytics.processor import default_data_processor
from stackalytics.processor import utils

LOG = logging.getLogger(__name__)

COMMIT_PROCESSOR = 1
REVIEW_PROCESSOR = 2


class RecordProcessor(object):
    def __init__(self, persistent_storage):
        self.persistent_storage = persistent_storage

    def process(self, record_iterator):
        pass


class CachedProcessor(RecordProcessor):
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

        self.releases = list(persistent_storage.get_releases())
        self.releases_dates = [r['end_date'] for r in self.releases]

    def _get_release(self, timestamp):
        release_index = bisect.bisect(self.releases_dates, timestamp)
        return self.releases[release_index]['release_name']

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

    def _persist_user(self, launchpad_id, email, user_name):
        # check if user with launchpad_id exists in persistent storage
        persistent_user_iterator = self.persistent_storage.get_users(
            launchpad_id=launchpad_id)
        for persistent_user in persistent_user_iterator:
            break
        else:
            persistent_user = None

        if persistent_user:
            # user already exist, merge
            LOG.debug('User exists in persistent storage, add new email %s',
                      email)
            persistent_user_email = persistent_user['emails'][0]
            if persistent_user_email not in self.users_index:
                return persistent_user
            user = self.users_index[persistent_user_email]
            user['emails'].append(email)
            self.persistent_storage.update_user(user)
        else:
            # add new user
            LOG.debug('Add new user into persistent storage')
            company = (self._get_company_by_email(email) or
                       self._get_independent())
            user = {
                'user_id': launchpad_id,
                'launchpad_id': launchpad_id,
                'user_name': user_name,
                'emails': [email],
                'companies': [{
                    'company_name': company,
                    'end_date': 0,
                }],
            }
            default_data_processor.normalize_user(user)
            self.persistent_storage.insert_user(user)

        return user

    def _unknown_user_email(self, email, user_name):

        lp_profile = None
        if not re.match(r'[\w\d_\.-]+@([\w\d_\.-]+\.)+[\w]+', email):
            LOG.debug('User email is not valid %s' % email)
        else:
            LOG.debug('Lookup user email %s at Launchpad' % email)
            lp = launchpad.Launchpad.login_anonymously('stackalytics',
                                                       'production')
            try:
                lp_profile = lp.people.getByEmail(email=email)
            except Exception as error:
                LOG.warn('Lookup of email %s failed %s', email, error.message)

        if not lp_profile:
            # user is not found in Launchpad, create dummy record for commit
            # update
            LOG.debug('Email is not found at Launchpad, mapping to nobody')
            user = {
                'launchpad_id': None,
                'user_id': email,
                'user_name': user_name,
                'emails': [email],
                'companies': [{
                    'company_name': self._get_independent(),
                    'end_date': 0
                }]
            }
            default_data_processor.normalize_user(user)
            # add new user
            self.persistent_storage.insert_user(user)
        else:
            # get user's launchpad id from his profile
            launchpad_id = lp_profile.name
            user_name = lp_profile.display_name
            LOG.debug('Found user %s', launchpad_id)

            user = self._persist_user(launchpad_id, email, user_name)

        # update local index
        self.users_index[email] = user
        return user

    def _get_independent(self):
        return self.domains_index['']


class CommitProcessor(CachedProcessor):
    def __init__(self, persistent_storage):
        super(CommitProcessor, self).__init__(persistent_storage)
        LOG.debug('Commit processor is instantiated')

    def _update_commit_with_user_data(self, commit):
        email = commit['author_email'].lower()
        if email in self.users_index:
            user = self.users_index[email]
        else:
            user = self._unknown_user_email(email, commit['author'])

        commit['launchpad_id'] = user['launchpad_id']
        commit['user_id'] = user['user_id']

        company = self._get_company_by_email(email)
        if not company:
            company = self._find_company(user['companies'], commit['date'])
        commit['company_name'] = company

        if 'user_name' in user:
            commit['author_name'] = user['user_name']

    def process(self, record_iterator):
        for record in record_iterator:
            self._update_commit_with_user_data(record)

            if cfg.CONF.filter_robots and record['company_name'] == '*robots':
                continue

            record['record_type'] = 'commit'
            record['primary_key'] = record['commit_id']
            record['week'] = utils.timestamp_to_week(record['date'])
            record['loc'] = record['lines_added'] + record['lines_deleted']

            if not record['release']:
                record['release'] = self._get_release(record['date'])

            yield record


class ReviewProcessor(CachedProcessor):
    def __init__(self, persistent_storage):
        super(ReviewProcessor, self).__init__(persistent_storage)

        self.launchpad_to_company_index = {}
        users = persistent_storage.get_users()
        for user in users:
            self.launchpad_to_company_index[user['launchpad_id']] = user

        LOG.debug('Review processor is instantiated')

    def _process_user(self, email, launchpad_id, user_name, date):
        if email in self.users_index:
            user = self.users_index[email]
        else:
            user = self._persist_user(launchpad_id, email, user_name)
            self.users_index[email] = user

        company = self._get_company_by_email(email)
        if not company:
            company = self._find_company(user['companies'], date)
        return company, user['user_id']

    def _spawn_review(self, record):
        # copy everything except pathsets and flatten user data
        review = dict([(k, v) for k, v in record.iteritems()
                       if k not in ['patchSets', 'owner']])
        owner = record['owner']
        if 'email' not in owner or 'username' not in owner:
            return  # ignore

        review['record_type'] = 'review'
        review['primary_key'] = review['id']
        review['launchpad_id'] = owner['username']
        review['author'] = owner['name']
        review['author_email'] = owner['email'].lower()
        review['release'] = self._get_release(review['createdOn'])
        review['week'] = utils.timestamp_to_week(review['createdOn'])

        company, user_id = self._process_user(review['author_email'],
                                              review['launchpad_id'],
                                              review['author'],
                                              review['createdOn'])
        review['company_name'] = company
        review['user_id'] = user_id
        yield review

    def _spawn_marks(self, record):
        review_id = record['id']
        module = record['module']

        for patch in record['patchSets']:
            if 'approvals' not in patch:
                continue  # not reviewed by anyone
            for approval in patch['approvals']:
                # copy everything and flatten user data
                mark = dict([(k, v) for k, v in approval.iteritems()
                             if k != 'by'])
                reviewer = approval['by']

                if 'email' not in reviewer or 'username' not in reviewer:
                    continue  # ignore

                mark['record_type'] = 'mark'
                mark['primary_key'] = (record['id'] +
                                       str(mark['grantedOn']) +
                                       mark['type'])
                mark['launchpad_id'] = reviewer['username']
                mark['author'] = reviewer['name']
                mark['author_email'] = reviewer['email'].lower()
                mark['module'] = module
                mark['review_id'] = review_id
                mark['release'] = self._get_release(mark['grantedOn'])
                mark['week'] = utils.timestamp_to_week(mark['grantedOn'])

                company, user_id = self._process_user(mark['author_email'],
                                                      mark['launchpad_id'],
                                                      mark['author'],
                                                      mark['grantedOn'])
                mark['company_name'] = company
                mark['user_id'] = user_id

                yield mark

    def process(self, record_iterator):
        """
         Process a review. Review spawns into records of two types:
          * review - records that a user created review request
          * mark - records that a user set approval mark to given review
        """
        for record in record_iterator:
            for gen in [self._spawn_review, self._spawn_marks]:
                for r in gen(record):
                    yield r


def get_record_processor(processor_type, persistent_storage):
    LOG.debug('Record processor is requested of type %s' % processor_type)
    if processor_type == COMMIT_PROCESSOR:
        return CommitProcessor(persistent_storage)
    elif processor_type == REVIEW_PROCESSOR:
        return ReviewProcessor(persistent_storage)
    else:
        raise Exception('Unknown commit processor type %s' % processor_type)

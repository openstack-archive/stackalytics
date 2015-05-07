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
import collections
import copy
import time

from oslo_log import log as logging
import six

from stackalytics.processor import launchpad_utils
from stackalytics.processor import user_processor
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)


class RecordProcessor(object):
    def __init__(self, runtime_storage_inst):
        self.runtime_storage_inst = runtime_storage_inst

        self.domains_index = runtime_storage_inst.get_by_key('companies')

        self.releases = runtime_storage_inst.get_by_key('releases')
        self.releases_dates = [r['end_date'] for r in self.releases]

        self.modules = None
        self.alias_module_map = None

    def _get_release(self, timestamp):
        release_index = bisect.bisect(self.releases_dates, timestamp)
        if release_index >= len(self.releases):
            LOG.warn('Timestamp %s is beyond releases boundaries, the last '
                     'release will be used. Please consider adding a '
                     'new release into default_data.json', timestamp)
            release_index = len(self.releases) - 1
        return self.releases[release_index]['release_name']

    def _get_modules(self):
        if self.modules is None:
            self.modules = set()
            self.alias_module_map = dict()

            for repo in utils.load_repos(self.runtime_storage_inst):
                module = repo['module'].lower()
                module_aliases = repo.get('aliases') or []

                add = True
                for module_name in ([module] + module_aliases):
                    for m in self.modules:
                        if module_name.find(m) >= 0:
                            add = False
                            break
                        if m.find(module_name) >= 0:
                            self.modules.remove(m)
                            break
                    if add:
                        self.modules.add(module_name)

                for alias in module_aliases:
                    self.alias_module_map[alias] = module

        return self.modules, self.alias_module_map

    def _find_company(self, companies, date):
        for r in companies:
            if date < r['end_date']:
                return r['company_name'], 'strict'
        return companies[-1]['company_name'], 'open'  # may be overridden

    def _get_company_by_email(self, email):
        if not email:
            return None

        name, at, domain = email.partition('@')
        if domain:
            parts = domain.split('.')
            for i in range(len(parts), 1, -1):
                m = '.'.join(parts[len(parts) - i:])
                if m in self.domains_index:
                    return self.domains_index[m]
        return None

    def _create_user(self, launchpad_id, email, gerrit_id, user_name):
        company = (self._get_company_by_email(email) or
                   self._get_independent())
        emails = []
        if email:
            emails = [email]
        user = {
            'user_id': user_processor.make_user_id(
                emails=emails, launchpad_id=launchpad_id, gerrit_id=gerrit_id),
            'launchpad_id': launchpad_id,
            'user_name': user_name or '',
            'companies': [{
                'company_name': company,
                'end_date': 0,
            }],
            'emails': emails,
        }
        if gerrit_id:
            user['gerrit_id'] = gerrit_id
        return user

    def _get_lp_info(self, email):
        lp_profile = None
        if not utils.check_email_validity(email):
            LOG.debug('User email is not valid %s', email)
        else:
            lp_profile = launchpad_utils.lp_profile_by_email(email)

        if not lp_profile:
            LOG.debug('User with email %s not found', email)
            return None, None

        LOG.debug('Email %(email)s is mapped to launchpad user %(lp)s',
                  {'email': email, 'lp': lp_profile['name']})
        return lp_profile['name'], lp_profile['display_name']

    def _get_lp_user_name(self, launchpad_id):
        if not launchpad_id:
            return None

        lp_profile = launchpad_utils.lp_profile_by_launchpad_id(launchpad_id)

        if not lp_profile:
            LOG.debug('User with id %s not found', launchpad_id)
            return launchpad_id

        return lp_profile['display_name']

    def _get_independent(self):
        return '*independent'

    def _update_user_affiliation(self, user):
        for email in user.get('emails'):
            company_name = self._get_company_by_email(email)
            uc = user['companies']
            if (company_name and (len(uc) == 1) and
                    (uc[0]['company_name'] == self._get_independent())):
                LOG.debug('Updating affiliation of user %s to %s',
                          user['user_id'], company_name)
                uc[0]['company_name'] = company_name
                break

    def _get_user_exact_company(self, user):
        if len(user.get('companies', [])) == 1:
            return user['companies'][0]['company_name']
        return None

    def _merge_user_profiles(self, user_profiles):
        LOG.debug('Merge profiles: %s', user_profiles)

        # check of there are more than 1 launchpad_id nor gerrit_id
        lp_ids = set(u.get('launchpad_id') for u in user_profiles
                     if u.get('launchpad_id'))
        if len(lp_ids) > 1:
            LOG.info('Ambiguous launchpad ids: %s on profiles: %s',
                     lp_ids, user_profiles)
        g_ids = set(u.get('gerrit_id') for u in user_profiles
                    if u.get('gerrit_id'))
        if len(g_ids) > 1:
            LOG.info('Ambiguous gerrit ids: %s on profiles: %s',
                     g_ids, user_profiles)

        merged_user = {}  # merged user profile

        # collect ordinary fields
        for key in ['seq', 'user_name', 'user_id', 'gerrit_id', 'github_id',
                    'launchpad_id', 'companies', 'static', 'ldap_id']:
            value = next((v.get(key) for v in user_profiles if v.get(key)),
                         None)
            if value:
                merged_user[key] = value

        # update user_id, prefer it to be equal to launchpad_id
        merged_user['user_id'] = (merged_user.get('launchpad_id') or
                                  merged_user.get('user_id'))

        # merge emails
        emails = set([])
        core_in = set([])
        for u in user_profiles:
            emails |= set(u.get('emails', []))
            core_in |= set(u.get('core', []))
        merged_user['emails'] = list(emails)
        if core_in:
            merged_user['core'] = list(core_in)

        # merge companies
        merged_companies = merged_user['companies']
        for u in user_profiles:
            companies = u.get('companies')
            if companies:
                if (companies[0]['company_name'] != self._get_independent() or
                        len(companies) > 1):
                    merged_companies = companies
                    break
        merged_user['companies'] = merged_companies

        self._update_user_affiliation(merged_user)

        seqs = set(u.get('seq') for u in user_profiles if u.get('seq'))
        if len(seqs) > 1:
            # profiles are merged, keep only one, remove others
            seqs.remove(merged_user['seq'])

            for u in user_profiles:
                if u.get('seq') in seqs:
                    LOG.debug('Delete user: %s', u)
                    user_processor.delete_user(
                        self.runtime_storage_inst, u)
        return merged_user

    def update_user(self, record):
        email = record.get('author_email')
        user_e = user_processor.load_user(
            self.runtime_storage_inst, email=email) or {}

        user_name = record.get('author_name')
        launchpad_id = record.get('launchpad_id')
        if (email and (not user_e) and (not launchpad_id) and
                (not user_e.get('launchpad_id'))):
            # query LP
            launchpad_id, lp_user_name = self._get_lp_info(email)
            if lp_user_name:
                user_name = lp_user_name

        gerrit_id = record.get('gerrit_id')
        if gerrit_id:
            user_g = user_processor.load_user(
                self.runtime_storage_inst, gerrit_id=gerrit_id) or {}
            if ((not user_g) and (not launchpad_id) and
                    (not user_e.get('launchpad_id'))):
                # query LP
                guessed_lp_id = gerrit_id
                lp_user_name = self._get_lp_user_name(guessed_lp_id)
                if lp_user_name == user_name:
                    launchpad_id = guessed_lp_id
        else:
            user_g = {}

        user_l = user_processor.load_user(
            self.runtime_storage_inst, launchpad_id=launchpad_id) or {}

        if ((user_e.get('seq') == user_l.get('seq') == user_g.get('seq')) and
                user_e.get('seq')):
            # sequence numbers are set and the same, merge is not needed
            user = user_e
        else:
            user = self._create_user(launchpad_id, email, gerrit_id, user_name)

            if user_e or user_l or user_g:
                user = self._merge_user_profiles(
                    [user_e, user_l, user_g, user])
            else:
                # create new
                if not user_name:
                    user_name = self._get_lp_user_name(launchpad_id)
                    if user_name:
                        user['user_name'] = user_name
                LOG.debug('Created new user: %s', user)

            user_processor.store_user(self.runtime_storage_inst, user)
            LOG.debug('Stored user: %s', user)

        return user

    def _update_record_and_user(self, record):
        user = self.update_user(record)

        record['user_id'] = user['user_id']
        if user.get('user_name'):
            record['author_name'] = user['user_name']

        company, policy = self._find_company(user['companies'], record['date'])
        if not user.get('static'):
            # for auto-generated profiles affiliation may be overridden
            if company != '*robots' and policy == 'open':
                company = (self._get_company_by_email(
                    record.get('author_email')) or company)
        record['company_name'] = company

    def _process_commit(self, record):
        record['primary_key'] = record['commit_id']
        record['loc'] = record['lines_added'] + record['lines_deleted']
        record['author_email'] = record['author_email'].lower()
        record['commit_date'] = record['date']

        coauthors = record.get('coauthor')
        if not coauthors:
            self._update_record_and_user(record)

            if record['company_name'] != '*robots':
                yield record
        else:
            if record['author_email'] not in [
                    c['author_email'] for c in coauthors]:
                coauthors.append({'author_name': record['author_name'],
                                  'author_email': record['author_email']})
            for coauthor in coauthors:
                coauthor['date'] = record['date']
                self._update_record_and_user(coauthor)

            for coauthor in coauthors:
                new_record = copy.deepcopy(record)
                new_record.update(coauthor)
                new_record['primary_key'] += coauthor['author_email']

                yield new_record

    def _make_review_record(self, record):
        # copy everything except patchsets and flatten user data
        review = dict([(k, v) for k, v in six.iteritems(record)
                       if k not in ['patchSets', 'owner', 'createdOn',
                                    'comments']])
        owner = record['owner']

        review['primary_key'] = review['id']
        if owner.get('username'):
            review['gerrit_id'] = owner['username']
        review['author_name'] = owner['name']
        if owner.get('email'):
            review['author_email'] = owner['email'].lower()
        review['date'] = record['createdOn']

        patch_sets = record.get('patchSets', [])
        review['updated_on'] = review['date']
        if patch_sets:
            patch = patch_sets[-1]
            if 'approvals' in patch:
                review['value'] = min([int(p['value'])
                                       for p in patch['approvals']])
                review['updated_on'] = patch['approvals'][0]['grantedOn']
            else:
                review['updated_on'] = patch['createdOn']

        if 'value' not in review:
            review['value'] = 0

        self._update_record_and_user(review)
        return review

    def _make_patch_record(self, review, patch):
        patch_record = dict()
        patch_record['record_type'] = 'patch'
        patch_record['primary_key'] = utils.get_patch_id(
            review['id'], patch['number'])
        patch_record['number'] = patch['number']
        patch_record['date'] = patch['createdOn']
        uploader = patch['uploader']
        if uploader.get('username'):
            patch_record['gerrit_id'] = uploader['username']
        patch_record['author_name'] = uploader['name']
        if uploader.get('email'):
            patch_record['author_email'] = uploader['email'].lower()
        patch_record['module'] = review['module']
        patch_record['branch'] = review['branch']
        patch_record['review_id'] = review['id']

        self._update_record_and_user(patch_record)
        return patch_record

    def _make_mark_record(self, review, patch, approval):
        # copy everything and flatten user data
        mark = dict([(k, v) for k, v in six.iteritems(approval)
                     if k not in ['by', 'grantedOn', 'value', 'description']])
        reviewer = approval['by']

        mark['record_type'] = 'mark'
        mark['value'] = int(approval['value'])
        mark['date'] = approval['grantedOn']
        mark['primary_key'] = (review['id'] + str(mark['date']) + mark['type'])
        mark['gerrit_id'] = reviewer['username']
        mark['author_name'] = reviewer['name']
        mark['author_email'] = reviewer['email'].lower()
        mark['module'] = review['module']
        mark['branch'] = review['branch']
        mark['review_id'] = review['id']
        mark['patch'] = int(patch['number'])

        self._update_record_and_user(mark)
        return mark

    def _process_review(self, record):
        """Process a review.

        Review spawns into records of three types:
          * review - records that a user created review request
          * patch - records that a user submitted another patch set
          * mark - records that a user set approval mark to given review
        """
        owner = record['owner']
        if 'email' in owner or 'username' in owner:
            yield self._make_review_record(record)

        for patch in record.get('patchSets', []):
            if (('email' in patch['uploader']) or
                    ('username' in patch['uploader'])):
                yield self._make_patch_record(record, patch)

            if 'approvals' not in patch:
                continue  # not reviewed by anyone

            for approval in patch['approvals']:
                if approval['type'] not in ('Code-Review', 'Workflow'):
                    continue  # keep only Code-Review and Workflow
                if ('email' not in approval['by'] or
                        'username' not in approval['by']):
                    continue  # ignore

                yield self._make_mark_record(record, patch, approval)

    def _guess_module(self, record):
        subject = record['subject'].lower()
        pos = len(subject)
        best_guess_module = None

        modules, alias_module_map = self._get_modules()
        for module in modules:
            find = subject.find(module)
            if (find >= 0) and (find < pos):
                pos = find
                best_guess_module = module

        if best_guess_module:
            if (((pos > 0) and (subject[pos - 1] == '[')) or
                    (not record.get('module'))):
                record['module'] = best_guess_module

        if not record.get('module'):
            record['module'] = 'unknown'
        elif record['module'] in alias_module_map:
            record['module'] = alias_module_map[record['module']]

    def _process_email(self, record):
        record['primary_key'] = record['message_id']
        record['author_email'] = record['author_email'].lower()

        self._update_record_and_user(record)
        self._guess_module(record)

        if not record.get('blueprint_id'):
            del record['body']

        yield record

    def _process_blueprint(self, record):
        bpd_author = record.get('drafter') or record.get('owner')

        bpd = dict([(k, v) for k, v in six.iteritems(record)
                    if k.find('_link') < 0])
        bpd['record_type'] = 'bpd'
        bpd['primary_key'] = 'bpd:' + record['id']
        bpd['launchpad_id'] = bpd_author
        bpd['date'] = record['date_created']

        self._update_record_and_user(bpd)

        yield bpd

        if (record.get('assignee') and record['date_completed'] and
                record.get('implementation_status') == 'Implemented'):
            bpc = dict([(k, v) for k, v in six.iteritems(record)
                        if k.find('_link') < 0])
            bpc['record_type'] = 'bpc'
            bpc['primary_key'] = 'bpc:' + record['id']
            bpc['launchpad_id'] = record['assignee']
            bpc['date'] = record['date_completed']

            self._update_record_and_user(bpc)

            yield bpc

    def _process_bug(self, record):

        bug_created = record.copy()
        bug_created['primary_key'] = 'bugf:' + record['id']
        bug_created['record_type'] = 'bugf'
        bug_created['launchpad_id'] = record.get('owner')
        bug_created['date'] = record['date_created']

        self._update_record_and_user(bug_created)

        yield bug_created

        FIXED_BUGS = ['Fix Committed', 'Fix Released']
        if 'date_fix_committed' in record and record['status'] in FIXED_BUGS:
            bug_fixed = record.copy()
            bug_fixed['primary_key'] = 'bugr:' + record['id']
            bug_fixed['record_type'] = 'bugr'
            bug_fixed['launchpad_id'] = record.get('assignee') or '*unassigned'
            bug_fixed['date'] = record['date_fix_committed']

            self._update_record_and_user(bug_fixed)

            yield bug_fixed

    def _process_member(self, record):
        user_id = user_processor.make_user_id(member_id=record['member_id'])
        record['primary_key'] = user_id
        record['date'] = utils.member_date_to_timestamp(record['date_joined'])
        record['author_name'] = record['member_name']
        record['module'] = 'unknown'
        company_draft = record['company_draft']

        company_name = self.domains_index.get(utils.normalize_company_name(
            company_draft)) or (utils.normalize_company_draft(company_draft))

        # author_email is a key to create new user
        record['author_email'] = user_id
        record['company_name'] = company_name
        # _update_record_and_user function will create new user if needed
        self._update_record_and_user(record)
        record['company_name'] = company_name
        user = user_processor.load_user(self.runtime_storage_inst, user_id)

        user['user_name'] = record['author_name']
        user['companies'] = [{
            'company_name': company_name,
            'end_date': 0,
        }]
        user['company_name'] = company_name

        user_processor.store_user(self.runtime_storage_inst, user)

        record['company_name'] = company_name

        yield record

    def _process_ci(self, record):
        ci_vote = dict((k, v) for k, v in six.iteritems(record)
                       if k not in ['reviewer'])

        reviewer = record['reviewer']
        ci_vote['primary_key'] = ('%s:%s' % (reviewer['username'],
                                  ci_vote['date']))
        ci_vote['user_id'] = reviewer['username']
        ci_vote['gerrit_id'] = reviewer['username']
        ci_vote['author_name'] = reviewer.get('name') or reviewer['username']
        ci_vote['author_email'] = (
            reviewer.get('email') or reviewer['username']).lower()

        self._update_record_and_user(ci_vote)

        yield ci_vote

    def _renew_record_date(self, record):
        record['week'] = utils.timestamp_to_week(record['date'])
        if ('release' not in record) or (not record['release']):
            record['release'] = self._get_release(record['date'])

    def process(self, record_iterator):
        PROCESSORS = {
            'commit': self._process_commit,
            'review': self._process_review,
            'email': self._process_email,
            'bp': self._process_blueprint,
            'bug': self._process_bug,
            'member': self._process_member,
            'ci_vote': self._process_ci,
        }

        for record in record_iterator:
            for r in PROCESSORS[record['record_type']](record):
                self._renew_record_date(r)
                yield r

    def _update_records_with_releases(self, release_index):
        LOG.debug('Update records with releases')

        for record in self.runtime_storage_inst.get_all_records():
            if record['primary_key'] in release_index:
                release = release_index[record['primary_key']]
            else:
                release = self._get_release(record['date'])

            if record['release'] != release:
                record['release'] = release
                yield record

    def _update_records_with_user_info(self):
        LOG.debug('Update user info in records')

        for record in self.runtime_storage_inst.get_all_records():
            company_name = record['company_name']
            user_id = record['user_id']
            author_name = record['author_name']

            self._update_record_and_user(record)

            if ((record['company_name'] != company_name) or
                    (record['user_id'] != user_id) or
                    (record['author_name'] != author_name)):
                LOG.debug('User info (%(id)s, %(name)s, %(company)s) has '
                          'changed in record %(record)s',
                          {'id': user_id, 'name': author_name,
                           'company': company_name, 'record': record})
                yield record

    def _update_commits_with_merge_date(self):
        LOG.debug('Update commits with merge date')

        change_id_to_date = {}
        for record in self.runtime_storage_inst.get_all_records():
            if (record['record_type'] == 'review' and
                    record.get('status') == 'MERGED'):
                change_id_to_date[record['id']] = record['lastUpdated']

        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] == 'commit':
                change_id_list = record.get('change_id')
                if change_id_list and len(change_id_list) == 1:
                    change_id = change_id_list[0]
                    if change_id in change_id_to_date:
                        old_date = record['date']
                        if old_date != change_id_to_date[change_id]:
                            record['date'] = change_id_to_date[change_id]
                            self._renew_record_date(record)
                            LOG.debug('Date %(date)s has changed in record '
                                      '%(record)s', {'date': old_date,
                                                     'record': record})
                            yield record

    def _update_blueprints_with_mention_info(self):
        LOG.debug('Process blueprints and calculate mention info')

        valid_blueprints = {}
        mentioned_blueprints = {}
        for record in self.runtime_storage_inst.get_all_records():
            for bp in record.get('blueprint_id', []):
                if bp in mentioned_blueprints:
                    mentioned_blueprints[bp]['count'] += 1
                    if record['date'] > mentioned_blueprints[bp]['date']:
                        mentioned_blueprints[bp]['date'] = record['date']
                else:
                    mentioned_blueprints[bp] = {
                        'count': 1,
                        'date': record['date']
                    }
            if record['record_type'] in ['bpd', 'bpc']:
                valid_blueprints[record['id']] = {
                    'primary_key': record['primary_key'],
                    'count': 0,
                    'date': record['date']
                }

        for bp_name, bp in six.iteritems(valid_blueprints):
            if bp_name in mentioned_blueprints:
                bp['count'] = mentioned_blueprints[bp_name]['count']
                bp['date'] = mentioned_blueprints[bp_name]['date']
            else:
                bp['count'] = 0
                bp['date'] = 0

        for record in self.runtime_storage_inst.get_all_records():
            need_update = False

            valid_bp = set([])
            for bp in record.get('blueprint_id', []):
                if bp in valid_blueprints:
                    valid_bp.add(bp)
                else:
                    LOG.debug('Update record %s: removed invalid bp: %s',
                              record['primary_key'], bp)
                    need_update = True
            record['blueprint_id'] = list(valid_bp)

            if record['record_type'] in ['bpd', 'bpc']:
                bp = valid_blueprints[record['id']]
                if ((record.get('mention_count') != bp['count']) or
                        (record.get('mention_date') != bp['date'])):
                    record['mention_count'] = bp['count']
                    record['mention_date'] = bp['date']
                    LOG.debug('Update record %s: mention stats: (%s:%s)',
                              record['primary_key'], bp['count'], bp['date'])
                    need_update = True

            if need_update:
                yield record

    def _update_reviews_with_sequence_number(self):
        LOG.debug('Set review number in review records')

        users_reviews = collections.defaultdict(list)
        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] == 'review':
                user_id = record.get('user_id')
                review = {'date': record['date'], 'id': record['id']}
                users_reviews[user_id].append(review)

        reviews_index = {}
        for reviews in six.itervalues(users_reviews):
            reviews.sort(key=lambda x: x['date'])
            review_number = 0
            for review in reviews:
                review_number += 1
                review['review_number'] = review_number
                reviews_index[review['id']] = review

        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] == 'review':
                review = reviews_index[record['id']]
                if record.get('review_number') != review['review_number']:
                    record['review_number'] = review['review_number']
                    yield record

    def _determine_core_contributors(self):
        LOG.debug('Determine core contributors')

        module_branches = collections.defaultdict(set)
        quarter_ago = int(time.time()) - 60 * 60 * 24 * 30 * 3  # a quarter ago

        for record in self.runtime_storage_inst.get_all_records():
            if (record['record_type'] == 'mark' and
                    record['date'] > quarter_ago and
                    record['value'] in [2, -2]):
                module_branch = (record['module'], record['branch'])
                user_id = record['user_id']
                module_branches[user_id].add(module_branch)

        for user in self.runtime_storage_inst.get_all_users():
            core_old = user.get('core')
            user_module_branch = module_branches.get(user['user_id'])
            if user_module_branch:
                user['core'] = list(user_module_branch)
            elif user.get('core'):
                del user['core']

            if user.get('core') != core_old:
                user_processor.store_user(self.runtime_storage_inst, user)

    def _close_patch(self, cores, marks):
        if len(marks) < 2:
            return

        core_mark = 0
        for mark in sorted(marks, key=lambda x: x['date'], reverse=True):

            if core_mark == 0:
                if (mark['module'], mark['branch'], mark['user_id']) in cores:
                    # mark is from core engineer
                    core_mark = mark['value']
                    continue

            disagreement = ((core_mark != 0) and
                            ((core_mark < 0 < mark['value']) or
                             (core_mark > 0 > mark['value'])))
            old_disagreement = mark.get('disagreement', False)
            mark['disagreement'] = disagreement
            if old_disagreement != disagreement:
                yield mark

    def _update_marks_with_disagreement(self):
        LOG.debug('Process marks to find disagreements')

        cores = set()
        for user in self.runtime_storage_inst.get_all_users():
            for (module, branch) in (user.get('core') or []):
                cores.add((module, branch, user['user_id']))

        # map from review_id to current patch and list of marks
        marks_per_patch = collections.defaultdict(
            lambda: {'patch_number': 0, 'marks': []})

        for record in self.runtime_storage_inst.get_all_records():
            if (record['record_type'] == 'mark' and
                    record['type'] == 'Code-Review'):
                review_id = record['review_id']
                patch_number = record['patch']

                if review_id in marks_per_patch:
                    # review is already seen, check if patch is newer
                    if (marks_per_patch[review_id]['patch_number'] <
                            patch_number):
                        # the patch is new, close the current
                        for processed in self._close_patch(
                                cores, marks_per_patch[review_id]['marks']):
                            yield processed
                        del marks_per_patch[review_id]

                marks_per_patch[review_id]['patch_number'] = patch_number
                marks_per_patch[review_id]['marks'].append(record)

        # purge the rest
        for marks_patch in marks_per_patch.values():
            for processed in self._close_patch(cores, marks_patch['marks']):
                yield processed

    def _update_members_company_name(self):
        LOG.debug('Update members with company names')

        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] != 'member':
                continue

            company_draft = record['company_draft']
            company_name = self.domains_index.get(
                utils.normalize_company_name(company_draft)) or (
                    utils.normalize_company_draft(company_draft))

            if company_name == record['company_name']:
                continue

            LOG.debug('Update record %s, company name changed to %s',
                      record, company_name)
            record['company_name'] = company_name

            yield record

            user = user_processor.load_user(self.runtime_storage_inst,
                                            record['user_id'])
            LOG.debug('Update user %s, company name changed to %s',
                      user, company_name)
            user['companies'] = [{
                'company_name': company_name,
                'end_date': 0,
            }]
            user_processor.store_user(self.runtime_storage_inst, user)

    def _update_self_made_marks(self):
        LOG.debug('Update self-made marks')
        patch_id_to_user_id = {}
        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] == 'patch':
                patch_id_to_user_id[record['primary_key']] = record['user_id']

        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] != 'mark':
                continue

            patch_id = utils.get_patch_id(record['review_id'], record['patch'])
            if record['user_id'] == patch_id_to_user_id.get(patch_id):
                if record['type'].find('Self-') < 0:
                    record['type'] = 'Self-%s' % record['type']
                    yield record

    def post_processing(self, release_index):
        self.runtime_storage_inst.set_records(
            self._update_records_with_user_info())

        self.runtime_storage_inst.set_records(
            self._update_commits_with_merge_date())

        self.runtime_storage_inst.set_records(
            self._update_records_with_releases(release_index))

        self.runtime_storage_inst.set_records(
            self._update_reviews_with_sequence_number())

        self.runtime_storage_inst.set_records(
            self._update_blueprints_with_mention_info())

        self._determine_core_contributors()

        # disagreement calculation must go after determining core contributors
        self.runtime_storage_inst.set_records(
            self._update_marks_with_disagreement())

        self.runtime_storage_inst.set_records(
            self._update_members_company_name())

        self.runtime_storage_inst.set_records(self._update_self_made_marks())

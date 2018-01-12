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

import copy

from oslo_log import log as logging

from stackalytics.processor import utils

LOG = logging.getLogger(__name__)

INDEPENDENT = '*independent'
ROBOTS = '*robots'


def make_user_id(emails=None, launchpad_id=None, gerrit_id=None,
                 member_id=None, github_id=None, zanata_id=None):
    if launchpad_id or emails:
        return launchpad_id or emails[0]
    if gerrit_id:
        return 'gerrit:%s' % gerrit_id
    if member_id:
        return 'member:%s' % member_id
    if github_id:
        return 'github:%s' % github_id
    if zanata_id:
        return 'zanata:%s' % zanata_id
    return None


def store_user(runtime_storage_inst, user):
    if not user.get('seq'):
        user['seq'] = runtime_storage_inst.inc_user_count()
        LOG.debug('New user: %s', user)

    runtime_storage_inst.set_by_key('user:%d' % user['seq'], user)
    if user.get('user_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['user_id'], user)
    if user.get('launchpad_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['launchpad_id'], user)
    if user.get('gerrit_id'):
        runtime_storage_inst.set_by_key('user:gerrit:%s' % user['gerrit_id'],
                                        user)
    if user.get('github_id'):
        runtime_storage_inst.set_by_key('user:github:%s' % user['github_id'],
                                        user)
    if user.get('zanata_id'):
        runtime_storage_inst.set_by_key('user:zanata:%s' % user['zanata_id'],
                                        user)
    for email in user.get('emails') or []:
        runtime_storage_inst.set_by_key('user:%s' % email, user)


def load_user(runtime_storage_inst, seq=None, user_id=None, email=None,
              launchpad_id=None, gerrit_id=None, member_id=None,
              github_id=None, zanata_id=None):

    key = make_user_id(gerrit_id=gerrit_id, member_id=member_id,
                       github_id=github_id, zanata_id=zanata_id)
    if not key:
        key = seq or user_id or launchpad_id or email
    if key:
        return runtime_storage_inst.get_by_key('user:%s' % key)
    return None


def delete_users(runtime_storage_inst, users):
    for user in users:
        LOG.debug('Delete user: %s', user)
        runtime_storage_inst.delete_by_key('user:%s' % user['seq'])


def update_user_profile(stored_user, user):
    # update stored_user with user and return it
    if stored_user:
        updated_user = copy.deepcopy(stored_user)
        updated_user.update(user)
        updated_user['emails'] = list(set(stored_user.get('emails', [])) |
                                      set(user.get('emails', [])))
    else:
        updated_user = copy.deepcopy(user)
    updated_user['static'] = True
    return updated_user


def get_company_for_date(companies, date):
    for r in companies:
        if date < r['end_date']:
            return r['company_name'], 'strict'
    return companies[-1]['company_name'], 'open'  # may be overridden


def get_company_by_email(domains_index, email):
    """Get company based on email domain

    Automatically maps email domain into company name. Prefers
    subdomains to root domains.

    :param domains_index: dict {domain -> company name}
    :param email: valid email. may be empty
    :return: company name or None if nothing matches
    """
    if not email:
        return None

    name, at, domain = email.partition('@')
    if domain:
        parts = domain.split('.')
        for i in range(len(parts), 1, -1):
            m = '.'.join(parts[len(parts) - i:])
            if m in domains_index:
                return domains_index[m]
    return None


def create_user(domains_index, launchpad_id, email, gerrit_id, zanata_id,
                user_name):
    company = get_company_by_email(domains_index, email) or INDEPENDENT
    emails = [email] if email else []

    user = {
        'user_id': make_user_id(
            emails=emails, launchpad_id=launchpad_id, gerrit_id=gerrit_id,
            zanata_id=zanata_id),
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
    if zanata_id:
        user['zanata_id'] = zanata_id

    return user


def update_user_affiliation(domains_index, user):
    """Update user affiliation

    Affiliation is updated only if user is currently independent
    but makes contribution from company domain.

    :param domains_index: dict {domain -> company name}
    :param user: user profile
    """
    for email in user.get('emails'):
        company_name = get_company_by_email(domains_index, email)

        uc = user['companies']
        if (company_name and (len(uc) == 1) and
                (uc[0]['company_name'] == INDEPENDENT)):
            LOG.debug('Updating affiliation of user %s to %s',
                      user['user_id'], company_name)
            uc[0]['company_name'] = company_name
            break


def merge_user_profiles(domains_index, user_profiles):
    """Merge user profiles into one

    The function merges list of user profiles into one figures out which
    profiles can be deleted.

    :param domains_index: dict {domain -> company name}
    :param user_profiles: user profiles to merge
    :return: tuple (merged user profile, [user profiles to delete])
    """
    LOG.debug('Merge profiles: %s', user_profiles)

    # check of there are more than 1 launchpad_id nor gerrit_id
    lp_ids = set(u.get('launchpad_id') for u in user_profiles
                 if u.get('launchpad_id'))
    if len(lp_ids) > 1:
        LOG.debug('Ambiguous launchpad ids: %s on profiles: %s',
                  lp_ids, user_profiles)
    g_ids = set(u.get('gerrit_id') for u in user_profiles
                if u.get('gerrit_id'))
    if len(g_ids) > 1:
        LOG.debug('Ambiguous gerrit ids: %s on profiles: %s',
                  g_ids, user_profiles)

    merged_user = {}  # merged user profile

    # collect ordinary fields
    for key in ['seq', 'user_name', 'user_id', 'gerrit_id', 'github_id',
                'launchpad_id', 'companies', 'static', 'zanata_id']:
        value = next((v.get(key) for v in user_profiles if v.get(key)),
                     None)
        if value:
            merged_user[key] = value

    # update user_id, prefer it to be equal to launchpad_id
    merged_user['user_id'] = (merged_user.get('launchpad_id') or
                              merged_user.get('user_id'))

    # always preserve `user_name` since its required field
    if 'user_name' not in merged_user:
        merged_user['user_name'] = merged_user['user_id']

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
            if (companies[0]['company_name'] != INDEPENDENT or
                    len(companies) > 1):
                merged_companies = companies
                break
    merged_user['companies'] = merged_companies

    update_user_affiliation(domains_index, merged_user)

    users_to_delete = []
    seqs = set(u.get('seq') for u in user_profiles if u.get('seq'))

    if len(seqs) > 1:
        # profiles are merged, keep only one, remove others
        seqs.remove(merged_user['seq'])

        for u in user_profiles:
            if u.get('seq') in seqs:
                users_to_delete.append(u)

    return merged_user, users_to_delete


def are_users_same(users):
    """True if all users are the same and not Nones"""
    x = set(u.get('seq') for u in users)
    return len(x) == 1 and None not in x


def resolve_companies_aliases(domains_index, companies):
    norm_companies = []

    prev_company_name = None
    for c in reversed(companies):
        company_name = c['company_name']
        company_name = (domains_index.get(
            utils.normalize_company_name(company_name))
            or (utils.normalize_company_draft(company_name)))

        if company_name != prev_company_name:
            r = copy.deepcopy(c)
            r['company_name'] = company_name
            norm_companies.append(r)

        prev_company_name = company_name

    return list(reversed(norm_companies))

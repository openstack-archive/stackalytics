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

import datetime
import operator
import re
import time

import six

from stackalytics.dashboard import parameters
from stackalytics.dashboard import vault
from stackalytics.processor import utils


INFINITY_HTML = '&#x221E;'


def _extend_author_fields(record):
    record['author_link'] = make_link(
        record['author_name'], '/',
        {'user_id': record['user_id'], 'company': ''})
    record['company_link'] = make_link(
        record['company_name'], '/',
        {'company': record['company_name'], 'user_id': ''})


def _extend_record_common_fields(record):
    _extend_author_fields(record)
    record['date_str'] = format_datetime(record['date'])
    record['module_link'] = make_link(
        record['module'], '/',
        {'module': record['module'], 'company': '', 'user_id': ''})
    record['blueprint_id_count'] = len(record.get('blueprint_id', []))
    record['bug_id_count'] = len(record.get('bug_id', []))

    for coauthor in record.get('coauthor') or []:
        _extend_author_fields(coauthor)


def _extend_by_parent_info(record, parent, prefix='parent_'):
    parent = vault.extend_record(parent)
    _extend_record_common_fields(parent)
    for k, v in six.iteritems(parent):
        record[prefix + k] = v


def extend_record(record):
    record = vault.extend_record(record)
    _extend_record_common_fields(record)

    if record['record_type'] == 'commit':
        record['branches'] = ','.join(record['branches'])
        if 'correction_comment' not in record:
            record['correction_comment'] = ''
        record['message'] = make_commit_message(record)
        if record['commit_date']:
            record['commit_date_str'] = format_datetime(record['commit_date'])
    elif record['record_type'] == 'mark':
        review = vault.get_memory_storage().get_record_by_primary_key(
            record['review_id'])
        patch = vault.get_memory_storage().get_record_by_primary_key(
            utils.get_patch_id(record['review_id'], record['patch']))
        if not review or not patch:
            return None

        _extend_by_parent_info(record, review, 'parent_')
        _extend_by_parent_info(record, patch, 'patch_')
    elif record['record_type'] == 'patch':
        review = vault.get_memory_storage().get_record_by_primary_key(
            record['review_id'])
        _extend_by_parent_info(record, review, 'parent_')
    elif record['record_type'] == 'email':
        record['email_link'] = record.get('email_link') or ''
        record['blueprint_links'] = []
        for bp_id in record.get('blueprint_id', []):
            bp_module, bp_name = bp_id.split(':')
            record['blueprint_links'].append(
                make_blueprint_link(bp_module, bp_name))
    elif record['record_type'] in ['bpd', 'bpc']:
        record['summary'] = utils.format_text(record['summary'])
        if record.get('mention_count'):
            record['mention_date_str'] = format_datetime(
                record['mention_date'])
        record['blueprint_link'] = make_blueprint_link(record['module'],
                                                       record['name'])
    elif record['record_type'] in ['bugr', 'bugf']:
        record['number'] = record['web_link'].split('/')[-1]
        record['title'] = filter_bug_title(record['title'])
        record['status_class'] = re.sub('\s+', '', record['status'])

    elif record['record_type'] == 'tr':
        record['date_str'] = format_date(record['date'])  # no need for hours

    return record


def get_current_company(user):
    now = time.time()
    idx = -1
    for i, r in enumerate(user['companies']):
        if now < r['end_date']:
            idx = i
    return user['companies'][idx]['company_name']


def extend_user(user):
    user = user.copy()

    user['id'] = user['user_id']
    user['text'] = user['user_name']
    if user['companies']:
        company_name = get_current_company(user)
        user['company_link'] = make_link(
            company_name, '/', {'company': company_name, 'user_id': ''})
    else:
        user['company_link'] = ''

    return user


def extend_module(module_id, project_type, release):
    module_id_index = vault.get_vault()['module_id_index']
    module_id = module_id.lower()

    if module_id not in module_id_index:
        return None

    repos_index = vault.get_vault()['repos_index']

    module = module_id_index[module_id]
    name = module['module_group_name']
    if name[0].islower():
        name = name.capitalize()

    # (module, release) pairs
    own_sub_modules = set(vault.resolve_modules([module_id], [release]))
    visible_sub_modules = own_sub_modules & set(vault.resolve_modules(
        vault.resolve_project_types([project_type]), [release]))

    child_modules = []
    for m, r in own_sub_modules:
        child = {'module_name': m, 'visible': (m, r) in visible_sub_modules}
        if m in repos_index:
            child['repo_uri'] = repos_index[m]['uri']
        child_modules.append(child)

    child_modules.sort(key=lambda x: x['module_name'])

    return {
        'id': module_id,
        'name': name,
        'tag': module['tag'],
        'modules': child_modules,
    }


def get_activity(records, start_record, page_size, query_message=None):
    if query_message:
        # note that all records are now dicts!
        key_func = operator.itemgetter('date')
        records = [vault.extend_record(r) for r in records]
        records = [r for r in records
                   if (r.get('message') and
                       r.get('message').find(query_message) > 0)]
    else:
        key_func = operator.attrgetter('date')

    records_sorted = sorted(records, key=key_func, reverse=True)

    result = []
    for record in records_sorted[start_record:]:
        processed_record = extend_record(record)
        if processed_record:
            result.append(processed_record)
            if len(result) == page_size:
                break

    return result


def get_contribution_summary(records):
    marks = dict((m, 0) for m in [-2, -1, 0, 1, 2, 'A', 'WIP', 'x', 's'])
    commit_count = 0
    loc = 0
    drafted_blueprint_count = 0
    completed_blueprint_count = 0
    email_count = 0
    filed_bug_count = 0
    resolved_bug_count = 0
    patch_set_count = 0
    change_request_count = 0
    abandoned_change_requests_count = 0
    translations = 0

    for record in records:
        record_type = record.record_type
        if record_type == 'commit':
            commit_count += 1
            loc += record.loc
        elif record_type == 'mark':
            value = 0
            if record.type == 'Workflow':
                if record.value == 1:
                    value = 'A'
                else:
                    value = 'WIP'
            elif record.type == 'Code-Review':
                value = record.value
            elif record.type == 'Abandon':
                value = 'x'
            elif record.type[:5] == 'Self-':
                value = 's'
            marks[value] += 1
        elif record_type == 'email':
            email_count += 1
        elif record_type == 'bpd':
            drafted_blueprint_count += 1
        elif record_type == 'bpc':
            completed_blueprint_count += 1
        elif record_type == 'bugf':
            filed_bug_count += 1
        elif record_type == 'bugr':
            resolved_bug_count += 1
        elif record_type == 'patch':
            patch_set_count += 1
        elif record_type == 'review':
            change_request_count += 1
            if record.status == 'ABANDONED':
                abandoned_change_requests_count += 1
        elif record_type == 'tr':
            translations += record.loc

    result = {
        'drafted_blueprint_count': drafted_blueprint_count,
        'completed_blueprint_count': completed_blueprint_count,
        'commit_count': commit_count,
        'email_count': email_count,
        'loc': loc,
        'marks': marks,
        'filed_bug_count': filed_bug_count,
        'resolved_bug_count': resolved_bug_count,
        'patch_set_count': patch_set_count,
        'change_request_count': change_request_count,
        'abandoned_change_requests_count': abandoned_change_requests_count,
        'translations': translations,
    }
    return result


def format_datetime(timestamp):
    return datetime.datetime.utcfromtimestamp(
        timestamp).strftime('%d %b %Y %H:%M:%S') + ' UTC'


def format_date(timestamp):
    return datetime.datetime.utcfromtimestamp(timestamp).strftime('%d %b %Y')


def format_launchpad_module_link(module):
    return '<a href="https://launchpad.net/%s">%s</a>' % (module, module)


def make_link(title, uri=None, options=None):
    param_names = ('release', 'project_type', 'module', 'company', 'user_id',
                   'metric')
    param_values = {}
    for param_name in param_names:
        value = parameters.get_parameter({}, param_name)
        if value:
            param_values[param_name] = ','.join(value)
    if options:
        param_values.update(options)
    if param_values:
        uri += '?' + '&'.join(['%s=%s' % (n, utils.safe_encode(v))
                               for n, v in six.iteritems(param_values)])
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': title}


def make_blueprint_link(module, name):
    uri = '/report/blueprint/' + module + '/' + name
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': name}


def make_commit_message(record):
    s = record['message']
    module = record['module']

    s = utils.format_text(s)

    # insert links
    s = re.sub(re.compile('(blueprint\s+)([\w-]+)', flags=re.IGNORECASE),
               r'\1<a href="https://blueprints.launchpad.net/' +
               module + r'/+spec/\2" class="ext_link">\2</a>', s)
    s = re.sub(re.compile('(bug[\s#:]*)([\d]{5,7})', flags=re.IGNORECASE),
               r'\1<a href="https://bugs.launchpad.net/bugs/\2" '
               r'class="ext_link">\2</a>', s)
    s = re.sub(r'\s+(I[0-9a-f]{40})',
               r' <a href="https://review.openstack.org/#q,\1,n,z" '
               r'class="ext_link">\1</a>', s)

    s = utils.unwrap_text(s)
    return s


def make_page_title(project_type_inst, release, module_inst, company,
                    user_inst):
    pt_class = project_type_inst['id']
    if project_type_inst.get('parent'):
        pt_class = project_type_inst['parent']['id']
    is_openstack = pt_class == 'all' or pt_class[:9] == 'openstack'

    if company or user_inst:
        if user_inst:
            s = user_inst['user_name']
            if company:
                s += ' (%s)' % company
        else:
            s = company
    else:
        if is_openstack:
            s = 'OpenStack community'
        else:
            s = project_type_inst['title'] + ' community'
    s += ' contribution'
    if module_inst:
        s += ' to %s' % module_inst['module_group_name']
    if is_openstack:
        s += ' in'
        if release != 'all':
            if company or user_inst:
                s += ' OpenStack'
            s += ' %s release' % release.capitalize()
        else:
            s += ' all releases'
    else:
        if release != 'all':
            s += ' during OpenStack %s release' % release.capitalize()
    return s


def filter_bug_title(title):
    return re.sub(r'^(?:Bug #\d+.+:\s+)"(.*)"', r'\1', title)

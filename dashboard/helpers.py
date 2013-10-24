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
import re
import urllib

from flask.ext import gravatar as gravatar_ext

from dashboard import parameters
from dashboard import vault
from stackalytics.processor import utils


gravatar = gravatar_ext.Gravatar(None, size=64, rating='g', default='wavatar')


def _extend_record_common_fields(record):
    record['date_str'] = format_datetime(record['date'])
    record['author_link'] = make_link(
        record['author_name'], '/',
        {'user_id': record['user_id'], 'company': ''})
    record['company_link'] = make_link(
        record['company_name'], '/',
        {'company': record['company_name'], 'user_id': ''})
    record['module_link'] = make_link(
        record['module'], '/',
        {'module': record['module'], 'company': '', 'user_id': ''})
    record['gravatar'] = gravatar(record.get('author_email', 'stackalytics'))
    record['blueprint_id_count'] = len(record.get('blueprint_id', []))
    record['bug_id_count'] = len(record.get('bug_id', []))


def extend_record(record):
    if record['record_type'] == 'commit':
        commit = record.copy()
        commit['branches'] = ','.join(commit['branches'])
        if 'correction_comment' not in commit:
            commit['correction_comment'] = ''
        commit['message'] = make_commit_message(record)
        _extend_record_common_fields(commit)
        return commit
    elif record['record_type'] == 'mark':
        review = record.copy()
        parent = vault.get_memory_storage().get_record_by_primary_key(
            review['review_id'])
        if parent:
            review['review_number'] = parent.get('review_number')
            review['subject'] = parent['subject']
            review['url'] = parent['url']
            review['parent_author_link'] = make_link(
                parent['author_name'], '/',
                {'user_id': parent['user_id'],
                 'company': ''})
            _extend_record_common_fields(review)
            return review
    elif record['record_type'] == 'email':
        email = record.copy()
        _extend_record_common_fields(email)
        email['email_link'] = email.get('email_link') or ''
        return email
    elif ((record['record_type'] == 'bpd') or
          (record['record_type'] == 'bpc')):
        blueprint = record.copy()
        _extend_record_common_fields(blueprint)
        blueprint['summary'] = utils.format_text(record['summary'])
        if record.get('mention_count'):
            blueprint['mention_date_str'] = format_datetime(
                record['mention_date'])
        blueprint['blueprint_link'] = make_blueprint_link(
            blueprint['name'], blueprint['module'])
        return blueprint


def format_datetime(timestamp):
    return datetime.datetime.utcfromtimestamp(
        timestamp).strftime('%d %b %Y %H:%M:%S')


def format_date(timestamp):
    return datetime.datetime.utcfromtimestamp(timestamp).strftime('%d-%b-%y')


def format_launchpad_module_link(module):
    return '<a href="https://launchpad.net/%s">%s</a>' % (module, module)


def safe_encode(s):
    return urllib.quote_plus(s.encode('utf-8'))


def make_link(title, uri=None, options=None):
    param_names = ('release', 'project_type', 'module', 'company', 'user_id',
                   'metric')
    param_values = {}
    for param_name in param_names:
        v = parameters.get_parameter({}, param_name, param_name)
        if v:
            param_values[param_name] = ','.join(v)
    if options:
        param_values.update(options)
    if param_values:
        uri += '?' + '&'.join(['%s=%s' % (n, safe_encode(v))
                               for n, v in param_values.iteritems()])
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': title}


def make_blueprint_link(name, module):
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


def make_page_title(company, user_id, module, release):
    if company:
        memory_storage = vault.get_memory_storage()
        company = memory_storage.get_original_company_name(company)
    if company or user_id:
        if user_id:
            s = vault.get_user_from_runtime_storage(user_id)['user_name']
            if company:
                s += ' (%s)' % company
        else:
            s = company
    else:
        s = 'OpenStack community'
    s += ' contribution'
    if module:
        s += ' to %s' % module
    if release != 'all':
        s += ' in %s release' % release.capitalize()
    else:
        s += ' in all releases'
    return s

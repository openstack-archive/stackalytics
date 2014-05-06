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

import cgi
import datetime
import json
import re
import time

import iso8601
import six
from six.moves.urllib import parse
from six.moves.urllib import request

from stackalytics.openstack.common import log as logging


LOG = logging.getLogger(__name__)


def date_to_timestamp(d):
    if not d:
        return 0
    if d == 'now':
        return int(time.time())
    return int(time.mktime(
        datetime.datetime.strptime(d, '%Y-%b-%d').timetuple()))


def date_to_timestamp_ext(d):
    try:
        return date_to_timestamp(d)
    except ValueError:
        return int(d)


def member_date_to_timestamp(d):
    if not d:
        return 0
    return int(time.mktime(
        datetime.datetime.strptime(d, '%B %d, %Y ').timetuple()))


def iso8601_to_timestamp(s):
    return int(time.mktime(iso8601.parse_date(s).timetuple()))


def timestamp_to_week(timestamp):
    # Jan 4th 1970 is the first Sunday in the Epoch
    return (timestamp - 3 * 24 * 3600) // (7 * 24 * 3600)


def week_to_date(week):
    timestamp = week * 7 * 24 * 3600 + 3 * 24 * 3600
    return (datetime.datetime.fromtimestamp(timestamp).
            strftime('%Y-%m-%d %H:%M:%S'))


def check_email_validity(email):
    if email:
        return re.match(r'[\w\d_\.-]+@([\w\d_\.-]+\.)+[\w]+', email)
    return False


def read_uri(uri):
    try:
        fd = request.urlopen(uri)
        raw = fd.read()
        fd.close()
        return raw
    except Exception as e:
        LOG.warn('Error while reading uri: %s' % e)


def read_json_from_uri(uri):
    try:
        return json.loads(read_uri(uri))
    except Exception as e:
        LOG.warn('Error parsing json: %s' % e)


def make_range(start, stop, step):
    last_full = stop - ((stop - start) % step)
    for i in xrange(start, last_full, step):
        yield xrange(i, i + step)
    if stop > last_full:
        yield xrange(last_full, stop)


def store_user(runtime_storage_inst, user):
    if not user.get('seq'):
        user['seq'] = runtime_storage_inst.inc_user_count()
    runtime_storage_inst.set_by_key('user:%s' % user['seq'], user)
    if user.get('user_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['user_id'], user)
    if user.get('launchpad_id'):
        runtime_storage_inst.set_by_key('user:%s' % user['launchpad_id'], user)
    for email in user.get('emails') or []:
        runtime_storage_inst.set_by_key('user:%s' % email, user)


def load_user(runtime_storage_inst, user_id):
    if user_id:
        return runtime_storage_inst.get_by_key('user:%s' % user_id)
    return None


def delete_user(runtime_storage_inst, user):
    runtime_storage_inst.delete_by_key('user:%s' % user['seq'])


def load_repos(runtime_storage_inst):
    return runtime_storage_inst.get_by_key('repos') or []


def unwrap_text(text):
    res = ''
    for line in text.splitlines():
        s = line.rstrip()
        if not s:
            continue
        res += line
        if (not s[0].isalpha()) or (s[-1] in ['.', '!', '?', '>', ':', ';']):
            res += '\n'
        else:
            res += ' '
    return res.rstrip()


def format_text(s):
    s = cgi.escape(re.sub(re.compile('\n{2,}', flags=re.MULTILINE), '\n', s))
    s = re.sub(r'([/\/\*=~]{1,2}|--|\+\+)', r'\1&#8203;', s)
    return s


def make_age_string(seconds):
    days = seconds / (3600 * 24)
    hours = (seconds / 3600) - (days * 24)
    minutes = (seconds / 60) - (days * 24 * 60) - (hours * 60)
    return '%d days, %d hours, %d minutes' % (days, hours, minutes)


def merge_records(original, new):
    need_update = False
    for key, value in six.iteritems(new):
        if original.get(key) != value:
            need_update = True
            original[key] = value
    return need_update


def get_blueprint_id(module, name):
    return module + ':' + name


def get_patch_id(review_id, patch_number):
    return review_id + ':' + patch_number


def add_index(sequence, start=1, item_filter=lambda x: True):
    n = start
    for item in sequence:
        if item_filter(item):
            item['index'] = n
            n += 1
        else:
            item['index'] = ''
    return sequence


def safe_encode(s):
    return parse.quote_plus(s.encode('utf-8'))


def make_module_group(module_group_id, name=None, modules=None, tag='module'):
    return {'id': module_group_id,
            'module_group_name': name or module_group_id,
            'modules': modules or [module_group_id],
            'tag': tag}

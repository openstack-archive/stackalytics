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
import iso8601
import json
import re
import time
import urllib

from stackalytics.openstack.common import log as logging


LOG = logging.getLogger(__name__)


def date_to_timestamp(d):
    if d == 'now':
        return int(time.time())
    return int(time.mktime(
        datetime.datetime.strptime(d, '%Y-%b-%d').timetuple()))


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
        fd = urllib.urlopen(uri)
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
    s = re.sub(r'([/\/\*=]{1,2}|--|\+\+)', r'\1&#8203;', s)
    return s


def merge_records(original, new):
    need_update = False
    for key, value in new.iteritems():
        if original.get(key) != value:
            need_update = True
            original[key] = value
    return need_update

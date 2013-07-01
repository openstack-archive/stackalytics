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
import time


def normalize_user(user):
    user['emails'] = [email.lower() for email in user['emails']]
    user['launchpad_id'] = user['launchpad_id'].lower()

    for c in user['companies']:
        end_date_numeric = 0
        if c['end_date']:
            end_date_numeric = date_to_timestamp(c['end_date'])
        c['end_date'] = end_date_numeric

    # sort companies by end_date
    def end_date_comparator(x, y):
        if x["end_date"] == 0:
            return 1
        elif y["end_date"] == 0:
            return -1
        else:
            return cmp(x["end_date"], y["end_date"])

    user['companies'].sort(cmp=end_date_comparator)
    return user


def date_to_timestamp(d):
    if d == 'now':
        return int(time.time())
    return int(time.mktime(
        datetime.datetime.strptime(d, '%Y-%b-%d').timetuple()))


def timestamp_to_week(timestamp):
    # Jan 4th 1970 is the first Sunday in the Epoch
    return (timestamp - 3 * 24 * 3600) // (7 * 24 * 3600)


def week_to_date(week):
    timestamp = week * 7 * 24 * 3600 + 3 * 24 * 3600
    return (datetime.datetime.fromtimestamp(timestamp).
            strftime('%Y-%m-%d %H:%M:%S'))

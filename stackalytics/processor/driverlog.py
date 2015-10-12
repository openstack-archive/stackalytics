# Copyright (c) 2014 Mirantis Inc.
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

import re

from oslo_log import log as logging
from stackalytics.processor import user_processor

LOG = logging.getLogger(__name__)


def _find_ci_result(review, drivers):
    """For a given stream of reviews yields results produced by CIs."""

    review_id = review['id']
    review_number = review['number']

    ci_id_set = set(d['ci']['id'] for d in drivers)
    candidate_drivers = [d for d in drivers]

    last_patch_set_number = review['patchSets'][-1]['number']

    for comment in reversed(review.get('comments') or []):
        comment_author = comment['reviewer'].get('username')
        if comment_author not in ci_id_set:
            continue  # not any of registered CIs

        message = comment['message']

        prefix = 'Patch Set'
        if comment['message'].find(prefix) != 0:
            continue  # look for special messages only

        prefix = 'Patch Set %s:' % last_patch_set_number
        if comment['message'].find(prefix) != 0:
            break  # all comments from the latest patch set already parsed
        message = message[len(prefix):].strip()

        result = None
        matched_drivers = set()

        for driver in candidate_drivers:
            ci = driver['ci']
            if ci['id'] != comment_author:
                continue

            # try to get result by parsing comment message
            success_pattern = ci.get('success_pattern')
            failure_pattern = ci.get('failure_pattern')

            message_lines = (l for l in message.split('\n') if l.strip())

            line = ''
            for line in message_lines:
                if success_pattern and re.search(success_pattern, line):
                    result = True
                    break
                elif failure_pattern and re.search(failure_pattern, line):
                    result = False
                    break

            if result is not None:
                matched_drivers.add(driver['name'])
                record = {
                    'user_id': user_processor.make_user_id(
                        ci_id=driver['name']),
                    'value': result,
                    'message': line,
                    'date': comment['timestamp'],
                    'branch': review['branch'],
                    'review_id': review_id,
                    'review_number': review_number,
                    'driver_name': driver['name'],
                    'driver_vendor': driver['vendor'],
                    'module': review['module']
                }
                if review['branch'].find('/') > 0:
                    record['release'] = review['branch'].split('/')[1]

                yield record

        candidate_drivers = [d for d in candidate_drivers
                             if d['name'] not in matched_drivers]
        if not candidate_drivers:
            break  # found results from all drivers


def log(review_iterator, drivers):
    for record in review_iterator:
        for driver_info in _find_ci_result(record, drivers):
            yield driver_info

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

LOG = logging.getLogger(__name__)


def _find_vote(review, ci_id, patch_set_number):
    """Finds vote corresponding to ci_id."""
    for patch_set in review['patchSets']:
        if patch_set['number'] == patch_set_number:
            for approval in (patch_set.get('approvals') or []):
                if approval['type'] not in ['Verified', 'VRIF']:
                    continue

                if approval['by'].get('username') == ci_id:
                    return approval['value'] in ['1', '2']

    return None


def find_ci_result(review, ci_map):
    """For a given stream of reviews yields results produced by CIs."""

    review_id = review['id']
    review_number = review['number']
    ci_already_seen = set()

    for comment in reversed(review.get('comments') or []):
        reviewer_id = comment['reviewer'].get('username')
        if reviewer_id not in ci_map:
            continue

        message = comment['message']
        m = re.match(r'Patch Set (?P<number>\d+):(?P<message>.*)',
                     message, flags=re.DOTALL)
        if not m:
            continue  # do not understand comment

        patch_set_number = m.groupdict()['number']
        message = m.groupdict()['message'].strip()

        result = None
        ci = ci_map[reviewer_id]['ci']

        # try to get result by parsing comment message
        success_pattern = ci.get('success_pattern')
        failure_pattern = ci.get('failure_pattern')

        if success_pattern and re.search(success_pattern, message):
            result = True
        elif failure_pattern and re.search(failure_pattern, message):
            result = False

        # try to get result from vote
        if result is None:
            result = _find_vote(review, ci['id'], patch_set_number)

        if result is not None:
            is_merged = (
                review['status'] == 'MERGED' and
                patch_set_number == review['patchSets'][-1]['number'] and
                ci['id'] not in ci_already_seen)

            ci_already_seen.add(ci['id'])

            yield {
                'reviewer': comment['reviewer'],
                'ci_result': result,
                'is_merged': is_merged,
                'message': message,
                'date': comment['timestamp'],
                'review_id': review_id,
                'review_number': review_number,
                'driver_name': ci_map[reviewer_id]['name'],
                'driver_vendor': ci_map[reviewer_id]['vendor'],
            }

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

import operator
import time

import flask

from dashboard import decorators
from dashboard import helpers
from dashboard import vault
from stackalytics.processor import utils


blueprint = flask.Blueprint('reports', __name__, url_prefix='/report')


@blueprint.route('/blueprint/<module>/<blueprint_name>')
@decorators.templated()
@decorators.exception_handler()
def blueprint_summary(module, blueprint_name):
    blueprint_id = module + ':' + blueprint_name
    bpd = vault.get_memory_storage().get_record_by_primary_key(
        'bpd:' + blueprint_id)
    if not bpd:
        flask.abort(404)
        return

    bpd = helpers.extend_record(bpd)
    record_ids = vault.get_memory_storage().get_record_ids_by_blueprint_ids(
        [blueprint_id])
    activity = [helpers.extend_record(record) for record in
                vault.get_memory_storage().get_records(record_ids)]
    activity.sort(key=lambda x: x['date'], reverse=True)

    return {'blueprint': bpd, 'activity': activity}


@blueprint.route('/reviews/<module>')
@decorators.templated()
@decorators.exception_handler()
def open_reviews(module):
    memory_storage = vault.get_memory_storage()
    now = int(time.time())
    review_ids = (memory_storage.get_record_ids_by_modules([module]) &
                  memory_storage.get_record_ids_by_type('review'))
    records = []
    for review in memory_storage.get_records(review_ids):
        if review['status'] != 'NEW':
            continue
        processed_review = review.copy()
        helpers.extend_record(processed_review)
        processed_review['age'] = utils.make_age_string(
            now - processed_review['date'])
        records.append(processed_review)

    return {
        'module': module,
        'oldest': sorted(records, key=operator.itemgetter('date'))[:5]
    }


@blueprint.route('/large_commits')
@decorators.jsonify('commits')
@decorators.exception_handler()
@decorators.record_filter()
def get_commit_report(records):
    loc_threshold = int(flask.request.args.get('loc_threshold') or 0)
    response = []
    for record in records:
        if ('loc' in record) and (record['loc'] > loc_threshold):
            nr = dict([(k, record[k]) for k in ['loc', 'subject', 'module',
                                                'primary_key', 'change_id']])
            response.append(nr)
    return response

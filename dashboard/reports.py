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
import json

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


def _get_day(timestamp, time_now):
    return int((time_now - timestamp) / 60 / 60 / 24)


def _process_stat(data, key, time_now):
    if not data:
        return None

    data = sorted(data, key=operator.itemgetter(key))

    days = _get_day(data[0][key], time_now)
    chart_data = [0] * (days + 1)
    sum_ages = 0
    for review in data:
        age = time_now - review[key]
        sum_ages += age
        review[key + '_age'] = utils.make_age_string(age)
        chart_data[_get_day(review[key], time_now)] += 1

    return {
        'reviews': data,
        'average': utils.make_age_string(sum_ages / len(data)),
        'max': data[0][key + '_age'],
        'chart_data': json.dumps(chart_data),
    }


@blueprint.route('/reviews/<module>')
@decorators.templated()
@decorators.exception_handler()
def open_reviews(module):
    memory_storage_inst = vault.get_memory_storage()
    time_now = int(time.time())

    module_id_index = vault.get_vault()['module_id_index']
    module = module.lower()
    if module in module_id_index:
        modules = module_id_index[module]['modules']
    else:
        modules = [module]

    review_ids = (memory_storage_inst.get_record_ids_by_modules(modules) &
                  memory_storage_inst.get_record_ids_by_type('review'))

    waiting_on_reviewer = []
    total_open = 0

    for review in memory_storage_inst.get_records(review_ids):
        if review['status'] == 'NEW':
            total_open += 1
            if review['value'] in [1, 2]:
                waiting_on_reviewer.append(review)

    return {
        'module': module,
        'total_open': total_open,
        'waiting_on_reviewer': len(waiting_on_reviewer),
        'waiting_on_submitter': total_open - len(waiting_on_reviewer),
        'latest_revision': _process_stat(
            waiting_on_reviewer, 'updated_on', time_now),
        'first_revision': _process_stat(waiting_on_reviewer, 'date', time_now),
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

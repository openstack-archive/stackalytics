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

import collections
import datetime
import json
import operator
import time

import flask

from stackalytics.dashboard import decorators
from stackalytics.dashboard import helpers
from stackalytics.dashboard import parameters
from stackalytics.dashboard import vault
from stackalytics.processor import utils


DEFAULT_DAYS_COUNT = 7
FIRST_MEMBER_DATE = "2012-Jul-18"

blueprint = flask.Blueprint('reports', __name__, url_prefix='/report')


@blueprint.route('/blueprint/<module>/<blueprint_name>')
@decorators.templated()
@decorators.exception_handler()
def blueprint_summary(module, blueprint_name):
    blueprint_id = utils.get_blueprint_id(module, blueprint_name)
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


@blueprint.route('/reviews/<module>/open')
@decorators.templated()
@decorators.exception_handler()
def open_reviews(module):
    memory_storage_inst = vault.get_memory_storage()
    time_now = int(time.time())

    module_id_index = vault.get_vault()['module_id_index']
    module = module.lower()
    if module not in module_id_index:
        flask.abort(404)

    modules = module_id_index[module]['modules']

    review_ids = (memory_storage_inst.get_record_ids_by_modules(modules) &
                  memory_storage_inst.get_record_ids_by_types(['review']))

    waiting_on_reviewer = []
    waiting_on_submitter = []
    total_open = 0

    for review in memory_storage_inst.get_records(review_ids):
        if review.status == 'NEW':
            total_open += 1

            # review.value is minimum from votes made for the latest patch
            if review.value in [1, 2]:
                # CI or engineer liked this change request, waiting for someone
                # to merge or to put dislike
                waiting_on_reviewer.append(helpers.extend_record(review))
            elif review.value in [-1, -2]:
                # CI or reviewer do not like this, waiting for submitter to fix
                waiting_on_submitter.append(helpers.extend_record(review))
            else:
                # new requests without votes, waiting for CI
                pass

    return {
        'module': module,
        'total_open': total_open,
        'waiting_on_reviewer': len(waiting_on_reviewer),
        'waiting_on_submitter': len(waiting_on_submitter),
        'waiting_on_ci': (total_open - len(waiting_on_reviewer) -
                          len(waiting_on_submitter)),
        'reviewer_latest_revision': _process_stat(
            waiting_on_reviewer, 'updated_on', time_now),
        'reviewer_first_revision': _process_stat(
            waiting_on_reviewer, 'date', time_now),
        'submitter_latest_revision': _process_stat(
            waiting_on_submitter, 'updated_on', time_now),
        'submitter_first_revision': _process_stat(
            waiting_on_submitter, 'date', time_now),
    }


@blueprint.route('/contribution/<module>/<days>')
@decorators.templated()
@decorators.exception_handler()
def contribution(module, days):
    return {
        'module': module,
        'days': days,
        'start_date': int(time.time()) - int(days) * 24 * 60 * 60
    }


@blueprint.route('/ci/<module>/<days>')
@decorators.templated()
@decorators.exception_handler()
def external_ci(module, days):
    if int(days) > 100:
        days = 100

    return {
        'module': module,
        'days': days,
        'start_date': int(time.time()) - int(days) * 24 * 60 * 60
    }


@blueprint.route('/members')
@decorators.exception_handler()
@decorators.templated()
def members():
    days = int(flask.request.args.get('days') or DEFAULT_DAYS_COUNT)
    all_days = int(time.time() - utils.date_to_timestamp_ext(
        FIRST_MEMBER_DATE)) / (24 * 60 * 60) + 1

    return {
        'days': days,
        'all_days': all_days
    }


@blueprint.route('/affiliation_changes')
@decorators.exception_handler()
@decorators.templated()
def affiliation_changes():
    start_days = str(flask.request.args.get('start_days') or
                     utils.timestamp_to_date(int(time.time()) -
                                             365 * 24 * 60 * 60))
    end_days = str(flask.request.args.get('end_days') or
                   utils.timestamp_to_date(int(time.time())))

    return {
        'start_days': start_days,
        'end_days': end_days,
    }


@blueprint.route('/cores')
@decorators.exception_handler()
@decorators.templated()
def cores():
    project_type = parameters.get_single_parameter({}, 'project_type')
    return {
        'project_type': project_type,
    }


def _get_punch_card_data(records):
    punch_card_raw = []  # matrix days x hours
    for wday in range(7):
        punch_card_raw.append([0] * 24)
    for record in records:
        tt = datetime.datetime.fromtimestamp(record.date).timetuple()
        punch_card_raw[tt.tm_wday][tt.tm_hour] += 1

    punch_card_data = []  # format for jqplot bubble renderer
    for wday in range(7):
        for hour in range(24):
            v = punch_card_raw[wday][hour]
            if v:
                punch_card_data.append([hour, 6 - wday, v, v])  # upside down

    # add corner point, otherwise chart doesn't know the bounds
    if punch_card_raw[0][0] == 0:
        punch_card_data.append([0, 0, 0, 0])
    if punch_card_raw[6][23] == 0:
        punch_card_data.append([23, 6, 0, 0])

    return json.dumps(punch_card_data)


def _get_activity_summary(record_ids):
    memory_storage_inst = vault.get_memory_storage()

    record_ids_by_type = memory_storage_inst.get_record_ids_by_types(
        ['mark', 'patch', 'email', 'bpd', 'bpc', 'ci'])

    record_ids &= record_ids_by_type
    punch_card_data = _get_punch_card_data(
        memory_storage_inst.get_records(record_ids))

    return {
        'punch_card_data': punch_card_data,
    }


@blueprint.route('/users/<user_id>')
@decorators.templated()
@decorators.exception_handler()
def user_activity(user_id):
    user = vault.get_user_from_runtime_storage(user_id)
    if not user:
        flask.abort(404)
    user = helpers.extend_user(user)

    memory_storage_inst = vault.get_memory_storage()
    result = _get_activity_summary(
        memory_storage_inst.get_record_ids_by_user_ids([user_id]))
    result['user'] = user

    return result


@blueprint.route('/companies/<company>')
@decorators.templated()
@decorators.exception_handler()
def company_activity(company):
    memory_storage_inst = vault.get_memory_storage()
    original_name = memory_storage_inst.get_original_company_name(company)

    result = _get_activity_summary(
        memory_storage_inst.get_record_ids_by_companies([original_name]))
    result['company_name'] = original_name

    return result


@blueprint.route('/activity')
@decorators.templated()
@decorators.exception_handler()
def activity():
    pass


@blueprint.route('/large_commits')
@decorators.response()
@decorators.jsonify('commits')
@decorators.exception_handler()
@decorators.record_filter()
def get_commit_report(records, **kwargs):
    loc_threshold = int(flask.request.args.get('loc_threshold') or 1000)
    response = []
    for record in records:
        if record.record_type == 'commit' and record.loc > loc_threshold:
            ext_record = vault.extend_record(record)
            nr = dict([(k, ext_record[k])
                       for k in ['loc', 'subject', 'module', 'primary_key',
                                 'change_id']
                       if k in ext_record])
            response.append(nr)
    return response


@blueprint.route('/single_plus_two_reviews')
@decorators.response()
@decorators.jsonify()
@decorators.exception_handler()
@decorators.record_filter(ignore='metric')
def get_single_plus_two_reviews_report(records, **kwargs):
    memory_storage_inst = vault.get_memory_storage()
    plus_twos = collections.defaultdict(list)
    for record in records:
        if record['record_type'] != 'mark':
            continue

        if (record['branch'] == 'master' and
                record['type'] == 'Code-Review' and record['value'] == +2):
            review_id = record['review_id']
            review = memory_storage_inst.get_record_by_primary_key(review_id)
            if review and review['status'] == 'MERGED':
                plus_twos[review_id].append(record)

    response = []
    for review_id in plus_twos.keys():
        if len(plus_twos[review_id]) < 2:
            mark = plus_twos[review_id][0]
            review = memory_storage_inst.get_record_by_primary_key(
                mark['review_id'])
            response.append({'review_by': review['user_id'],
                             'mark_by': mark['user_id'],
                             'subject': review['subject'],
                             'url': review['url'],
                             'project': review['project']})

    return response


@blueprint.route('/driverlog')
@decorators.templated()
@decorators.exception_handler()
def driverlog():
    pass

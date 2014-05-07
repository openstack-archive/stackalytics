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
import functools
import json

import flask
import six
from werkzeug import exceptions

from dashboard import helpers
from dashboard import parameters
from dashboard import vault
from stackalytics.openstack.common import log as logging
from stackalytics.processor import utils
from stackalytics import version as stackalytics_version


LOG = logging.getLogger(__name__)


def _get_time_filter(kwargs, ignore):
    start_date = parameters.get_single_parameter(kwargs, 'start_date')
    if start_date and 'start_date' not in ignore:
        start_date = utils.date_to_timestamp_ext(start_date)
    else:
        start_date = 0
    end_date = parameters.get_single_parameter(kwargs, 'end_date')
    if end_date and 'end_date' not in ignore:
        end_date = utils.date_to_timestamp_ext(end_date)
    else:
        end_date = utils.date_to_timestamp_ext('now')

    def time_filter(records):
        for record in records:
            if start_date <= record['date'] <= end_date:
                yield record

    return time_filter


def record_filter(ignore=None, use_default=True):
    if not ignore:
        ignore = []

    def decorator(f):
        def _filter_records_by_modules(memory_storage_inst, modules, releases):
            selected = set([])
            for m, r in vault.resolve_modules(modules, releases):
                y = memory_storage_inst.get_record_ids_by_modules([m])
                if r:
                    x = memory_storage_inst.get_record_ids_by_releases([r])
                    selected |= x & y
                else:
                    selected |= y
            return selected

        @functools.wraps(f)
        def record_filter_decorated_function(*args, **kwargs):

            memory_storage_inst = vault.get_memory_storage()
            record_ids = set(memory_storage_inst.get_record_ids())  # a copy

            releases = []
            if 'release' not in ignore:
                releases = parameters.get_parameter(kwargs, 'release',
                                                    'releases', use_default)
                if releases:
                    if 'all' not in releases:
                        record_ids &= (
                            memory_storage_inst.get_record_ids_by_releases(
                                c.lower() for c in releases))

            modules = parameters.get_parameter(kwargs, 'module', 'modules',
                                               use_default)

            if 'project_type' not in ignore:
                param = parameters.get_parameter(kwargs, 'project_type',
                                                 'project_types', use_default)
                if param:
                    record_ids &= _filter_records_by_modules(
                        memory_storage_inst,
                        vault.resolve_project_types(param),
                        releases)

            if 'module' not in ignore:
                if modules:
                    record_ids &= _filter_records_by_modules(
                        memory_storage_inst, modules, releases)

            if 'user_id' not in ignore:
                param = parameters.get_parameter(kwargs, 'user_id', 'user_ids')
                param = [u for u in param
                         if vault.get_user_from_runtime_storage(u)]
                if param:
                    record_ids &= (
                        memory_storage_inst.get_record_ids_by_user_ids(param))

            if 'company' not in ignore:
                param = parameters.get_parameter(kwargs, 'company',
                                                 'companies')
                if param:
                    record_ids &= (
                        memory_storage_inst.get_record_ids_by_companies(param))

            if 'metric' not in ignore:
                metrics = parameters.get_parameter(kwargs, 'metric')
                if 'all' not in metrics:
                    for metric in metrics:
                        if metric in parameters.METRIC_TO_RECORD_TYPE:
                            record_ids &= (
                                memory_storage_inst.get_record_ids_by_type(
                                    parameters.METRIC_TO_RECORD_TYPE[metric]))

                if 'tm_marks' in metrics:
                    filtered_ids = []
                    review_nth = int(parameters.get_parameter(
                        kwargs, 'review_nth')[0])
                    for record in memory_storage_inst.get_records(record_ids):
                        parent = memory_storage_inst.get_record_by_primary_key(
                            record['review_id'])
                        if (parent and ('review_number' in parent) and
                                (parent['review_number'] <= review_nth)):
                            filtered_ids.append(record['record_id'])
                    record_ids = filtered_ids

            if 'blueprint_id' not in ignore:
                param = parameters.get_parameter(kwargs, 'blueprint_id')
                if param:
                    record_ids &= (
                        memory_storage_inst.get_record_ids_by_blueprint_ids(
                            param))

            time_filter = _get_time_filter(kwargs, ignore)

            kwargs['record_ids'] = record_ids
            kwargs['records'] = time_filter(
                memory_storage_inst.get_records(record_ids))
            return f(*args, **kwargs)

        return record_filter_decorated_function

    return decorator


def incremental_filter(result, record, param_id):
    result[record[param_id]]['metric'] += 1


def loc_filter(result, record, param_id):
    result[record[param_id]]['metric'] += record['loc']


def mark_filter(result, record, param_id):
    result_by_param = result[record[param_id]]
    if record['type'] == 'APRV':
        value = 'A'
    else:
        value = record['value']
        result_by_param['metric'] += 1
    result_by_param[value] = result_by_param.get(value, 0) + 1

    if record.get('disagreement'):
        result_by_param['disagreements'] = (
            result_by_param.get('disagreements', 0) + 1)


def mark_finalize(record):
    new_record = record.copy()

    positive = 0
    numeric = 0
    mark_distribution = []
    for key in [-2, -1, 1, 2, 'A']:
        if key in record:
            if key in [1, 2]:
                positive += record[key]
            if key in [-2, -1, 1, 2]:
                numeric += record[key]
            mark_distribution.append(str(record[key]))
        else:
            mark_distribution.append('0')
            new_record[key] = 0

    new_record['disagreements'] = record.get('disagreements', 0)
    if numeric:
        positive_ratio = '%.1f%%' % (
            (positive * 100.0) / numeric)
        new_record['disagreement_ratio'] = '%.1f%%' % (
            (record.get('disagreements', 0) * 100.0) / numeric)
    else:
        positive_ratio = helpers.INFINITY_HTML
        new_record['disagreement_ratio'] = helpers.INFINITY_HTML
    new_record['mark_ratio'] = (
        '|'.join(mark_distribution) + ' (' + positive_ratio + ')')
    new_record['positive_ratio'] = positive_ratio

    return new_record


def man_days_filter(result, record, param_id):
    if record['record_type'] == 'commit':
        # commit is attributed with the date of the merge which is not an
        # effort of the author (author's effort is represented in patches)
        return

    day = record['date'] // (24 * 3600)

    result_by_param = result[record[param_id]]
    if 'days' not in result_by_param:
        result_by_param['days'] = collections.defaultdict(set)
    user = vault.get_user_from_runtime_storage(record['user_id'])
    result_by_param['days'][day] |= set([user['seq']])
    result_by_param['metric'] = 1


def man_days_finalize(result_item):
    metric = 0
    for day_set in six.itervalues(result_item['days']):
        metric += len(day_set)
    del result_item['days']
    result_item['metric'] = metric
    return result_item


def aggregate_filter():
    def decorator(f):
        @functools.wraps(f)
        def aggregate_filter_decorated_function(*args, **kwargs):

            metric_param = (flask.request.args.get('metric') or
                            parameters.get_default('metric'))
            metric = metric_param.lower()

            metric_to_filters_map = {
                'commits': (incremental_filter, None),
                'loc': (loc_filter, None),
                'marks': (mark_filter, mark_finalize),
                'tm_marks': (mark_filter, mark_finalize),
                'emails': (incremental_filter, None),
                'bpd': (incremental_filter, None),
                'bpc': (incremental_filter, None),
                'members': (incremental_filter, None),
                'man-days': (man_days_filter, man_days_finalize),
            }
            if metric not in metric_to_filters_map:
                metric = parameters.get_default('metric')

            kwargs['metric_filter'] = metric_to_filters_map[metric][0]
            kwargs['finalize_handler'] = metric_to_filters_map[metric][1]
            return f(*args, **kwargs)

        return aggregate_filter_decorated_function

    return decorator


def exception_handler():
    def decorator(f):
        @functools.wraps(f)
        def exception_handler_decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if isinstance(e, exceptions.HTTPException):
                    raise  # ignore Flask exceptions
                LOG.exception(e)
                flask.abort(404)

        return exception_handler_decorated_function

    return decorator


def templated(template=None, return_code=200):
    def decorator(f):
        @functools.wraps(f)
        def templated_decorated_function(*args, **kwargs):

            vault_inst = vault.get_vault()
            template_name = template
            if template_name is None:
                template_name = (flask.request.endpoint.replace('.', '/') +
                                 '.html')
            ctx = f(*args, **kwargs)
            if ctx is None:
                ctx = {}

            # put parameters into template
            metric = flask.request.args.get('metric')
            if metric not in parameters.METRIC_LABELS:
                metric = None
            ctx['metric'] = metric or parameters.get_default('metric')
            ctx['metric_label'] = parameters.METRIC_LABELS[ctx['metric']]

            project_type = flask.request.args.get('project_type')
            if not vault.is_project_type_valid(project_type):
                project_type = parameters.get_default('project_type')
            ctx['project_type'] = project_type

            release = flask.request.args.get('release')
            releases = vault_inst['releases']
            if release:
                release = release.lower()
                if release != 'all':
                    if release not in releases:
                        release = None
                    else:
                        release = releases[release]['release_name']
            ctx['release'] = (release or
                              parameters.get_default('release')).lower()
            ctx['review_nth'] = (flask.request.args.get('review_nth') or
                                 parameters.get_default('review_nth'))

            ctx['project_type_options'] = vault.get_project_types()
            ctx['release_options'] = vault.get_release_options()
            ctx['metric_options'] = sorted(parameters.METRIC_LABELS.items(),
                                           key=lambda x: x[0])

            ctx['company'] = parameters.get_single_parameter(kwargs, 'company')
            ctx['company_original'] = (
                vault.get_memory_storage().get_original_company_name(
                    ctx['company']))

            module = parameters.get_single_parameter(kwargs, 'module')
            ctx['module'] = module
            if module and module in vault_inst['module_id_index']:
                ctx['module_inst'] = vault_inst['module_id_index'][module]

            ctx['user_id'] = parameters.get_single_parameter(kwargs, 'user_id')
            ctx['page_title'] = helpers.make_page_title(
                ctx['company'], ctx['user_id'], ctx['module'], ctx['release'])
            ctx['stackalytics_version'] = (
                stackalytics_version.version_info.version_string())
            ctx['stackalytics_release'] = (
                stackalytics_version.version_info.release_string())

            return flask.render_template(template_name, **ctx), return_code

        return templated_decorated_function

    return decorator


def jsonify(root='data'):
    def decorator(func):
        @functools.wraps(func)
        def jsonify_decorated_function(*args, **kwargs):
            callback = flask.app.request.args.get('callback', False)
            data = json.dumps({root: func(*args, **kwargs)})

            if callback:
                data = str(callback) + '(' + data + ')'
                mimetype = 'application/javascript'
            else:
                mimetype = 'application/json'

            return flask.current_app.response_class(data, mimetype=mimetype)

        return jsonify_decorated_function

    return decorator


def query_filter(query_param='query'):
    def decorator(f):
        @functools.wraps(f)
        def query_filter_decorated_function(*args, **kwargs):

            query = flask.request.args.get(query_param)
            if query:
                kwargs['query_filter'] = lambda x: x.lower().find(query) >= 0
            else:
                kwargs['query_filter'] = lambda x: True

            return f(*args, **kwargs)

        return query_filter_decorated_function

    return decorator

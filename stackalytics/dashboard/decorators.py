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

import cProfile
import functools
import json
import operator
import time

import flask
from oslo_config import cfg
from oslo_log import log as logging
import six
from werkzeug import exceptions

from stackalytics.dashboard import helpers
from stackalytics.dashboard import parameters
from stackalytics.dashboard import vault
from stackalytics.processor import utils
from stackalytics import version as stackalytics_version


LOG = logging.getLogger(__name__)


def _check_param_in(params, name, collection, allow_all=False):
    for single in (params.get(name) or []):
        single = single.lower()
        if allow_all and single == 'all':
            continue
        if single not in collection:
            params[name] = []
            flask.abort(404)


def _validate_params(params):
    vault_inst = vault.get_vault()
    memory_storage_inst = vault.get_memory_storage()

    _check_param_in(params, 'release', vault_inst['releases'], True)
    _check_param_in(params, 'project_type', vault_inst['project_types_index'])
    _check_param_in(params, 'module', vault_inst['module_id_index'])
    _check_param_in(params, 'company',
                    memory_storage_inst.get_companies_lower())
    _check_param_in(params, 'user_id', memory_storage_inst.get_user_ids())
    _check_param_in(params, 'metric', parameters.METRIC_TO_RECORD_TYPE, True)


def _get_single(params):
    if params:
        return params[0]
    return None


def _prepare_params(kwargs, ignore):
    params = kwargs.get('_params')

    if not params:
        params = {'action': flask.request.path}
        for key in parameters.FILTER_PARAMETERS:
            params[key] = parameters.get_parameter(kwargs, key, key)

        if params['start_date']:
            params['start_date'] = [utils.round_timestamp_to_day(
                params['start_date'][0])]
        if params['end_date']:
            params['end_date'] = [utils.round_timestamp_to_day(
                params['end_date'][0])]

        _validate_params(params)
        kwargs['_params'] = params

    if ignore:
        return dict([(k, v if k not in ignore else [])
                     for k, v in six.iteritems(params)])
    else:
        return params


def cached(ignore=None):
    def decorator(func):
        @functools.wraps(func)
        def prepare_params_decorated_function(*args, **kwargs):

            params = _prepare_params(kwargs, ignore)

            cache_inst = vault.get_vault()['cache']
            key = json.dumps(params)
            value = cache_inst.get(key)

            if not value:
                value = func(*args, **kwargs)
                cache_inst[key] = value
                vault.get_vault()['cache_size'] += len(key) + len(value)
                LOG.debug('Cache size: %(size)d, entries: %(len)d',
                          {'size': vault.get_vault()['cache_size'],
                           'len': len(cache_inst.keys())})

            return value

        return prepare_params_decorated_function

    return decorator


def record_filter(ignore=None):

    def decorator(f):

        def _filter_records_by_days(start_date, end_date, memory_storage_inst):
            if start_date:
                start_date = utils.date_to_timestamp_ext(start_date[0])
            else:
                start_date = memory_storage_inst.get_first_record_day()
            if end_date:
                end_date = utils.date_to_timestamp_ext(end_date[0])
            else:
                end_date = utils.date_to_timestamp_ext('now')

            start_day = utils.timestamp_to_day(start_date)
            end_day = utils.timestamp_to_day(end_date)

            return memory_storage_inst.get_record_ids_by_days(
                six.moves.range(start_day, end_day + 1))

        def _filter_records_by_modules(memory_storage_inst, mr):
            selected = set([])
            for m, r in mr:
                if r is None:
                    selected |= memory_storage_inst.get_record_ids_by_modules(
                        [m])
                else:
                    selected |= (
                        memory_storage_inst.get_record_ids_by_module_release(
                            m, r))
            return selected

        def _intersect(first, second):
            if first is not None:
                return first & second
            return second

        @functools.wraps(f)
        def record_filter_decorated_function(*args, **kwargs):

            memory_storage_inst = vault.get_memory_storage()
            record_ids = None

            params = _prepare_params(kwargs, ignore)

            release = params['release']
            if release:
                if 'all' not in release:
                    record_ids = (
                        memory_storage_inst.get_record_ids_by_releases(
                            c.lower() for c in release))

            project_type = params['project_type']
            mr = None
            if project_type:
                mr = set(vault.resolve_modules(vault.resolve_project_types(
                    project_type), release))

            module = params['module']
            if module:
                mr = _intersect(mr, set(vault.resolve_modules(
                    module, release)))

            if mr is not None:
                record_ids = _intersect(
                    record_ids, _filter_records_by_modules(
                        memory_storage_inst, mr))

            user_id = params['user_id']
            user_id = [u for u in user_id
                       if vault.get_user_from_runtime_storage(u)]
            if user_id:
                record_ids = _intersect(
                    record_ids,
                    memory_storage_inst.get_record_ids_by_user_ids(user_id))

            company = params['company']
            if company:
                record_ids = _intersect(
                    record_ids,
                    memory_storage_inst.get_record_ids_by_companies(company))

            metric = params['metric']
            if 'all' not in metric:
                for metric in metric:
                    if metric in parameters.METRIC_TO_RECORD_TYPE:
                        record_ids = _intersect(
                            record_ids,
                            memory_storage_inst.get_record_ids_by_types(
                                parameters.METRIC_TO_RECORD_TYPE[metric]))

            blueprint_id = params['blueprint_id']
            if blueprint_id:
                record_ids = _intersect(
                    record_ids,
                    memory_storage_inst.get_record_ids_by_blueprint_ids(
                        blueprint_id))

            start_date = params['start_date']
            end_date = params['end_date']

            if start_date or end_date:
                record_ids = _intersect(
                    record_ids, _filter_records_by_days(start_date, end_date,
                                                        memory_storage_inst))

            kwargs['record_ids'] = record_ids
            kwargs['records'] = memory_storage_inst.get_records(record_ids)

            return f(*args, **kwargs)

        return record_filter_decorated_function

    return decorator


def incremental_filter(result, record, param_id, context):
    result[getattr(record, param_id)]['metric'] += 1


def loc_filter(result, record, param_id, context):
    result[getattr(record, param_id)]['metric'] += record.loc


def mark_filter(result, record, param_id, context):
    result_by_param = result[getattr(record, param_id)]
    value = 0
    record_type = record.type

    if record_type == 'Code-Review':
        result_by_param['metric'] += 1
        value = record.value
    elif record_type == 'Abandon':
        result_by_param['metric'] += 1
        value = 'x'
    elif record.type == 'Workflow':
        if record.value == 1:
            value = 'A'
        else:
            value = 'WIP'
    result_by_param[value] = result_by_param.get(value, 0) + 1

    if record.disagreement:
        result_by_param['disagreements'] = (
            result_by_param.get('disagreements', 0) + 1)


def mark_finalize(record):
    new_record = record.copy()

    positive = 0
    numeric = 0
    mark_distribution = []
    for key in [-2, -1, 1, 2, 'A', 'x']:
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


def ci_filter(result, record, param_id, context):
    result_by_param = result[getattr(record, param_id)]

    result_by_param['metric'] += 1

    key = 'success' if record.value else 'failure'
    result_by_param[key] = result_by_param.get(key, 0) + 1


def ci_finalize(record):
    new_record = record.copy()

    metric = record.get('metric')
    if metric:
        new_record['success_ratio'] = '%.1f%%' % (
            (record.get('success', 0) * 100.0) / metric)
    else:
        new_record['success_rate'] = helpers.INFINITY_HTML

    return new_record


def person_day_filter(result, record, param_id, context):
    day = utils.timestamp_to_day(record.date)
    # fact that record-days are grouped by days in some order is used
    if context.get('last_processed_day') != day:
        context['last_processed_day'] = day
        context['counted_user_ids'] = set()

    user_id = record.user_id
    value = getattr(record, param_id)
    if user_id not in context['counted_user_ids']:
        context['counted_user_ids'].add(user_id)
        result[value]['metric'] += 1


def generate_records_for_person_day(record_ids):
    memory_storage_inst = vault.get_memory_storage()
    id_dates = []
    for record in memory_storage_inst.get_records(record_ids):
        id_dates.append((record.date, record.record_id))

    id_dates.sort(key=operator.itemgetter(0))
    for record in memory_storage_inst.get_records(
            record_id for date, record_id in id_dates):
        yield record


def aggregate_filter():
    def decorator(f):
        @functools.wraps(f)
        def aggregate_filter_decorated_function(*args, **kwargs):

            metric_param = (flask.request.args.get('metric') or
                            parameters.get_default('metric'))
            metric = metric_param.lower()

            metric_to_filters_map = {
                'commits': (None, None),
                'loc': (loc_filter, None),
                'marks': (mark_filter, mark_finalize),
                'emails': (incremental_filter, None),
                'bpd': (incremental_filter, None),
                'bpc': (incremental_filter, None),
                'filed-bugs': (incremental_filter, None),
                'resolved-bugs': (incremental_filter, None),
                'members': (incremental_filter, None),
                'person-day': (person_day_filter, None),
                'ci': (ci_filter, ci_finalize),
                'patches': (None, None),
                'translations': (loc_filter, None),
            }
            if metric not in metric_to_filters_map:
                metric = parameters.get_default('metric')

            kwargs['metric_filter'] = metric_to_filters_map[metric][0]
            kwargs['finalize_handler'] = metric_to_filters_map[metric][1]

            if metric == 'person-day':
                kwargs['records'] = generate_records_for_person_day(
                    kwargs['record_ids'])

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

            try:
                _prepare_params(kwargs, [])
            except Exception:
                if return_code == 200:
                    raise  # do not re-raise on error page

            # put parameters into template
            ctx['metric'] = parameters.get_single_parameter(
                kwargs, 'metric', use_default=True)
            ctx['metric_label'] = parameters.METRIC_LABELS.get(ctx['metric'])

            project_type = parameters.get_single_parameter(
                kwargs, 'project_type', use_default=True)
            ctx['project_type'] = project_type
            ctx['project_type_inst'] = vault.get_project_type(project_type)

            ctx['release'] = parameters.get_single_parameter(
                kwargs, 'release', use_default=True)

            company = parameters.get_single_parameter(kwargs, 'company')
            ctx['company'] = company
            if company:
                ctx['company_original'] = (
                    vault.get_memory_storage().get_original_company_name(
                        ctx['company']))

            module = parameters.get_single_parameter(kwargs, 'module')
            ctx['module'] = module
            if module and module in vault_inst['module_id_index']:
                ctx['module_inst'] = vault_inst['module_id_index'][module]

            ctx['user_id'] = parameters.get_single_parameter(kwargs, 'user_id')
            if ctx['user_id']:
                ctx['user_inst'] = vault.get_user_from_runtime_storage(
                    ctx['user_id'])

            ctx['page_title'] = helpers.make_page_title(
                ctx['project_type_inst'],
                ctx.get('release'), ctx.get('module_inst'),
                ctx.get('company_original'), ctx.get('user_inst'))

            ctx['stackalytics_version'] = (
                stackalytics_version.version_info.version_string())
            ctx['stackalytics_release'] = (
                stackalytics_version.version_info.release_string())
            update_time = vault_inst['runtime_storage_update_time']
            ctx['runtime_storage_update_time'] = update_time
            ctx['runtime_storage_update_time_str'] = helpers.format_datetime(
                update_time) if update_time else None

            # deprecated -- top mentor report
            ctx['review_nth'] = parameters.get_single_parameter(
                kwargs, 'review_nth')

            return flask.render_template(template_name, **ctx), return_code

        return templated_decorated_function

    return decorator


def jsonify(root='data'):
    def decorator(func):
        @functools.wraps(func)
        def jsonify_decorated_function(*args, **kwargs):
            value = func(*args, **kwargs)
            if isinstance(value, tuple):
                result = dict([(root[i], value[i])
                               for i in six.moves.range(min(len(value),
                                                            len(root)))])
            else:
                result = {root: value}
            return json.dumps(result)

        return jsonify_decorated_function

    return decorator


def profiler_decorator(func):
    @functools.wraps(func)
    def profiler_decorated_function(*args, **kwargs):
        profiler = None
        profile_filename = cfg.CONF.collect_profiler_stats

        if profile_filename:
            LOG.debug('Profiler is enabled')
            profiler = cProfile.Profile()
            profiler.enable()

        result = func(*args, **kwargs)

        if profile_filename:
            profiler.disable()
            profiler.dump_stats(profile_filename)
            LOG.debug('Profiler stats is written to file %s', profile_filename)

        return result

    return profiler_decorated_function


def response():
    def decorator(func):
        @functools.wraps(func)
        @profiler_decorator
        def response_decorated_function(*args, **kwargs):
            callback = flask.app.request.args.get('callback', False)
            data = func(*args, **kwargs)

            if callback:
                data = str(callback) + '(' + data + ')'
                mimetype = 'application/javascript'
            else:
                mimetype = 'application/json'

            resp = flask.current_app.response_class(data, mimetype=mimetype)
            update_time = vault.get_vault()['vault_next_update_time']
            now = utils.date_to_timestamp('now')
            if now < update_time:
                max_age = update_time - now
            else:
                max_age = 0
            resp.headers['cache-control'] = 'public, max-age=%d' % (max_age,)
            resp.headers['expires'] = time.strftime(
                '%a, %d %b %Y %H:%M:%S GMT',
                time.gmtime(vault.get_vault()['vault_next_update_time']))
            resp.headers['access-control-allow-origin'] = '*'
            return resp

        return response_decorated_function

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

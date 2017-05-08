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

import calendar
import cgi
import datetime
import gzip
import random
import re
import time

import iso8601
from oslo_config import cfg
from oslo_log import log as logging
import requests
import requests_file
import six
import yaml


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def init_config_and_logging(opts):
    CONF.register_cli_opts(opts)
    CONF.register_opts(opts)
    logging.register_options(CONF)
    logging.set_defaults()

    CONF(project='stackalytics')

    logging.setup(CONF, 'stackalytics')
    LOG.info('Logging enabled')
    CONF.log_opt_values(LOG, logging.DEBUG)


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
    except (ValueError, TypeError):
        return int(d)


def member_date_to_timestamp(d):
    if not d:
        return 0
    return int(time.mktime(
        datetime.datetime.strptime(d, '%B %d, %Y ').timetuple()))


def iso8601_to_timestamp(s):
    return calendar.timegm(iso8601.parse_date(s).utctimetuple())


def timestamp_to_date(timestamp):
    return (datetime.datetime.fromtimestamp(timestamp).
            strftime('%Y-%b-%d'))


def timestamp_to_week(timestamp):
    # Jan 4th 1970 is the first Sunday in the Epoch
    return (timestamp - 3 * 24 * 3600) // (7 * 24 * 3600)


def week_to_date(week):
    timestamp = week * 7 * 24 * 3600 + 3 * 24 * 3600
    return (datetime.datetime.fromtimestamp(timestamp).
            strftime('%Y-%m-%d %H:%M:%S'))


def timestamp_to_day(timestamp):
    return timestamp // (24 * 3600)


def timestamp_to_utc_date(timestamp):
    return (datetime.datetime.fromtimestamp(timestamp).
            strftime('%Y-%m-%d'))


def round_timestamp_to_day(timestamp):
    return (int(timestamp) // (24 * 3600)) * (24 * 3600)


def check_email_validity(email):
    if email:
        return re.match(r'[\w\d_\.-\\+]+@([\w\d_\.-]+\.)+[\w]+', email)
    return False


user_agents = [
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) Gecko/20100101 Firefox/41.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/600.8.9',
    'Mozilla/5.0 (Windows NT 6.3; WOW64; rv:41.0) Gecko/20100101 Firefox/41.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/45.0.2062.120',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko'
]


def _session_request(session, uri, method):
    session.mount('file://', requests_file.FileAdapter())
    user_agent = random.choice(user_agents)

    headers = {'User-Agent': user_agent, 'Accept': 'application/json'}
    return session.request(method, uri, headers=headers,
                           timeout=CONF.read_timeout)


def do_request(uri, method='get', session=None):
    if session:
        return _session_request(session, uri, method)
    else:
        with requests.Session() as session:
            return _session_request(session, uri, method)


def read_uri(uri, session=None):
    try:
        return do_request(uri, session=session).text
    except Exception as e:
        LOG.warning('Error "%(error)s" retrieving uri %(uri)s',
                    {'error': e, 'uri': uri})


def read_json_from_uri(uri, session=None):
    try:
        return do_request(uri, session=session).json()
    except Exception as e:
        LOG.warning('Error "%(error)s" parsing json from uri %(uri)s',
                    {'error': e, 'uri': uri})


def read_yaml_from_uri(uri):
    try:
        return yaml.safe_load(read_uri(uri))
    except Exception as e:
        LOG.warning('Error "%(error)s" parsing yaml from uri %(uri)s',
                    {'error': e, 'uri': uri})


def _gzip_decompress(content):
    if six.PY3:
        return gzip.decompress(content).decode('utf8')
    else:
        gzip_fd = gzip.GzipFile(fileobj=six.moves.StringIO(content))
        return gzip_fd.read()


def read_gzip_from_uri(uri):
    try:
        return _gzip_decompress(do_request(uri).content)
    except Exception as e:
        LOG.warning('Error "%(error)s" retrieving uri %(uri)s',
                    {'error': e, 'uri': uri})


def get_uri_last_modified(uri):
    try:
        return do_request(uri, method='head').headers['last-modified']
    except Exception as e:
        LOG.warning('Error "%(error)s" retrieving uri %(uri)s',
                    {'error': e, 'uri': uri})


def cmp_to_key(mycmp):  # ported from python 3
    """Convert a cmp= function into a key= function."""
    class K(object):
        __slots__ = ['obj']

        def __init__(self, obj):
            self.obj = obj

        def __lt__(self, other):
            return mycmp(self.obj, other.obj) < 0

        def __gt__(self, other):
            return mycmp(self.obj, other.obj) > 0

        def __eq__(self, other):
            return mycmp(self.obj, other.obj) == 0

        def __le__(self, other):
            return mycmp(self.obj, other.obj) <= 0

        def __ge__(self, other):
            return mycmp(self.obj, other.obj) >= 0

        def __ne__(self, other):
            return mycmp(self.obj, other.obj) != 0

        __hash__ = None
    return K


def make_range(start, stop, step):
    last_full = stop - ((stop - start) % step)
    for i in six.moves.range(start, last_full, step):
        yield six.moves.range(i, i + step)
    if stop > last_full:
        yield six.moves.range(last_full, stop)


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

    def replace_dots(match_obj):
        return re.sub(r'([\./]+)', r'\1&#8203;', match_obj.group(0))

    s = re.sub(r'((?:\w+[\./]+)+\w+)', replace_dots, s)
    return s


def make_age_string(seconds):
    days = seconds / (3600 * 24)
    hours = (seconds / 3600) - (days * 24)
    return '%d days and %d hours' % (days, hours)


def merge_records(original, new):
    need_update = False
    for key, value in six.iteritems(new):
        if original.get(key) != value:
            need_update = True
            original[key] = value
    return need_update


def get_blueprint_id(module, name):
    return module + ':' + name


def make_bug_id(bug_id, module, release=None):
    if release:
        return '/'.join([module, release, bug_id])
    else:
        return '/'.join([module, bug_id])


def get_patch_id(review_id, patch_number):
    return '%s:%s' % (review_id, patch_number)


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
    return six.moves.urllib.parse.quote(s.encode('utf-8'))


def keep_safe_chars(s):
    return re.sub(r'[^\x21-\x7e\x80-\xff]+', '', s)


def make_module_group(module_group_id, name=None, modules=None, tag='module'):
    return {'id': module_group_id,
            'module_group_name': name or module_group_id,
            'modules': modules or {module_group_id},
            'tag': tag}

BAD_NAME_SUFFIXES = ['Ltd', 'Pvt', 'Inc', 'GmbH', 'AG', 'Corporation', 'Corp',
                     'Company', 'Co', 'Group', 'Srl', 'Limited', 'LLC', 'IT']

BAD_NAME_SUFFIXES_WITH_STOPS = ['S.p.A.', 's.r.o.', 'L.P.', 'B.V.', 'K.K.',
                                'd.o.o.']


def normalize_company_name(name):
    regex = '(\\b(' + '|'.join(BAD_NAME_SUFFIXES) + ')\\b)'
    regex += '|' + '((^|\\s)(' + '|'.join(BAD_NAME_SUFFIXES_WITH_STOPS) + '))'
    name = re.sub(re.compile(regex, re.IGNORECASE), '', name)
    return ''.join([c.lower() for c in name if c.isalnum()])


def normalize_company_draft(name):
    name = re.sub(',', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name


def validate_lp_display_name(lp_profile):
    if lp_profile:
        if "<email address hidden>" == lp_profile['display_name']:
            lp_profile['display_name'] = lp_profile['name']


def make_pipeline_processor(processors):

    def get_passes(_processors):
        # every processor yields one or more record handlers
        # this function groups record handlers by pass and returns list of them
        processor_generators = [p() for p in _processors]

        work = True
        while work:
            work = False
            record_handlers = []

            for generator in processor_generators:
                try:
                    record_handlers.append(next(generator))
                except StopIteration:
                    pass

            if record_handlers:
                work = True
                yield record_handlers

    def pipeline_processor(record_generator):

        # for every pass
        for one_pass in get_passes(processors):
            # iterate every record in producer
            for record in record_generator():
                # iterate over record handlers within single pass
                for record_handler in one_pass:
                    # feed record to the handler
                    for r in record_handler(record) or []:
                        # yield processed record
                        yield r

    return pipeline_processor

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

from email import utils as email_utils
import re

from oslo_log import log as logging
import six
from six.moves.urllib import parse

from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

EMAIL_HEADER_PATTERN = ('From \S+(?: at \S+)?\s+'
                        '\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}(?::\d{2})?'
                        '(?:\s+\S+)?\s+\d{4}.*?\n')

MAIL_BOX_PATTERN = re.compile(
    '^' + EMAIL_HEADER_PATTERN +
    'From: (?P<author_email>\S+(?: at \S+))'
    '(?:\W+(?P<author_name>\w+(?:\s\w+)*))?.*?\n'
    'Date: (?P<date>.*?)\n'
    'Subject: (?P<subject>.*?)(?=\n\S+:)'
    '.*?Message-ID: (?P<message_id>\S+)\n'
    '\n(?P<body>.*?)\n'
    '(?=' + EMAIL_HEADER_PATTERN + 'From: )',
    flags=re.MULTILINE | re.DOTALL)

MESSAGE_PATTERNS = {
    'bug_id': re.compile(r'https://bugs.launchpad.net/bugs/(?P<id>\d+)',
                         re.IGNORECASE),
    'blueprint_id': re.compile(r'https://blueprints.launchpad.net/'
                               r'(?P<module>[^\/]+)/\+spec/(?P<id>[a-z0-9-]+)',
                               re.IGNORECASE),
}

TRAILING_RECORD = ('From ishakhat at mirantis.com  Tue Sep 17 07:30:43 2013\n'
                   'From: ')


def _get_mail_archive_links(uri):
    content = utils.read_uri(uri)
    if not content:
        LOG.warning('Mail archive list is not found at %s', uri)
        return []

    links = set(re.findall(r'\shref\s*=\s*[\'"]([^\'"]*\.txt\.gz)', content,
                           flags=re.IGNORECASE))
    return [parse.urljoin(uri, link) for link in links]


def _uri_content_changed(uri, runtime_storage_inst):
    LOG.debug('Check changes for mail archive located at: %s', uri)
    last_modified = utils.get_uri_last_modified(uri)

    if last_modified != runtime_storage_inst.get_by_key('mail_link:' + uri):
        LOG.debug('Mail archive changed, last modified at: %s', last_modified)
        runtime_storage_inst.set_by_key('mail_link:' + uri, last_modified)
        return True

    return False


def _optimize_body(email_body):
    result = []
    for line in email_body.split('\n'):
        line = line.strip()

        if line[:1] == '>' or line[:8] == '--------':
            continue  # ignore replies and part delimiters

        if (not result) or (result and result[-1] != line):
            result.append(line)

    return '\n'.join(result)


def _retrieve_mails(uri):
    LOG.debug('Retrieving mail archive from: %s', uri)
    content = utils.read_gzip_from_uri(uri)
    if not content:
        LOG.error('Error reading mail archive from: %s', uri)
        return

    LOG.debug('Mail archive is loaded, start processing')

    content += TRAILING_RECORD

    for rec in re.finditer(MAIL_BOX_PATTERN, content):
        email = rec.groupdict()
        email['author_email'] = email['author_email'].replace(' at ', '@', 1)
        if not utils.check_email_validity(email['author_email']):
            continue

        email['date'] = int(email_utils.mktime_tz(
            email_utils.parsedate_tz(email['date'])))

        email['body'] = _optimize_body(email['body'])

        for pattern_name, pattern in six.iteritems(MESSAGE_PATTERNS):
            collection = set()
            for item in re.finditer(pattern, email['body']):
                groups = item.groupdict()
                item_id = groups['id']
                if 'module' in groups:
                    item_id = groups['module'] + ':' + item_id
                    email['module'] = groups['module']
                collection.add(item_id)
            email[pattern_name] = list(collection)

        yield email


def log(uri, runtime_storage_inst):

    links = _get_mail_archive_links(uri)
    for link in links:
        if _uri_content_changed(link, runtime_storage_inst):
            for mail in _retrieve_mails(link):
                LOG.debug('New mail: %s', mail['message_id'])
                yield mail

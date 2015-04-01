# Copyright (c) 2015 Mirantis Inc.
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

import os
import sys

try:
    import ConfigParser as configparser
except ImportError:
    import configparser


def split_multiline(value):
    value = [element for element in
             (line.strip() for line in value.split('\n'))
             if element]
    return value


def get_entry_points(config):
    if 'entry_points' not in config:
        return {}
    return dict((option, split_multiline(value))
                for option, value in config['entry_points'].items())


def make(cfg, dest):
    parser = configparser.RawConfigParser()
    parser.read(cfg)
    config = {}
    for section in parser.sections():
        config[section] = dict(parser.items(section))
    entry_points = get_entry_points(config)

    console_scripts = entry_points.get('console_scripts')
    if console_scripts:
        for item in console_scripts:
            tool = item.split('=')[0].strip()
            print('Running %s' % tool)
            os.system('%(tool)s --help > %(dest)s/%(tool)s.txt' %
                      dict(tool=tool, dest=dest))


if len(sys.argv) < 2:
    print('Usage: cli_auto_doc <dest folder>')
    sys.exit(1)


print('Generating docs from help to console tools')
make(cfg='setup.cfg', dest=sys.argv[1])

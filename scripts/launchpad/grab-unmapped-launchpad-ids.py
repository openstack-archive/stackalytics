#
# fetch launchpad ids for unknown persons
#

import httplib

from launchpadlib import launchpad

try:
    conn = httplib.HTTPConnection("analytics.vm.mirantis.net")
    conn.request("GET", "/unmapped")
    r1 = conn.getresponse()
    data = r1.read()
except Exception as e:
    print ('Error while retrieving mapping report. Check that the server '
           'is up and running. \nDetails: %s' % e)
    exit(1)

lp = launchpad.Launchpad.login_with('openstack-dm', 'production')

for line in data.split('\n'):
    line = line.strip()
    if not line:
        continue

    (email, sep, name) = line.partition(' ')
    try:
        person = lp.people.getByEmail(email=email)
        if person:
            if name == person.display_name:
                print person.name, email, person.display_name
            else:
                print person.name, email, person.display_name, '*', name
    except Exception:
        continue

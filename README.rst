Stackalytics
============

Application Features
--------------------
Stackalytics is a service that automatically analyzes OpenStack
development activities and displays statistics on contribution. The features are:
 * Extraction of author information from git log, store it in the database;
 * Calculate metrics on number of lines changed (LOC) and commits;
 * Mapping authors to companies and launchpad ids;
 * Filter statistics by time, modules, companies, authors;
 * Extract blueprint and bug ids from commit messages;
 * Auto-update of database.

Quickstart
----------

To run Stackalytics, you first need to create two kind of configuration files.
The one is default_data.json which shows which sources(git repo, ml, etc.) need
to be analyzed. Another is stackalytics.conf which shows basic configuration like
HTTP listening host and port, etc. Stackalytics repository contains the default
files of these configuration under etc/ directory. It would be useful to copy and
change them as you like.

#. You need to install Stackalytics. This is done with pip after you check out
   Stackalytics repository::

    $ git clone http://git.openstack.org/openstack/stackalytics
    $ cd stackalytics
    $ sudo pip install -r requirements.txt
    $ sudo python setup.py install

#. Install and run memcached DB::

    $ sudo apt-get install -y memcached
    $ memcached -u memcache -d

#. Analyze data which are specifed on default_data.json and store the data into memcached DB::

    $ stackalytics-processor

#. Start HTTP server of Stackalytics::

    $ stackalytics-dashboard

#. Users can access Stackalytics site on http://127.0.0.1:8080 as the default.


Project Info
-------------

 * Web-site: http://stackalytics.com/
 * Source Code: http://git.openstack.org/cgit/openstack/stackalytics
 * Wiki: https://wiki.openstack.org/wiki/Stackalytics
 * Launchpad: https://launchpad.net/stackalytics
 * Blueprints: https://blueprints.launchpad.net/stackalytics
 * Bugs: https://bugs.launchpad.net/stackalytics
 * Code Reviews: https://review.openstack.org/#q,status:open+project:openstack/stackalytics,n,z
 * IRC: #openstack-stackalytics at freenode

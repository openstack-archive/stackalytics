Stackalytics JSON API v1.0
**************************

.. note::

    JSON API v1.0 corresponds to Stackalytics v0.X

1 General API information
=========================

This section contains base info about the Stackalytics JSON API design.


1.2 Request / Response Types
----------------------------

The Stackalytics API default response format is "application/json". However if HTTP attribute 'callback' is
specified then JSONP response is returned. That allows to use response in client-side code and avoid same-host
requests limitations.

Example:

.. sourcecode:: none

    GET /api/1.0/stats/companies

or

.. sourcecode:: none

    GET /api/1.0/stats/companies?callback=myCallback
    Accept: application/javascript

1.3 Faults
----------

The Stackalytics API returns an error response if a failure occurs while processing a request.
Stackalytics uses only standard HTTP error codes. 4xx errors indicate problems in the particular
request being sent from the client and 5xx errors indicate server-side problems.


2 Methods
=========

2.1 Common Parameters
---------------------

All requests support common set of parameters that allow to filter resulting data.

+----------------+---------------------------------------------------------------------------+
| Parameter      | Description                                                               |
+================+===========================================================================+
| release        | Name of OpenStack release or 'all', by default current release            |
+----------------+---------------------------------------------------------------------------+
| project_type   | Type of project, by default 'openstack'                                   |
+----------------+---------------------------------------------------------------------------+
| module         | Name of module (repository name)                                          |
+----------------+---------------------------------------------------------------------------+
| company        | Company name                                                              |
+----------------+---------------------------------------------------------------------------+
| user_id        | Launchpad id of user or email if no Launchpad id is mapped.               |
+----------------+---------------------------------------------------------------------------+
| metric         | Metric: e.g. 'commits', 'loc', 'marks', 'emails'                          |
+----------------+---------------------------------------------------------------------------+

2.1.1 Other query parameters
............................

Data can be queried by time period:

==========  ===========
Parameter   Description
==========  ===========
start_date  When the period starts
end_date    When the period ends
==========  ===========

Both ``start_date`` and ``end_date`` take as their argument `Unix time
<https://en.wikipedia.org/wiki/Unix_time>`_

For example to specify ``'Thu Jan  1 00:00:00 UTC 2015'`` the value would be
``1420070400``

Note that if both release and time period are specified then the data is selected for the
intersection (thus the useful way is to specify release as ``all``).

2.2 Contribution by Modules
---------------------------

**Description**

Stats on contribution per modules. The data contains list of modules with their metric.
Modules which metric is 0 are omitted.

**Request**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /api/1.0/stats/modules                                            | Contribution by Modules                             |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

**Example Request**

.. sourcecode:: none

    GET /api/1.0/stats/modules?release=havana&metric=commits&project_type=openstack&user_id=zulcss

**Example Response**

.. sourcecode:: json

    {
        "stats": [
            {
                "metric": 18,
                "id": "oslo-incubator",
                "name": "oslo-incubator"
            },
            {
                "metric": 7,
                "id": "keystone",
                "name": "keystone"
            },
            {
                "metric": 1,
                "id": "python-neutronclient",
                "name": "python-neutronclient"
            }
        ]
    }


2.3 Contribution by Companies
-----------------------------

**Description**

Stats on contribution per companies. The data contains list of companies with their metric.
Companies which metric is 0 are omitted.

**Request**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /api/1.0/stats/companies                                          | Contribution by Companies                           |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

**Example Request**

.. sourcecode:: none

    GET /api/1.0/stats/companies?release=havana&metric=commits&project_type=openstack&module=neutron

**Example Response**

.. sourcecode:: json

    {
        "stats": [
            {
                "metric": 155,
                "id": "VMware",
                "name": "VMware"
            },
            {
                "metric": 76,
                "id": "Mirantis",
                "name": "Mirantis"
            },
            {
                "metric": 53,
                "id": "Red Hat",
                "name": "Red Hat"
            },
            {
                "metric": 49,
                "id": "Cisco Systems",
                "name": "Cisco Systems"
            },
            {
                "metric": 46,
                "id": "*independent",
                "name": "*independent"
            }
        ]
    }


2.4 Contribution by Engineers
-----------------------------

**Description**

Stats on contribution per engineers. The data contains list of engineers with their metric.
Engineers who has metric 0 are omitted. For reviews also added column with review distribution.

**Request**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /api/1.0/stats/engineers                                          | Contribution by Engineers                           |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

**Example Request: Commits**

.. sourcecode:: none

    GET /api/1.0/stats/engineers?release=havana&metric=commits&project_type=openstack&module=pbr

**Example Response**

.. sourcecode:: json

    {
        "stats": [
            {
                "metric": 54,
                "id": "mordred",
                "name": "Monty Taylor"
            },
            {
                "metric": 6,
                "id": "jdanjou",
                "name": "Julien Danjou"
            },
            {
                "metric": 4,
                "id": "doug-hellmann",
                "name": "Doug Hellmann"
            },
            {
                "metric": 3,
                "id": "slukjanov",
                "name": "Sergey Lukjanov"
            }
        ]
    }

**Example Request: Reviews**

.. sourcecode:: none

    GET /api/1.0/stats/engineers?release=havana&metric=marks&project_type=openstack&module=pbr


**Example Response**

.. sourcecode:: json

    {
        "stats": [
            {
                "comment": "1|3|55|45 (96.2%)",
                "metric": 104,
                "id": "mordred",
                "name": "Monty Taylor"
            },
            {
                "comment": "0|13|18|51 (84.1%)",
                "metric": 82,
                "id": "cboylan",
                "name": "Clark Boylan"
            },
            {
                "comment": "0|13|11|36 (78.3%)",
                "metric": 60,
                "id": "doug-hellmann",
                "name": "Doug Hellmann"
            }
        ]
    }


2.5 Activity log
----------------

**Description**

Depending on selected metric Activity log contains commits, reviews, emails or blueprints.

**Request**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /api/1.0/activity                                                 | Activity log                                        |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

When querying the activity log, the page_size and start_record parameters can be used to manage
the paging of results (splitting results over multiple requests/responses). The default value of
page_size is 10.

**Example Response**

.. sourcecode:: json

    {
        "activity": [
            {
                "record_type": "commit",
                "primary_key": "63580a7298887e6909602d8d96859b4e96b017e3",
                "commit_id": "63580a7298887e6909602d8d96859b4e96b017e3",
                "user_id": "zulcss",
                "launchpad_id": "zulcss",
                "author_name": "Chuck Short",
                "author_email": "chuck.short@canonical.com",
                "module": "ceilometer",
                "release": "havana",
                "blueprint_id": [],
                "bug_id": [],
                "date": 1370134263,
                "branches": "master",
                "message": "Introduce py33 to tox.ini to make testing with python3 easier.\n",
                "subject": "python3: Introduce py33 to tox.ini",
                "change_id": [
                    "I96d1ecd3f0069295e27127239c83afc32673ffec"
                ],
                "company_name": "Canonical",
                "loc": 2,
                "files_changed": 1,
                "lines_added": 1,
                "lines_deleted": 1
            }
        ]
    }



2.6 Contribution summary
------------------------

**Description**

Get contribution summary: number of commits, locs, emails, drafted and completed blueprints,
review marks with distribution per mark (-2..+2).

**Request**

+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+
| Verb            | URI                                                               | Description                                         |
+=================+===================================================================+=====================================================+
| GET             | /api/1.0/contribution                                             | Contribution summary                                |
+-----------------+-------------------------------------------------------------------+-----------------------------------------------------+

**Example Response**

.. sourcecode:: json

    {
        "contribution": {
            "loc": 252,
            "new_blueprint_count": 2,
            "email_count": 7,
            "commit_count": 5,
            "competed_blueprint_count": 0,
            "marks": {
                "0": 0,
                "1": 12,
                "2": 2,
                "-1": 5,
                "-2": 0
            }
        }
    }


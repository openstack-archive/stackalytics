/*
 Copyright (c) 2014 Mirantis Inc.

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

function getUrlVars() {
    var vars = {};
    var parts = window.location.href.replace(/[?&]+([^=&]+)=([^&]*)/gi, function (m, key, value) {
        vars[key] = decodeURIComponent(value);
    });
    return vars;
}

function make_uri(uri, options) {
    var ops = {};
    $.extend(ops, getUrlVars());
    if (options != null) {
        $.extend(ops, options);
    }
    var str = $.map(ops,function (val, index) {
        return index + "=" + encodeURIComponent(val).toLowerCase();
    }).join("&");

    return (str == "") ? uri : uri + "?" + str;
}

function getPageState() {
    return {
        project_id: $('#project_id').val(),
        vendor: $('#vendor').val(),
        release_id: $('#release_id').val()
    };
}

function reload(extra) {
    window.location.search = $.map($.extend(getPageState(), extra), function (val, index) {
        return val? (index + "=" + encodeURIComponent(val)) : null;
    }).join("&")
}

function initSelectors(base_url) {

    function initSingleSelector(name, data_container, api_url, select2_extra_options, change_handler) {
        $("#" + name).val(0).select2({
            data: [{id: 0, text: "Loading..." }],
            formatSelection: function(item) { return "<div class=\"select2-loading\">" + item.text + "</div>"}
        }).select2("enable", false);

        $.ajax({
            url: api_url,
            dataType: "jsonp",
            success: function (data) {
                var initial_value = getUrlVars()[name];
                if (!initial_value && data["default"]) {
                    initial_value = data["default"];
                }
                $("#" + name).
                    val(initial_value).
                    select2($.extend({
                        data: data[data_container]
                    }, select2_extra_options)).
                    on("select2-selecting",function (e) { /* don't use 'change' event, because it changes value and then refreshes the page */
                        var options = {};
                        options[name] = e.val;
                        if (change_handler) {
                            change_handler(options);
                            console.log(options);
                        }
                        reload(options);
                    }).
                    on("select2-removed",function (e) {
                        var options = {};
                        options[name] = '';
                        reload(options);
                    }).
                    select2("enable", true);
            }
        });
    }

    initSingleSelector("project_id", "project_ids", make_uri(base_url + "api/1.0/list/project_ids"), {allowClear: true});
    initSingleSelector("vendor", "vendors", make_uri(base_url + "api/1.0/list/vendors"), {allowClear: true});
    initSingleSelector("release", "releases", make_uri(base_url + "api/1.0/list/releases"), {allowClear: true});
}

function showDriverInfo(driver) {
    $("#driver_info_container").empty();
    $("#driver_info_template").tmpl(driver).appendTo("#driver_info_container");

    var table = $("#driver_info_releases_table");
    table.dataTable({
        "bInfo": false,
        "bPaginate": false,
        "bAutoWidth": false,
        "bSearchable": false,
        "bFilter": false,
        "aaSorting": [[ 0, "desc" ]],
        "aoColumnDefs": [
            { "sClass": "center", "aTargets": [1] }
        ]
    });

    table.find(".timeago").each(function () {
        var message = $.timeago(new Date(this.title * 1000));
        $(this).text(message);
    });

    $("#driver_info_container").find(".gravatar").each(function () {
        var email = this.title;
        if (!email) {
            email = "driverlog";
        }
        $(this).append($.gravatar(email, {"image": "wavatar", "rating": "g", "size": 64}))
    });

    $("#driver_info_dialog").dialog("open");
}

function setupDriverInfoHandler(table_id, element_id, driver) {
    $("#driver_info_dialog").dialog({
        autoOpen: false,
        width: "70%",
        modal: true,
        buttons: {
            Close: function () {
                $(this).dialog("close");
            }
        },
        close: function () {
        }
    });

    $("#" + table_id).on("click", "#" + element_id, function (event) {
        event.preventDefault();
        event.stopPropagation();

        showDriverInfo(driver);
    });
}

function showSummary(base_url) {
    var table_column_names = ["project_name", "vendor", "driver_info", "in_trunk", "ci_tested", "maintainers_info"];
    var table_id = "data_table";

    $.ajax({
        url: make_uri(base_url + "api/1.0/drivers"),
        dataType: "jsonp",

        success: function (data) {
            var tableData = data["drivers"];

            var tableColumns = [];
            for (var i = 0; i < table_column_names.length; i++) {
                tableColumns.push({"mData": table_column_names[i]});
            }

            for (i = 0; i < tableData.length; i++) {
                tableData[i].driver_info = "<a href=\"#\" title=\"Show driver details\">" + tableData[i].name + "</a>";
                tableData[i].driver_info = "<div id=\"driver_" + i + "\">" + tableData[i].driver_info + "</div>";

                if (tableData[i].description) {
                    tableData[i].driver_info += "<div>" + tableData[i].description + "</div>";
                }

                setupDriverInfoHandler(table_id, "driver_" + i, tableData[i]);

                var releases_list = [];
                for (var j = 0; j < tableData[i].releases_info.length; j++) {
                    releases_list.push("<a href=\"" + tableData[i].releases_info[j].wiki + "\">" +
                            tableData[i].releases_info[j].name + "</a>");
                }
                tableData[i].in_trunk = releases_list.join(" ");

                tableData[i].ci_tested = "";
                if (tableData[i].ci) {
                    if (tableData[i].releases_info.length > 0) {
                        var last_release = tableData[i].releases_info[tableData[i].releases_info.length - 1].release_id;
                        var master = tableData[i].releases[last_release];
                        if (master.review_url) {
                            var ci_result = master.ci_result;
                            var ci_result_str;
                            var ci_title;
                            if (ci_result) {
                                ci_result_str = "<span style=\"color: limegreen; font-size: 130%;\">&#x2714;</span>";
                                ci_title = "CI is enabled on master and the latest job SUCCEED";
                            } else {
                                ci_result_str = "<span style=\"color: darkred\">&#x2714;</span>";
                                ci_title = "CI is enabled on master and the latest job FAILED";
                            }
                            tableData[i].ci_tested = "<a href=\"" + master.review_url +
                                    "\" title=\"" + ci_title + "\">" + ci_result_str + "</a>";
                        } else {
                            tableData[i].ci_tested = "<span style=\"color: goldenrod\" title=\"CI is configured, but no results observed\">&#x2716;</span>";
                        }
                    } else {
                        tableData[i].ci_tested = "<span style=\"color: goldenrod\" title=\"CI is configured, but no results observed\">&#x2716;</span>";
                    }
                } else {
                    tableData[i].ci_tested = "<span style=\"color: darkred\" title=\"CI is not configured\">&#x2716;</span>";
                }

                var maintainers_list = [];
                if (tableData[i].maintainers) {
                    for (j = 0; j < tableData[i].maintainers.length; j++) {
                        var maintainer = tableData[i].maintainers[j];
                        var mn = maintainer.name;
                        if (maintainer.launchpad_id) {
                            maintainers_list.push("<a href=\"http://stackalytics.com/?user_id=" +
                                maintainer.launchpad_id + "\">" + mn + "</a>");
                        }
                        else if (maintainer.irc) {
                            maintainers_list.push("<a href=\"irc:" + maintainer.irc + "\">" + mn + "</a>");
                        } else {
                            maintainers_list.push(mn);
                        }
                    }
                    tableData[i].maintainers_info = maintainers_list.join(", ");
                } else {
                    tableData[i].maintainers_info = "";
                }
            }

            if (table_id) {
                $("#" + table_id).dataTable({
                    "aLengthMenu": [
                        [10, 25, 50, -1],
                        [10, 25, 50, "All"]
                    ],
                    "aaSorting": [
                        [ 0, "asc" ],
                        [ 1, "asc"]
                    ],
                    "iDisplayLength": -1,
                    "bAutoWidth": false,
                    "bPaginate": false,
                    "aaData": tableData,
                    "aoColumns": tableColumns
                });
            }
        }
    });
}

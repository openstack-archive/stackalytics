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

function make_std_options() {
    var options = {};
    options['project_id'] = $('#project_selector').val();
    options['vendor'] = $('#vendor_selector').val();
    options['release_id'] = $('#release_selector').val();

    return options;
}

function reload() {
    var ops = {};
    $.extend(ops, getUrlVars());
    $.extend(ops, make_std_options());
    window.location.search = $.map(ops,function (val, index) {
        return index + "=" + encodeURIComponent(val);
    }).join("&")
}

function init_selectors(base_url) {
    $(document).tooltip();

    var project_id = getUrlVars()["project_id"];

    $("#project_selector").val(project_id).select2({
        allowClear: true,
        placeholder: "Select Project",
        ajax: {
            url: make_uri(base_url + "api/1.0/list/project_ids"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                return {results: data["project_ids"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "api/1.0/list/project_ids/" + id), {
                    dataType: "jsonp"
                }).done(function (data) {
                        callback(data["project_id"]);
                    });
            }
        }
    });

    $('#project_selector')
        .on("change", function (e) {
            reload();
        });

    var vendor = getUrlVars()["vendor"];

    $("#vendor_selector").val(vendor).select2({
        allowClear: true,
        placeholder: "Select Vendor",
        ajax: {
            url: make_uri(base_url + "api/1.0/list/vendors"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                return {results: data["vendors"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "api/1.0/list/vendors/" + id), {
                    dataType: "jsonp"
                }).done(function (data) {
                        callback(data["vendor"]);
                    });
            }
        }
    });

    $('#vendor_selector')
        .on("change", function (e) {
            reload();
        });

    var release_id = getUrlVars()["release_id"];

    $("#release_selector").val(release_id).select2({
        allowClear: true,
        placeholder: "Select Release",
        ajax: {
            url: make_uri(base_url + "api/1.0/list/releases"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                return {results: data["releases"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "api/1.0/list/releases/" + id), {
                    dataType: "jsonp"
                }).done(function (data) {
                        callback(data["release"]);
                    });
            }
        }
    });

    $('#release_selector')
        .on("change", function (e) {
            reload();
        });

}

function show_driver_info(driver) {
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

function setup_driver_info_handler(table_id, element_id, driver) {
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

        show_driver_info(driver);
    });
}

function show_summary(base_url) {
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

                setup_driver_info_handler(table_id, "driver_" + i, tableData[i]);

                var releases_list = [];
                for (var j = 0; j < tableData[i].releases_info.length; j++) {
                    releases_list.push("<a href=\"" + tableData[i].releases_info[j].wiki + "\" target=\"_blank\">" +
                            tableData[i].releases_info[j].name + "</a>");
                }
                tableData[i].in_trunk = releases_list.join(" ");

                tableData[i].ci_tested = "";
                if (tableData[i].ci) {
                    if (tableData[i].releases_info.length > 0) {
                        var last_release = tableData[i].releases_info[tableData[i].releases_info.length - 1].release_id;
                        var master = tableData[i].releases[last_release];
                        if (master.review_url) {
                            tableData[i].ci_tested = "<a href=\"" + master.review_url +
                                    "\" target=\"_blank\" title=\"Click for details\"><span style=\"color: #008000\">&#x2714;</span></a>";
                        } else {
                            tableData[i].ci_tested = "<span style=\"color: #808080\">&#x2714;</span>";
                        }
                    } else {
                        tableData[i].ci_tested = "<span style=\"color: #808080\">&#x2714;</span>";
                    }
                } else {
                    tableData[i].ci_tested = "<span style=\"color: darkred\">&#x2716;</span>";
                }

                var maintainers_list = [];
                if (tableData[i].maintainers) {
                    for (j = 0; j < tableData[i].maintainers.length; j++) {
                        var maintainer = tableData[i].maintainers[j];
                        var mn = maintainer.name;
                        if (maintainer.launchpad_id) {
                            maintainers_list.push("<a href=\"http://stackalytics.com/?user_id=" +
                                maintainer.launchpad_id + "\" target=\"_blank\">" + mn + "</a>");
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
                    "aaData": tableData,
                    "aoColumns": tableColumns
                });
            }
        }
    });
}

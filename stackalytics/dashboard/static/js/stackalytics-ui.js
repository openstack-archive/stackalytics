/*
 Copyright (c) 2013 Mirantis Inc.

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


function stringTrunc(string, length) {

    if (string.length <= length) {
        return string;
    }

    return string.substr(0, string.substr(0, length).lastIndexOf(' ')) + "...";
}

function _createTimeline(data) {
    var plot = $.jqplot('timeline', data, {
        gridPadding: {
            right: 35
        },
        cursor: {
            show: false
        },
        highlighter: {
            show: true,
            sizeAdjust: 6
        },
        axes: {
            xaxis: {
                tickRenderer: $.jqplot.CanvasAxisTickRenderer,
                tickOptions: {
                    fontSize: '8pt',
                    angle: -90,
                    formatString: '%b \'%y'
                },
                renderer: $.jqplot.DateAxisRenderer,
                tickInterval: '1 month'
            },
            yaxis: {
                min: 0,
                label: ''
            },
            y2axis: {
                min: 0,
                label: ''
            }
        },
        series: [
            {
                shadow: false,
                fill: true,
                fillColor: '#4bb2c5',
                fillAlpha: 0.3
            },
            {
                shadow: false,
                fill: true,
                color: '#4bb2c5',
                fillColor: '#4bb2c5'
            },
            {
                shadow: false,
                lineWidth: 1.5,
                showMarker: true,
                markerOptions: {size: 5},
                yaxis: 'y2axis'
            }
        ]
    });

    $('.navigation').resize(function () {
        plot.replot({resetAxes: true});
    })

}

function renderTimeline(options) {
    $(document).ready(function () {
        $.ajax({
            url: makeURI("/api/1.0/stats/timeline", options),
            dataType: "json",
            success: function (data) {
                _createTimeline(data["timeline"]);
            }
        });
    });
}

function renderTableAndChart(url, container_id, table_id, chart_id, link_param, table_column_names) {

    $(document).ready(function () {

        $.ajax({
            url: makeURI(url),
            dataType: "json",
            success: function (data) {

                var tableData = [];
                //var chartData = [['name', 'metric']];

                var chartData = [];

                const limit = 10;
                var aggregate = 0;
                var i;

                data = data["stats"];

                if (data.length == 0) {
                    $("#" + container_id).hide();
                    return;
                }

                for (i = 0; i < data.length; i++) {
                    if (i < limit - 1) {
                        chartData.push([stringTrunc(data[i].name, 36), data[i].metric]);
                    } else {
                        aggregate += data[i].metric;
                    }

                    if (!data[i].link) {
                        if (data[i].id) {
                            data[i].link = makeLink(data[i].id, data[i].name, link_param, true);
                        } else {
                            data[i].link = data[i].name
                        }
                    }

                    if (data[i].core == "master") {
                        data[i].link += '&nbsp;&#x273B;'
                    } else if (data[i].core) {
                        data[i].link += "&nbsp;&#x272C; <small><i>" + data[i].core + "</i></small>";
                    }

                    tableData.push(data[i]);
                }

                if (i == limit) {
                    chartData.push([stringTrunc(data[i - 1].name, 36), data[i - 1].metric]);
                } else if (i > limit) {
                    chartData.push(["others", aggregate]);
                }

                if (!table_column_names) {
                    table_column_names = ["index", "link", "metric"];
                }
                var tableColumns = [];
                var sort_by_column = 0;
                for (i = 0; i < table_column_names.length; i++) {
                    tableColumns.push({"mData": table_column_names[i]});
                    if (table_column_names[i] == "metric") {
                        sort_by_column = i;
                    }
                }

                if (table_id) {
                    $("#" + table_id).dataTable({
                        "oLanguage": {
                            "sLengthMenu": "Show _MENU_ entries",
                            "sSearch": "",
                            //"oPaginate": {
                            //    "sPrevious": "&lt;",
                            //    "sNext": "&gt;"
                            //}
                        },
                        "aLengthMenu": [
                            [10, 25, 50, -1],
                            [10, 25, 50, "All"]
                        ],
                        "aaSorting": [
                            [sort_by_column, "desc"]
                        ],
                        "sPaginationType": "simple",
                        "iDisplayLength": chart_id == 10,
                        "aaData": tableData,
                        "aoColumns": tableColumns,
                        "autoWidth": false,
                        //"sDom": '<"H"r><"clear">t<"F"pfl>',
                        "fnCreatedRow": function (row, data, dataIndex) {

                            var colors = [
                                "#754998",
                                "#d32473",
                                "#0090cd",
                                "#d12148",
                                "#f68121",
                                "#faef01",
                                "#b7cd44",
                                "#764a99",
                                "#d12148",
                                "#43cd6e"
                            ]

                            if (dataIndex < 9 && table_id != 'engineer_table') {
                                var span = $('<span>', {
                                    class: 'chartColor',
                                    style: 'background-color: ' + colors[dataIndex]
                                });

                                $(row).children("td:nth-child(2)").prepend(span);
                            }

                            if (table_id == 'engineer_table') {
                                var value = Number($(row).children("td:nth-child(9)").text().replace('%', ''));
                                var color = 'green';
                                if (value < 60) {
                                    color = 'red';
                                }
                                $(row).children("td:nth-child(9)").html('<span class="' + color + '">' + $(row).children("td:nth-child(9)").text().replace('%', '') + '</span>');
                            }
                        },
                        "fnDrawCallback": function () {
                            //$('#' + table_id + ' thead .sorting:first-child, #'+ table_id + ' thead .sorting:nth-child(2)').text('').removeClass('sorting');
                            //$('#' + table_id).parent().find('div:last-child').prependTo($('#' + table_id).parent().parent().parent().parent().parent().find('.container_footer'));
                            $(".dataTables_filter input").attr("placeholder", "Search");
                            if (table_id != 'engineer_table') {

                                $('#' + table_id + ' tbody tr td:nth-child(2) a').hover(function () {
                                    if (chart.data($(this).text()).length != 0) {
                                        chart.focus($(this).text());
                                    }
                                }, function () {
                                    if (chart.data($(this).text()).length != 0) {
                                        chart.focus();
                                    }
                                });
                            }
                        }
                    });
                }

                if (chart_id && chart_id != 'engineer_chart') {
                    var colors = [
                        "#754998",
                        "#d32473",
                        "#0090cd",
                        "#d12148",
                        "#f68121",
                        "#faef01",
                        "#b7cd44",
                        "#764a99",
                        "#d12148",
                        "#43cd6e"
                    ];
                    var chartColors = {};
                    for (var i = 0; i < chartData.length; i++) {
                        chartColors[chartData[i][0]] = colors[i];
                    }

                    var chart = c3.generate({
                        bindto: d3.select("#" + chart_id),
                        legend: {
                            hide: true
                        },
                        tooltip: {
                            format: {
                                value: function (value, ratio, id, index) {
                                    return value;
                                }
                            }
                        },
                        pie: {
                            expand: false
                        },
                        data: {
                            selection: {
                                enabled: true
                            },
                            columns: chartData,
                            type: "pie",
                            colors: chartColors,
                            onclick: function (d, i) {
                                var link = $('a[data-chart="' + d.name + '"]');
                                var href = $(link).attr('href');

                                if (link.length > 0 && href !== undefined) {
                                    window.location.href = href;
                                }
                            },
                        }
                    });

                }
            }
        });
    });
}

function renderBarChart(chart_id, chart_data) {
    $.jqplot(chart_id, chart_data, {
        seriesDefaults: {
            renderer: $.jqplot.BarRenderer,
            rendererOptions: {
                barMargin: 1
            },
            pointLabels: {show: true}
        },
        axes: {
            xaxis: {
                renderer: $.jqplot.CategoryAxisRenderer,
                label: "Age"
            },
            yaxis: {
                label: "Count",
                labelRenderer: $.jqplot.CanvasAxisLabelRenderer
            }
        }
    });
}

function renderPunchCard(chart_id, chart_data) {
    $.jqplot(chart_id, chart_data, {
        seriesDefaults: {
            renderer: $.jqplot.BubbleRenderer,
            rendererOptions: {
                varyBubbleColors: false,
                color: '#a09898',
                autoscalePointsFactor: -0.25,
                highlightAlpha: 0.7
            },
            shadow: true,
            shadowAlpha: 0.05
        },
        axesDefaults: {
            tickRenderer: $.jqplot.CanvasAxisTickRenderer
        },
        axes: {
            xaxis: {
                label: 'hour, UTC',
                labelRenderer: $.jqplot.CanvasAxisLabelRenderer,
                tickOptions: {
                    formatter: function (format, val) {
                        if (val < 0 || val > 23) {
                            return ""
                        }
                        return val;
                    }
                }
            },
            yaxis: {
                label: 'day of week',
                labelRenderer: $.jqplot.CanvasAxisLabelRenderer,
                tickOptions: {
                    formatter: function (format, val) {
                        if (val < 0 || val > 6) {
                            return ""
                        }
                        var labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].reverse();
                        return labels[val];
                    }
                }
            }
        }
    });
}

function extendWithGravatar(record, image_size) {
    var gravatar = "stackalytics";
    if (record.author_email) {
        gravatar = record.author_email;
    } else if (record.emails && record.emails.length > 0) {
        gravatar = record.emails[0];
    } else if (record.user_id) {
        gravatar = record.user_id;
    }
    record.gravatar = $.gravatarImageURI(gravatar, {
        "image": "wavatar",
        "rating": "g",
        "size": image_size ? image_size : 64
    });
}

function extendWithTweet(record) {
    var tweet = null;

    if (record.record_type == "commit") {
        tweet = "«" + record.subject + "» is committed by " + record.author_name + " in " + record.module;
    } else if (record.record_type == "mark") {
        if (record.type == "Workflow" && record.value == 1) {
            tweet = record.author_name + " approved «" + record.parent_subject + "» in " + record.module + ":P";
        } else if (record.type == "Self-Workflow" && record.value == 1) {
            tweet = record.author_name + " self-approved patch in " + record.module;
        } else if (record.type == "Workflow" && record.value == -1) {
            tweet = record.author_name + " work in progress on patch in " + record.module;
        } else if (record.type == "Abandon" || record.type == "Self-Abandon") {
            tweet = record.author_name + " abandoned patch in " + record.module;
        } else {
            var smile = [";(", ":(", "", ":)", ":D"][record.value + 2];
            tweet = "Got " + ((record.value > 0) ? "+" : "") + record.value + " from " + record.author_name + " on patch in " + record.module + smile;
        }
    } else if (record.record_type == "review") {
        tweet = record.status + " change request by " + record.author_name + " in " + record.module;
    } else if (record.record_type == "patch") {
        tweet = record.author_name + " submitted «" + record.parent_subject + "» in " + record.module;
    } else if (record.record_type == "email") {
        tweet = record.author_name + " emails about " + record.subject;
    } else if (record.record_type == "bpd" || record.record_type == "bpc") {
        tweet = "Blueprint «" + record.title + "» in " + record.module;
    } else if (record.record_type == "bugf" || record.record_type == "bugr") {
        tweet = record.status + " bug «" + record.title + "» in " + record.module + " " + record.web_link;
    } else if (record.record_type == "tr") {
        tweet = record.author_name + " translated " + record.loc + " words into " + record.language;
    }

    record.tweet = tweet;
    record.tweet_url = "http://stackalytics.com/report/record/" + record.primary_key;
}

function encodeURI(s) {
    s = encodeURIComponent(s);
    s = s.replace("*", "%2A");
    return s;
}

function getUrlVars() {
    var vars = {};
    window.location.href.replace(/[?&]+([^=&]+)=([^&]*)/gi, function (m, key, value) {
        vars[key] = decodeURIComponent(value);
    });
    return vars;
}

function makeLink(id, title, param_name, data_attr) {
    var options = {};
    var data = "";
    if (data_attr) {
        data = ' data-chart="' + title + '" ';
    }
    options[param_name] = id.toLowerCase();
    var link = makeURI("/" + window.location.pathname.split('/')[1], options);
    return "<a " + data + " href=\"" + link + "\">" + title + "</a>"
}

function makeURI(uri, options) {
    var ops = {};

    if (window.location.pathname.split('/')[1] == 'cncf') {
        ops = makeDate({project_type: "cncf-group", release: "all", metric: "commits"});
    }

    if (window.location.pathname.split('/')[1] == 'unaffiliated') {
        ops = makeDate({project_type: "unaffiliated", release: "all", metric: "commits"});
    }

    $.extend(ops, getUrlVars());
    if (options != null) {
        $.extend(ops, options);
    }
    var str = $.map(ops, function (val, index) {
        return index + "=" + encodeURI(("" + val).replace("&", "")).toLowerCase();
    }).join("&");

    return (str == "") ? uri : uri + "?" + str;
}

function makeDate(ops) {
    var date = getUrlVars()['date'];

    var result = {};

    if (!date || date == 'all') {
        return ops;
    }

    var end_date = new Date();
    var start_date = new Date().setDate(end_date.getDate() - Number(date));
    return $.extend(ops, {start_date: toTimestamp(new Date(start_date)), end_date: toTimestamp(new Date())});
}

function toTimestamp(strDate) {
    var datum = Date.parse(strDate);
    return datum / 1000;
}

function getPageState() {
    return {
        release: $('#release').val(),
        project_type: $('#project_type').val(),
        module: $('#module').val(),
        company: $('#company').val(),
        user_id: $('#user').val(),
        metric: $('#metric').val(),
        date: $('#date').val()
    };
}

function reload(extra) {
    window.location.search = $.map($.extend(getUrlVars(), extra), function (val, index) {
        return val ? (index + "=" + val) : null;
    }).join("&")
}

function initSingleSelector(name, api_url, select2_extra_options, change_handler) {
    var selectorId = "#" + name + "_selector";

    $(selectorId).val(0).select2({
        data: [
            {id: 0, text: "Loading..."}
        ],
        formatSelection: function (item) {
            return "<div class=\"select2-loading\">" + item.text + "</div>"
        }
    });

    if (name == 'date') {
        var initial_value = getUrlVars()[name];
        if (initial_value) {
            initial_value = (initial_value).toLocaleLowerCase();
        } else {
            initial_value = 'all';
        }
        $(selectorId).val(initial_value).select2($.extend({
            data: [{"text": "All", "id": "all"}, {"text": "7 days", "id": "7"}, {
                "text": "30 days",
                "id": "30"
            }, {"text": "60 days", "id": "60"}, {"text": "90 days", "id": "90"}, {
                "text": "180 days",
                "id": "180"
            }]
        }, select2_extra_options)).on("select2-selecting", function (e) {
            var options = {};
            options[name] = e.val;
            if (change_handler) {
                change_handler(options);
            }
            reload(options);
        }).on("select2-removed", function (e) {
            console.log('select2-removed');
            var options = {};
            options[name] = '';
            reload(options);
        }).select2("enable", true);
    } else {
        $.ajax({
            url: api_url,
            dataType: "json",
            success: function (data) {
                var initial_value = getUrlVars()[name];
                if (initial_value) {
                    initial_value = (initial_value).toLocaleLowerCase();
                } else if (window.location.pathname.split('/')[1] == 'cncf') {

                    switch (name) {
                        case "release":
                            initial_value = "all";
                            break;
                        case "metric":
                            initial_value = "commits";
                            break;
                        case "project_type":
                            initial_value = "cncf-group";
                            break;
                        default:
                            initial_value = data["default"];
                            break;
                    }
                } else if (window.location.pathname.split('/')[1] == 'unaffiliated') {
                    switch (name) {
                        case "release":
                            initial_value = "all";
                            break;
                        case "metric":
                            initial_value = "commits";
                            break;
                        case "project_type":
                            initial_value = "unaffiliated";
                            break;
                        default:
                            initial_value = data["default"];
                            break;
                    }
                } else if (data["default"]) {
                    initial_value = data["default"];
                }


                var selectData = data["data"];

                if (name == 'project_type') {
                    selectData = processProjects(data["data"]);
                }

                if (name == 'release') {
                    var filter = "openstack";
                }


                $(selectorId).val(initial_value).select2($.extend({
                    data: selectData
                }, select2_extra_options)).on("select2-selecting", function (e) {
                    var options = {};
                    options[name] = e.val;
                    if (change_handler) {
                        change_handler(options);
                    }
                    reload(options);
                }).on("select2-removed", function (e) {
                    console.log('select2-removed');
                    var options = {};
                    options[name] = '';
                    reload(options);
                }).select2("enable", true);
            }
        });
    }
}

function initSelectors(base_url) {
    initSingleSelector("release", makeURI(base_url + "/api/1.0/releases"));
    initSingleSelector("project_type", makeURI(base_url + "/api/1.0/project_types"), {
        formatResultCssClass: function (item) {
            return (item.child) ? "project_group_item" : "project_group";
        }
    }, function (options) {
        options['module'] = null;
    });
    initSingleSelector("module", makeURI(base_url + "/api/1.0/modules", {tags: "module,program,group"}), {
        formatResultCssClass: function (item) {
            return (item.tag) ? ("select_module_" + item.tag) : "";
        },
        allowClear: true
    });
    initSingleSelector("company", makeURI(base_url + "/api/1.0/companies"), {allowClear: true});
    initSingleSelector("user_id", makeURI(base_url + "/api/1.0/users"), {allowClear: true});
    initSingleSelector("metric", makeURI(base_url + "/api/1.0/metrics"));
    initSingleSelector("date", "", {allowClear: false});
}

function processProjects(data) {

    var result = {};
    var parent = "";
    for (i = 0; i < data.length; i++) {
        if (!data[i].child) {
            //create new array
            parent = data[i].id;
            result[parent] = [data[i]]
        } else {
            result[parent].push(data[i]);
        }
    }

    var url = window.location.pathname.split('/')[1];

    var projects = result["all"];

    if (url == "cncf") {
        projects = result["cncf-group"];
    }
    if (url == "unaffiliated") {
        projects = result["unaffiliated"];
    }

    return projects;
}

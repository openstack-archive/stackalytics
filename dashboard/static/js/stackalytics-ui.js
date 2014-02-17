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

function createTimeline(data) {
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
                markerOptions: { size: 5 },
                yaxis: 'y2axis'
            }
        ]
    });
}

function renderTimeline(options) {
    $(document).ready(function () {
        $.ajax({
            url: make_uri("/api/1.0/stats/timeline", options),
            dataType: "json",
            success: function (data) {
                createTimeline(data["timeline"]);
            }
        });
    });
}

function renderTableAndChart(url, container_id, table_id, chart_id, link_param, table_column_names) {

    $(document).ready(function () {

        $.ajax({
            url: make_uri(url),
            dataType: "jsonp",
            success: function (data) {

                var tableData = [];
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
                        chartData.push([data[i].name, data[i].metric]);
                    } else {
                        aggregate += data[i].metric;
                    }

                    if (!data[i].link) {
                        if (data[i].id) {
                            data[i].link = make_link(data[i].id, data[i].name, link_param);
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
                    chartData.push([data[i - 1].name, data[i - 1].metric]);
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
                        "aLengthMenu": [
                            [10, 25, 50, -1],
                            [10, 25, 50, "All"]
                        ],
                        "aaSorting": [
                            [ sort_by_column, "desc" ]
                        ],
                        "sPaginationType": "full_numbers",
                        "iDisplayLength": 10,
                        "aaData": tableData,
                        "aoColumns": tableColumns
                    });
                }

                if (chart_id) {
                    var plot = $.jqplot(chart_id, [chartData], {
                        seriesDefaults: {
                            renderer: jQuery.jqplot.PieRenderer,
                            rendererOptions: {
                                showDataLabels: true
                            }
                        },
                        legend: { show: true, location: 'e' }
                    });
                }
            }
        });
    });
}

function render_bar_chart(chart_id, chart_data) {
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

function render_punch_card(chart_id, chart_data) {
    $.jqplot(chart_id, chart_data, {
        seriesDefaults:{
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
                label: 'Hour',
                labelRenderer: $.jqplot.CanvasAxisLabelRenderer,
                tickOptions: {
                    formatter: function (format, val) {
                        if (val < 0 || val > 24) { return "" }
                        return val;
                    }
                }
            },
            yaxis: {
                label: 'Day of week',
                labelRenderer: $.jqplot.CanvasAxisLabelRenderer,
                tickOptions: {
                    formatter: function (format, val) {
                        if (val < 0 || val > 6) { return "" }
                        var labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
                        return labels[val];
                    }
                }
            }
        }
    });
}

function getUrlVars() {
    var vars = {};
    var parts = window.location.href.replace(/[?&]+([^=&]+)=([^&]*)/gi, function (m, key, value) {
        vars[key] = decodeURIComponent(value);
    });
    return vars;
}

function make_link(id, title, param_name) {
    var options = {};
    options[param_name] = encodeURIComponent(id).toLowerCase();
    var link = make_uri("/", options);
    return "<a href=\"" + link + "\">" + title + "</a>"
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
    options['release'] = $('#release').val();
    options['metric'] = $('#metric').val();
    options['project_type'] = $('#project_type').val();
    options['module'] = $('#module').val() || '';
    options['company'] = $('#company').val() || '';
    options['user_id'] = $('#user').val() || '';

    return options;
}

function reload() {
    window.location.search = $.map(make_std_options(),function (val, index) {
        return index + "=" + encodeURIComponent(val);
    }).join("&")
}

function init_selectors(base_url) {
    var release = getUrlVars()["release"];
    if (!release) {
        release = "_default";
    }
    $("#release").val(release).select2({
        ajax: {
            url: make_uri(base_url + "/api/1.0/releases"),
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
            $.ajax(make_uri(base_url + "/api/1.0/releases/" + id), {
                dataType: "jsonp"
            }).done(function (data) {
                    callback(data["release"]);
                    $("#release").val(data["release"].id)
                });
        }
    });
    $('#release')
        .on("change", function (e) {
            reload();
        });

    var metric = getUrlVars()["metric"];
    if (!metric) {
        metric = "_default";
    }
    $("#metric").val(metric).select2({
        ajax: {
            url: make_uri(base_url + "/api/1.0/metrics"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                return {results: data["metrics"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            $.ajax(make_uri(base_url + "/api/1.0/metrics/" + id), {
                dataType: "jsonp"
            }).done(function (data) {
                    callback(data["metric"]);
                    $("#metric").val(data["metric"].id);
                });
        }
    });
    $('#metric')
        .on("change", function (e) {
            reload();
        });

    var project_type = getUrlVars()["project_type"];
    if (!project_type) {
        project_type = "_default";
    }
    $("#project_type").val(project_type).select2({
        ajax: {
            url: make_uri(base_url + "/api/1.0/project_types"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                const project_types = data["project_types"];
                var result = [];
                for (var key in project_types) {
                    result.push({id: project_types[key].id, text: project_types[key].text, group: true});
                    for (var i in project_types[key].items) {
                        var item = project_types[key].items[i];
                        result.push({id: item.id, text: item.text});
                    }
                }
                return {results: result};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            $.ajax(make_uri(base_url + "/api/1.0/project_types/" + id), {
                dataType: "jsonp"
            }).done(function (data) {
                    callback(data["project_type"]);
                    $("#project_type").val(data["project_type"].id);
                });
        },
        formatResultCssClass: function (item) {
            if (item.group) {
                return "project_group"
            } else {
                return "project_group_item";
            }
        }
    });
    $('#project_type')
        .on("change", function (e) {
            $('#module').val('');
            reload();
        });

    $("#company").select2({
        allowClear: true,
        ajax: {
            url: make_uri(base_url + "/api/1.0/companies"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    company_name: term
                };
            },
            results: function (data, page) {
                return {results: data["companies"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "/api/1.0/companies/" + id), {
                    dataType: "jsonp"
                }).done(function (data) {
                        callback(data["company"]);
                    });
            }
        }
    });

    $('#company')
        .on("change", function (e) {
            reload();
        });

    $("#module").select2({
        allowClear: true,
        ajax: {
            url: make_uri(base_url + "/api/1.0/modules", {tags: "module,program,group"}),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    query: term
                };
            },
            results: function (data, page) {
                return {results: data["modules"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "/api/1.0/modules/" + id), {
                    dataType: "jsonp"
                }).done(function (data) {
                        callback(data["module"]);
                    });
            }
        },
        formatResultCssClass: function (item) {
            if (item.tag) {
                return "select_module_" + item.tag;
            }
            return "";
        }
    });

    $('#module')
        .on("change", function (e) {
            reload();
        });

    $("#user").select2({
        allowClear: true,
        ajax: {
            url: make_uri(base_url + "/api/1.0/users"),
            dataType: 'jsonp',
            data: function (term, page) {
                return {
                    user_name: term
                };
            },
            results: function (data, page) {
                return {results: data["users"]};
            }
        },
        initSelection: function (element, callback) {
            var id = $(element).val();
            if (id !== "") {
                $.ajax(make_uri(base_url + "/api/1.0/users/" + id), {
                    dataType: "json"
                }).done(function (data) {
                        callback(data["user"]);
                    });
            }
        }
    });

    $('#user')
        .on("change", function (e) {
            reload();
        });
}

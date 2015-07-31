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

function showError(container, message) {
    container.append($("<pre class='error'>Error! " + message + "</pre>"));
}

function appendKpiBlock(container_id, kpi_block) {
    var container = container_id;
    if (typeof container_id == "string") {
        container = $("#" + container_id);
    }
    var template = $("#kpi_block_template");
    if (template.length > 0) {
        container.append(template.tmpl(kpi_block));
    } else {
        container.append($("<pre>" + JSON.stringify(kpi_block) + "</pre>"));
    }
}

function processStats(container_id, url, query_options, item_id, metric, text_goal, comparator) {
    $.ajax({
        url: makeURI(url, query_options),
        dataType: "jsonp",
        success: function (data) {
            data = data["stats"];
            var position = -1;
            var sum = 0;

            for (var i = 0; i < data.length; i++) {
                sum += data[i][metric];
                data[i].index = data[i]["index"];
                if (data[i].id == item_id) {
                    position = i;
                }
            }

            var result = {
                mark: false,
                text_goal: text_goal
            };

            if (position < 0) {
                result.info = "Item " + item_id + " is not found in the stats";
            }
            else {
                var comparison_result = comparator(data[position], sum);
                result.mark = comparison_result.mark;
                result.info = comparison_result.info;
            }
            appendKpiBlock(container_id, result);
        }
    });
}

function goalPositionInTop(container_id, query_options, item_type, item_id, position, text_goal) {
    $(document).ready(function () {
        processStats(container_id, "/api/1.0/stats/" + item_type, query_options, item_id, "metric", text_goal,
            function (item, sum) {
                var mark = item.index <= position;
                return {
                    mark: mark,
                    info: mark ? "Achieved position is " + item.index :
                        "Position " + item.index + " is worse than the goal position " + position,
                    value: item.index
                }
            });
    });
}

function goalMetric(container_id, query_options, item_type, item_id, target, text_goal) {
    $(document).ready(function () {
        processStats(container_id, "/api/1.0/stats/" + item_type, query_options, item_id, "metric", text_goal,
            function (item, sum) {
                var mark = item.metric >= target;
                return {
                    mark: mark,
                    info: mark ? "Achieved metric " + item.metric :
                        "Metric " + item.metric + " is worse than the goal in " + target,
                    value: item.index
                }
            });
    });
}

function goalPercentageInTopLessThan(container_id, query_options, item_type, item_id, target_percentage, text_goal) {
    $(document).ready(function () {
        processStats(container_id, "/api/1.0/stats/" + item_type, query_options, item_id, "metric", text_goal,
            function (item, sum) {
                var percentage = item.metric / sum;
                var mark = percentage <= target_percentage;
                var percentage_formatted = Math.round(percentage * 100) + "%";
                var goal_percentage_formatted = Math.round(target_percentage * 100) + "%";
                return {
                    mark: mark,
                    info: mark ? "Achieved percentage " + percentage_formatted :
                        "Value " + percentage_formatted + " is more than the goal " + goal_percentage_formatted,
                    value: percentage_formatted
                }
            });
    });
}

function goalDisagreementRatioLessThan(container_id, query_options, item_id, target_percentage, text_goal) {
    $(document).ready(function () {
        processStats(container_id, "/api/1.0/stats/engineers", query_options, item_id, "disagreement_ratio", text_goal,
            function (item, sum) {
                var percentage = parseFloat(item["disagreement_ratio"]);
                var mark = percentage < target_percentage * 100;
                var goal_percentage_formatted = Math.round(target_percentage * 100) + "%";
                return {
                    mark: mark,
                    info: mark ? "Achieved percentage " + item["disagreement_ratio"] :
                        "Value " + item["disagreement_ratio"] + " is more than the goal " + goal_percentage_formatted,
                    value: percentage
                }
            });
    });
}

function goalCoreEngineerInProject(container_id, user_id, project, text_goal) {
    $(document).ready(function () {
        $.ajax({
            url: makeURI("/api/1.0/users/" + user_id),
            dataType: "jsonp",
            success: function (data) {
                var user = data.user;
                var is_core = false;
                if (user.core) {
                    for (var i in user.core) {
                        if (user.core[i][0] == project) {
                            is_core = true;
                        }
                    }
                }
                var result = {
                    mark: is_core,
                    text_goal: text_goal,
                    info: user.user_name + " (" + user_id + ") is " + (is_core ? "" : "not ") + "core engineer in " + project
                };
                appendKpiBlock(container_id, result);
            },
            error: function () {
                var result = {
                    mark: false,
                    text_goal: text_goal,
                    info: "Item " + user_id + " is not found in the stats"
                };
                appendKpiBlock(container_id, result);
            }
        });
    });
}

function loadAndShowUserProfile(container, user_id) {
    $.ajax({
        url: makeURI("/api/1.0/users/" + user_id),
        dataType: "json",
        success: function (data) {
            var user = data["user"];
            container.html(user["user_name"] + " (" + user["user_id"] + ")");
        }
    });
}

function loadAndShowModuleDetails(container, module_id) {
    $.ajax({
        url: makeURI("/api/1.0/modules/" + module_id),
        dataType: "json",
        success: function (data) {
            var module = data["module"];
            container.html(module["name"] + " (" + module["id"] + ")");
        }
    });
}

var now = Math.floor(Date.now() / 1000);

var release_pattern = /Release (\S+)/;
var group_pattern = /Group (\S+)/;
var company_pattern = /Company (\S+)/;
var user_pattern = /User (\S+)/;

var in_pattern = /.*?(\s+in\s+(\S+)).*/;
var during_pattern = /.*?(\s+during\s+(\d+)\s+days).*/;
var make_pattern = /(make|draft|send|write|implement|file|fix|complete)\s+(\d+)\s+(\S+)/;
var top_pattern = /top\s+(\d+)\s+by\s+(\S+)/;
var core_pattern = /(become|stay)\s+core/;
var not_less_than_pattern = /less\s+than\s+(\d+)%\s+by\s+(\S+)/;

function makeKpiRequestOptions(release, metric, module, duration) {
    var options = {metric: metric, module: module, project_type: "all"};
    if (duration) {
        options["start_date"] = now - duration * 60 * 60 * 24;
        options["release"] = "all";
    } else {
        options["release"] = release;
    }
    return options;
}

function runMakeStatement(statement, verb, count, noun, duration, item_type, item_id, module, release, container) {
    var metric = noun;

    if (noun == "blueprints") {
        metric = (verb == "draft" || verb == "file") ? "bpd" : "bpc";
    }
    if (noun == "bugs") {
        metric = (verb == "file") ? "filed-bugs" : "resolved-bugs";
    }
    if (noun == "reviews") {
        metric = "marks";
    }

    goalMetric(container, makeKpiRequestOptions(release, metric, module, duration),
        item_type, item_id, count, statement);
}

function runTopStatement(statement, position, noun, duration, item_type, item_id, module, release, container) {
    var metric = noun;
    if (noun == "reviews") {
        metric = "marks";
    }

    goalPositionInTop(container, makeKpiRequestOptions(release, metric, module, duration),
        item_type, item_id, position, statement);
}

function runNotLessThanStatement(statement, percentage, noun, duration, item_type, item_id, module, release, container) {
    var metric = noun;
    if (noun == "reviews") {
        metric = "marks";
    }

    goalPercentageInTopLessThan(container,
        makeKpiRequestOptions(release, metric, module, duration),
        item_type, item_id, percentage / 100.0, statement);
}

function parseStatements(item_type, item_id, module, release, details, container) {
    for (var i in details) {
        var original_statement = details[i];
        var statement = original_statement;
        var local_module = module;
        var duration = null;

        var pattern_match = in_pattern.exec(statement);
        if (pattern_match) {
            local_module = pattern_match[2];
            statement = statement.replace(pattern_match[1], "");
        }
        pattern_match = during_pattern.exec(statement);
        if (pattern_match) {
            duration = pattern_match[2];
            statement = statement.replace(pattern_match[1], "");
        }

        statement = statement.trim();

        pattern_match = make_pattern.exec(statement);
        if (pattern_match) {
            runMakeStatement(original_statement, pattern_match[1], pattern_match[2], pattern_match[3], duration,
                item_type, item_id, local_module, release, container);
            continue;
        }

        pattern_match = top_pattern.exec(statement);
        if (pattern_match) {
            runTopStatement(original_statement, pattern_match[1], pattern_match[2], duration,
                item_type, item_id, local_module, release, container);
            continue;
        }

        pattern_match = core_pattern.exec(statement);
        if (pattern_match) {
            goalCoreEngineerInProject(container, item_id, local_module, original_statement);
            continue;
        }

        pattern_match = not_less_than_pattern.exec(statement);
        if (pattern_match) {
            runNotLessThanStatement(original_statement, pattern_match[1], pattern_match[2], duration,
                item_type, item_id, local_module, release, container);
            continue;
        }

        showError(container, "Could not parse statement: '" + statement + "'");
    }
}

function parseGroup(group, release, details, container) {
    var users = [];

    for (var token in details) {
        var pattern_match = user_pattern.exec(token);
        if (pattern_match) {
            var user = pattern_match[1];
            users.push(user);

            var body = $("<div id='u" + Math.random() + "'/>");
            var user_title_block = $("<h3>" + user + "</h3>");
            container.append(user_title_block).append(body);

            loadAndShowUserProfile(user_title_block, user);

            parseStatements("engineers", user, group, release, details[token], body);
            continue;
        }

        pattern_match = company_pattern.exec(token);
        if (pattern_match) {
            var company = pattern_match[1];

            body = $("<div/>");
            container.append($("<h3>" + company + "</h3>")).append(body);

            parseStatements("companies", company, group, release, details[token], body);
            continue;
        }

        showError(container, "Could not parse line: '" + details[token] + "'");
    }
}

function parseRelease(release, details, container) {
    for (var token in details) {
        var pattern_match = group_pattern.exec(token);
        if (pattern_match) {
            var group = pattern_match[1];

            var body = $("<div/>");
            var title_block = $("<h2>" + group + "</h2>");
            container.append(title_block).append(body);

            loadAndShowModuleDetails(title_block, group);

            parseGroup(group, release, details[token], body);
            continue;
        }

        pattern_match = company_pattern.exec(token);
        if (pattern_match) {
            var company = pattern_match[1];

            body = $("<div/>");
            container.append($("<h2>" + company + "</h2>")).append(body);

            parseStatements("companies", company, "all", release, details[token], body);
            continue;
        }

        showError(container, "Could not parse line: '" + token + "'");
    }
}

function parseKpiScript(parsed_script, container) {
    for (var token in parsed_script) {
        var pattern_match = release_pattern.exec(token);
        if (pattern_match) {
            var release = pattern_match[1];

            var body = $("<div/>");
            $(container).append($("<h1>" + release + "</h1>")).append(body);

            parseRelease(release, parsed_script[token], body);
            continue;
        }
        showError(container, "Could not parse line: '" + token + "'");
    }
}

function readKpiScript(kpi_script, container_id) {
    var root_container = $("#" + container_id).empty();

    try {
        var parsed_script = jsyaml.safeLoad(kpi_script);
        parseKpiScript(parsed_script, root_container);
    } catch (e) {
        showError(root_container, "Could not parse script: '" + kpi_script + "'");
    }
}

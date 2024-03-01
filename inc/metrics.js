function getHttpChartData(server) {
    var hide_http_metrics = localStorage.getItem('hide_http_metrics');
    if (hide_http_metrics == 'disabled') {
        return false;
    }
    $.ajax({
        url: "/app/metrics/haproxy/" + server + "/http",
		data: {
            time_range: $( "#time-range option:selected" ).val(),
		},
		type: "POST",
        success: function (result) {    
            var data = [];
            data.push(result.chartData.http_2xx);
            data.push(result.chartData.http_3xx);
            data.push(result.chartData.http_4xx);
            data.push(result.chartData.http_5xx);
            data.push('HTTP statuses for '+result.chartData.server);

            var labels = result.chartData.labels;
            renderHttpChart(data, labels, server);
        }
    });
}
var charts = []
function renderHttpChart(data, labels, server) {
    // Преобразование данных в массивы
    const dataArray0 = data[0].split(',');
    const dataArray1 = data[1].split(',');
    const dataArray2 = data[2].split(',');
    const dataArray3 = data[3].split(',');

    // Удаление последнего пустого элемента в каждом массиве
    dataArray0.pop();
    dataArray1.pop();
    dataArray2.pop();
    dataArray3.pop();

    var ctx = document.getElementById('http_' + server).getContext('2d');
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    normalized: true,
                    label: '2xx',
                    data: dataArray0,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true
                },
                {
                    normalized: true,
                    label: '3xx',
                    data: dataArray1,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    fill: true
                },
                {
                    normalized: true,
                    label: '4xx',
                    data: dataArray2,
                    borderColor: 'rgba(255, 206, 86, 1)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    fill: true
                },
                {
                    normalized: true,
                    label: '5xx',
                    dataArray3,
                    borderColor: 'rgb(255,86,86)',
                    backgroundColor: 'rgba(255,86,86,0.2)',
                    fill: true
                },
            ],
        },
        options: {
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: data[4],
                    font: {
                        size: 20,
                    },
                },
                legend: {
                    position: 'bottom'
                }
            },
            scales: {
                y: {
                    ticks: {
                        beginAtZero: true,
                    },
                },
                x: {
                    ticks: {
                        beginAtZero: true,
                        major: {
                            enabled: true,
                            fontStyle: 'bold',
                        },
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding: 45,
                        maxRotation: 0,
                    },
                },
            },
            legend: {
                display: true,
                labels: {
                    color: 'rgb(255, 99, 132)',
                    font: {
                        size: 10,
                        family: 'BlinkMacSystemFont',
                    },
                },
            },
        },
    });
    charts.push(myChart);
}
function getChartData(server) {
    $.ajax({
        url: "/app/metrics/haproxy/" + server,
		data: {
            time_range: $( "#time-range option:selected" ).val(),
		},
		type: "POST",
        success: function (result) {
            var data = [];
            data.push(result.chartData.curr_con);
            data.push(result.chartData.curr_ssl_con);
            data.push(result.chartData.sess_rate);
            data.push(result.chartData.server);

            var labels = result.chartData.labels;
            renderChart(data, labels, server);
        }
    });
}
function renderChart(data, labels, server) {
    // Преобразование данных в массивы
    const dataArray0 = data[0].split(',');
    const dataArray1 = data[1].split(',');
    const dataArray2 = data[2].split(',');

    // Удаление последнего пустого элемента в каждом массиве
    dataArray0.pop();
    dataArray1.pop();
    dataArray2.pop();
    var ctx = document.getElementById(server);
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    normalized: true,
                    label: 'Connections',
                    data: dataArray0,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true
                },
                {
                    normalized: true,
                    label: 'SSL Connections',
                    data: dataArray1,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    fill: true
                },
                {
                    normalized: true,
                    label: 'Session rate',
                    data: dataArray2,
                    borderColor: 'rgba(255, 206, 86, 1)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                    fill: true
                }
            ]
        },
        options: {
			maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                },
                x: {
                    ticks: {
                        major: {
                            enabled: true,
                            fontStyle: 'bold'
                        },
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding: 45,
                        maxRotation: 0
                    }
                }
            },
			plugins: {
                title: {
                    display: true,
                    text: data[3],
                    font: {
                        size: 20,
                    },
                },
				legend: {
					display: true,
					labels: {
						color: 'rgb(255, 99, 132)',
						font: {
                            size: 10,
                            family: 'BlinkMacSystemFont'
                        }
					},
                    position: 'bottom'
				}
			}
        }
    });
    charts.push(myChart);
}
function getWafChartData(server) {
    $.ajax({
        url: "/app/metrics/waf/" + server,
		data: {
            time_range: $( "#time-range option:selected" ).val(),
		},
		type: "POST",
        success: function (result) {   
            var data = [];
            data.push(result.chartData.curr_con);
            data.push(result.chartData.server);
            var labels = result.chartData.labels;
            renderServiceChart(data, labels, server, 'waf');
        }
    });
}
function renderServiceChart(data, labels, server, service) {
    const dataArray = data[0].split(',');

    // Удаление последнего пустого элемента в каждом массиве
    dataArray.pop();
    var ctx = document.getElementById(service + '_' + server).getContext('2d');
    var additional_title = '';
    if (service === 'waf') {
        additional_title = 'WAF ';
    }
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    normalized: true,
                    label: 'Connections',
                    data: dataArray,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true
                }
            ]
        },
        options: {
            animation: false,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: additional_title + data[1],
                    font: {
                        size: 20
                    },
                     legend: {
                         position: 'bottom'
                     }
                },
                legend: {
                    display: true,
                    labels: {
                        color: 'rgb(255, 99, 132)',
                        font: {
                            size: '10',
                            family: 'BlinkMacSystemFont'
                        }
                    },
                    position: 'bottom'
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                },
                x: {
                    ticks: {
                        major: {
                            enabled: true,
                            fontStyle: 'bold'
                        },
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding: 45,
                        maxRotation: 0
                    }
                }
            }
        }
    });
    charts.push(myChart);
}
function getNginxChartData(server) {
    $.ajax({
        url: "/app/metrics/nginx/" + server,
		data: {
            time_range: $( "#time-range option:selected" ).val(),
		},
		type: "POST",
        success: function (result) {
            var data = [];
            data.push(result.chartData.curr_con);
            data.push(result.chartData.server);
            var labels = result.chartData.labels;
            renderServiceChart(data, labels, server, 'nginx');
        }
    });
}
function getApacheChartData(server) {
    $.ajax({
        url: "/app/metrics/apache/" + server,
		data: {
            time_range: $( "#time-range option:selected" ).val(),
		},
		type: "POST",
        success: function (result) {
            let data = [];
            data.push(result.chartData.curr_con);
            data.push(result.chartData.server);
            let labels = result.chartData.labels;
            renderServiceChart(data, labels, server, 'apache');
        }
    });
}
function loadMetrics() {
    let service = $('#service').val();
    $.ajax({
        url: "/app/metrics/" + service + "/table-metrics",
        beforeSend: function () {
            $('#table_metrics').html('<img class="loading_full_page" src="/app/static/images/loading.gif"  alt="loading..."/>')
        },
        type: "GET",
        success: function (data) {
            if (data.indexOf('error:') != '-1') {
                toastr.error(data);
            } else {
                $("#table_metrics").html(data);
            }
        }
    });
}
function getChartDataHapWiRam(ip) {
    $.ajax({
        url: "/app/metrics/ram",
		data: {
			metrics_hapwi_ram: '1',
			ip: ip,
			token: $('#token').val()
		},
		beforeSend: function() {
			$('#ram').html('<img class="loading_hapwi_overview" src="/app/static/images/loading.gif" alt="loading..." />')
		},
		type: "POST",
        success: function (result) {  
            let data = [];
            data.push(result.chartData.rams);
            // Получение значений из строки и разделение их на массив
            const ramsData = data[0].trim().split(' ');

            // Преобразование значений в числа
            const formattedData = ramsData.map(value => parseFloat(value));
            renderChartHapWiRam(formattedData);
        }
    });
}
function renderChartHapWiRam(data) {
    var ctx = document.getElementById('ram').getContext('2d');
    var myChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['total','used','free','shared','buff','available'],
            datasets: [
                {
                    normalized: true,
                    data: data,
                    backgroundColor: [
                        '#36a2eb',
                        '#ff6384',
                        '#33ff26',
                        '#ff9f40',
                        '#ffcd56',
                        '#4bc0c0',
                    ]
                }
            ]
        },
        options: {
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: "RAM usage in Mb",
                    font: {
                        size: 15
                    },
                    padding: {
                        top: 10,
                        bottom: 0
                    }
                },
                legend: {
                    display: false,
                    align: 'start',
                    position: 'left',
                    labels: {
                        color: 'rgb(255, 99, 132)',
                        font: {
                            size: 5,
                            family: 'BlinkMacSystemFont'
                        },
                        boxWidth: 13,
                        padding: 5
                    },
                }
            }
        }
    });
    charts.push(myChart);
}
function getChartDataHapWiCpu(ip) {
    $.ajax({
        url: "/app/metrics/cpu",
		data: {
			metrics_hapwi_cpu: '1',
			ip: ip,
			token: $('#token').val()
		},
		type: "POST",
        success: function (result) {   
            // Получение значений из строки и разделение их на массив
            const ramsData = result.chartData.cpus.trim().split(' ').map(parseFloat);

            // Преобразование значений в числа
            const formattedData = ramsData.map(value => parseFloat(value));
            renderChartHapWiCpu(formattedData);
        }
    });
}
function renderChartHapWiCpu(data) {
    var ctx = document.getElementById('cpu').getContext('2d');
    var myChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['user','sys','nice','idle','wait','hi','si','steal'],
            datasets: [
                {
                    normalized: true,
                    data: data,
                    backgroundColor: [
						'#ff6384',
						'#36a2eb',
						'#ff9f40',
						'#ffcd56',
						'#4bc0c0',
						'#5d9ceb',
						'#2c6969',
					]
                }
            ]
        },
        options: {
            animation: true,
			maintainAspectRatio: false,
			plugins: {
				title: {
					display: true,
					text: "CPU usage in %",
					font: { size: 15 },
					padding: { top: 10 }
				},
				legend: {
					display: false,
					position: 'left',
					align: 'end',
					labels: {
						color: 'rgb(255, 99, 132)',
						font: { size: 10, family: 'BlinkMacSystemFont' },
						boxWidth: 13,
						padding: 5
					},
				}
			},
            scales: {
                x: {
                    ticks: {
                        max: 100,
                        min: 100
                    }
                }
            },
        }
    });
    charts.push(myChart);
}
$( function() {
   $('#dis_table_metric').click(function() {
       localStorage.setItem('table_metrics', 0);
       $('#body_table_metrics').css('display', 'none');
       $('#en_table_metric').css('display', 'inline');
       $('#dis_table_metric').css('display', 'none');
   });
    $('#en_table_metric').click(function() {
        localStorage.setItem('table_metrics', 1);
        $('#en_table_metric').css('display', 'none');
        $('#dis_table_metric').css('display', 'inline');
        loadMetrics();
    });

    // Check is showing http metrics enabled
    var hide_http_metrics = localStorage.getItem('hide_http_metrics');
    if(hide_http_metrics === null) {
        $('#hide_http_metrics').prop('checked', false);
        $('#hide_http_metrics').checkboxradio('refresh');
        $('.http_metrics_div').show();
    } else if (hide_http_metrics === 'disabled') {
        $('#hide_http_metrics').prop('checked', true);
        $('#hide_http_metrics').checkboxradio('refresh');
        $('.http_metrics_div').hide();
    }
    // Disable or enable showing http metrics
    $('#hide_http_metrics').change(function() {
        if($(this).is(':checked')) {
            localStorage.setItem('hide_http_metrics', 'disabled');
            $('.http_metrics_div').hide();
            showMetrics();
        } else {
            localStorage.removeItem('hide_http_metrics');
            $('.http_metrics_div').show();
            showMetrics();
        }
    });
});
function showOverviewHapWI() {
    removeData();
	getChartDataHapWiCpu('1');
	getChartDataHapWiRam('1');
	NProgress.configure({showSpinner: false});
}
function updatingCpuRamCharts() {
	if (cur_url[0] == 'overview') {
		showOverviewHapWI();
	} else if (cur_url[0] == 'service' && cur_url[2]) {
		NProgress.configure({showSpinner: false});
        showOverviewHapWI();
		getChartData(server_ip);
		getHttpChartData(server_ip);
		getWafChartData(server_ip);
	} else {
        removeData();
    }
}Œ

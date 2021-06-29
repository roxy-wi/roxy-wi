function getHttpChartData(server) {
    $.ajax({
        url: "options.py",
		data: {
			new_http_metrics: '1',
			server: server,
            time_range: $( "#time-range option:selected" ).val(),
			token: $('#token').val()
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
    var ctx = 'http_'+server
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    parsing: false,
                    normalized: true,
                    label: '2xx',
                    data: data[0].split(','),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                },
                {
                    parsing: false,
                    normalized: true,
                    label: '3xx',
                    data: data[1].split(','),
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                },
                {
				    parsing: false,
                    normalized: true,
                    label: '4xx',
                    data: data[2].split(','),
                    borderColor: 'rgba(255, 206, 86, 1)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                },
                {
				    parsing: false,
                    normalized: true,
                    label: '5xx',
                    data: data[3].split(','),
                    borderColor: 'rgb(255,86,86)',
                    backgroundColor: 'rgba(255,86,86,0.2)',
                }
            ]
        },
        options: {
            animation: false,
			maintainAspectRatio: false,
			title: {
				display: true,
				text: data[4],
				fontSize: 20,
				padding: 0,
			},
            scales: {
                yAxes: [{
                    ticks: {
                        beginAtZero: true,
                    }
                }],
                xAxes: [{
                    ticks: {
                        major: {
                            enabled: true,
                            fontStyle: 'bold'
                        },
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding:45,
                        maxRotation: 0
                    }
                }]
            },
			legend: {
				display: true,
				labels: {
					fontColor: 'rgb(255, 99, 132)',
					defaultFontSize: '10',
					defaultFontFamily: 'BlinkMacSystemFont'
				},
			}
        }
    });
    charts.push(myChart);
}
function getChartData(server) {
    $.ajax({
        url: "options.py",
		data: {
			new_metrics: '1',
			server: server,
            time_range: $( "#time-range option:selected" ).val(),
			token: $('#token').val()
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
    var ctx = document.getElementById(server)
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    parsing: false,
                    normalized: true,
                    label: 'Connections',
                    data: data[0].split(','),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                },
                {
                    parsing: false,
                    normalized: true,
                    label: 'SSL Connections',
                    data: data[1].split(','),
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                },
                {
				    parsing: false,
                    normalized: true,
                    label: 'Session rate',
                    data: data[2].split(','),
                    borderColor: 'rgba(255, 206, 86, 1)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                }
            ]
        },
        options: {
            animation: false,
			maintainAspectRatio: false,
			title: {
				display: true,
				text: data[3],
				fontSize: 20,
				padding: 0,
			},
            scales: {
                yAxes: [{
                    ticks: {
                        beginAtZero: true,
                    }
                }],
                xAxes: [{
                    ticks: {
                        major: {
                            enabled: true,
                            fontStyle: 'bold'
                        },
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding:45,
                        maxRotation: 0
                    }
                }]
            },
			legend: {
				display: true,
				labels: {
					fontColor: 'rgb(255, 99, 132)',
					defaultFontSize: '10',
					defaultFontFamily: 'BlinkMacSystemFont'
				},
			}
        }
    });
    charts.push(myChart);
}

function getWafChartData(server) {
    $.ajax({
        url: "options.py",
		data: {
			new_waf_metrics: '1',
			server: server,
            time_range: $( "#time-range option:selected" ).val(),
			token: $('#token').val()
		},
		type: "POST",
        success: function (result) {   
            var data = [];
            data.push(result.chartData.curr_con);
            data.push(result.chartData.server);
            var labels = result.chartData.labels;
            renderWafChart(data, labels, server);
        }
    });
}
function renderWafChart(data, labels, server) {
    var ctx = 's_'+server
    var myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.split(','),
            datasets: [
                {
                    parsing: false,
                    normalized: true,
                    label: 'Connections',
                    data: data[0].split(','),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                }
            ]
        },
        options: {
            animation: false,
			maintainAspectRatio: false,
			title: {
				display: true,
				text: "WAF "+data[1],
				fontSize: 20,
				padding: 0,
			},
            scales: {
                yAxes: [{
                    ticks: {
                        beginAtZero: true,
                    }
                }],
                xAxes: [{
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
                }]
            },
			legend: {
				display: true,
				labels: {
					fontColor: 'rgb(255, 99, 132)',
					defaultFontSize: '10',
					defaultFontFamily: 'BlinkMacSystemFont'
				},
			}
        }
    });
    charts.push(myChart);
}
$("#secIntervals").css("display", "none");

function loadMetrics() {
	 $.ajax({
        url: "options.py",
		data: {
			table_metrics: '1',
			token: $('#token').val()
		},
		beforeSend: function() {
			$('#table_metrics').html('<img class="loading_full_page" src="/inc/images/loading.gif" />')
		},
		type: "POST",
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
        url: "options.py",
		data: {
			metrics_hapwi_ram: '1',
			ip: ip,
			token: $('#token').val()
		},
		beforeSend: function() {
			$('#ram').html('<img class="loading_hapwi_overview" src="/inc/images/loading.gif" />')
		},
		type: "POST",
        success: function (result) {  
            var data = [];
            data.push(result.chartData.rams);
            renderChartHapWiRam(data);
        }
    });
}
function renderChartHapWiRam(data) {
    var ctx = 'ram'
    var myChart = new Chart(ctx, {
        type: 'horizontalBar',
        data: {
            labels: ['total','used','free','shared','buff/cache','avaliable'],
            datasets: [
                {
                    parsing: false,
                    normalized: true,
                    data: data[0].split(' '),
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
            animation: false,
			maintainAspectRatio: false,
			title: {
				display: true,
				text: "RAM usage in Mb",
				fontSize: 15,
				padding: 0,
			},
			legend: {
				display: false,
				align: 'start',
				position: 'left',
				labels: {
					fontColor: 'rgb(255, 99, 132)',
					defaultFontSize: 2,
					fontColor: 'black',
					defaultFontFamily: 'BlinkMacSystemFont',					
					boxWidth: 13,
					padding: 5
				},
			}
        }
    });
}
function getChartDataHapWiCpu(ip) {
    $.ajax({
        url: "options.py",
		data: {
			metrics_hapwi_cpu: '1',
			ip: ip,
			token: $('#token').val()
		},
		type: "POST",
        success: function (result) {   
            var data = [];
            data.push(result.chartData.cpus);
            renderChartHapWiCpu(data);
        }
    });
}

function renderChartHapWiCpu(data) {
    var ctx = 'cpu'
    var myChart = new Chart(ctx, {
        type: 'horizontalBar',
        data: {
            labels: ['user','sys','nice','idle','wait','hi','si','steal'],
            datasets: [
                {
                    parsing: false,
                    normalized: true,
                    data: data[0].split(' '),
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
            animation: false,
			maintainAspectRatio: false,
			title: {
				display: true,
				text: "CPU usage in %",
				fontSize: 15,
				padding: 0,
			},
			legend: {
				display: false,
				position: 'left',
				align: 'end',
				labels: {
					fontColor: 'rgb(255, 99, 132)',
					defaultFontSize: 2,
					defaultFontFamily: 'BlinkMacSystemFont',
					fontColor: 'black',
					boxWidth: 13,
					padding: 5
				},
			},
            scales: {
                xAxes: [{
                    ticks: {
                        suggestedMax: 100
                    }
                }]
            },
        }
    });
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
});
function removeData() {
    for (i = 0; i < charts.length; i++) {
        chart = charts[i];
        chart.destroy();
    }
}
function showOverviewHapWI() {
	getChartDataHapWiCpu('1');
	getChartDataHapWiRam('1');
	NProgress.configure({showSpinner: false});
}
function removeCpuRamCharts() {
    var ctxCpu = document.getElementById("cpu")
    var ctxRam = document.getElementById("ram")
    ctxCpu.remove();
    ctxRam.remove();
    $('#cpu_div').html('<canvas id="cpu" role="img"></canvas>');
    $('#ram_div').html('<canvas id="ram" role="img"></canvas>');
}
function updatingCpuRamCharts() {
	if (cur_url[0] == 'overview.py') {
		removeCpuRamCharts();
		showOverviewHapWI();
	} else if (cur_url[0] == 'hapservers.py' && cur_url[1].split('=')[0] == 'service') {
		removeCpuRamCharts();
		NProgress.configure({showSpinner: false});
		getChartDataHapWiCpu(server_ip);
		getChartDataHapWiRam(server_ip);
		removeData();
		getChartData(server_ip);
		getHttpChartData(server_ip);
		getWafChartData(server_ip);
	}
}

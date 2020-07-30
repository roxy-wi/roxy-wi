function getChartData(server) {
    $.ajax({
        url: "options.py",
		data: {
			new_metrics: '1',
			server: server,
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
                    label: 'Connections',
                    data: data[0].split(','),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                },
                {
                    label: 'SSL Connections',
                    data: data[1].split(','),
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                },
				 {
                    label: 'Session rate',
                    data: data[2].split(','),
                    borderColor: 'rgba(255, 206, 86, 1)',
                    backgroundColor: 'rgba(255, 206, 86, 0.2)',
                }
            ]
        },
        options: {
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
}

function getWafChartData(server) {
    $.ajax({
        url: "options.py",
		data: {
			new_waf_metrics: '1',
			server: server,
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
                    label: 'Connections',
                    data: data[0].split(','),
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                }
            ]
        },
        options: {
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
        type: 'pie',
        data: {
            labels: ['used','free','shared','buff/cache','avaliable'],
            datasets: [
                {
                    data: data[0].split(' '),
                    backgroundColor: [						
						'#ff6384',
						'#36a2eb',
						'#ff9f40',
						'#ffcd56',
						'#4bc0c0',
						
					]
                }
            ]
        },
        options: {
			maintainAspectRatio: false,
			title: {
				display: true,
				text: "RAM usage in Mb",
				fontSize: 15,
				padding: 0,
			},
			legend: {
				display: true,
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
        type: 'pie',
        data: {
            labels: ['user','sys','nice','idle','wait','hi','si','steal'],
            datasets: [
                {
                    data: data[0].split(' '),
                    backgroundColor: [						
						'#ff6384',
						'#36a2eb',
						'#ff9f40',
						'#ffcd56',
						'#4bc0c0',
						'#5d9ceb',
						'#4bc0c0',
						
					]
                }
            ]
        },
        options: {
			maintainAspectRatio: false,
			title: {
				display: true,
				text: "CPU usage in %",
				fontSize: 15,
				padding: 0,
			},
			legend: {
				display: true,
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
			}
        }
    });
}


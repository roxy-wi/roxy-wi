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
           $( "#table_metrics" ).html( data );
        }
    });
}



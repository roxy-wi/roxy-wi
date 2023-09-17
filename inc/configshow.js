$( function() {
	$( "input[type=submit], button" ).button();
	$( ".configShow" ).accordion({
		collapsible: true,
		heightStyle: "content",
		icons: { "header": "ui-icon-plus", "activeHeader": "ui-icon-minus" }
	});
	$('#raw').click(function() {	
		$(".configShow").accordion("destroy");
		$('#raw').css('display', 'none');
		$('.numRow').css('display', 'none');
		$('#according').css('display', 'inline-block');
		$('.accordion-expand-all').css('display', 'none');
	});
	$('#according').click(function() {	
		$( ".configShow" ).accordion({
			collapsible: true,
			heightStyle: "content",
			icons: { "header": "ui-icon-plus", "activeHeader": "ui-icon-minus" }
		});
		$('#raw').css('display', 'inline-block');
		$('.numRow').css('display', 'inline-block');
		$('#according').css('display', 'none');
		$('.accordion-expand-all').css('display', 'inline-block');
	});
	var headers = $('.configShow .accordion-header');
	var contentAreas = $('.configShow .ui-accordion-content ').hide()
	.first().show().end();
	var expandLink = $('.accordion-expand-all');
	headers.click(function() {
		// close all panels
		contentAreas.slideUp();
		// open the appropriate panel
		$(this).next().slideDown();
		// reset Expand all button
		expandLink.text('Expand all')
			.data('isAllOpen', false);
		// stop page scroll
		return false;
		});
	// hook up the expand/collapse all
	expandLink.click(function(){
		var isAllOpen = !$(this).data('isAllOpen');
		console.log({isAllOpen: isAllOpen, contentAreas: contentAreas})
		contentAreas[isAllOpen? 'slideDown': 'slideUp']();
			
	expandLink.text(isAllOpen? 'Collapse All': 'Expand all')
				.data('isAllOpen', isAllOpen);    
	});
	$(".accordion-link a").on("click", function(event) { 
	  window.location.href = $(this).attr("href"); 
      event.preventDefault(); 
	 });

	$( "#saveconfig" ).on("click", ":submit", function(e){
		var frm = $('#saveconfig');
		var service = $('#service').val();
		myCodeMirror.save();
		$.ajax({
			url: frm.attr('action'),
			data: frm.serialize() + "&save=" + $(this).val(),
			type: frm.attr('method'),
			success: function( data ) {
				data = data.replace(/\n/g, "<br>");
				if (data.indexOf(service + ': command not found') != '-1') {
					try {
						toastr.error('Cannot save config. There is no ' + service);
					} catch (err) {
						console.log(err);
					}
				} else {
					toastr.clear();
					returnNiceCheckingConfig(data);
					$(window).unbind('beforeunload');
				}
				if (data.indexOf('warning: ') != '-1') {
					toastr.warning(data)
				}
			}
		});
		event.preventDefault();
	});
})

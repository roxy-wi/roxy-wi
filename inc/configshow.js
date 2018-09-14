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

})
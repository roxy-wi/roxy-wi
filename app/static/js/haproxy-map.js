let haproxyDependencyGraph = null;
let haproxyDependencyGraphData = null;
let haproxyDependencySearchTimer = null;

function destroyHaproxyDependencyGraph() {
    if (haproxyDependencyGraph) {
        haproxyDependencyGraph.destroy();
        haproxyDependencyGraph = null;
    }
}

function haproxyMapDisplayName(node) {
    return String(node.display_name || node.name || node.id || '');
}

function haproxyMapNodeLabel(node) {
    const details = node.address || (node.addresses || []).join(', ');
    let label = haproxyMapDisplayName(node);
    if (details) {
        label += '\n' + details;
    }
    if (node.defined === false) {
        label += '\nnot defined';
    }
    return label;
}

function haproxyMapSearchText(value) {
    return Object.values(value || {}).map(function (item) {
        return Array.isArray(item) ? item.join(' ') : String(item || '');
    }).join(' ').toLowerCase();
}

function haproxyMapConnectedNodeIds(graph, focusId) {
    if (!focusId) {
        return null;
    }

    const connected = new Set([focusId]);
    let changed = true;
    while (changed) {
        changed = false;
        graph.edges.forEach(function (edge) {
            if (connected.has(edge.source) && !connected.has(edge.target)) {
                connected.add(edge.target);
                changed = true;
            } else if (connected.has(edge.target) && !connected.has(edge.source)) {
                connected.add(edge.source);
                changed = true;
            }
        });
    }
    return connected;
}

function haproxyMapVisibleNodeIds(graph) {
    const focusId = $('#haproxy-map-focus').val() || '';
    const query = String($('#haproxy-map-search').val() || '').trim().toLowerCase();
    const focusIds = haproxyMapConnectedNodeIds(graph, focusId);
    let queryIds = null;

    if (query) {
        const directlyMatched = new Set();
        queryIds = new Set();
        graph.nodes.forEach(function (node) {
            if (haproxyMapSearchText(node).includes(query)) {
                directlyMatched.add(node.id);
                queryIds.add(node.id);
            }
        });
        graph.edges.forEach(function (edge) {
            if (
                directlyMatched.has(edge.source)
                || directlyMatched.has(edge.target)
                || haproxyMapSearchText(edge).includes(query)
            ) {
                queryIds.add(edge.source);
                queryIds.add(edge.target);
            }
        });
    }

    return new Set(graph.nodes.filter(function (node) {
        return (!focusIds || focusIds.has(node.id)) && (!queryIds || queryIds.has(node.id));
    }).map(function (node) {
        return node.id;
    }));
}

function haproxyMapElements(graph) {
    const focusId = $('#haproxy-map-focus').val() || '';
    const visibleNodeIds = haproxyMapVisibleNodeIds(graph);
    const nodes = graph.nodes.filter(function (node) {
        return visibleNodeIds.has(node.id);
    }).map(function (node) {
        const classes = ['type-' + node.type];
        if (node.defined === false) {
            classes.push('missing');
        }
        if (node.id === focusId) {
            classes.push('focused');
        }
        return {
            data: Object.assign({}, node, {
                displayLabel: haproxyMapNodeLabel(node)
            }),
            classes: classes.join(' ')
        };
    });
    const edges = graph.edges.filter(function (edge) {
        return visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target);
    }).map(function (edge) {
        return {
            data: Object.assign({}, edge, {
                displayLabel: edge.label || ''
            }),
            classes: 'type-' + edge.type
        };
    });

    return nodes.concat(edges);
}

function haproxyMapLayoutOptions() {
    const layout = $('#haproxy-map-layout').val() || 'breadthfirst';
    if (layout === 'breadthfirst') {
        return {
            name: 'breadthfirst',
            directed: true,
            circle: false,
            grid: true,
            spacingFactor: 1.35,
            padding: 50,
            animate: true
        };
    }
    if (layout === 'circle' || layout === 'grid') {
        return {name: layout, padding: 40, animate: true};
    }
    return {
        name: 'cose',
        randomize: false,
        idealEdgeLength: 120,
        nodeOverlap: 20,
        fit: true,
        padding: 40,
        animate: true
    };
}

function haproxyMapStyle() {
    return [
        {
            selector: 'node',
            style: {
                'label': 'data(displayLabel)',
                'text-wrap': 'wrap',
                'text-max-width': 150,
                'font-size': 11,
                'font-weight': 600,
                'color': '#0f172a',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 8,
                'background-color': '#64748b',
                'border-width': 2,
                'border-color': '#ffffff',
                'width': 44,
                'height': 44,
                'overlay-opacity': 0
            }
        },
        {selector: 'node.type-frontend', style: {'background-color': '#2563eb'}},
        {selector: 'node.type-backend', style: {'background-color': '#7c3aed', 'shape': 'hexagon'}},
        {
            selector: 'node.type-server',
            style: {'background-color': '#16a34a', 'shape': 'round-rectangle', 'width': 58, 'height': 34}
        },
        {selector: 'node.type-listen', style: {'background-color': '#f59e0b', 'shape': 'diamond'}},
        {
            selector: 'node.missing',
            style: {
                'background-color': '#fee2e2',
                'border-color': '#dc2626',
                'border-style': 'dashed',
                'border-width': 3
            }
        },
        {
            selector: 'node.focused',
            style: {'width': 58, 'height': 58, 'border-width': 4, 'border-color': '#0f172a', 'z-index': 20}
        },
        {
            selector: 'edge',
            style: {
                'curve-style': 'bezier',
                'target-arrow-shape': 'triangle',
                'line-color': '#64748b',
                'target-arrow-color': '#64748b',
                'width': 2,
                'font-size': 9,
                'color': '#475569',
                'text-background-color': '#ffffff',
                'text-background-opacity': 0.88,
                'text-background-padding': 3,
                'label': 'data(displayLabel)',
                'overlay-opacity': 0
            }
        },
        {selector: 'edge.type-default_backend', style: {'width': 3}},
        {selector: 'edge.type-use_backend', style: {'line-style': 'dashed'}},
        {
            selector: 'edge.type-server, edge.type-server-template',
            style: {'line-color': '#16a34a', 'target-arrow-color': '#16a34a'}
        },
        {
            selector: ':selected',
            style: {
                'border-width': 4,
                'border-color': '#0f172a',
                'line-color': '#0f172a',
                'target-arrow-color': '#0f172a'
            }
        }
    ];
}

function showHaproxyMapDetails(data, isEdge) {
    const $details = $('#haproxy-map-details').empty();
    const title = isEdge
        ? (data.type || 'dependency') + ': ' + (data.label || data.source + ' -> ' + data.target)
        : (data.type || 'node') + ': ' + haproxyMapDisplayName(data);
    $('<strong>').text(title).appendTo($details);

    const detail = isEdge
        ? (data.condition || data.label || '')
        : (data.address || (data.addresses || []).join(', ') || (data.defined === false ? 'Referenced but not defined' : ''));
    if (detail) {
        $('<span>').text(' | ' + detail).appendTo($details);
    }
}

function renderHaproxyDependencyGraph() {
    const container = document.getElementById('haproxy-dependency-graph');
    if (!container || !haproxyDependencyGraphData) {
        return;
    }
    if (typeof cytoscape !== 'function') {
        container.innerHTML = '<div class="empty-state">Cytoscape.js is not loaded</div>';
        return;
    }

    const elements = haproxyMapElements(haproxyDependencyGraphData);
    if (!elements.some(function (element) { return !element.data.source; })) {
        destroyHaproxyDependencyGraph();
        container.innerHTML = '<div class="empty-state">No matching HAProxy dependencies</div>';
        return;
    }

    destroyHaproxyDependencyGraph();
    container.innerHTML = '';
    haproxyDependencyGraph = cytoscape({
        container: container,
        elements: elements,
        style: haproxyMapStyle(),
        layout: haproxyMapLayoutOptions(),
        minZoom: 0.15,
        maxZoom: 2.5,
        wheelSensitivity: 0.18
    });
    haproxyDependencyGraph.on('tap', 'node', function (event) {
        showHaproxyMapDetails(event.target.data(), false);
    });
    haproxyDependencyGraph.on('tap', 'edge', function (event) {
        event.target.select();
        showHaproxyMapDetails(event.target.data(), true);
    });
    haproxyDependencyGraph.on('tap', function (event) {
        if (event.target === haproxyDependencyGraph) {
            $('#haproxy-map-details').text('Select a node or connection to see details.');
        }
    });
    setTimeout(function () {
        if (haproxyDependencyGraph) {
            haproxyDependencyGraph.resize();
            haproxyDependencyGraph.fit(undefined, 40);
        }
    }, 100);
}

function populateHaproxyMapFocus(graph) {
    const $select = $('#haproxy-map-focus').empty();
    $('<option>').val('').text('All components').appendTo($select);
    graph.nodes.slice().sort(function (left, right) {
        return haproxyMapDisplayName(left).localeCompare(haproxyMapDisplayName(right));
    }).forEach(function (node) {
        $('<option>').val(node.id).text(node.type + ': ' + haproxyMapDisplayName(node)).appendTo($select);
    });
}

function initializeHaproxyMapControls() {
    $('#haproxy-map-focus, #haproxy-map-layout')
        .off('.haproxyMap')
        .on('change.haproxyMap', renderHaproxyDependencyGraph);
    $('#haproxy-map-search')
        .off('.haproxyMap')
        .on('input.haproxyMap', function () {
            clearTimeout(haproxyDependencySearchTimer);
            haproxyDependencySearchTimer = setTimeout(renderHaproxyDependencyGraph, 150);
        });
    $('#haproxy-map-fit')
        .off('.haproxyMap')
        .on('click.haproxyMap', function () {
            if (haproxyDependencyGraph) {
                haproxyDependencyGraph.fit(undefined, 40);
            }
        });
}

function haproxyMapShell() {
    return [
        '<div class="haproxy-map-card">',
        '  <div class="haproxy-map-heading">',
        '    <h3 id="haproxy-map-title">HAProxy dependency map</h3>',
        '    <span id="haproxy-map-summary" class="haproxy-map-summary"></span>',
        '  </div>',
        '  <div class="haproxy-map-toolbar">',
        '    <input id="haproxy-map-search" class="haproxy-map-search" type="search" placeholder="Search frontend, backend, server or address..." autocomplete="off">',
        '    <select id="haproxy-map-focus" title="Focus component"><option value="">All components</option></select>',
        '    <select id="haproxy-map-layout" title="Graph layout">',
        '      <option value="breadthfirst" selected>Hierarchy</option>',
        '      <option value="cose">Force-directed</option>',
        '      <option value="circle">Circle</option>',
        '      <option value="grid">Grid</option>',
        '    </select>',
        '    <button id="haproxy-map-fit" type="button" class="ui-button ui-widget ui-corner-all">Fit</button>',
        '  </div>',
        '  <div id="haproxy-dependency-graph" class="haproxy-dependency-graph"><div class="empty-state">Loading dependency graph...</div></div>',
        '  <div class="haproxy-map-legend">',
        '    <strong>Nodes</strong>',
        '    <span><i class="haproxy-map-legend-dot haproxy-map-legend-frontend"></i>Frontend</span>',
        '    <span><i class="haproxy-map-legend-dot haproxy-map-legend-backend"></i>Backend</span>',
        '    <span><i class="haproxy-map-legend-dot haproxy-map-legend-server"></i>Server</span>',
        '    <span><i class="haproxy-map-legend-dot haproxy-map-legend-listen"></i>Listen</span>',
        '    <span><i class="haproxy-map-legend-dot haproxy-map-legend-missing"></i>Referenced, not defined</span>',
        '  </div>',
        '  <div id="haproxy-map-details" class="haproxy-map-details">Select a node or connection to see details.</div>',
        '</div>'
    ].join('');
}

function showMap() {
    destroyHaproxyDependencyGraph();
    haproxyDependencyGraphData = null;
    clearAllAjaxFields();
    $('#ajax-config_file_name').empty();
    $('#ajax').html(haproxyMapShell());

    const server = $('#serv').val();
    if (!server) {
        toastr.error('Choose a HAProxy server');
        $('#haproxy-dependency-graph').html('<div class="empty-state">Choose a HAProxy server</div>');
        return;
    }
    $.ajax({
        url: '/config/map/haproxy/' + encodeURIComponent(server) + '/show',
        dataType: 'json',
        success: function (data) {
            if (data.error) {
                toastr.error(data.error);
                $('#haproxy-dependency-graph').html('<div class="empty-state">Cannot load dependency graph</div>');
                return;
            }

            haproxyDependencyGraphData = data;
            const counts = data.counts || {};
            $('#haproxy-map-title').text('HAProxy dependency map | ' + data.server);
            $('#haproxy-map-summary').text(
                (counts.frontend || 0) + ' frontends | '
                + (counts.listen || 0) + ' listens | '
                + (counts.backend || 0) + ' backends | '
                + (counts.server || 0) + ' servers'
            );
            populateHaproxyMapFocus(data);
            initializeHaproxyMapControls();
            renderHaproxyDependencyGraph();
            toastr.clear();
        },
        error: function (xhr) {
            const response = xhr.responseJSON || {};
            const message = response.error || 'Cannot load HAProxy dependency graph';
            toastr.error(message);
            $('#haproxy-dependency-graph').html('<div class="empty-state">Cannot load dependency graph</div>');
        }
    });
}

"""Prune abandoned module branches from exported Vivado clock trees.

Development tool only; requires Python's Tcl/Tk module. Inputs must be native
exports containing Tcl lists made with ``[list set variable value]``. They are
parsed as data, never evaluated as Tcl commands. The output is a FIXED_ROUTE
reference, not a routed or deployable checkpoint. Native route, timing and
static preservation checks remain mandatory.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tkinter


def dictionary(tcl, value):
    parts = tcl.splitlist(value)
    if len(parts) % 2:
        raise ValueError('Odd-sized Tcl dictionary')
    return dict(zip(parts[::2], parts[1::2]))


def read_sets(tcl, path):
    parts = tcl.splitlist(path.read_text(encoding='utf-8'))
    if len(parts) % 3:
        raise ValueError('Expected serialized set commands')
    values = {}
    for i in range(0, len(parts), 3):
        command, name, value = parts[i:i+3]
        if command != 'set' or name in values:
            raise ValueError('Invalid or duplicate data declaration')
        values[name] = value
    return values


def prune_tree(tcl, graph):
    split = tcl.splitlist
    nodes = set(split(graph['nodes']))
    sources = split(graph['source_nodes'])
    sinks = set(split(graph['static_sink_nodes']))
    if len(sources) != 1 or sources[0] not in nodes or not sinks <= nodes:
        raise ValueError('Missing source or disconnected static load')
    root = sources[0]
    adjacent = defaultdict(list)
    edges = set()
    for row in split(graph['edges']):
        pip, up, down, directional = split(row)
        if directional not in ('0', '1') or up not in nodes or down not in nodes:
            raise ValueError(f'Invalid PIP endpoint/direction: {pip}')
        adjacent[up].append((down, directional, True))
        adjacent[down].append((up, directional, False))
        edges.add((up, down))
    if len(edges) != len(nodes)-1:
        raise ValueError('PIP graph does not have tree edge count')
    parent, children = {}, defaultdict(list)
    reached, stack = {root}, [root]
    while stack:
        node = stack.pop()
        for child, directional, forward in adjacent[node]:
            if child == parent.get(node):
                continue
            if child in reached or (directional == '1' and not forward):
                raise ValueError('Cycle or reversed directional PIP')
            parent[child] = node
            children[node].append(child)
            reached.add(child)
            stack.append(child)
    if reached != nodes:
        raise ValueError('Disconnected PIP graph')
    keep = {root}
    for sink in sinks:
        node = sink
        while node not in keep:
            keep.add(node)
            node = parent[node]

    def route(node):
        branches = [c for c in children[node] if c in keep]
        if not branches:
            return node
        return ' '.join([node] + ['{' + route(c) + '}' for c in branches[:-1]]
                        + [route(branches[-1])])

    return '{' + route(root) + '}', tuple(sorted(keep)), tuple(sorted(sinks)), {
        'before_nodes': len(nodes), 'retained_nodes': len(keep),
        'removed_exclusive_nodes': len(nodes-keep),
        'static_sink_nodes': len(sinks),
        'static_clock_pins': int(graph['static_pin_count']), 'source': root,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    if len({p.resolve() for p in (args.reference, args.graph, args.out, args.proof)}) != 4:
        raise ValueError('Inputs and outputs must have distinct paths')
    tcl = tkinter.Tcl()
    reference = read_sets(tcl, args.reference)
    routes = dictionary(tcl, reference['clock_routes'])
    nodes = dictionary(tcl, reference['clock_nodes'])
    graphs = dictionary(tcl, read_sets(tcl, args.graph)['graph'])
    if set(routes) != set(nodes) or not set(graphs) <= set(routes):
        raise ValueError('Clock sets differ')
    statistics, sinks = {}, {}
    for name, value in graphs.items():
        routes[name], nodes[name], sinks[name], statistics[name] = prune_tree(
            tcl, dictionary(tcl, value))
    output = ''
    for name, value in [('clock_routes', routes), ('clock_nodes', nodes),
                        ('static_clock_sink_nodes', sinks)]:
        flat = [item for pair in value.items() for item in pair]
        serialized = tcl.call('dict', 'create', *flat)
        output += str(tcl.call('format', '%s', tcl.call('list', 'set', name, serialized))) + '\n'
    args.out.write_text(output, encoding='utf-8')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    proof = dict(passed=True, native_validated=False,
                 method='Original single-source PIP tree; retain ancestors of every static sink',
                 clock_graph_sha256=sha(args.graph), reference_sha256=sha(args.out),
                 original_reference_sha256=sha(args.reference), script_sha256=sha(Path(__file__)),
                 statistics=statistics)
    args.proof.write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps(statistics, indent=2))


if __name__ == '__main__':
    main()

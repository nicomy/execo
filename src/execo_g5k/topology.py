# Copyright 2009-2014 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Execo.
#
# Execo is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Execo is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Execo.  If not, see <http://www.gnu.org/licenses/>

""" A module based on `networkx <http://networkx.github.io/>`_ to create a
topological graph of the Grid'5000 platform. "Nodes" are used to represent
hosts (compute nodes, switch, router, renater) and "Edges" are the network
links. Nodes has a kind data (+ power and core for compute nodes) 
whereas edges has bandwidth and latency information.
\n
All information comes from the Grid'5000 reference API

"""
from execo import logger
from api_cache import get_api_data
from networkx import Graph, set_edge_attributes, get_edge_attributes, \
    draw_networkx_nodes, draw_networkx_edges, draw_networkx_labels

arbitrary_latency = 2.25E-3

topo_cache = None


def backbone_graph():
    """Return a networkx undirected graph describing the Grid'5000
    backbone from the list of backbone equipements:
    - nodes data: kind (renater, gw, switch, )"""
    network, _ = get_api_data()
    backbone = network['backbone']
    gr = Graph()
    # Adding backbone equipments and links
    for equip in backbone:
        src = equip['uid'].replace('renater-', 'renater.')
        if not gr.has_node(src):
            gr.add_node(src, kind='renater')
        for lc in equip['linecards']:
            for port in lc['ports']:
                kind = 'renater' if not 'kind' in port else port['kind']
                dst = port['uid'] if not 'site_uid' in port else port['uid'] \
                + '.' + port['site_uid']
                dst = dst.replace('renater-', 'renater.')
                rate = lc['rate'] if not 'rate' in port else port['rate']
                latency = port['latency'] if 'latency' in port \
                    else arbitrary_latency
                if not gr.has_node(dst):
                    gr.add_node(dst, kind=kind)
                if not gr.has_edge(src, dst):
                    gr.add_edge(src, dst, bandwidth=rate, latency=latency)
    return gr


def site_graph(site):
    """Return a networkx undirected graph describing the site
    topology from the dict of hosts and list of site equipments"""
    network, all_hosts = get_api_data()
    equips = network[site]
    hosts = all_hosts[site]
    sgr = Graph()
    for equip in equips:
        src = equip['uid'] + '.' + site
        if not sgr.has_node(src):
            sgr.add_node(src, kind=equip['kind'])
        for lc in filter(lambda n: 'ports' in n, equip['linecards']):
            if not 'kind' in lc:
                lc['kind'] = 'unknown'
            for port in filter(lambda p: 'uid' in p, lc['ports']):
                kind = lc['kind'] if not 'kind' in port else port['kind']
                dst = port['uid'] + '.' + site
                rate = lc['rate'] if not 'rate' in port else port['rate']
                latency = port['latency'] if 'latency' in port \
                    else arbitrary_latency
                if kind in ['switch', 'router']:
                    if not sgr.has_node(dst):
                        sgr.add_node(dst, kind=kind)
                    if not sgr.has_edge(src, dst):
                        sgr.add_edge(src, dst, bandwidth=rate, latency=latency)
                    else:
                        tmp = get_edge_attributes(sgr, 'bandwidth')
                        if (src, dst) in tmp.keys():
                            set_edge_attributes(sgr, 'bandwidth',
                                        {(src, dst): rate + tmp[(src, dst)]})

    for cluster_hosts in hosts.itervalues():
        for host in cluster_hosts:
            src = host['uid'] + '.' + site
            if not sgr.has_node(src):
                sgr.add_node(src, kind='node',
                             power=host['performance']['core_flops'],
                             core=host['architecture']['smt_size'])
            for adapt in filter(lambda n: n['enabled'] and not n['management']
                                and n['interface'] == 'Ethernet',
                                host['network_adapters']):
                if adapt['switch'] is None:
                    logger.warning('%s: link between %s and %s is not correct',
                                    site, src, dst)
                else:
                    dst = adapt['switch'] + '.' + site
                if not sgr.has_edge(src, dst):
                    sgr.add_edge(src, dst,
                                 bandwidth=adapt['rate'],
                                 latency=latency)
    return sgr


# def gr_to_map(gr, out='png'):
#     """Export a topology graph to a map"""
#     backbone = [node[0] for node in gr.nodes_iter(data=True)
#     if node[1]['kind'] == 'renater']
#     gw_nodes = [node[0] for node in gr.nodes_iter(data=True)
#         if node[1]['kind'] == 'router']
#     sw_nodes = [node[0] for node in gr.nodes_iter(data=True)
#         if node[1]['kind'] == 'switch']
#     nodes_nodes = [node[0] for node in gr.nodes_iter(data=True)
#         if node[1]['kind'] == 'node']
# 
#     edges_1G = [(edge[0], edge[1]) for edge in gr.edges_iter(data=True)
#         if edge[2]['bandwidth'] == 1000000000]
#     edges_3G = [(edge[0], edge[1]) for edge in gr.edges_iter(data=True)
#         if edge[2]['bandwidth'] == 3000000000]
#     edges_10G = [(edge[0], edge[1]) for edge in gr.edges_iter(data=True)
#         if edge[2]['bandwidth'] == 10000000000]
#     edges_20G = [(edge[0], edge[1]) for edge in gr.edges_iter(data=True)
#         if edge[2]['bandwidth'] == 20000000000]
#     edges_other = [(edge[0], edge[1]) for edge in gr.edges_iter(data=True)
#         if edge[2]['bandwidth'] not in [1000000000, 3000000000, 10000000000,
#                                         20000000000]]
# 
# 
# 
#     logger.info('Drawing nodes')
#     draw_networkx_nodes(gr, pos, nodelist=backbone,
#         node_shape='p', node_color='#9CF7BC', node_size=200)
#     draw_networkx_nodes(gr, pos, nodelist=gw_nodes,
#         node_shape='8', node_color='#BFDFF2', node_size=300,
#         labels=gw_nodes)
#     draw_networkx_nodes(gr, pos, nodelist=sw_nodes,
#         node_shape='s', node_color='#F5C9CD', node_size=100)
#     draw_networkx_nodes(gr, pos, nodelist=nodes_nodes,
#         node_shape='o', node_color='#F0F7BE', node_size=10)

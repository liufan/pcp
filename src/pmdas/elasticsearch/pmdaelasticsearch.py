#!/usr/bin/env pmpython
#
# Copyright (C) 2018 Red Hat.
# Copyright (C) 2017 Marko Myllynen <myllynen@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#

# pylint: disable=bad-whitespace, line-too-long, too-many-return-statements
# pylint: disable=broad-except

""" Performance Metrics Domain Agent exporting Elasticsearch metrics. """

try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser

import sys
import json
from ctypes import c_int
from pcp.pmda import PMDA, pmdaMetric, pmdaIndom
from pcp.pmapi import pmUnits
from pcp.pmapi import pmContext as PCP
from cpmapi import PM_INDOM_NULL
from cpmapi import PM_TYPE_32, PM_TYPE_U32, PM_TYPE_U64, PM_TYPE_STRING
from cpmapi import PM_SEM_COUNTER, PM_SEM_INSTANT, PM_SEM_DISCRETE
from cpmapi import PM_COUNT_ONE, PM_SPACE_BYTE, PM_TIME_MSEC
from cpmapi import PM_ERR_AGAIN, PM_ERR_PMID, PM_ERR_APPVERSION

DEFAULT_PORT = 9200
DEFAULT_URL = "http://localhost:%s/" % DEFAULT_PORT
DEFAULT_VERSION = 2
DEFAULT_USER = "root"

class elasticsearchPMDA(PMDA):
    """ PCP Elasticsearch PMDA """
    def __init__(self, name, domain):
        """ Constructor """
        PMDA.__init__(self, name, domain)
        self.user = DEFAULT_USER
        self.baseurl = DEFAULT_URL
        self.auth = None
        self.password = None
        self.request = None
        self.version = DEFAULT_VERSION
        self.read_config()

        if not self.user:
            self.log("Switching to user '%s'" % self.user)
            self.set_user(self.user)

        self.connect_pmcd()
        try:
            connection = self.baseurl
            self.request = self.setup_urllib(self.baseurl, self.auth, self.password)
            request = self.request.urlopen(self.baseurl)
            request.read()
            request.close()
        except Exception as error:
            self.log("Failed to connection to Elasticsearch at %s: %s" % (connection, error))

        # metrics setup
        self.cluster_indom = PM_INDOM_NULL
        self.cluster_cluster = 0
        self.cluster_metrics = [
            # Name - type - semantics - units - help
            [ 'cluster.cluster_name',          PM_TYPE_STRING, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Name of the elasticsearch cluster'],
            [ 'cluster.status.colour',         PM_TYPE_STRING, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Status (green,yellow,red) of the elasticsearch cluster'],
            [ 'cluster.timed_out',             PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Timed out status (0:false,1:true) of the elasticsearch cluster'],
            [ 'cluster.number_of_nodes',       PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of nodes in the elasticsearch cluster'],
            [ 'cluster.number_of_data_nodes',  PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of data nodes in the elasticsearch cluster'],
            [ 'cluster.active_primary_shards', PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of active primary shards in the elasticsearch cluster'],
            [ 'cluster.active_shards',         PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of primary shards in the elasticsearch cluster'],
            [ 'cluster.relocating_shards',     PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of relocating shards in the elasticsearch cluster'],
            [ 'cluster.initializing_shards',   PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of initializing shards in the elasticsearch cluster'],
            [ 'cluster.unassigned_shards',     PM_TYPE_U32,    PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Number of unassigned shards in the elasticsearch cluster'],
            [ 'cluster.status.code',           PM_TYPE_32,     PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  'Status code (0:green,1:yellow,2:red) of the elasticsearch cluster'],
        ]

        for item in range(len(self.cluster_metrics)):
            self.add_metric(name + '.' +
                            self.cluster_metrics[item][0],
                            pmdaMetric(self.pmid(self.cluster_cluster, item),
                                       self.cluster_metrics[item][1],
                                       self.cluster_indom,
                                       self.cluster_metrics[item][2],
                                       self.cluster_metrics[item][3]),
                            self.cluster_metrics[item][4],
                            self.cluster_metrics[item][4])

        self.nodes_indom = self.indom(0)
        self.nodes_insts = pmdaIndom(self.nodes_indom, {})
        self.add_indom(self.nodes_insts)
        self.nodes_cluster = 1
        self.nodes_metrics = [
            # Name - type - semantics - units - help
            [ 'nodes.indices.size_in_bytes',                                           PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 0
            [ 'nodes.indices.docs.count',                                               PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 1
            [ 'nodes.indices.docs.num_docs',                                           PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 2
            [ 'nodes.indices.cache.field_evictions',                                   PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 3
            [ 'nodes.indices.cache.field_size_in_bytes',                               PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 4
            [ 'nodes.indices.cache.filter_count',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 5
            [ 'nodes.indices.cache.filter_evictions',                                  PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 6
            [ 'nodes.indices.cache.filter_size_in_bytes',                              PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 7
            [ 'nodes.indices.merges.current',                                          PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 8
            [ 'nodes.indices.merges.total',                                            PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 9
            [ 'nodes.indices.merges.total_time_in_millis',                             PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 10
            [ 'nodes.jvm.uptime_in_millis',                                            PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 11
            [ 'nodes.jvm.uptime',                                                      PM_TYPE_STRING, PM_SEM_INSTANT, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 12
            [ 'nodes.jvm.mem.heap_used_in_bytes',                                      PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 13
            [ 'nodes.jvm.mem.heap_committed_in_bytes',                                 PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 14
            [ 'nodes.jvm.mem.non_heap_used_in_bytes',                                  PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 15
            [ 'nodes.jvm.mem.non_heap_committed_in_bytes',                             PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 16
            [ 'nodes.jvm.threads.count',                                               PM_TYPE_U32, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 17
            [ 'nodes.jvm.threads.peak_count',                                          PM_TYPE_U32, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 18
            [ 'nodes.jvm.gc.collection_count',                                         PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 19
            [ 'nodes.jvm.gc.collection_time_in_millis',                                PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 20
            [ 'nodes.jvm.gc.collectors.Copy.collection_count',                         PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 21
            [ 'nodes.jvm.gc.collectors.Copy.collection_time_in_millis',                PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 22
            [ 'nodes.jvm.gc.collectors.ParNew.collection_count',                       PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 23
            [ 'nodes.jvm.gc.collectors.ParNew.collection_time_in_millis',              PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 24
            [ 'nodes.jvm.gc.collectors.ConcurrentMarkSweep.collection_count',          PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 25
            [ 'nodes.jvm.gc.collectors.ConcurrentMarkSweep.collection_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 26
            [ 'nodes.indices.docs.deleted',                                            PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 27
            [ 'nodes.indices.indexing.index_total',                                    PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 28
            [ 'nodes.indices.indexing.index_time_in_millis',                           PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 29
            [ 'nodes.indices.indexing.delete_total',                                   PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 30
            [ 'nodes.indices.indexing.delete_time_in_millis',                          PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 31
            [ 'nodes.indices.merges.current_docs',                                     PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 32
            [ 'nodes.indices.merges.current_size_in_bytes',                            PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 33
            [ 'nodes.indices.merges.total_docs',                                       PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 34
            [ 'nodes.indices.merges.total_size_in_bytes',                              PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 35
            [ 'nodes.indices.refresh.total',                                           PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 36
            [ 'nodes.indices.refresh.total_time_in_millis',                            PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 37
            [ 'nodes.indices.flush.total',                                             PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 38
            [ 'nodes.indices.flush.total_time_in_millis',                              PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 39
            [ 'nodes.process.timestamp',                                               PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 40
            [ 'nodes.process.open_file_descriptors',                                   PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 41
            [ 'nodes.process.cpu.percent',                                             PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 42
            [ 'nodes.process.cpu.sys_in_millis',                                       PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 43
            [ 'nodes.process.cpu.user_in_millis',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 44
            [ 'nodes.process.mem.resident_in_bytes',                                   PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 45
            [ 'nodes.process.mem.total_virtual_in_bytes',                              PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 46
            [ 'nodes.indices.store.size_in_bytes',                                     PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 47
            [ 'nodes.indices.get.total',                                               PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 48
            [ 'nodes.indices.get.time_in_millis',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 49
            [ 'nodes.indices.get.exists_total',                                        PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 50
            [ 'nodes.indices.get.exists_time_in_millis',                               PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 51
            [ 'nodes.indices.get.missing_total',                                       PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 52
            [ 'nodes.indices.get.missing_time_in_millis',                              PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 53
            [ 'nodes.indices.search.query_total',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 54
            [ 'nodes.indices.search.query_time_in_millis',                             PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 55
            [ 'nodes.indices.search.fetch_total',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 56
            [ 'nodes.indices.search.fetch_time_in_millis',                             PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0),  ''], # 57
            [ 'nodes.transport.server_open',                                           PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 58
            [ 'nodes.transport.rx_count',                                              PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 59
            [ 'nodes.transport.rx_size_in_bytes',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 60
            [ 'nodes.transport.tx_count',                                              PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 61
            [ 'nodes.transport.tx_size_in_bytes',                                      PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(1,0,0,PM_SPACE_BYTE,0,0),  ''], # 62
            [ 'nodes.http.current_open',                                               PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0),  ''], # 63
            [ 'nodes.http.total_opened',                                               PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE),  ''], # 64
        ]

        for item in range(len(self.nodes_metrics)):
            self.add_metric(name + '.' +
                            self.nodes_metrics[item][0],
                            pmdaMetric(self.pmid(self.nodes_cluster, item),
                                       self.nodes_metrics[item][1],
                                       self.nodes_indom,
                                       self.nodes_metrics[item][2],
                                       self.nodes_metrics[item][3]),
                            self.nodes_metrics[item][4],
                            self.nodes_metrics[item][4])
        self.node_info_indom = self.indom(1)
        self.node_info_insts = pmdaIndom(self.node_info_indom, {})
        self.add_indom(self.node_info_insts)
        self.node_info_cluster = 2
        self.node_info_metrics = [
            # Name - type - semantics - units - help
            [ 'nodes.jvm.pid',                        PM_TYPE_U32,    PM_SEM_DISCRETE, pmUnits(0,0,0,0,0,0),             ''], # 0
            [ 'nodes.jvm.version',                    PM_TYPE_STRING, PM_SEM_INSTANT,  pmUnits(0,0,0,0,0,0),             ''], # 1
            [ 'nodes.jvm.vm_name',                    PM_TYPE_STRING, PM_SEM_INSTANT,  pmUnits(0,0,0,0,0,0),             ''], # 2
            [ 'nodes.jvm.vm_version',                 PM_TYPE_STRING, PM_SEM_INSTANT,  pmUnits(0,0,0,0,0,0),             ''], # 3
            [ 'nodes.jvm.mem.heap_init_in_bytes',     PM_TYPE_U64,    PM_SEM_INSTANT,  pmUnits(0,0,0,0,0,0),             ''], # 4
            [ 'nodes.jvm.mem.heap_max_in_bytes',      PM_TYPE_U64,    PM_SEM_INSTANT,  pmUnits(1,0,0,PM_SPACE_BYTE,0,0), ''], # 5
            [ 'nodes.jvm.mem.non_heap_init_in_bytes', PM_TYPE_U64,    PM_SEM_INSTANT,  pmUnits(1,0,0,PM_SPACE_BYTE,0,0), ''], # 6
            [ 'nodes.jvm.mem.non_heap_max_in_bytes',  PM_TYPE_U64,    PM_SEM_INSTANT,  pmUnits(1,0,0,PM_SPACE_BYTE,0,0), ''], # 7
            [ 'nodes.process.max_file_descriptors',   PM_TYPE_U64,    PM_SEM_DISCRETE, pmUnits(0,0,0,0,0,0),             ''], # 8
        ]
        for item in range(len(self.node_info_metrics)):
            self.add_metric(name + '.' +
                            self.node_info_metrics[item][0],
                            pmdaMetric(self.pmid(self.node_info_cluster, item),
                                       self.node_info_metrics[item][1],
                                       self.node_info_indom,
                                       self.node_info_metrics[item][2],
                                       self.node_info_metrics[item][3]),
                            self.node_info_metrics[item][4],
                            self.node_info_metrics[item][4])

        self.version_indom = PM_INDOM_NULL
        self.version_cluster = 3
        self.version_metrics = [
            # Name - type - semantics - units - help
            [ 'version.number', PM_TYPE_STRING, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Version number of elasticsearch'],
        ]
        for item in range(len(self.version_metrics)):
            self.add_metric(name + '.' +
                            self.version_metrics[item][0],
                            pmdaMetric(self.pmid(self.version_cluster, item),
                                       self.version_metrics[item][1],
                                       self.version_indom,
                                       self.version_metrics[item][2],
                                       self.version_metrics[item][3]),
                            self.version_metrics[item][4],
                            self.version_metrics[item][4])

        self.search_indom = PM_INDOM_NULL
        self.search_cluster = 4
        self.search_metrics = [
            [ 'search.shards.total', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Number of shards in the elasticsearch cluster'],
            [ 'search.shards.successful', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Number of successful shards in the elasticsearch cluster'],
            [ 'search.shards.failed', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Number of failed shards in the elasticsearch cluster'],
            [ 'search.all.primaries.search.query_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search queries to all elasticsearch primaries'],
            [ 'search.all.primaries.search.query_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search queries to all elasticsearch primaries'],
            [ 'search.all.primaries.search.fetch_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search fetches to all elasticsearch primaries'],
            [ 'search.all.total.search.query_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search queries to all elasticsearch primaries'],
            [ 'search.all.total.search.query_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search queries to all elasticsearch primaries'],
            [ 'search.all.total.search.fetch_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search fetches to all elasticsearch primaries'],
            [ 'search.all.total.fetch_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search fetches to all elasticsearch primaries'],
        ]

        for item in range(len(self.search_metrics)):
            self.add_metric(name + '.' +
                            self.search_metrics[item][0],
                            pmdaMetric(self.pmid(self.search_cluster, item),
                                       self.search_metrics[item][1],
                                       self.search_indom,
                                       self.search_metrics[item][2],
                                       self.search_metrics[item][3]),
                            self.search_metrics[item][4],
                            self.search_metrics[item][4])

        self.perindex_indom = self.indom(2)
        self.perindex_insts = pmdaIndom(self.perindex_indom, {})
        self.add_indom(self.perindex_insts)
        self.perindex_cluster = 5
        self.perindex_metrics = [
            [ 'search.perindex.primaries.search.query_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search fetches to all elasticsearch primaries'],
            [ 'search.perindex.primaries.search.query_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search queries to all elasticsearch primaries'],
            [ 'search.perindex.primaries.search.fetch_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search fetches to all elasticsearch primaries'],
            [ 'search.perindex.primaries.search.fetch_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search fetches to all elasticsearch primaries'],
            [ 'search.perindex.total.search.query_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search queries to all elasticsearch primaries'],
            [ 'search.perindex.total.search.query_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search queries to all elasticsearch primaries'],
            [ 'search.perindex.total.search.fetch_total', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,0,1,0,0,PM_COUNT_ONE), 'Number of search fetches to all elasticsearch primaries'],
            [ 'search.perindex.total.search.fetch_time_in_millis', PM_TYPE_U64, PM_SEM_COUNTER, pmUnits(0,1,0,0,PM_TIME_MSEC,0), 'Time spent in search fetches to all elasticsearch primaries'],
        ]
        for item in range(len(self.perindex_metrics)):
            self.add_metric(name + '.' +
                            self.perindex_metrics[item][0],
                            pmdaMetric(self.pmid(self.perindex_cluster, item),
                                       self.perindex_metrics[item][1],
                                       self.perindex_indom,
                                       self.perindex_metrics[item][2],
                                       self.perindex_metrics[item][3]),
                            self.perindex_metrics[item][4],
                            self.perindex_metrics[item][4])

        self.master_node_indom = PM_INDOM_NULL
        self.master_node_cluster = 6
        self.master_node_metrics = [
            [ 'cluster.master_node', PM_TYPE_STRING, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Internal identifier of the master node of the cluster'],
        ]
        for item in range(len(self.master_node_metrics)):
            self.add_metric(name + '.' +
                            self.master_node_metrics[item][0],
                            pmdaMetric(self.pmid(self.master_node_cluster, item),
                                       self.master_node_metrics[item][1],
                                       self.master_node_indom,
                                       self.master_node_metrics[item][2],
                                       self.master_node_metrics[item][3]),
                            self.master_node_metrics[item][4],
                            self.master_node_metrics[item][4])

        self.index_indom = self.indom(3)
        self.index_insts = pmdaIndom(self.index_indom, {})
        self.add_indom(self.index_insts)
        self.index_cluster = 7
        self.index_metrics = [
            [ 'index.settings.gateway_snapshot_interval', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Interval between gateway snapshots'],
            [ 'index.settings.number_of_replicas', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Number of replicas of shards index setting'],
            [ 'index.settings.number_of_shards', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'Number of shards index setting'],
            [ 'index.settings.version_created', PM_TYPE_U64, PM_SEM_INSTANT, pmUnits(0,0,0,0,0,0), 'The version of elasticsearch the index was created with'],
        ]
        for item in range(len(self.index_metrics)):
            self.add_metric(name + '.' +
                            self.index_metrics[item][0],
                            pmdaMetric(self.pmid(self.index_cluster, item),
                                       self.index_metrics[item][1],
                                       self.index_indom,
                                       self.index_metrics[item][2],
                                       self.index_metrics[item][3]),
                            self.index_metrics[item][4],
                            self.index_metrics[item][4])
        self.set_refresh(self.elasticsearch_refresh)
        self.set_fetch_callback(self.elasticsearch_fetch_callback)

    def read_config(self):
        """ Read Configuration file """

        configfile = PCP.pmGetConfig('PCP_PMDAS_DIR')
        # Retain es.conf name from original version of the PMDA
        configfile += '/' + self.read_name() + '/es.conf'
        # Python < 3.2 compat
        if sys.version_info[0] >= 3 and sys.version_info[1] >= 2:
            config = ConfigParser.ConfigParser()
        else:
            config = ConfigParser.SafeConfigParser()
        config.read(configfile)
        if config.has_section('pmda'):
            for opt in config.options('pmda'):
                if opt == 'user':
                    self.user = config.get('pmda', opt)
                elif opt == 'baseurl':
                    self.baseurl = config.get('pmda', opt)
                elif opt == 'auth':
                    self.auth = config.get('pmda', opt)
                elif opt == 'password':
                    self.password = config.get('pmda', opt)
                else:
                    self.err("Invalid directrive '%s' in %s." % (opt, configfile))
                    sys.exit(1)

    def setup_urllib(self, url, auth, pasw):
        """ Setup urllib """
        try:
            import urllib.request as httprequest
        except Exception:
            import urllib2 as httprequest
        passman = httprequest.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, auth, pasw)
        authhandler = httprequest.HTTPBasicAuthHandler(passman)
        opener = httprequest.build_opener(authhandler)
        httprequest.install_opener(opener)
        return httprequest

    def get_url(self, url):
        """ Perform HTTP GET """
        self.log(str("url: " + str(url)))
        try:
            req = self.request.urlopen(url)
        except Exception as error:
            self.log("Failed to connect to %s - %s" % (url, error))
            if self.cluster:
                self.cluster = {}
            if self.nodes:
                self.nodes = {}
            if self.node_info:
                self.node_info = {}
            if self.info:
                self.info = {}
            if self.stat:
                self.stat = {}
            if self.search:
                self.search = {}
            if self.perindex:
                self.perindex = {}
            if self.master_node:
                self.master_node = ()
            if self.index:
                self.index = {}
            return None
        return req

    def elasticsearch_refresh(self, cluster):
        """ Refresh """
        if cluster == self.cluster_cluster:
            request = self.get_url(self.baseurl + "_cluster/health")
            self.cluster = json.loads(request.read())

        if cluster == self.nodes_cluster:
            temp = {}
            insts = {}
            request = self.get_url(self.baseurl + "_nodes/stats")
            temp = json.loads(request.read())
            request.close()
            self.nodes = temp['nodes']
            for nodes in temp['nodes']:
                insts[nodes] = c_int(1)
            self.nodes_insts.set_instances(self.nodes_indom, insts)
            self.replace_indom(self.nodes_indom, insts)

        if cluster == self.node_info_cluster:
            temp = {}
            insts = {}
            request = self.get_url(self.baseurl + "_nodes")
            temp = json.loads(request.read())
            request.close()
            self.node_info = temp['nodes']
            for nodes in temp['nodes']:
                insts[nodes] = c_int(1)
            self.node_info_insts.set_instances(self.node_info_indom, insts)
            self.replace_indom(self.node_info_indom, insts)

        if cluster == self.version_cluster:
            request = self.get_url(self.baseurl)
            self.info = json.loads(request.read())
            request.close()

        if cluster in (self.search_cluster, self.perindex_cluster):
            temp = {}
            insts = {}
            request = self.get_url(self.baseurl + "_stats/search")
            temp = json.loads(request.read())
            request.close()
            if cluster == self.search_cluster:
                self.search = temp
            else:
                self.perindex = temp['indices']
                for index in temp['indices']:
                    insts[index] = c_int(1)
                self.perindex_insts.set_instances(self.perindex_indom, insts)
                self.replace_indom(self.perindex_indom, insts)

        if cluster in (self.master_node_cluster, cluster == self.index_cluster):
            temp = {}
            insts = {}
            request = self.get_url(self.baseurl + "_cluster/state")
            temp = json.loads(request.read())
            request.close()
            if cluster == self.master_node_cluster:
                self.master_node = temp
            else:
                self.index = temp['metadata']['indices']
                for index in temp['metadata']['indices']:
                    insts[index] = c_int(1)
                self.index_insts.set_instances(self.index_indom, insts)
                self.replace_indom(self.index_indom, insts)

    def elasticsearch_fetch_callback(self, cluster, item, inst):
        """ Fetch Callback """
        if cluster == self.cluster_cluster:
            if not self.cluster:
                return [PM_ERR_AGAIN, 0]
            try:
                if item == 0:
                    return [str(self.cluster['cluster_name']), 1]
                elif item == 1:
                    return [str(self.cluster['status']), 1]
                elif item == 2:
                    return [self.cluster['timed_out'], 1]
                elif item == 3:
                    return [self.cluster['number_of_nodes'], 1]
                elif item == 4:
                    return [self.cluster['number_of_data_nodes'], 1]
                elif item == 5:
                    return [self.cluster['active_primary_shards'], 1]
                elif item == 6:
                    return [self.cluster['active_shards'], 1]
                elif item == 7:
                    return [self.cluster['relocating_shards'], 1]
                elif item == 8:
                    return [self.cluster['initializing_shards'], 1]
                elif item == 9:
                    return [self.cluster['unassigned_shards'], 1]
                elif item == 10:
                    if self.cluster['status'] == 'green':
                        return [0, 1]
                    elif self.cluster['status'] == 'yellow':
                        return [1, 1]
                    elif self.cluster['status'] == 'red':
                        return [2, 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.nodes_cluster:
            if not self.nodes:
                return [PM_ERR_AGAIN, 0]
            try:
                node = self.nodes_insts.inst_name_lookup(inst)
                if item == 0:
                    return [self.nodes[node]['indices']['completion']['size_in_bytes'], 1]
                elif item == 1:
                    return [self.nodes[node]['indices']['docs']['count'], 1]
                elif item == 2:
                    return [self.nodes[node]['indices']['docs']['num_docs'], 1]
                elif item == 3:
                    return [self.nodes[node]['indices']['cache']['field_evictions'], 1]
                elif item == 4:
                    return [self.nodes[node]['indices']['cache']['field_size_in_bytes'], 1]
                elif item == 5:
                    return [self.nodes[node]['indices']['cache']['filter_count'], 1]
                elif item == 6:
                    return [self.nodes[node]['indices']['cache']['filter_evictions'], 1]
                elif item == 7:
                    return [self.nodes[node]['indices']['cache']['filter_size_in_bytes'], 1]
                elif item == 8:
                    return [self.nodes[node]['indices']['merges']['current'], 1]
                elif item == 9:
                    return [self.nodes[node]['indices']['merges']['total'], 1]
                elif item == 10:
                    return [self.nodes[node]['indices']['merges']['total_time_in_millis'], 1]
                elif item == 11:
                    return [self.nodes[node]['jvm']['uptime_in_millis'], 1]
                elif item == 12:
                    return [self.nodes[node]['jvm']['uptime'], 1]
                elif item == 13:
                    return [self.nodes[node]['jvm']['mem']['heap_used_in_bytes'], 1]
                elif item == 14:
                    return [self.nodes[node]['jvm']['mem']['heap_committed_in_bytes'], 1]
                elif item == 15:
                    return [self.nodes[node]['jvm']['mem']['non_heap_used_in_bytes'], 1]
                elif item == 16:
                    return [self.nodes[node]['jvm']['mem']['non_heap_committed_in_bytes'], 1]
                elif item == 17:
                    return [self.nodes[node]['jvm']['threads']['count'], 1]
                elif item == 18:
                    return [self.nodes[node]['jvm']['threads']['peak_count'], 1]
                elif item == 19:
                    return [self.nodes[node]['jvm']['gc']['collection_count'], 1]
                elif item == 20:
                    return [self.nodes[node]['jvm']['gc']['collection_time_in_millis'], 1]
                elif item == 21:
                    return [self.nodes[node]['jvm']['gc']['collectors']['Copy']['collection_count'], 1]
                elif item == 22:
                    return [self.nodes[node]['jvm']['gc']['collectors']['Copy']['collection_time_in_millis'], 1]
                elif item == 23:
                    return [self.nodes[node]['jvm']['gc']['collectors']['ParNew']['collection_count'], 1]
                elif item == 24:
                    return [self.nodes[node]['jvm']['gc']['collectors']['ParNew']['collection_time_in_millis'], 1]
                elif item == 25:
                    return [self.nodes[node]['jvm']['gc']['collectors']['ConcurrentMarkSweep']['collection_count'], 1]
                elif item == 26:
                    return [self.nodes[node]['jvm']['gc']['collectors']['ConcurrentMarkSweep']['collection_time_in_millis'], 1]
                elif item == 27:
                    return [self.nodes[node]['indices']['docs']['deleted'], 1]
                elif item == 28:
                    return [self.nodes[node]['indices']['indexing']['index_total'], 1]
                elif item == 29:
                    return [self.nodes[node]['indices']['indexing']['index_time_in_millis'], 1]
                elif item == 30:
                    return [self.nodes[node]['indices']['indexing']['delete_total'], 1]
                elif item == 31:
                    return [self.nodes[node]['indices']['indexing']['delete_time_in_millis'], 1]
                elif item == 32:
                    return [self.nodes[node]['indices']['merges']['current_docs'], 1]
                elif item == 33:
                    return [self.nodes[node]['indices']['merges']['current_size_in_bytes'], 1]
                elif item == 34:
                    return [self.nodes[node]['indices']['merges']['total_docs'], 1]
                elif item == 35:
                    return [self.nodes[node]['indices']['merges']['total_size_in_bytes'], 1]
                elif item == 36:
                    return [self.nodes[node]['indices']['refresh']['total'], 1]
                elif item == 37:
                    return [self.nodes[node]['indices']['refresh']['total_time_in_millis'], 1]
                elif item == 38:
                    return [self.nodes[node]['indices']['flush']['total'], 1]
                elif item == 39:
                    return [self.nodes[node]['indices']['flush']['total_time_in_millis'], 1]
                elif item == 40:
                    return [self.nodes[node]['process']['timestamp'], 1]
                elif item == 41:
                    return [self.nodes[node]['process']['open_file_descriptors'], 1]
                elif item == 42:
                    return [self.nodes[node]['process']['cpu']['percent'], 1]
                elif item == 43:
                    return [self.nodes[node]['process']['cpu']['sys_in_millis'], 1]
                elif item == 44:
                    return [self.nodes[node]['process']['cpu']['user_in_millis'], 1]
                elif item == 45:
                    return [self.nodes[node]['process']['mem']['resident_in_bytes'], 1]
                elif item == 46:
                    return [self.nodes[node]['process']['mem']['total_virtual_in_bytes'], 1]
                elif item == 47:
                    return [self.nodes[node]['indices']['store']['size_in_bytes'], 1]
                elif item == 48:
                    return [self.nodes[node]['indices']['get']['total'], 1]
                elif item == 49:
                    return [self.nodes[node]['indices']['get']['time_in_millis'], 1]
                elif item == 50:
                    return [self.nodes[node]['indices']['get']['exists_total'], 1]
                elif item == 51:
                    return [self.nodes[node]['indices']['get']['exists_time_in_millis'], 1]
                elif item == 52:
                    return [self.nodes[node]['indices']['get']['missing_total'], 1]
                elif item == 53:
                    return [self.nodes[node]['indices']['get']['missing_time_in_millis'], 1]
                elif item == 54:
                    return [self.nodes[node]['indices']['search']['query_total'], 1]
                elif item == 55:
                    return [self.nodes[node]['indices']['search']['query_time_in_millis'], 1]
                elif item == 56:
                    return [self.nodes[node]['indices']['search']['fetch_total'], 1]
                elif item == 57:
                    return [self.nodes[node]['indices']['search']['fetch_time_in_millis'], 1]
                elif item == 58:
                    return [self.nodes[node]['transport']['server_open'], 1]
                elif item == 59:
                    return [self.nodes[node]['transport']['rx_count'], 1]
                elif item == 60:
                    return [self.nodes[node]['transport']['rx_size_in_bytes'], 1]
                elif item == 61:
                    return [self.nodes[node]['transport']['tx_count'], 1]
                elif item == 62:
                    return [self.nodes[node]['transport']['tx_size_in_bytes'], 1]
                elif item == 63:
                    return [self.nodes[node]['http']['current_open'], 1]
                elif item == 64:
                    return [self.nodes[node]['http']['total_opened'], 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.node_info_cluster:
            if not self.node_info:
                return [PM_ERR_AGAIN, 0]
            try:
                node = self.node_info_insts.inst_name_lookup(inst)
                if item == 0:
                    return [self.node_info[node]['jvm']['pid'], 1]
                elif item == 1:
                    return [str(self.node_info[node]['jvm']['version']), 1]
                elif item == 2:
                    return [str(self.node_info[node]['jvm']['vm_name']), 1]
                elif item == 3:
                    return [str(self.node_info[node]['jvm']['vm_version']), 1]
                elif item == 4:
                    return [self.node_info[node]['jvm']['mem']['heap_init_in_bytes'], 1]
                elif item == 5:
                    return [self.node_info[node]['jvm']['mem']['heap_max_in_bytes'], 1]
                elif item == 6:
                    return [self.node_info[node]['jvm']['mem']['non_heap_init_in_bytes'], 1]
                elif item == 7:
                    return [self.node_info[node]['jvm']['mem']['non_heap_max_in_bytes'], 1]
                elif item == 8:
                    return [self.node_info[node]['process']['max_file_descriptors'], 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.version_cluster:
            if not self.info:
                return [PM_ERR_AGAIN, 0]
            try:
                return [str(self.info['version']['number']), 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.search_cluster:
            if not self.search:
                return [PM_ERR_AGAIN, 0]
            try:
                if item == 0:
                    return [self.search['_shards']['total'], 1]
                elif item == 1:
                    return [self.search['_shards']['successful'], 1]
                elif item == 2:
                    return [self.search['_shards']['failed'], 1]
                elif item == 3:
                    return [self.search['_all']['primaries']['search']['query_total'], 1]
                elif item == 4:
                    return [self.search['_all']['primaries']['search']['query_time_in_millis'], 1]
                elif item == 5:
                    return [self.search['_all']['primaries']['search']['fetch_total'], 1]
                elif item == 6:
                    return [self.search['_all']['total']['search']['query_total'], 1]
                elif item == 7:
                    return [self.search['_all']['total']['search']['query_time_in_millis'], 1]
                elif item == 8:
                    return [self.search['_all']['total']['search']['fetch_total'], 1]
                elif item == 9:
                    return [self.search['_all']['total']['search']['fetch_time_in_millis'], 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.perindex_cluster:
            if not self.search:
                return [PM_ERR_AGAIN, 0]
            try:
                index = self.perindex_insts.inst_name_lookup(inst)
                if item == 0:
                    return [self.perindex[index]['primaries']['search']['query_total'], 1]
                elif item == 1:
                    return [self.perindex[index]['primaries']['search']['query_time_in_millis'], 1]
                elif item == 2:
                    return [self.perindex[index]['primaries']['search']['fetch_total'], 1]
                elif item == 3:
                    return [self.perindex[index]['primaries']['search']['fetch_time_in_millis'], 1]
                elif item == 4:
                    return [self.perindex[index]['total']['search']['query_total'], 1]
                elif item == 5:
                    return [self.perindex[index]['total']['search']['query_time_in_millis'], 1]
                elif item == 6:
                    return [self.perindex[index]['total']['search']['fetch_total'], 1]
                elif item == 7:
                    return [self.perindex[index]['total']['search']['fetch_time_in_millis'], 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.master_node_cluster:
            if not self.master_node:
                return [PM_ERR_AGAIN, 0]
            try:
                if item == 0:
                    return [str(self.master_node['master_node']), 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        if cluster == self.index_cluster:
            if not self.index:
                return [PM_ERR_AGAIN, 0]
            try:
                index = self.index_insts.inst_name_lookup(inst)
                if item == 0:
                    return [int(self.index[index]['settings']['index']['gateway_snapshot_interval']), 1]
                elif item == 1:
                    return [int(self.index[index]['settings']['index']['number_of_replicas']), 1]
                elif item == 2:
                    return [int(self.index[index]['settings']['index']['number_of_shards']), 1]
                elif item == 3:
                    return [int(self.index[index]['settings']['index']['version_created']), 1]
            except Exception:
                return [PM_ERR_APPVERSION, 0]

        return [PM_ERR_PMID, 0]


if __name__ == '__main__':
    elasticsearchPMDA('elasticsearch', 108).run()
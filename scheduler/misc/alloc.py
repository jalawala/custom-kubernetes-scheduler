#!/usr/bin/env python

import time
import random
import json
from pprint import pprint

import kubernetes as k8s

from pint        import UnitRegistry
from collections import defaultdict

__all__ = ["compute_allocated_resources"]

def compute_allocated_resources():
    ureg = UnitRegistry()
    ureg.load_definitions('kubernetes_units.txt')

    Q_   = ureg.Quantity
    data = {}

    # doing this computation within a k8s cluster
    #k8s.config.load_incluster_config()
    k8s.config.load_kube_config()
    
    core_v1 = k8s.client.CoreV1Api()

    for node in core_v1.list_node().items:
        pprint(node)
        stats          = {}
        node_name      = node.metadata.name
        allocatable    = node.status.allocatable
        max_pods       = int(int(allocatable["pods"]) * 1.5)
        field_selector = ("status.phase!=Succeeded,status.phase!=Failed," +
                          "spec.nodeName=" + node_name)

        stats["cpu_alloc"] = Q_(allocatable["cpu"])
        stats["mem_alloc"] = Q_(allocatable["memory"])

        pods = core_v1.list_pod_for_all_namespaces(limit=max_pods,
                                                   field_selector=field_selector).items

        # compute the allocated resources
        cpureqs,cpulmts,memreqs,memlmts = [], [], [], []
        for pod in pods:
            for container in pod.spec.containers:
                res  = container.resources
                reqs = defaultdict(lambda: 0, res.requests or {})
                lmts = defaultdict(lambda: 0, res.limits or {})
                cpureqs.append(Q_(reqs["cpu"]))
                memreqs.append(Q_(reqs["memory"]))
                cpulmts.append(Q_(lmts["cpu"]))
                memlmts.append(Q_(lmts["memory"]))

        stats["cpu_req"]     = sum(cpureqs)
        stats["cpu_lmt"]     = sum(cpulmts)
        stats["cpu_req_per"] = (stats["cpu_req"] / stats["cpu_alloc"] * 100)
        stats["cpu_lmt_per"] = (stats["cpu_lmt"] / stats["cpu_alloc"] * 100)

        stats["mem_req"]     = sum(memreqs)
        stats["mem_lmt"]     = sum(memlmts)
        stats["mem_req_per"] = (stats["mem_req"] / stats["mem_alloc"] * 100)
        stats["mem_lmt_per"] = (stats["mem_lmt"] / stats["mem_alloc"] * 100)

        data[node_name] = stats

    return data


if __name__ == '__main__':
    #ready_nodes = nodes_available()
    #pprint(ready_nodes)
    #name='review-v1-787d8fbfbb-ltdzt'
    node='ip-10-0-3-253.ec2.internal'
    #namespace='ecommerce'
    #ret=scheduler(name, node, namespace)
    #pprint(ret)
    #main()
    #test()
    #testpod()
    #check_node_resources(node)
    data=compute_allocated_resources()
    pprint(data)
    
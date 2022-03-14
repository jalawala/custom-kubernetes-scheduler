#! /usr/bin/python3

'''
Copyright 2018 Sysdig.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

[Copy of README.md]

# Kubernetes scheduler using Sysdig metrics - Python version

This folder contains the much simpler Python version of the Golang scheduler that
you can find in the repository root.

You have a full description on how to use this code here:
[How to write a custom Kubernetes scheduler using your monitoring metrics](https://sysdig.com/blog/kubernetes-scheduler/)
'''

#!/usr/bin/env python

import time
import random
import json
from pprint import pprint
from kubernetes.client.rest import ApiException

from kubernetes import client, config, watch
#from sdcclient import SdcClient

config.load_kube_config()
core_api = client.CoreV1Api()
apis_api = client.AppsV1Api()

#sdclient = SdcClient(<Your Sysdig API token>)
sysdig_metric = "net.http.request.time"
metrics = [{ "id": sysdig_metric, "aggregations": { "time": "timeAvg", "group": "avg" } }]

scheduler_name = "Ec2SpotK8sScheduler"


def get_request_time(hostname):
    hostfilter = "host.hostName = '%s'" % hostname
    start = -60
    end = 0
    sampling = 60
#    metricdata = sdclient.get_data(metrics, start, end, sampling, filter=hostfilter)
    #request_time = float(metricdata[1].get('data')[0].get('d')[0])
    #print hostname + " (" + sysdig_metric + "): " + str(request_time)
    request_time='1'
    return request_time


def select_right_node():
    nodes = nodes_available()
    #print("Avaialble nodes are ={}".format(nodes))
    if not nodes:
        return []
    #node_times = [get_request_time(hostname) for hostname in nodes]
    #best_node = nodes[node_times.index(min(node_times))]
    #print("Best node: {}".format(best_node))
    return nodes[1]


def nodes_available():
    ready_nodes = []
    for n in apis_api.list_node().items:
            #pprint(n)
            for status in n.status.conditions:
                if status.status == "True" and status.type == "Ready":
                    ready_nodes.append(n.metadata.name)
    #pprint(ready_nodes)
    return ready_nodes


def scheduler(name, node, namespace):
    
    target=client.V1ObjectReference(api_version='v1', kind="Node", name=node)
    #target.kind="Node"
    #target.apiVersion="v1"
    #target.name= node
    #pprint(target)
    meta=client.V1ObjectMeta()
    meta.name=name
    #pprint(meta)
    body=client.V1Binding(metadata=meta,  target=target)
    #body.target=target
    #body.metadata=meta
    return apis_api.create_namespaced_binding(namespace, body, _preload_content=False)

def check_node_resources(node):

    read_node = apis_api.read_node(name=node)
    #pprint("read_node={}".format(read_node))
    pprint(read_node)

def main():
    w = watch.Watch()
    scheduledPods = []
    pendingPods = []
    for event in w.stream(apis_api.list_namespaced_pod, "default"):
    #for event in w.stream(apis_api.list_namespaced_pod):        
        #pprint("event={}".format(event))
        
        pod_name =  event['object'].metadata.name
        pod_status =  event['object'].status.phase
        pod_scheduler = event['object'].spec.scheduler_name
        print("name={} status={} scheduler={}".format(pod_name, pod_status, pod_scheduler))
        if pod_status == "Pending" and  pod_scheduler == scheduler_name:
            try:
                node = select_right_node()
                namespace="default"
                if pod_name not in scheduledPods:
                    print("Scheduling Pod={} on to the node={}".format(pod_name, node))
                    res = scheduler(pod_name, node, namespace)
                    #print("res={}",format(res))
                    scheduledPods.append(pod_name)
                    time.sleep(15)
                else:
                    print("Pod ={} is already scheduled earlier but still pending".format(pod_name))
            except client.rest.ApiException as e:
                pprint(json.loads(e.body)['message'])

def test():
    try:
        
        
        V1NamespaceBody = client.V1Namespace()
        pprint("V1NamespaceBody={}".format(V1NamespaceBody))
        
        V1ObjectReferenceBody = client.V1ObjectReference()
        pprint("V1ObjectReferenceBody={}".format(V1ObjectReferenceBody))    
        
        V1ObjectMetaBody = client.V1ObjectMeta()
        pprint("V1ObjectMetaBody={}".format(V1ObjectMetaBody))    
    
    
        #V1BindingBody = client.V1Binding()
        #pprint("V1BindingBody={}".format(V1BindingBody))    
    
    
        V1ConfigMapBody = client.V1ConfigMap()
        pprint("V1ConfigMapBody={}".format(V1ConfigMapBody))    
    
    
        V1Pod = client.V1Pod()
        pprint("V1Pod={}".format(V1Pod))    
    
    
        V1PodTemplate = client.V1PodTemplate()
        pprint("V1PodTemplate={}".format(V1PodTemplate))    
    
    
        V1ReplicationController = client.V1ReplicationController()
        pprint("V1ReplicationController={}".format(V1ReplicationController))    
    
    
        V1Service = client.V1Service()
        pprint("V1Service={}".format(V1Service))    
    
    
        V1Node = client.V1Node()
        pprint("V1Node={}".format(V1Node))   
        
        pod = 'nginx-no-split-655b866cfd-54xmg'
        namespace='default'
        read_pod = apis_api.read_namespaced_pod(name=pod,namespace=namespace)
        pprint("read_pod={}".format(read_pod))   
        
        lifecycle=read_pod.spec.node_selector.lifecycle
        pprint("lifecycle={}".format(lifecycle))   
        read_pod.spec.node_selector.lifecycle='OnDemand'
        pprint("read_pod={}".format(read_pod))  
        #metadata = read_pod.metadata
        #pprint("metadata={}".format(metadata))   
        #metadata.cluster_name = 'Ec2SpotEKS4'
        #pprint("metadata={}".format(metadata))   
        
    except Exception as e:
        print("Exception when calling CoreV1Api->create_namespace: %s\n" % e)    


def testpod():

        
    pod_name = 'nginx-no-split-655b866cfd-54xmg'
    namespace='default'
    read_pod = apis_api.read_namespaced_pod(name=pod_name,namespace=namespace)
    #pprint("read_pod={}".format(read_pod))   
    
    lifecycle=read_pod.spec.node_selector
    
    pprint("lifecycle type={}".format(type(lifecycle)))
    pprint("lifecycle data={}".format(lifecycle))
    pprint("lifecycle={}".format(lifecycle['lifecycle']))
    
    #lifecycle['lifecycle'] = 'OnDemand'
    
    read_pod.spec.node_selector['lifecycle'] = 'OnDemand1'
    #pprint("read_pod={}".format(read_pod))
    
    body = {
        "spec": {
            'node_selector': {'lifecycle': 'OnDemand'}
        }
    }    
    response = apis_api.patch_namespaced_pod(name=pod_name, namespace=namespace, body=body)
    
    #response = apis_api.replace_namespaced_pod(name=pod_name, namespace=namespace, body=read_pod)
    
    pprint("response={}".format(response))
    #read_pod = apis_api.read_namespaced_pod(name=pod_name,namespace=namespace)
    #pprint("read_pod={}".format(read_pod))
    
    V1Node = client.V1Node()
    pprint("V1Node={}".format(V1Node))      
    #metadata = read_pod.metadata
    #pprint("metadata={}".format(metadata))   
    #metadata.cluster_name = 'Ec2SpotEKS4'
    #pprint("metadata={}".format(metadata))   
        
 
def pod_owner():
    # the pod owner

    pod = core_api.read_namespaced_pod(name=name, namespace=namespace)
    owner_references = pod.metadata.owner_references
    if isinstance(owner_references, list):
        owner_name = owner_references[0].name
        owner_kind = owner_references[0].kind
        # owner  StatefulSet
        if owner_kind == 'ReplicaSet':
            replica_set = apis_api.read_namespaced_replica_set(name=owner_name, namespace=namespace)
            owner_references2 = replica_set.metadata.owner_references
            if isinstance(owner_references2, list):
                print(owner_references2[0].name)
            else:
                print(owner_name)
        # owner Deployment
        else:
            print(owner_name)
    print(name)    

def check_node_deployments():
    namespace='default'
    apis_api = client.AppsV1Api()
    # get deployment by namespace
    resp = apis_api.list_namespaced_deployment(namespace=namespace)
    for i in resp.items:
        print(i)    

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
    check_node_deployments()
    

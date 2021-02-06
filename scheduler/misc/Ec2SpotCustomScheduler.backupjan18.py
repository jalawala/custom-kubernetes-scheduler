#! /usr/bin/python3

import time
import random
import json
import os
from pprint import pprint
from kubernetes.client.rest import ApiException
from pint        import UnitRegistry
from collections import defaultdict
from kubernetes import client, config, watch
from timeloop import Timeloop
from datetime import timedelta



config.load_kube_config()
#config.load_incluster_config()
    # doing this computation within a k8s cluster
    #k8s.config.load_incluster_config()
core_api = client.CoreV1Api()
apis_api = client.AppsV1Api()
#sdclient = SdcClient(<Your Sysdig API token>)
sysdig_metric = "net.http.request.time"
metrics = [{ "id": sysdig_metric, "aggregations": { "time": "timeAvg", "group": "avg" } }]

scheduler_name = "Ec2SpotK8sScheduler"
ureg = UnitRegistry()
ureg.load_definitions('kubernetes_units.txt')

pendingPodsList = []
failedPodsList = []

Q_   = ureg.Quantity



def scheduler(name, node, namespace):
    
    target=client.V1ObjectReference(api_version='v1', kind="Node", name=node)
    meta=client.V1ObjectMeta()
    meta.name=name
    body=client.V1Binding(metadata=meta,  target=target)
    return core_api.create_namespaced_binding(namespace, body, _preload_content=False)

#tl = Timeloop()

#@tl.job(interval=timedelta(seconds=10))  
def RunEc2SpotCustomScheduler():
    
    global pendingPodsList
    global failedPodsList
    
    Ec2SpotK8SCustomSchedulingData = get_custom_deployments()
    
    pprint("Ec2SpotK8SCustomSchedulingData={}".format(Ec2SpotK8SCustomSchedulingData))
    
    namespace = 'default'
    lifecycleList = ['OnDemand', 'Ec2Spot']
    for deploymentData in Ec2SpotK8SCustomSchedulingData:

        podsList = getPodsListForDeployment(deploymentData['Name'])        
        runningPodsList = podsList['runningPodsList']
        pendingPodsList = podsList['pendingPodsList']
        failedPodsList  = podsList['failedPodsList']       
        NumOfPodsPending  = len (pendingPodsList)
        NumOfPodsFailed   = len (failedPodsList)        
        
        for lifecycle in lifecycleList:

            print("Scheduling pods for lifecycle={}".format(lifecycle))
            if lifecycle == 'OnDemand':
                NumOfPodsToBeRunning = deploymentData['NumOfOnDemandPodsToBeRunning']
            else:
                NumOfPodsToBeRunning = deploymentData['NumOfSpotPodsToBeRunning']
                
            #pprint(podsList)

            #lifecycle = 'OnDemand'
            NodesList = get_node_available_nodes_list(lifecycle)
            #pprint(NodesList)
            
            NumOfPodsRunningAlready = 0
            LifecyclePodsRunningList =  []
            
            for podRunning in runningPodsList:
                if podRunning['node_name'] in NodesList.keys():
                    LifecyclePodsRunningList.append(podRunning)
    
            NumOfLifecyclePodsRunningAlready = len (LifecyclePodsRunningList)

            print("lifecycle={} NumOfLifecyclePodsRunningAlready={}".format(lifecycle, NumOfLifecyclePodsRunningAlready))
            for p in  LifecyclePodsRunningList:
                pprint("running pod_name={} node_name={}".format(p['name'], p['node_name']))
            print("lifecycle={} NumOfPodsPending={}".format(lifecycle, NumOfPodsPending))
            for p in  pendingPodsList:
                pprint("pending pod_name={}".format(p['name']))
            
            print("lifecycle={} NumOfNodes={}".format(lifecycle, len(NodesList)))
            for n in  NodesList.keys():
                pprint("node_name={}".format(n))  
                
            
            if NumOfLifecyclePodsRunningAlready == NumOfPodsToBeRunning:
                print("NumOfLifecyclePodsRunningAlready == NumOfPodsToBeRunning = {}. So no need to Schedule".format(NumOfLifecyclePodsRunningAlready))
            elif NumOfLifecyclePodsRunningAlready < NumOfPodsToBeRunning:
                NumOfPodsToBeScheduled = NumOfPodsToBeRunning - NumOfLifecyclePodsRunningAlready
                try:
                    schedulePods(NumOfPodsToBeScheduled, NodesList)
                except Exception as e:
                    pprint(e)
            elif NumOfLifecyclePodsRunningAlready > NumOfPodsToBeRunning:
                NumOfPodsToDeleted = NumOfLifecyclePodsRunningAlready - NumOfPodsToBeRunning
                try:
                    deletePods(NumOfPodsToDeleted, LifecyclePodsRunningList)
                except Exception as e:
                    pprint(e)
    
        pendingPodsList = []                
        NumOfPodsFailed = []
        #pprint(podsList)
        #lifecycle = 'OnDemand'
        #lifecycle = 'Ec2Spot'
        #get_node_available_nodes_list(lifecycle)
        
def deletePods(NumOfPodsToDeleted, LifecyclePodsRunningList):
    
    namespace = 'default'    
    for i in range(0, NumOfPodsToDeleted):
        pod = LifecyclePodsRunningList[i]
        grace_period_seconds = 30
        body = client.V1DeleteOptions()
        #body = {}  
        pprint("deletePods i={} pod={} NumOfPodsToDeleted={}".format(i, pod['name'], NumOfPodsToDeleted ))    
        response = core_api.delete_namespaced_pod(name=pod['name'], namespace=namespace, grace_period_seconds=grace_period_seconds, body=body)
        pprint(response)        
        
def schedulePods(NumOfPodsToBeScheduled, NodesList):
    
    global pendingPodsList
    global failedPodsList
    
    namespace = 'default'
    
    if NumOfPodsToBeScheduled > len(pendingPodsList):
        pprint("schedulePods NumOfPodsToBeScheduled={} is greater than number of pending pods={}. So skipping schedulePods".format(NumOfPodsToBeScheduled, len(pendingPodsList)))
        return        
        
    for i in range(NumOfPodsToBeScheduled):
        pod = pendingPodsList[0]
        print("schedulePods Trying to schedule i={} NumOfPodsToBeScheduled={} pod={} with cpu_req={} mem_req={}".format(i, NumOfPodsToBeScheduled, pod['name'], pod['cpu_req'], pod['mem_req']))
                    
        for node, stats in NodesList.items():
                        
            print("schedulePods Checking for free resources on node={} with cpu_free={} mem_free={}".format(node, stats['cpu_free'], stats['mem_free']))
                        #pprint(node)
            if pod['cpu_req'] <= stats['cpu_free'] and pod['mem_req'] <= stats['mem_free']:
                print("schedulePods scheduling pod={} onto the node={}".format(pod['name'], node))
                res = scheduler(pod['name'], node, namespace)
                pprint(res)
                stats['cpu_free'] = stats['cpu_free'] - pod['cpu_req']
                stats['mem_free'] = stats['mem_free'] - pod['mem_req']
                pendingPodsList.remove(pod)
                break
                                
        
def getPodsListForDeployment(deploymentName):
    
    global pendingPodsList
    
    runningPodsList =[]
    
    failedPodsList =[]
    podsList = {}
    
    namespace='default'
    name='Ec2SpotK8sScheduler'
    field_selector = ("spec.scheduler_name=" + name)    
    #pods = core_api.list_namespaced_pod(namespace=namespace, field_selector=field_selector).to_dict()
    pods = core_api.list_namespaced_pod(namespace=namespace).to_dict()
    for pod in pods['items']:
        #pprint(pod)
        #print("node_name={}".format(pod['spec']['node_name']))
        #return ""
        stats          = {}
        cpureqs,cpulmts,memreqs,memlmts = [], [], [], []
        if deploymentName in pod['metadata']['name'] and pod['spec']['scheduler_name'] == 'Ec2SpotK8sScheduler':
            for container in pod['spec']['containers']:
                res  = container['resources']
                reqs = defaultdict(lambda: 0, res['requests'] or {})
                lmts = defaultdict(lambda: 0, res['limits'] or {})
                cpureqs.append(Q_(reqs["cpu"]))
                memreqs.append(Q_(reqs["memory"]))
                cpulmts.append(Q_(lmts["cpu"]))
                memlmts.append(Q_(lmts["memory"]))            
            
         
            stats["cpu_req"]     = sum(cpureqs)
            stats["cpu_lmt"]     = sum(cpulmts)
            stats["mem_req"]     = sum(memreqs)
            stats["mem_lmt"]     = sum(memlmts)
            stats["name"]        = pod['metadata']['name']
            stats["status"]      = pod['status']['phase']
            if stats["status"] == 'Pending':
                pendingPodsList.append(stats)
            elif stats["status"] == 'Running':
                stats["node_name"]  = pod['spec']['node_name']
                runningPodsList.append(stats)
            elif stats["status"] == 'Failed':
                failedPodsList.append(stats)
            
            podsList['pendingPodsList'] = pendingPodsList
            podsList['runningPodsList'] = runningPodsList
            podsList['failedPodsList'] = failedPodsList
            
        
    #pprint(podsList)
    #pprint("pendingPodsList={} runningPodsList={} failedPodsList={}".format(runningPodsList, runningPodsList, failedPodsList )
    #return pendingPodsList,runningPodsList,failedPodsList
    return podsList
    
    
def get_custom_deployments():
    Ec2SpotK8SCustomSchedulingData  = []
    namespace='default'
    #name = 'nginx'
    name = '1'
    #field_selector = ("metadata.name=" + name)
    field_selector = ("metadata.annotations.OnDemandBase=" + name)    
    # get deployment by namespace
    #resp = apis_api.list_namespaced_deployment(namespace=namespace, field_selector=field_selector)
    resp = apis_api.list_namespaced_deployment(namespace=namespace)    
    for deployment in resp.items:
        #pprint(deployment.metadata.annotations)
        #pprint(deployment)
        deploymentData = {}
        annotations = deployment.metadata.annotations
        if 'Ec2SpotK8SCustomScheduler' in annotations.keys():
            if annotations['Ec2SpotK8SCustomScheduler'] == 'true':
                deploymentData['Name'] = deployment.metadata.name
                deploymentData['OnDemandBase'] = int(annotations['OnDemandBase'])
                deploymentData['OnDemandAbovePercentage'] = int(annotations['OnDemandAbovePercentage'])
                deploymentData['SpotASGName'] = annotations['SpotASGName']
                deploymentData['OnDemandASGName'] = annotations['OnDemandASGName']
                deploymentData['pod_replicas'] = deployment.spec.replicas
                deploymentData['NumOfOnDemandPodsToBeRunning'] = int (deploymentData['OnDemandBase'] + (deploymentData['pod_replicas'] - deploymentData['OnDemandBase']) *  deploymentData['OnDemandAbovePercentage'] / 100)
                deploymentData['NumOfSpotPodsToBeRunning'] = deploymentData['pod_replicas'] - deploymentData['NumOfOnDemandPodsToBeRunning']
                
                Ec2SpotK8SCustomSchedulingData.append(deploymentData)
                
                
                
    return Ec2SpotK8SCustomSchedulingData            
                
                #print("OnDemandBase={}, OnDemandAbovePercentage={} SpotASGName={} OnDemandASGName={} pod_replicas={} NumOfOnDemandPods={} NumOfSpotPods={}".format(OnDemandBase, OnDemandAbovePercentage, SpotASGName, OnDemandASGName, pod_replicas, NumOfOnDemandPods, NumOfSpotPods))
                
                
                
                
__all__ = ["get_node_available_nodes_list"]

def get_node_available_nodes_list(lifecycle):

    #data = []
    data = {}
    
    for node in core_api.list_node().to_dict()['items']:
        #pprint(node)
        
        node_labels    = node['metadata']['labels']
        if 'lifecycle' in node_labels.keys():
            if node_labels['lifecycle'] == lifecycle:
                stats          = {}
                node_name      = node['metadata']['name']
                
                allocatable    = node['status']['allocatable']
                max_pods       = int(int(allocatable["pods"]) * 1.5)
                field_selector = ("status.phase!=Succeeded,status.phase!=Failed," +
                                  "spec.nodeName=" + node_name)
        
                stats["cpu_alloc"] = Q_(allocatable["cpu"])
                stats["mem_alloc"] = Q_(allocatable["memory"])
                stats["lifecycle"] = lifecycle
        
                pods = core_api.list_pod_for_all_namespaces(limit=max_pods,
                                                           field_selector=field_selector).to_dict()['items']
        
                # compute the allocated resources
                cpureqs,cpulmts,memreqs,memlmts = [], [], [], []
                for pod in pods:
                    #pprint(pod)
                    for container in pod['spec']['containers']:
                        res  = container['resources']
                        reqs = defaultdict(lambda: 0, res['requests'] or {})
                        lmts = defaultdict(lambda: 0, res['limits'] or {})
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
                 
                stats["cpu_free"]     =  stats["cpu_alloc"] - stats["cpu_req"]
                stats["mem_free"]     =  stats["mem_alloc"] - stats["mem_req"]
                #stats["name"]         =  node['metadata']['name']
                
                #data.append(stats)
                data[node_name] = stats

    #pprint(data)
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
    #RunEc2SpotCustomScheduler()
    #getPodsListForDeployment(' ')
    #lifecycle = 'OnDemand'
    #lifecycle = 'Ec2Spot'
    #get_node_available_nodes_list(lifecycle)
    #RunEc2SpotCustomScheduler()
    #NumOfPodsToDeleted = 1
    #LifecyclePodsRunningList = []
    #d ={'name':'nginx-66cb875766-vx6bp'}
    #LifecyclePodsRunningList.append(d)
    #deletePods(NumOfPodsToDeleted, LifecyclePodsRunningList)
    #deploymentName='nginx'
    #deploymentName = 'kube-ops-view'
    #getPodsListForDeployment(deploymentName)
    #testlist()
    #tl.start(block=True)
    while True:
        RunEc2SpotCustomScheduler()
        time.sleep(10)
    
    

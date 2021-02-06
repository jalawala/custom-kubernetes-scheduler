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

#scheduler_name = "Ec2SpotK8sScheduler"
CustomSchedulerName ='K8SCustomScheduler'

ureg = UnitRegistry()
ureg.load_definitions('kubernetes_units.txt')

pendingPodsList = []
failedPodsList = []
runningPodsList =[]
nodesListPerNodeLabel = {}
DEBUG_ENABLED = 0

Q_   = ureg.Quantity



def scheduler(name, node, namespace):
    
    target=client.V1ObjectReference(api_version='v1', kind="Node", name=node)
    meta=client.V1ObjectMeta()
    meta.name=name
    body=client.V1Binding(metadata=meta,  target=target)
    return core_api.create_namespaced_binding(namespace, body, _preload_content=False)

#tl = Timeloop()

#@tl.job(interval=timedelta(seconds=10))  
def RunCustomKubeScheduler():
    
    DEBUG_ENABLED = 0
    #global pendingPodsList
    #global failedPodsList
    
    print("Running RunCustomKubeScheduler loop !!!")
    
    CustomKubeSchedulingClusterDeploymentData = get_custom_deployments()

    #print("CustomKubeSchedulingClusterDeploymentData={}".format(CustomKubeSchedulingClusterDeploymentData))
    
    for namespace,  deploymentCustomSchedulingData in CustomKubeSchedulingClusterDeploymentData.items():
        if DEBUG_ENABLED:
            print("namespace={} deploymentCustomSchedulingData={}".format(namespace, deploymentCustomSchedulingData))
        if  deploymentCustomSchedulingData != {}:
            CustomSchedulePerNamespace(namespace, deploymentCustomSchedulingData)
            
        
def CustomSchedulePerNamespace(namespace, deploymentCustomSchedulingData):
    
    global runningPodsList
    global pendingPodsList
    global failedPodsList
    global nodesListPerNodeLabel
    
    
    #print("namespace={} deploymentCustomSchedulingData={}".format(namespace, deploymentCustomSchedulingData))
    #exit(0)
    #namespace = 'default'
    #lifecycleList = ['OnDemand', 'Ec2Spot']
    for deploymentName, CustomSchedulingData in deploymentCustomSchedulingData.items():
        
        print("namespace={} deploymentName={} CustomSchedulingData={}".format(namespace, deploymentName, CustomSchedulingData))
        
        #exit(0)
        
        #podsList = getPodsListForDeployment(namespace, deploymentName)
        runningPodsList = []
        pendingPodsList = []
        failedPodsList =[]
        
        
        getPodsListForDeployment(namespace, deploymentName)  
        
        NumOfPodsRunning  = len (runningPodsList)
        NumOfPodsPending  = len (pendingPodsList)
        NumOfPodsFailed   = len (failedPodsList) 
        
        #print("NumOfPodsRunning={} runningPodsList={}".format(NumOfPodsRunning, runningPodsList))
        #print("NumOfPodsPending={} pendingPodsList={}".format(NumOfPodsPending, pendingPodsList))
        #print("NumOfPodsFailed={} failedPodsList={}".format(NumOfPodsFailed, failedPodsList))

        DEBUG_ENABLED = 1
        
        if DEBUG_ENABLED:
            print("No of currently running pods in namespace {} for deployment {} is {}".format(namespace, deploymentName, NumOfPodsRunning))
            print("No of currently pending pods in namespace {} for deployment {} is {}".format(namespace, deploymentName, NumOfPodsPending))
            print("No of currently failed pods in namespace {} for deployment {} is {}".format(namespace, deploymentName, NumOfPodsFailed))
    
                    
        nodesListPerNodeLabel = {}
        get_node_available_nodes_list(CustomSchedulingData)
        
        DEBUG_ENABLED = 0
        
        if DEBUG_ENABLED:
            for i, pod in  enumerate (runningPodsList):
                print("i={} running pod_name={} node_name={}".format(i+1, pod['name'], pod['node_name']))
    
            for i, pod in  enumerate (pendingPodsList):
                print("i={} pending pod_name={}".format(i+1, pod['name']))
    
            for i, pod in  enumerate (failedPodsList):
                print("i={} failed pod_name={}".format(i+1, pod['name']))

        for nodeLabel, availableNodesData in nodesListPerNodeLabel.items():
            #print("nodeLabel={} availableNodesData={}".format(nodeLabel, availableNodesData))
            i = 1
            for nodeName in availableNodesData.keys():
                print("Available node with Label: {} i={} node={}".format(nodeLabel, i, nodeName))
                i += 1
        
        #runningPodsList = podsList['runningPodsList']
        #pendingPodsList = podsList['pendingPodsList']
        #failedPodsList  = podsList['failedPodsList']       
       
        #exit(0)
        
        for nodeLabel, NumOfPodsToBeRunning in CustomSchedulingData.items():

            #NumOfPodsToBeRunning = numOfReplicas
            print("CustomScheduleStrategy needs {} pods running on Label: {}".format(NumOfPodsToBeRunning, nodeLabel))
            
            #pprint(podsList)

            #lifecycle = 'OnDemand'
            #NodesList = get_node_available_nodes_list(lifecycle)
            #pprint(NodesList)
            
            NumOfPodsRunningAlready = 0
            podsAlreadyRunningOnNodeLabelList =  []
            
            DEBUG_ENABLED = 1
            for pod in runningPodsList:
                if pod['node_name'] in nodesListPerNodeLabel[nodeLabel].keys():
                    NumOfPodsRunningAlready += 1
                    podsAlreadyRunningOnNodeLabelList.append(pod)
                    if DEBUG_ENABLED:
                        print("i={} pod={} already runs on node={} Label: {}".format(NumOfPodsRunningAlready, pod['name'], pod['node_name'], nodeLabel))
    
            if NumOfPodsRunningAlready == NumOfPodsToBeRunning:
                print("Required no of pods i.e. {} already running on Label: {}. So no need to Schedule !!".format(NumOfPodsRunningAlready, nodeLabel))
            elif NumOfPodsRunningAlready < NumOfPodsToBeRunning:
                NumOfPodsToBeScheduled = NumOfPodsToBeRunning - NumOfPodsRunningAlready
                if NumOfPodsPending >= NumOfPodsToBeScheduled:
                    print("Need {} pods on Label: {} and {} are already running. Scheduling remaining {} pods".format(NumOfPodsToBeRunning, nodeLabel, NumOfPodsRunningAlready, NumOfPodsToBeScheduled))
                    try:
                        schedulePods(namespace,  NumOfPodsToBeScheduled, nodeLabel)
                        #exit(0)
                    except Exception as e:
                        print(e)                    
                elif NumOfPodsPending < NumOfPodsToBeScheduled:
                    if NumOfPodsPending > 0:
                        NumOfPodsToBeScheduled = NumOfPodsPending
                        print("Need {} pods on Label: {} and {} are already running. But only {} are pending. So scheduling them for now".format(NumOfPodsToBeRunning, nodeLabel, NumOfPodsRunningAlready, NumOfPodsToBeScheduled))
                    elif NumOfPodsPending == 0:
                        print("Need {} pods on Label: {} and {} are already running. But no pods are pending. So skipping scheduling for now until they are in pending state".format(NumOfPodsToBeRunning, nodeLabel, NumOfPodsRunningAlready))
            elif NumOfPodsRunningAlready > NumOfPodsToBeRunning:
                NumOfPodsToDeleted = NumOfPodsRunningAlready - NumOfPodsToBeRunning
                print("Need {} pods on Label: {} and {} are already running. Deleting additional {} pods".format(NumOfPodsToBeRunning, nodeLabel, NumOfPodsRunningAlready, NumOfPodsToDeleted))
                try:
                    deletePods(namespace, NumOfPodsToDeleted, podsAlreadyRunningOnNodeLabelList)
                except Exception as e:
                    print(e)
    
        #pendingPodsList = []                
        #NumOfPodsFailed = []
        #pprint(podsList)
        #lifecycle = 'OnDemand'
        #lifecycle = 'Ec2Spot'
        #get_node_available_nodes_list(lifecycle)
        
def deletePods(namespace, NumOfPodsToDeleted, podsAlreadyRunningOnNodeLabelList):
    
    #namespace = 'default'    
    for i in range(NumOfPodsToDeleted):
        pod = podsAlreadyRunningOnNodeLabelList[i]
        grace_period_seconds = 30
        body = client.V1DeleteOptions()
        #body = {}  
        print("Deleting {}/{} pod {}".format(i+1, NumOfPodsToDeleted, pod['name']))    
        response = core_api.delete_namespaced_pod(name=pod['name'], namespace=namespace, grace_period_seconds=grace_period_seconds, body=body)
        #pprint(response)        
        
def schedulePods(namespace, NumOfPodsToBeScheduled, nodeLabel):
    
    global pendingPodsList
    global failedPodsList
    global runningPodsList
    
    #namespace = 'default'
    
        
    for i in range(NumOfPodsToBeScheduled):
        pod = pendingPodsList[0]
        print("attempting to schedule {}/{} pod={} with cpu_req={} mem_req={} for nodeLabel={}".format(i+1, NumOfPodsToBeScheduled, pod['name'], pod['cpu_req'], pod['mem_req'], nodeLabel))
         
        isPodScheduled = 0
        
        for node, stats in nodesListPerNodeLabel[nodeLabel].items():
                        
            print("Checking free resources on node={} with cpu_free={} and mem_free={} for nodeLabel={}".format(node, stats['cpu_free'], stats['mem_free'], nodeLabel))
            
            if pod['cpu_req'] <= stats['cpu_free'] and pod['mem_req'] <= stats['mem_free']:
                
                #before_node_cpu_free = nodesListPerNodeLabel[nodeLabel][node]['cpu_free']
                #before_node_mem_free = nodesListPerNodeLabel[nodeLabel][node]['mem_free']
                #print("node resources before scheduling pod: Label={}, node={} cpu_free={} mem_free={}".format(nodeLabel, node, nodesListPerNodeLabel[nodeLabel][node]['cpu_free'], nodesListPerNodeLabel[nodeLabel][node]['mem_free']))
                res = scheduler(pod['name'], node, namespace)
                isPodScheduled = 1
                stats['cpu_free'] = stats['cpu_free'] - pod['cpu_req']
                stats['mem_free'] = stats['mem_free'] - pod['mem_req']                
                #after_node_cpu_free = nodesListPerNodeLabel[nodeLabel][node]['cpu_free']
                #after_node_mem_free = nodesListPerNodeLabel[nodeLabel][node]['mem_free']
                
                print("Scheduled {}/{} pod={} on node={} with nodeLabel={}".format(i+1, NumOfPodsToBeScheduled, pod['name'], node, nodeLabel))
                #print("pod={} pod_cpu_req={} (node_cpu_free = {} - {}) pod_mem_req={} (node_mem_free = {} - {})".format(pod['name'], pod['cpu_req'], before_node_cpu_free, after_node_cpu_free, pod['mem_req'], before_node_mem_free, after_node_mem_free))
                print("node resources after scheduling pod: Label={}, node={} cpu_free={} mem_free={}".format(nodeLabel, node, nodesListPerNodeLabel[nodeLabel][node]['cpu_free'], nodesListPerNodeLabel[nodeLabel][node]['mem_free']))
                #pprint(res)

                pendingPodsList.remove(pod)
                
                break
                                
        
        if isPodScheduled == 0:
            print("failed scheduling {}/{} pod={} with cpu_req={} mem_req={} for nodeLabel={}".format(i+1, NumOfPodsToBeScheduled, pod['name'], pod['cpu_req'], pod['mem_req'], nodeLabel))
            break
        
def getPodsListForDeployment(namespace, deploymentName):
    
    #global pendingPodsList
    
    #runningPodsList =[]
    #failedPodsList =[]
    #podsList = {}
    
    #namespace='default'
    #name='Ec2SpotK8sScheduler'
    
    
    #field_selector = ("spec.scheduler_name=" + CustomSchedulerName)
    field_selector = ("spec.schedulerName=" + CustomSchedulerName)    
    
    
    pods = core_api.list_namespaced_pod(namespace=namespace, field_selector=field_selector).to_dict()
    #pods = core_api.list_namespaced_pod(namespace=namespace).to_dict()
    #print("pods={}".format(pods))
    for pod in pods['items']:
        #pprint(pod)
        #print("node_name={}".format(pod['spec']['node_name']))
        #return ""
        stats          = {}
        cpureqs,cpulmts,memreqs,memlmts = [], [], [], []
        if deploymentName in pod['metadata']['name'] and pod['spec']['scheduler_name'] == CustomSchedulerName:
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
            
            #podsList['pendingPodsList'] = pendingPodsList
            #podsList['runningPodsList'] = runningPodsList
            #podsList['failedPodsList'] = failedPodsList
            
        
    #pprint(podsList)
    #pprint("pendingPodsList={} runningPodsList={} failedPodsList={}".format(runningPodsList, runningPodsList, failedPodsList )
    #return pendingPodsList,runningPodsList,failedPodsList
    #return podsList

def get_custom_deployments():

    DEBUG_ENABLED = 0
    CustomKubeSchedulingClusterDeploymentData  = {}
    #namespaceList =[]
    namespacedataList = core_api.list_namespace().to_dict()['items']
    for namespaceData in namespacedataList:
        namespace = namespaceData['metadata']['name']
        CustomKubeSchedulingClusterDeploymentData[namespace] = get_custom_deployments_per_namespace(namespace)
        #namespaceList.append(name)
        
    if DEBUG_ENABLED:
        print("CustomKubeSchedulingClusterDeploymentData={}".format(CustomKubeSchedulingClusterDeploymentData))
    
    return CustomKubeSchedulingClusterDeploymentData
    
def get_custom_deployments_per_namespace(namespace):
    
    DEBUG_ENABLED = 0
    #CustomKubeSchedulingDeploymentData  = []
    CustomKubeSchedulingDeploymentData  = {}
    #namespace='default'
    #name = 'nginx'
    name = '1'
    #field_selector = ("metadata.name=" + name)
    #field_selector = ("metadata.annotations.OnDemandBase=" + name)    
    # get deployment by namespace
    #resp = apis_api.list_namespaced_deployment(namespace=namespace, field_selector=field_selector)

    resp = apis_api.list_namespaced_deployment(namespace=namespace)    
    for deployment in resp.items:
        #pprint(deployment.metadata.annotations)
        #pprint(deployment)
        deploymentData = {}
        CustomPodScheduleStrategy = {}
        annotations = deployment.metadata.annotations
        if 'UseCustomKubeScheduler' in annotations.keys():
            if annotations['UseCustomKubeScheduler'] == 'true':
                deploymentName = deployment.metadata.name
                numOfReplicas = deployment.spec.replicas
                #deploymentData[deploymentName] = deployment.metadata.name
                Strategy = annotations['CustomPodScheduleStrategy']
                DEBUG_ENABLED = 1
                if DEBUG_ENABLED:
                    print("Found CustomPodScheduleStrategy : {} for deployment {} with numOfReplicas {} in namespace {}".format(Strategy, deploymentName, numOfReplicas, namespace))
                #deploymentData['pod_replicas'] = deployment.spec.replicas
                #deploymentData['CustomPodScheduleStrategy'] = get_pods_custom_pod_schedule_strategy(Strategy, deployment.spec.replicas)
                CustomKubeSchedulingDeploymentData[deploymentName] = get_pods_custom_pod_schedule_strategy(Strategy, numOfReplicas)
                DEBUG_ENABLED = 0
                if DEBUG_ENABLED:
                    print("Pod to label mapping for deployment = {} is {}".format(deploymentName, CustomKubeSchedulingDeploymentData[deploymentName]))
                #deploymentData['NumOfOnDemandPodsToBeRunning'] = int (deploymentData['OnDemandBase'] + (deploymentData['pod_replicas'] - deploymentData['OnDemandBase']) *  deploymentData['OnDemandAbovePercentage'] / 100)
                #deploymentData['NumOfSpotPodsToBeRunning'] = deploymentData['pod_replicas'] - deploymentData['NumOfOnDemandPodsToBeRunning']
                
                #CustomKubeSchedulingDeploymentData.append(deploymentData)
                
                
                
    return CustomKubeSchedulingDeploymentData            
                
                #print("OnDemandBase={}, OnDemandAbovePercentage={} SpotASGName={} OnDemandASGName={} pod_replicas={} NumOfOnDemandPods={} NumOfSpotPods={}".format(OnDemandBase, OnDemandAbovePercentage, SpotASGName, OnDemandASGName, pod_replicas, NumOfOnDemandPods, NumOfSpotPods))
                
def get_pods_custom_pod_schedule_strategy(Strategy, numOfReplicas):
    
    DEBUG_ENABLED = 0
    
    if DEBUG_ENABLED:
        print("Strategy={} numOfReplicas={}".format(Strategy, numOfReplicas))
    
    CustomPodScheduleStrategy = {}
    nodeLabelToReplicas = {}
    nodeLabelToWights = {}
    totalWeight = 0
    
    StrategyList = Strategy.split(':')
    
    if DEBUG_ENABLED:
        print("StrategyList={}".format(StrategyList))
    
    numOfBaseValues = 0
    for nodeStrategy in StrategyList:
        
        if DEBUG_ENABLED:
            print("nodeStrategy: {}".format(nodeStrategy))
        
        nodeStrategyPartsList = nodeStrategy.split(',')
        
        base = 0
        weight = 0
        nodeLabel = ''
        
        for nodeStrategyPart in nodeStrategyPartsList:
            nodeStrategySubPartList = nodeStrategyPart.split('=')
            if nodeStrategySubPartList[0] == 'base':
                if numOfBaseValues != 0:
                    print("base value cannot be non-zero for more than node strategy")
                    exit(1)
                else:
                    numOfBaseValues += 1
                    
                base = int(nodeStrategySubPartList[1])
                if base <= numOfReplicas:
                    numOfReplicas -= base
                else:
                    base = numOfReplicas
                    numOfReplicas = 0
                if DEBUG_ENABLED:
                    print("base={}".format(nodeStrategySubPartList[1]))
            elif nodeStrategySubPartList[0] == 'weight':
                weight = int(nodeStrategySubPartList[1])
                totalWeight += weight
                if DEBUG_ENABLED:
                    print("weight={}".format(weight))                
            else:
                nodeLabel = nodeStrategyPart
                if DEBUG_ENABLED:
                    print("label key={} value={}".format(nodeStrategySubPartList[0], nodeStrategySubPartList[1]))
                
        #nodeLabelToReplicas [nodeLabel] = base
        nodeLabelToWights [nodeLabel] = weight
        CustomPodScheduleStrategy [nodeLabel] = base
        
    
    if DEBUG_ENABLED:
        print("nodeLabelToReplicas={} nodeLabelToWights={}".format(nodeLabelToReplicas, nodeLabelToWights))
        print("numOfBaseValues = {} totalWeight={} numOfReplicas={}".format(numOfBaseValues, totalWeight, numOfReplicas))
        print("CustomPodScheduleStrategy = {}".format(CustomPodScheduleStrategy))
    
    totalNumOfLables = len (CustomPodScheduleStrategy)
    labelNum = 0
    
    for key, replicas in CustomPodScheduleStrategy.items():
        weight = nodeLabelToWights[key]
        if DEBUG_ENABLED:
            print("key: {} replicas={} weight={}, totalWeight={}".format(key, replicas, weight, totalWeight))
        if labelNum == totalNumOfLables - 1:
            weightReplicas = numOfReplicas
            replicas = replicas + weightReplicas
        else:
            weightReplicas = int (numOfReplicas * (weight/totalWeight))
            replicas = replicas + weightReplicas
            
        labelNum += 1
        numOfReplicas -= weightReplicas
        if DEBUG_ENABLED:
            print("weightReplicas: {} replicas={} labelNum={}, numOfReplicas={}".format(weightReplicas, replicas, labelNum, numOfReplicas))           
        CustomPodScheduleStrategy[key] = replicas
    
    if DEBUG_ENABLED:
        print("CustomPodScheduleStrategy = {}".format(CustomPodScheduleStrategy))    
        print("numOfBaseValues = {} totalWeight={} numOfReplicas={}".format(numOfBaseValues, totalWeight, numOfReplicas))
            
    return CustomPodScheduleStrategy
    
    
                
                
__all__ = ["get_node_available_nodes_list"]

def get_node_available_nodes_list(CustomSchedulingData):

    global nodesListPerNodeLabel
    
    #data = []
    #data = {}
    
    for nodeLabel in CustomSchedulingData.keys():
        nodesListPerNodeLabel[nodeLabel] = {}
        nodeLabelParts = nodeLabel.split('=')
        nodeLabelKey = nodeLabelParts[0]
        nodeLabelValue = nodeLabelParts[1]
        
        #selector = "metadata.labels."+nodeLabelParts[0]+"="+nodeLabelParts[1]
        #selector = "metadata.labels.nodesize="+nodeLabelParts[1]
        #print("selector={}".format(selector))
        #name = 'ip-192-168-73-104.ec2.internal'
        #selector = "metadata.name"+"="+name
        #print("selector={}".format(selector))
        #field_selector = (selector)
        #resp = core_api.list_node(field_selector=field_selector).to_dict()['items']
        #pprint("resp={}".format(resp))
        #exit(0)
        
        availableNodesData = {}                          
        for node in core_api.list_node().to_dict()['items']:
            #pprint(node)
            
            
            node_labels    = node['metadata']['labels']
            
            if nodeLabelKey in node_labels.keys():
                if node_labels[nodeLabelKey] == nodeLabelValue:
                    stats          = {}
                    node_name      = node['metadata']['name']
                    
                    allocatable    = node['status']['allocatable']
                    max_pods       = int(int(allocatable["pods"]) * 1.5)
                    field_selector = ("status.phase!=Succeeded,status.phase!=Failed," +
                                      "spec.nodeName=" + node_name)
            
                    stats["cpu_alloc"] = Q_(allocatable["cpu"])
                    stats["mem_alloc"] = Q_(allocatable["memory"])
                    #stats["lifecycle"] = lifecycle
            
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
                    availableNodesData[node_name] = stats
        nodesListPerNodeLabel[nodeLabel] = availableNodesData
    
    #print(nodesListPerNodeLabel)
    #for nodeLabel, availableNodesData in nodesListPerNodeLabel.items():
        #print("nodeLabel={} availableNodesData={}".format(nodeLabel, availableNodesData))
    
    #exit(0)
                    

    #pprint(data)
    #return data
    
if __name__ == '__main__':
    #ready_nodes = nodes_available()
    #pprint(ready_nodes)
    #name='review-v1-787d8fbfbb-ltdzt'
    #node='ip-10-0-3-253.ec2.internal'
    #namespace='ecommerce'
    #ret=scheduler(name, node, namespace)
    #pprint(ret)
    #main()
    #test()
    #testpod()
    #check_node_resources(node)
    #RunCustomKubeScheduler()
    #getPodsListForDeployment(' ')
    #lifecycle = 'OnDemand'
    #lifecycle = 'Ec2Spot'
    #get_node_available_nodes_list(lifecycle)
    #RunCustomKubeScheduler()
    #NumOfPodsToDeleted = 1
    #podsAlreadyRunningOnNodeLabelList = []
    #d ={'name':'nginx-66cb875766-vx6bp'}
    #podsAlreadyRunningOnNodeLabelList.append(d)
    #deletePods(NumOfPodsToDeleted, podsAlreadyRunningOnNodeLabelList)
    #deploymentName='nginx'
    #deploymentName = 'kube-ops-view'
    #getPodsListForDeployment(deploymentName)
    #testlist()
    #tl.start(block=True)
    while True:
        RunCustomKubeScheduler()
        val = input("Enter any letter to continue: ")
        #time.sleep(10)
    
    

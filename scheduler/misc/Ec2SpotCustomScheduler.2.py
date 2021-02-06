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

#from sdcclient import SdcClient

#config.load_kube_config()
config.load_incluster_config()
    # doing this computation within a k8s cluster
    #k8s.config.load_incluster_config()
core_api = client.CoreV1Api()
apis_api = client.AppsV1Api()
asgclient = boto3.client('autoscaling')
#sdclient = SdcClient(<Your Sysdig API token>)
sysdig_metric = "net.http.request.time"
metrics = [{ "id": sysdig_metric, "aggregations": { "time": "timeAvg", "group": "avg" } }]

scheduler_name = "Ec2SpotK8sScheduler"
ureg = UnitRegistry()
ureg.load_definitions('kubernetes_units.txt')

pendingPodsList = []
failedPodsList = []

Q_   = ureg.Quantity

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
    return core_api.create_namespaced_binding(namespace, body, _preload_content=False)

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

def scaleEc2Autoscaling(asg_name, DesiredCapacity):

    response = client.describe_auto_scaling_groups(
          AutoScalingGroupNames=[
            asg_name,
          ]
        )
    pprint(response)
    CurrentDesiredCapacity=response['AutoScalingGroups'][0]['DesiredCapacity']

    response = client.set_desired_capacity(
      AutoScalingGroupName=asg_name,
      DesiredCapacity=DesiredCapacity,
      HonorCooldown=True
    )
  
tl = Timeloop()

@tl.job(interval=timedelta(seconds=10))  
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
                


def sample_job_every_2s():
    print("2s job current time : {}".format(time.ctime()))
    
l = []
def testlist():
    global l
    print("testlist")
    l = ['a', 'b', 'c']
    pprint(l)
    test1()
    pprint(l)
    
def test1():
    global l
    print("test1")
    pprint(l)
    pprint(l[0])
    l.remove('a')
    pprint(l[0])
    
    
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
    tl.start(block=True)
    
    

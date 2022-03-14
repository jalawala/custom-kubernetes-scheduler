# Custom Kube Scheduler with Karpenter

This repo contains a sample demo on how to run the custom kubernetes scheduler along with Karpneter.
The custom kube scheduler is designed to allow flexible placenent of pods across various nodegroups in a gievn ratio. This is similar to AWS ECS capacity provider straregy which allowws different weights for each capacity provider. Each service can specify its own scheduling strategy for the placement of tasks. Similary you can specify this strategy for each kubernetes deployment.

The default Kubernetes Cluster Autoscaler does not support custom schedulers. Karpenter is a metric driven cluster autoscaler designed by AWS and it is open sourced.
This repo hosts a sample nginx deployment to demonstrate both custom kube scheduler and Karpneter.

The custom kube scheduler checks for a specific annotation in the deployment across all namespaces in the cluster. This annotation specify the custom scheduling strategy similar to Amazon ECS capacity provideers.

Its basic work flow is as follows.

![](./docs/CustomKubeScheduler.jpg)



## Prerequisites
Install Python3 is installed and run below command to deploy the required packages

```bash
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py --force-reinstall
pip3 install -r requirements.txt  
```
## Create EKS Cluster
Create an EKS cluster or re-use an existing cluster. Ensure that basic commands wor

```bash
kubectl get nodes 
```

## Create EKS Managed nodegroups

For this demo, create 1 EKS managed node group completely on On-demand and 2 using EC2 Spot

```bash
eksctl create nodegroup --cluster eksworkshop --version 1.17 --region us-east-1 --name od-mng-4vcp-16gb --instance-types m5.xlarge,m4.xlarge,m5a.xlarge,m5d.xlarge,m5n.xlarge,m5ad.xlarge,m5dn.xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --node-labels "lc=od,apps=critical,nodesize=od4vcpu16gb" 

eksctl create nodegroup --cluster eksworkshop --version 1.17 --region us-east-1 --name spot-mng-4vcp-16gb --instance-types m5.xlarge,m4.xlarge,m5a.xlarge,m5d.xlarge,m5n.xlarge,m5ad.xlarge,m5dn.xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --spot --node-labels "lc=spot,apps=noncritical,nodesize=spot4vcpu16gb"

eksctl create nodegroup --cluster eksworkshop --version 1.17 --region us-east-1 --name spot-mng-8vcp-32gb --instance-types m5.2xlarge,m4.2xlarge,m5a.2xlarge,m5d.2xlarge,m5n.2xlarge,m5ad.2xlarge,m5dn.2xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --spot --node-labels "lc=spot,apps=noncritical,nodesize=spot8vcpu32gb"
```

Get the node group ARNs and deploy the Karpenter resources


```bash
cd karpenter-aws-demo/k8s_custom_scheduler \
OD_NODE_GROUP_ARN=$(aws eks describe-nodegroup --nodegroup-name od-mng-4vcp-16gb --cluster-name eksworkshop --output json | jq -r ".nodegroup.nodegroupArn") \
echo "OD_NODE_GROUP_ARN = $OD_NODE_GROUP_ARN"  \
SPOT_NODE_GROUP1_ARN=$(aws eks describe-nodegroup --nodegroup-name spot-mng-4vcp-16gb --cluster-name eksworkshop --output json | jq -r ".nodegroup.nodegroupArn") \
echo "SPOT_NODE_GROUP1_ARN = $SPOT_NODE_GROUP1_ARN"  \
SPOT_NODE_GROUP2_ARN=$(aws eks describe-nodegroup --nodegroup-name spot-mng-8vcp-32gb --cluster-name eksworkshop --output json | jq -r ".nodegroup.nodegroupArn") \
echo "SPOT_NODE_GROUP2_ARN = $SPOT_NODE_GROUP2_ARN"  \
envsubst < karpenter_resources.yaml | kubectl apply -f -

```

## Create port forward for the prometheus service and open it in brower

```bash
kubectl -n karpenter port-forward prometheus-karpenter-monitor-0 8080:9090
```


## Configuring the Deployment for the Kube Scheduler
Add the following annotation to the deployment in nginx.yaml
Note that replica is set to 5 initially.

```bash
kind: Deployment
metadata:
  name: nginx
  annotations:
    UseCustomKubeScheduler: 'true'
    CustomPodScheduleStrategy: 'nodesize=od4vcpu16gb,base=1,weight=0:nodesize=spot4vcpu16gb,weight=1:nodesize=spot8vcpu32gb,weight=1'
  labels:
    ...  
```
The *CustomPodScheduleStrategy* specify how pods within a deployment should be spread

## Deploy the Sample nginx deployment. 

```bash
cd karpenter-aws-demo/k8s_custom_scheduler
kubectl apply -f nginx.yaml
```
## Run the Kube Custom Scheduler as a standalone python script on Cloud9

Note that custom kube scheduler can be run in two modes. 
1) as a standlone python script for debugging purpose
2) kubernetes deployment inside the cluster 

To run as the standalone script, set the RUN_AS_K8S_DEPLOYMENT=0 in the CustomKubeScheduler.py file
In this mode, it waits for a user input every time before running the main loop. This is to allow enoigh time for debugging the output of the custom kube scheduler.

```bash
./CustomKubeScheduler.py
```

Enter any letter to proceed further to next loop
]
In a new terminal, change the replica to 5 in nginx.yaml and deploy

```bash
cd karpenter-aws-demo/k8s_custom_scheduler
kubectl apply -f nginx.yaml
```

Note that kube scheduler deploy the 5 pods in this ratio

```bash
namespace=default deploymentName=nginx CustomSchedulingData={'nodesize=od4vcpu16gb': 1, 'nodesize=spot4vcpu16gb': 2, 'nodesize=spot8vcpu32gb': 2}
```

The output of custom kube scheduler should like below

![](./docs/replicas-5.png)


Now change the replica from 5 to 10 nginx and redeploy nging.yaml

```bash
cd karpenter-aws-demo/k8s_custom_scheduler
kubectl apply -f nginx.yaml
```

The output of custom kube scheduler should like below

![](./docs/replicas-10.png)


Now change the replica from 10 to 30 nginx and redeploy nging.yaml

```bash
cd karpenter-aws-demo/k8s_custom_scheduler
kubectl apply -f nginx.yaml
```

The output of custom kube scheduler should like below

![](./docs/replicas-30.png)

As you see, Karpenter one instance in the nodegroup spot-mng-4vcp-16gb

# Manually open in 5 separate terminals
To see Karpenter scaling activities, run below commands in seoperate terminals for nodegroup spot-mng-4vcp-16gb
 

```bash
watch 'kubectl get pods -n karpenter-custom-kube-scheduler-demo'
watch 'kubectl get nodes'
watch -d 'kubectl get metricsproducers.autoscaling.karpenter.sh spot-mng-4vcp-16gb -n karpenter-custom-kube-scheduler-demo -ojson | jq .status.reservedCapacity'
watch -d 'kubectl get horizontalautoscalers.autoscaling.karpenter.sh spot-mng-4vcp-16gb -n karpenter-custom-kube-scheduler-demo -ojson | jq ".status" | jq del\(.conditions\)'
watch -d 'kubectl get scalablenodegroups.autoscaling.karpenter.sh spot-mng-4vcp-16gb -n karpenter-custom-kube-scheduler-demo -ojson | jq "del(.status.conditions)"| jq ".spec, .status"'
```

## Run Custom Scheduler as Deployment


### Step0 :  Ensure CA is not running and manually scale ASGs with instances needed for your workload
 kubectl delete -f ~/environment/cluster-autoscaler/cluster_autoscaler.yml 

### Step1 : Set the mode to run as kubernetes deployment

To run as the a kubernetes deployment script, set the RUN_AS_K8S_DEPLOYMENT=1 in the CustomKubeScheduler.py file


### Step2 : Create an ECR Repo

aws ecr create-repository \
    --repository-name customkubescheduler \
    --image-scanning-configuration scanOnPush=true
    
### Step3 :  Build customer Scheduler container and push it to ECR

cd karpenter-aws-demo/k8s_custom_scheduler

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com


docker build --no-cache -t customkubescheduler .
docker build  -t customkubescheduler .
docker tag customkubescheduler:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/customkubescheduler:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/customkubescheduler:latest
 
### Step4 :  Build and Deploy the customer Scheduler onto OnDemand Instances
Update the docker image path in customkubescheduler.yaml. 

envsubst < CustomKubeScheduler.yaml | kubectl apply -f -

kubectl apply  -f CustomKubeScheduler.yaml 

envsubst < CustomKubeScheduler.yaml | kubectl apply -f -


### Step5 : Monitor the logs for the custom scheduler
kubectl logs -f customkubescheduler-78b6c6c989-bzn5x


### Step6 : Try changing the pod distribution by changing OnDemandBase, OnDemandAbovePercentage and replica

export EDITOR=vim
kubectl edit deploy nginx

check out the custom scheduler logs also check 'kubectl get pods'

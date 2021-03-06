# Kubernetes Mutating Webhook for Custom Pod Scheduling

This tutorial shows how to build and deploy a [MutatingAdmissionWebhook](https://kubernetes.io/docs/admin/admission-controllers/#mutatingadmissionwebhook-beta-in-19) that implements a custom pod scheduling mutating
webhook. This webhook adds a nodeSelector with a specific nodelabel for the incoming pods from APi server. The custom pod schedule strategy needs to be specified as an annotation in the pod specification.

## Prerequisites

### Install Below Tools

Ensure that below tools are installed in your environment.

- [git](https://git-scm.com/downloads)
- [go](https://golang.org/dl/) version v1.12+
- [docker](https://docs.docker.com/install/) version 17.03+
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) version v1.11.3+
- Access to a Kubernetes v1.11.3+ cluster with the `admissionregistration.k8s.io/v1beta1` API enabled. Verify that by the following command:


Set few environment variables

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --output text --query Account)
export AWS_REGION=$(curl -s 169.254.169.254/latest/dynamic/instance-identity/document | jq -r '.region')
export CUSTOM_SCHEDULER_WEBHOOK=custom-kube-scheduler-webhook
git clone https://github.com/jalawala/custom-kubernetes-scheduler.git
cd custom-kubernetes-scheduler/admissionwebhook

```


### Create an EKS Cluster and Managed nodegroups

If you don't have an EKS cluster already available, refer to [this page](https://www.eksworkshop.com/030_eksctl/launcheks/)  to create a cluster and setup the kubectl command.

Set the EKS cluster name
```bash
export CLUSTER_NAME=eksworkshop
```


Create 3 Managed Node groups (1 on-demand and 2 spot nodegroups) which we will be used in the sample application

```bash
eksctl create nodegroup --cluster $CLUSTER_NAME --version 1.18 --region $AWS_REGION --name od-mng-4vcp-16gb --instance-types m5.xlarge,m4.xlarge,m5a.xlarge,m5d.xlarge,m5n.xlarge,m5ad.xlarge,m5dn.xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --node-labels "lc=od,apps=critical,nodesize=od4vcpu16gb" 

eksctl create nodegroup --cluster $CLUSTER_NAME --version 1.18 --region $AWS_REGION --name spot-mng-4vcp-16gb --instance-types m5.xlarge,m4.xlarge,m5a.xlarge,m5d.xlarge,m5n.xlarge,m5ad.xlarge,m5dn.xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --spot --node-labels "lc=spot,apps=noncritical,nodesize=spot4vcpu16gb"

eksctl create nodegroup --cluster $CLUSTER_NAME --version 1.18 --region $AWS_REGION --name spot-mng-8vcp-32gb --instance-types m5.2xlarge,m4.2xlarge,m5a.2xlarge,m5d.2xlarge,m5n.2xlarge,m5ad.2xlarge,m5dn.2xlarge --nodes 1 --nodes-min 1 --nodes-max 20 --managed  --asg-access --spot --node-labels "lc=spot,apps=noncritical,nodesize=spot8vcpu32gb"
```

Run the below command to check the required features are enabled in the cluster

```
kubectl api-versions | grep admissionregistration.k8s.io
```
The result should be:
```
admissionregistration.k8s.io/v1
admissionregistration.k8s.io/v1beta1
```

## Build and Push the Image to the ECR repo



### Create an ECR Repo

```
aws ecr create-repository --repository-name $CUSTOM_SCHEDULER_WEBHOOK/$CUSTOM_SCHEDULER_WEBHOOK
```

### Build the docker image and push it to the ECR repo

Run the below script to build the go binary, container image and push it to the ECR repo 

```
./build_and_push.sh
```

## Deploy the Mutating Pod Webook 

### Create the namespace

Create namespace `custom-kube-scheduler-webhook` in which the mutating pod webhook will be deployed:

```
 kubectl create ns custom-kube-scheduler-webhook
```

### Create the Certificate and Secrets

Create a signed cert/key pair and store it in a Kubernetes `secret` that will be consumed by mutating pod webhook deployment:

```
./deploy/webhook-create-signed-cert.sh \
    --service custom-kube-scheduler-webhook \
    --secret custom-kube-scheduler-webhook-certs \
    --namespace custom-kube-scheduler-webhook
```

The above script also creates a kubernetes secret `custom-kube-scheduler-webhook-certs`

Ensure that secret is created successfully

```
 kubectl get secret custom-kube-scheduler-webhook-certs -n custom-kube-scheduler-webhook -ojson
```

### Deploy the mutating pod webhook

Patch the `MutatingWebhookConfiguration` by set `caBundle` with correct value from Kubernetes cluster:

```
cat deploy/mutatingwebhook.yaml | \
    deploy/webhook-patch-ca-bundle.sh > \
    deploy/mutatingwebhook-ca-bundle.yaml
```

Deploy the mutating pod web hook configuration and the deployment

```
kubectl create -f deploy/custom-kube-scheduler-webhook.yaml
kubectl create -f deploy/mutatingwebhook-ca-bundle.yaml
```

## Deploy a sample application 

### Create a test namespace and deploy the sample app

Verify that web hook is running fine

```
kubectl create -f deploy/namespaces.yaml
# kubectl -n custom-kube-scheduler-webhook get pod
NAME                                            READY   STATUS    RESTARTS   AGE
custom-kube-scheduler-webhook-66dd85646-qp244   1/1     Running   0          7m22s
```

Create new namespace `custom-kube-scheduler-test` and label it with `custom-kube-scheduler-webhook: enabled':

```
kubectl create -f deploy/namespaces.yaml
kubectl get namespace -lcustom-kube-scheduler-webhook=enabled
NAME                         STATUS   AGE
custom-kube-scheduler-test   Active   8m43s
```

Deploy an app in Kubernetes cluster, take `alpine` app as an example

```
kubectl create -f deploy/alpine.yaml
```

Note that alpine has below strategy

```
annotations:
UseCustomKubeScheduler: 'true'
CustomPodScheduleStrategy: 'nodesize=od4vcpu16gb,base=1,weight=0:nodesize=spot4vcpu16gb,weight=1:nodesize=spot8vcpu32gb,weight=1'
spec:
replicas: 10

```
As per this label 'nodesize=od4vcpu16gb' should have 1 pod and 'nodesize=spot4vcpu16gb' should have 4 and 'nodesize=spot8vcpu32gb' should have 5 pods 

Verify pods are distributed as per the strategy

```
./check_pod_spread.sh 
NAME                      READY   STATUS    RESTARTS   AGE
alpine-5c4ff85997-6qwxs   1/1     Running   0          5m22s
alpine-5c4ff85997-7gbnz   1/1     Running   0          5m23s
alpine-5c4ff85997-8wlvk   1/1     Running   0          5m21s
alpine-5c4ff85997-gxc2d   1/1     Running   0          9m35s
alpine-5c4ff85997-kh2xr   1/1     Running   0          5m22s
alpine-5c4ff85997-kntr6   1/1     Running   0          5m23s
alpine-5c4ff85997-mr2l8   1/1     Running   0          5m50s
alpine-5c4ff85997-rp6vh   1/1     Running   0          5m50s
alpine-5c4ff85997-tpksf   1/1     Running   0          5m50s
alpine-5c4ff85997-vgfgw   1/1     Running   0          5m50s
Number of Pods in namespace custom-kube-scheduler-test is 10
Number of Occurences for nodesize:od4vcpu16g is 1
Number of Occurences for nodesize:spot4vcpu16g is 4
Number of Occurences for nodesize:spot8vcpu32gb is 5
```

## Troubleshooting


### Check Webhook logs 

Run this script on a seperate terminal to check logs

```
./check_webhook_logs.sh
```

The log levels are controlled by environment variable in the deployment spec file i.e. 'deploy\custom-kube-scheduler-webhook.yaml'

```
          env:
          - name: LOG_LEVEL
            value: "INFO"
```

Only one value i.e.  default "INFO" is supported for now. It prints detailed logging information.
To reduce the log output, replace "INFO" with a empty "" string and re-deploy the deployment.

```
kubectl apply -f ./deploy/custom-kube-scheduler-webhook.yaml
```
### Source code  

The source code is available in two Go files i.e.  cmd/main.go and cmd/webhook.go

### Debug the code

if you need to make any changes in the code and re-build the container and re-deploy it, run below command

```
./build_and_push.sh
kubectl -n custom-kube-scheduler-webhook rollout restart deployment custom-kube-scheduler-webhook
```

### Block list namespaces 

You can avoid/ignore certain name spaces for this custom pod scheduling webhook functionality

This is specified as environment variable  the deployment spec file i.e. 'deploy\custom-kube-scheduler-webhook.yaml'

```
          - name: BLOCKLISTED_NAMESPACE_LIST
            value: "kube-system,kube-public,default"
```

if you want to add an additional name space, add it to above list WITHOUT any extra spaces after comma and re-deploy it
# Kubernetes Mutating Webhook for Custom Pod Scheduling

This tutoral shows how to build and deploy a [MutatingAdmissionWebhook](https://kubernetes.io/docs/admin/admission-controllers/#mutatingadmissionwebhook-beta-in-19) that implements a custom pod sccheduling
based on the scheduling strategy defined in the annotation of the deployment.

## Prerequisites

- [git](https://git-scm.com/downloads)
- [go](https://golang.org/dl/) version v1.12+
- [docker](https://docs.docker.com/install/) version 17.03+
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) version v1.11.3+
- Access to a Kubernetes v1.11.3+ cluster with the `admissionregistration.k8s.io/v1beta1` API enabled. Verify that by the following command:

```
kubectl api-versions | grep admissionregistration.k8s.io
```
The result should be:
```
admissionregistration.k8s.io/v1
admissionregistration.k8s.io/v1beta1
```

> Note: In addition, the `MutatingAdmissionWebhook` and `ValidatingAdmissionWebhook` admission controllers should be added and listed in the correct order in the admission-control flag of kube-apiserver.

## Build

1. Build binary

```
# make build-linux
```

2. Create an ECR repo like below

```
$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/custom-kube-scheduler-webhook/custom-kube-scheduler-webhook
```

2. Build docker image
   
```
# make build-image
```

3. push docker image

```
# make push-image
```

> Note: log into the docker registry before pushing the image.

## Deploy

1. Create namespace `custom-kube-scheduler-webhook` in which the custom-kube-scheduler-webhook is deployed:

```
 kubectl create ns custom-kube-scheduler-webhook
```

2. Create a signed cert/key pair and store it in a Kubernetes `secret` that will be consumed by sidecar injector deployment:

```
./deploy/webhook-create-signed-cert.sh \
    --service custom-kube-scheduler-webhook \
    --secret custom-kube-scheduler-webhook-certs \
    --namespace custom-kube-scheduler-webhook
```

3. Ensure that secret is created successfully

```
 kubectl get secret custom-kube-scheduler-webhook-certs -n custom-kube-scheduler-webhook -ojson
```


3. Patch the `MutatingWebhookConfiguration` by set `caBundle` with correct value from Kubernetes cluster:

```
cat deploy/mutatingwebhook.yaml | \
    deploy/webhook-patch-ca-bundle.sh > \
    deploy/mutatingwebhook-ca-bundle.yaml
```

4. Deploy custom-kube-scheduler-webhook:

```
kubectl create -f deploy/custom-kube-scheduler-webhook.yaml
kubectl create -f deploy/mutatingwebhook-ca-bundle.yaml
```

## Verify

1. verify that web hook is running fine

```
kubectl create -f deploy/namespaces.yaml
# kubectl -n custom-kube-scheduler-webhook get pod
NAME                                            READY   STATUS    RESTARTS   AGE
custom-kube-scheduler-webhook-66dd85646-qp244   1/1     Running   0          7m22s
```

2. Create new namespace `custom-kube-scheduler-test` and label it with `custom-kube-scheduler-webhook: enabled':

```
kubectl create -f deploy/namespaces.yaml
kubectl get namespace -lcustom-kube-scheduler-webhook=enabled
NAME                         STATUS   AGE
custom-kube-scheduler-test   Active   8m43s
```

3. Deploy an app in Kubernetes cluster, take `alpine` app as an example

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

4. Verify pods are distributed as per the strategy

```
jp:~/environment/jalawala/custom-kubernetes-scheduler/admissionwebhook (main) $ ./build3.sh 
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

TBD


#!/bin/bash


sleep 1
export POD_NAME=$(kubectl get pods -n sidecar-injector -l app=sidecar-injector -o jsonpath='{.items[].metadata.name}')
kubectl logs -f $POD_NAME -n sidecar-injector


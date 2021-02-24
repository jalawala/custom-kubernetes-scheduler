#!/bin/bash


#sleep 1
#kubectl get pods -n injection -l app=alpine | jq -r '.'

export LABEL1="nodesize:od4vcpu16g"
export LABEL2="nodesize:spot4vcpu16g"
export LABEL3="nodesize:spot8vcpu32gb"
export NAMESPACE="injection"

#kubectl get pods -n injection -l app=alpine -o jsonpath='{.items[*].spec.nodeSelector}' | grep $LABEL1

kubectl get pod -n $NAMESPACE
PODS=$(kubectl get pod -n $NAMESPACE | wc -l)
PODS=$((PODS-1))
echo "Number of Pods in namespace $NAMESPACE is $PODS"
L1=$(kubectl get pods -n injection -l app=alpine -o jsonpath='{.items[*].spec.nodeSelector}' | grep  -o  $LABEL1 | wc -l)
echo "Number of Occurences for $LABEL1 is $L1"
L2=$(kubectl get pods -n injection -l app=alpine -o jsonpath='{.items[*].spec.nodeSelector}' | grep  -o  $LABEL2 | wc -l)
echo "Number of Occurences for $LABEL2 is $L2"
L3=$(kubectl get pods -n injection -l app=alpine -o jsonpath='{.items[*].spec.nodeSelector}' | grep  -o  $LABEL3 | wc -l)
echo "Number of Occurences for $LABEL3 is $L3"
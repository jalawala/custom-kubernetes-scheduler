#!/bin/bash


make build-linux
make build-image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 000474600478.dkr.ecr.us-east-1.amazonaws.com
make push-image

sleep 1
kubectl -n sidecar-injector rollout restart deployment sidecar-injector-webhook-deployment


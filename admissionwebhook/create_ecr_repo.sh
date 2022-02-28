#!/bin/bash
IMAGE_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_NAME="custom-kube-scheduler-webhook3"


export ECR_REPO_URI=$(aws ecr describe-repositories --repository-name ${IMAGE_NAME}  | jq -r '.repositories[0].repositoryUri')

if [ -z "$ECR_REPO_URI" ]
then
      echo "${IMAGE_REPO}/${IMAGE_NAME} does not exist. So creating it..."
      ECR_REPO_URI=$(aws ecr create-repository \
        --repository-name $IMAGE_NAME\
        --region $AWS_REGION \
        --query 'repository.repositoryUri' \
        --output text)
      echo "ECR_REPO_URI=$ECR_REPO_URI"
else
      echo "${IMAGE_REPO}/${IMAGE_NAME} already exist..."
fi


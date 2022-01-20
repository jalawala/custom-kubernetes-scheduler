FROM alpine:latest

# set labels for metadata
LABEL maintainer="Jayaprakash Alawala<jalawala@amazon.com>" \
  name="custom-kube-scheduler-webhook" \
  description="A Kubernetes mutating webhook server that implements custom kube scheduler" \
  summary="A Kubernetes mutating webhook server that implements custom kube scheduler"

# set environment variables
ENV CUSTOM_KUBE_SCHEDULER_WEBHOOK=/usr/local/bin/custom-kube-scheduler-webhook \
  USER_UID=1001 \
  USER_NAME=custom-kube-scheduler-webhook

# install sidecar-injector binary
COPY output/custom-kube-scheduler-webhook ${CUSTOM_KUBE_SCHEDULER_WEBHOOK}

# copy licenses
RUN mkdir /licenses
COPY LICENSE /licenses

# set entrypoint
ENTRYPOINT ["/usr/local/bin/custom-kube-scheduler-webhook"]

# switch to non-root user
USER ${USER_UID}

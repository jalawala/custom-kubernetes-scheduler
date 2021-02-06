#! /usr/bin/python3
import yaml
import os.path
import base64
import boto3
import sys
from pprint import pprint
from botocore.signers import RequestSigner
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging

# for event engine, use ops role credentials
ACCESS_KEY_ID=''
SECRET_ACCESS_KEY=''
SESSION_TOKEN=''
#isen test.

#ACCOUNT_ID = ''
MAP_USER_NAME = 'sukumar-test'
MAP_ROLE_NAME = 'TeamRole'

REGION = 'us-east-1'
CLUSTER_NAME = 'Ec2SpotEKS4'
CLUSTER_ROLE_NAME = 'Ec2SpotEKS4-NodeInstanceRole'

#env variables for AWS
ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
# SESSION_TOKEN = os.environ['AWS_SESSION_TOKEN']
# REGION = os.environ['AWS_DEFAULT_REGION']
# ACCOUNT_ID = os.environ['AWS_ACCOUNT_ID']
#IAM user that EKS should allow admin access. leave this empty if you do not want.
# MAP_USER_NAME = os.environ['EKS_IAM_USER_NAME']
#IAM role that EKS should allow admin access. leave this empty if you do not want.
# MAP_ROLE_NAME = os.environ['EKS_IAM_ROLE_NAME']
#EKS cluster where aws-auth config needs to be applied
# CLUSTER_NAME = os.environ['EKS_CLUSTER_NAME']
#role to allow nodes to join EKS cluster (nodegroup instances)
# CLUSTER_ROLE_NAME = os.environ['EKS_CLUSTER_ROLE_NAME']

#env variables for STS, K8s Client
EKS_HEADER = 'x-k8s-aws-id'
EKS_PREFIX = 'k8s-aws-v1.'
STS_END_POINT = 'sts.amazonaws.com'
STS_ACTION = 'Action=GetCallerIdentity&Version=2011-06-15'
EXPIRES_IN = 60
KUBE_FILEPATH = '/tmp/kubeconfig'


def get_aws_session():
    #aws_session
    if SESSION_TOKEN == '':
        print("empty session token")
        aws_session = boto3.Session(
            aws_access_key_id=ACCESS_KEY_ID,
            aws_secret_access_key=SECRET_ACCESS_KEY,
            region_name=REGION
        )
    else:
        print("####################################")
        aws_session = boto3.Session(
            aws_access_key_id=ACCESS_KEY_ID,
            aws_secret_access_key=SECRET_ACCESS_KEY,
            aws_session_token=SESSION_TOKEN,
            region_name=REGION
        )

    #use assume role, if needed
    return aws_session

def get_token():

    session = get_aws_session()

    sts_client = session.client("sts", region_name=REGION)
    print("caller identity ***####*************" + str (sts_client.get_caller_identity()))
    service_id = sts_client.meta.service_model.service_id
    print("service id ######" + service_id )
    signer = RequestSigner(
        service_id,
        session.region_name,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )

    params = {
        'method': 'GET',
        'url': 'https://' + STS_END_POINT + '/?' + STS_ACTION,
        'body': {},
        'headers': {
            EKS_HEADER: CLUSTER_NAME
        },
        'context': {}
    }

    signed_url = signer.generate_presigned_url(
        params,
        region_name=session.region_name,
        expires_in=EXPIRES_IN,
        operation_name=''
    )
    print("signed url:  " + signed_url)

    return (
            EKS_PREFIX +
            base64.urlsafe_b64encode(
                signed_url.encode('utf-8')
            ).decode('utf-8')
    )


def create_kube_config_file_for_eks():
    token = get_token()
    #get eks cluster details for creating kubeconfig content
    eks_api = get_aws_session().client('eks', region_name=REGION)
    cluster_info = eks_api.describe_cluster(name=CLUSTER_NAME)
    certificate = cluster_info['cluster']['certificateAuthority']['data']
    endpoint = cluster_info['cluster']['endpoint']

    print("eks cluster endpoint=    " + endpoint)

    #generate kubeconfig
    kube_cfg_content = dict()

    kube_cfg_content['apiVersion'] = 'v1'
    kube_cfg_content['clusters'] = [
        {
            'cluster':
                {
                    'server': endpoint,
                    'certificate-authority-data': certificate
                },
            'name':'kubernetes'

        }]

    kube_cfg_content['contexts'] = [
        {
            'context':
                {
                    'cluster':'kubernetes',
                    'user':'aws'
                },
            'name':'aws'
        }]

    kube_cfg_content['current-context'] = 'aws'
    kube_cfg_content['Kind'] = 'config'
    kube_cfg_content['users'] = [
        {
            'name':'aws',
            'user':{'name': 'lambda'}
        }]
#    {'name': 'lambda'}

    # 'user' value in 'users' content above should be key value {'name': 'lambda'} for k8s client version > 9. for version 9, just have {'user': 'lambda'}
    print("############")
    print("kube config content:    " + str(kube_cfg_content))

    #Write to kubeconfig file
    try:
        with open(KUBE_FILEPATH, 'w') as outfile:
            yaml.dump(kube_cfg_content, outfile, default_flow_style=False)
    except OSError as err:
        print("OS error: {0}".format(err))
    except:
        print("Unexpected error:", sys.exc_info()[0])


def construct_configmap_object():
    cfg_metadata = client.V1ObjectMeta( name="aws-auth",namespace="kube-system")

    #{
    #    'mapRoles': '- rolearn: arn:aws:iam::810309775316:role/Ec2SpotEKS-NodeInstanceRole\n  username: system:node:{{EC2PrivateDNSName}}\n  groups:\n    - system:bootstrappers\n    - system:nodes\n\n- rolearn: arn:aws:iam::423718654226:role/TeamRole\n  username: TeamRole\n  groups:\n  - system:masters\n',
    #    'mapUsers': '- userarn: arn:aws:iam::810309775316:user/sukumar-test\n  username: sukumar-test\n  groups:\n    - system:masters\n'
    #}

    #prepare role arn
    #arn:aws:iam::<account_id>:role/EKS-NodeInstanceRole
    node_role_arn = 'arn:aws:iam::' + ACCOUNT_ID + ':role/' + CLUSTER_ROLE_NAME
    map_role_txt = '- rolearn: ' + node_role_arn + '\n  username: system:node:{{EC2PrivateDNSName}}\n  groups:\n    - system:bootstrappers\n    - system:nodes\n'

    if MAP_ROLE_NAME != '':
        # arn:aws:iam::<account_id>:role/TeamRole
        iam_role_arn = 'arn:aws:iam::' + ACCOUNT_ID + ':role/' + MAP_ROLE_NAME
        map_role_txt = map_role_txt + '- rolearn: ' + iam_role_arn + '\n  username: ' + MAP_ROLE_NAME + '\n  groups:\n  - system:masters\n'

    #prepare user arn
    user_arn = ''
    if MAP_USER_NAME != '':
        #arn:aws:iam::<account_id>:user/sukumar-test
        user_arn = 'arn:aws:iam::' + ACCOUNT_ID + ':user/' + MAP_USER_NAME

    if user_arn != '':
        map_user_txt = '- userarn: ' + user_arn +'\n  username: ' + MAP_USER_NAME + '\n  groups:\n    - system:masters\n'

    # cfg_data= {
    #     'mapRoles': map_role_txt
    # }

    cfg_data= {
        'mapRoles': map_role_txt,
        'mapUsers': map_user_txt
    }

    print("**Config data:\n\n")
    print(cfg_data)
    print("Config data**\n\n")

    #TODO. add IAM group, once support is added in EKS. refer enhancement request in container roadmap.

    configmap = client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=cfg_metadata,
        data=cfg_data
    )
    return configmap

def apply_configmap(client_api_instance, configmap):
    try:
        api_response = client_api_instance.create_namespaced_config_map(
            namespace="kube-system",
            body=configmap,
            pretty = 'pretty_example',
        )
        pprint(api_response)

    except ApiException as e:
        print("Exception when calling CoreV1Api->create_namespaced_config_map: %s\n" % e)


def apply_aws_auth_config_map():
    #logging.basicConfig(level=logging.ERROR)
    token = get_token()
    print("token:   "+token)

    create_kube_config_file_for_eks()

    #k8s client call with api token to update aws-auth configmap
    config.load_kube_config(KUBE_FILEPATH)
    configuration = client.Configuration()
    configuration.api_key_prefix['authorization'] = 'Bearer'
    configuration.api_key['authorization'] = token

    api = client.ApiClient(configuration)
    v1 = client.CoreV1Api(api)

    print("accessing k8s api through client:   ")
    # Get all the pods
    res = v1.list_namespaced_pod("kube-system")
    print("type ={}".format(type(res)))
    #pprint(res)
    
    for key in res.keys():
        print(key)    
    podsList = res['items']
    num_pods = len(podsList)
    

    
    print("num_pods={}".format(num_pods))
    for pod in podsList:
        name = pod['metadata']['name']
        print("name={}".format(name))
        
    
    

    #list existing config maps in kube-system namespace
    config_map_read = v1.list_namespaced_config_map(namespace="kube-system")
    #print("get config map:" + str(config_map_read))

    #configmapObj = construct_configmap_object()
    print("***************")
    #print("configMap:" + str(configmapObj))
    #apply_configmap(v1, configmapObj)
    print("...config map created...")


def lambda_handler(event, context):
    apply_aws_auth_config_map()
    return "success"

#standalone test. comment when creating lambda package


def main():
    apply_aws_auth_config_map()

if __name__ == "__main__":
    main()



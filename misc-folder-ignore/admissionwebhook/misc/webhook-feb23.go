package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	//	"time"

	"github.com/ghodss/yaml"
	"github.com/golang/glog"
	"k8s.io/api/admission/v1beta1"
	//	admissionregistrationv1beta1 "k8s.io/api/admissionregistration/v1beta1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/serializer"
	//"k8s.io/kubernetes/pkg/apis/core/v1"
	//"k8s.io/client-go/pkg/api/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

var (
	runtimeScheme = runtime.NewScheme()
	codecs        = serializer.NewCodecFactory(runtimeScheme)
	deserializer  = codecs.UniversalDeserializer()

	// (https://github.com/kubernetes/kubernetes/issues/57982)
	defaulter = runtime.ObjectDefaulter(runtimeScheme)
)

var (
	config, err1    = rest.InClusterConfig()
	clientset, err2 = kubernetes.NewForConfig(config)
	api             = clientset.CoreV1()
)

var ignoredNamespaces = []string{
	metav1.NamespaceSystem,
	metav1.NamespacePublic,
}

const (
	admissionWebhookAnnotationInjectKey = "sidecar-injector-webhook.morven.me/inject"
	admissionWebhookAnnotationStatusKey = "sidecar-injector-webhook.morven.me/status"
)

type WebhookServer struct {
	sync.Mutex
	sidecarConfig *Config
	server        *http.Server
}

// Webhook Server parameters
type WhSvrParameters struct {
	port           int    // webhook server port
	certFile       string // path to the x509 certificate for https
	keyFile        string // path to the x509 private key matching `CertFile`
	sidecarCfgFile string // path to sidecar injector configuration file
}

type Config struct {
	Containers []corev1.Container `yaml:"containers"`
	Volumes    []corev1.Volume    `yaml:"volumes"`
}

type patchOperation struct {
	Op    string      `json:"op"`
	Path  string      `json:"path"`
	Value interface{} `json:"value,omitempty"`
}

/*
func init() {
	_ = corev1.AddToScheme(runtimeScheme)
	_ = admissionregistrationv1beta1.AddToScheme(runtimeScheme)
	// defaulting with webhooks:
	// https://github.com/kubernetes/kubernetes/issues/57982
	_ = v1.AddToScheme(runtimeScheme)
}
*/
// (https://github.com/kubernetes/kubernetes/issues/57982)
/*
func applyDefaultsWorkaround(containers []corev1.Container, volumes []corev1.Volume) {
	defaulter.Default(&corev1.Pod{
		Spec: corev1.PodSpec{
			Containers: containers,
			Volumes:    volumes,
		},
	})
}

*/

var (
	serviceInstance = 1
)

func loadConfig(configFile string) (*Config, error) {
	data, err := ioutil.ReadFile(configFile)
	if err != nil {
		return nil, err
	}
	glog.Infof("New configuration: sha256sum %x", sha256.Sum256(data))

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}

	return &cfg, nil
}

// Check whether the target resoured need to be mutated
func mutationRequired(ignoredList []string, metadata *metav1.ObjectMeta) bool {
	// skip special kubernete system namespaces
	for _, namespace := range ignoredList {
		if metadata.Namespace == namespace {
			glog.Infof("Skip mutation for %v for it's in special namespace:%v", metadata.Name, metadata.Namespace)
			return false
		}
	}

	annotations := metadata.GetAnnotations()
	if annotations == nil {
		annotations = map[string]string{}
	}

	status := annotations[admissionWebhookAnnotationStatusKey]

	// determine whether to perform mutation based on annotation for the target resource
	var required bool
	if strings.ToLower(status) == "injected" {
		required = false
	} else {
		switch strings.ToLower(annotations[admissionWebhookAnnotationInjectKey]) {
		default:
			required = false
		case "y", "yes", "true", "on":
			required = true
		}
	}

	glog.Infof("Mutation policy for %v/%v: status: %q required:%v", metadata.Namespace, metadata.Name, status, required)
	return required
}

func addContainer(target, added []corev1.Container, basePath string) (patch []patchOperation) {
	first := len(target) == 0
	var value interface{}
	for _, add := range added {
		value = add
		path := basePath
		if first {
			first = false
			value = []corev1.Container{add}
		} else {
			path = path + "/-"
		}
		patch = append(patch, patchOperation{
			Op:    "add",
			Path:  path,
			Value: value,
		})
	}
	return patch
}

func addVolume(target, added []corev1.Volume, basePath string) (patch []patchOperation) {
	first := len(target) == 0
	var value interface{}
	for _, add := range added {
		value = add
		path := basePath
		if first {
			first = false
			value = []corev1.Volume{add}
		} else {
			path = path + "/-"
		}
		patch = append(patch, patchOperation{
			Op:    "add",
			Path:  path,
			Value: value,
		})
	}
	return patch
}

func updateNodeSelectors(target map[string]string, added map[string]string, basePath string) (patch []patchOperation) {
	for key, value := range added {
		if target == nil || target[key] == "" {
			target = map[string]string{}
			patch = append(patch, patchOperation{
				Op:   "add",
				Path: basePath,
				Value: map[string]string{
					key: value,
				},
			})
		} else {
			patch = append(patch, patchOperation{
				Op:   "add",
				Path: basePath,
				Value: map[string]string{
					key: value,
				},
			})
		}
	}
	return patch
}

func updateAnnotation(target map[string]string, added map[string]string) (patch []patchOperation) {
	for key, value := range added {
		if target == nil || target[key] == "" {
			target = map[string]string{}
			patch = append(patch, patchOperation{
				Op:   "add",
				Path: "/metadata/annotations",
				Value: map[string]string{
					key: value,
				},
			})
		} else {
			patch = append(patch, patchOperation{
				Op:    "replace",
				Path:  "/metadata/annotations/" + key,
				Value: value,
			})
		}
	}
	return patch
}

// create mutation patch for resoures
//func createPatch(pod *corev1.Pod, sidecarConfig *Config, annotations map[string]string) ([]byte, error) {
func createPatch(pod *corev1.Pod, sidecarConfig *Config, nodeselectors map[string]string) ([]byte, error) {
	var patch []patchOperation

	//patch = append(patch, addContainer(pod.Spec.Containers, sidecarConfig.Containers, "/spec/containers")...)
	//patch = append(patch, addVolume(pod.Spec.Volumes, sidecarConfig.Volumes, "/spec/volumes")...)
	//patch = append(patch, updateAnnotation(pod.Annotations, annotations)...)
	patch = append(patch, updateNodeSelectors(pod.Spec.NodeSelector, nodeselectors, "/spec/nodeSelector")...)

	return json.Marshal(patch)
}

// main mutation process
func (whsvr *WebhookServer) mutate(ar *v1beta1.AdmissionReview, serviceInstanceNum int) *v1beta1.AdmissionResponse {
	req := ar.Request
	var pod corev1.Pod
	if err := json.Unmarshal(req.Object.Raw, &pod); err != nil {
		glog.Errorf("Could not unmarshal raw object: %v", err)
		return &v1beta1.AdmissionResponse{
			Result: &metav1.Status{
				Message: err.Error(),
			},
		}
	}

	//glog.Infof("mutate: req=%v\n", req)
	//glog.Infof("mutate: pod=%v\n", pod)
	glog.Infof("serviceInstanceNum=%d AdmissionReview for Namespace=%v UID=%v patchOperation=%v",
		serviceInstanceNum, req.Kind, req.Namespace, req.UID, req.Operation)
	//glog.Infof("AdmissionReview for Kind=%v, Namespace=%v Name=%v (%v) UID=%v patchOperation=%v UserInfo=%v",
	//	req.Kind, req.Namespace, req.Name, pod.Name, req.UID, req.Operation, req.UserInfo)

	//glog.Infof("mutate Pod Kind=%v, GenerateName=%v Namespace=%v Labels=%v Annotations=%v Spec=%v Status=%v",

	//pod.Kind, pod.GenerateName, pod.Namespace, pod.Labels, pod.Annotations, pod.Spec, pod.Status)

	// determine whether to perform mutation
	if !mutationRequired(ignoredNamespaces, &pod.ObjectMeta) {
		glog.Infof("serviceInstanceNum=%d Skipping mutation for %s/%s due to policy check", serviceInstanceNum, pod.Namespace, pod.Name)
		return &v1beta1.AdmissionResponse{
			Allowed: true,
		}
	}

	// Workaround: https://github.com/kubernetes/kubernetes/issues/57982
	//applyDefaultsWorkaround(whsvr.sidecarConfig.Containers, whsvr.sidecarConfig.Volumes)
	//annotations := map[string]string{admissionWebhookAnnotationStatusKey: "injected"}
	//nodeselectors := map[string]string{"eks.amazonaws.com/capacityType": "SPOT"}
	nodeselectors, ok := GetNodeLabel(req.Namespace, pod.GenerateName, pod.Labels["pod-template-hash"], serviceInstanceNum)
	if !ok {
		glog.Infof("serviceInstanceNum=%d Skipping mutation for %s/%s due to GetNodeLabel failure", serviceInstanceNum, pod.Namespace, pod.Name)
		return &v1beta1.AdmissionResponse{
			Allowed: true,
		}
	}

	patchBytes, err := createPatch(&pod, whsvr.sidecarConfig, nodeselectors)
	if err != nil {
		return &v1beta1.AdmissionResponse{
			Result: &metav1.Status{
				Message: err.Error(),
			},
		}
	}

	glog.Infof("serviceInstanceNum=%d AdmissionResponse: patch=%v\n", serviceInstanceNum, string(patchBytes))
	return &v1beta1.AdmissionResponse{
		Allowed: true,
		Patch:   patchBytes,
		PatchType: func() *v1beta1.PatchType {
			pt := v1beta1.PatchTypeJSONPatch
			return &pt
		}(),
	}
}

// Serve method for webhook server
func (whsvr *WebhookServer) serve(w http.ResponseWriter, r *http.Request) {

	glog.Infof("serve: serviceInstance=%d", serviceInstance)
	whsvr.Lock()
	defer whsvr.Unlock()
	//glog.Infof("serve: blocking on the channel")
	//<-done

	serviceInstanceNum := serviceInstance
	serviceInstance++

	var body []byte
	if r.Body != nil {
		if data, err := ioutil.ReadAll(r.Body); err == nil {
			body = data
		}
	}

	//glog.Infof("serve: r=%v\n", r.Body)
	//glog.Infof("serve: w=%v\n", string(w))

	if len(body) == 0 {
		glog.Error("empty body")
		http.Error(w, "empty body", http.StatusBadRequest)
		return
	}

	// verify the content type is accurate
	contentType := r.Header.Get("Content-Type")
	if contentType != "application/json" {
		glog.Errorf("Content-Type=%s, expect application/json", contentType)
		http.Error(w, "invalid Content-Type, expect `application/json`", http.StatusUnsupportedMediaType)
		return
	}

	var admissionResponse *v1beta1.AdmissionResponse
	ar := v1beta1.AdmissionReview{}
	if _, _, err := deserializer.Decode(body, nil, &ar); err != nil {
		glog.Errorf("Can't decode body: %v", err)
		admissionResponse = &v1beta1.AdmissionResponse{
			Result: &metav1.Status{
				Message: err.Error(),
			},
		}
	} else {
		admissionResponse = whsvr.mutate(&ar, serviceInstanceNum)
	}

	admissionReview := v1beta1.AdmissionReview{}
	if admissionResponse != nil {
		admissionReview.Response = admissionResponse
		if ar.Request != nil {
			admissionReview.Response.UID = ar.Request.UID
		}
	}

	resp, err := json.Marshal(admissionReview)
	if err != nil {
		glog.Errorf("Can't encode response: %v", err)
		http.Error(w, fmt.Sprintf("could not encode response: %v", err), http.StatusInternalServerError)
	}

	//glog.Infof("serve: resp=%v\n", string(resp))
	//	glog.Infof("Sleepig for 15 Seconds before write reponse ...")
	//	time.Sleep(15 * time.Second)
	//glog.Infof("After Sleep: Ready to write reponse ...")
	glog.Infof("Ready to write reponse ...")
	if _, err := w.Write(resp); err != nil {
		glog.Errorf("Can't write response: %v", err)
		http.Error(w, fmt.Sprintf("could not write response: %v", err), http.StatusInternalServerError)
	}

	//glog.Infof("serve: setting true to channel")
	//done <- true

}

func GetNodeLabel(nameSpace string, podGenerateName string, podTemplateHash string, serviceInstanceNum int) (map[string]string, bool) {

	if err1 != nil {
		panic(err1.Error())
	}
	if err2 != nil {
		panic(err2.Error())
	}

	var numOfReplicas int

	result := false
	nodeselectors := make(map[string]string)
	deploymentAnnotations := map[string]string{}

	glog.Infof("serviceInstanceNum=%d GetNodeLabel  nameSpace=%v podGenerateName=%v podTemplateHash=%v", serviceInstanceNum, nameSpace, podGenerateName, podTemplateHash)

	podNameSplitList := strings.Split(podGenerateName, podTemplateHash)
	fmt.Println("")
	deploymentName := strings.Trim(podNameSplitList[0], "-")
	//glog.Infof("deploymentName = %s\n", deploymentName)
	deploymentsClient := clientset.AppsV1().Deployments(nameSpace)
	deploymentData, getErr := deploymentsClient.Get(context.TODO(), deploymentName, metav1.GetOptions{})
	if getErr != nil {
		panic(fmt.Errorf("Failed to get latest version of Deployment: %v", getErr))
	}
	//fmt.Println("deploymentData=", deploymentData)
	deploymentAnnotations = deploymentData.Annotations
	//fmt.Println("deploymentAnnotations=", deploymentAnnotations)

	if IsCustomSchedulingDefined, ok := deploymentAnnotations["UseCustomKubeScheduler"]; ok && IsCustomSchedulingDefined == "true" {
		strategy := deploymentAnnotations["CustomPodScheduleStrategy"]
		numOfReplicas = int(*deploymentData.Spec.Replicas)
		glog.Infof("serviceInstanceNum=%d Found a deployment %s with total replicas %d and strategy=%s", serviceInstanceNum, deploymentName, numOfReplicas, strategy)
		//glog.Infof("\nnumOfReplicas=%d\n", numOfReplicas)
		if customSchedulingStrategyMap, ok := GetPodsCustomSchedulingStrategyMap(strategy, numOfReplicas, serviceInstanceNum); ok {
			glog.Infof("serviceInstanceNum=%d customSchedulingStrategyMap=%v", serviceInstanceNum, customSchedulingStrategyMap)
			for nodeLabel, replicas := range customSchedulingStrategyMap {
				glog.Infof("serviceInstanceNum=%d nodeLabel=%s needs %d replicas\n", serviceInstanceNum, nodeLabel, replicas)
				if numOfExistingPods, result := GetNumOfExistingPods(nameSpace, podGenerateName, nodeLabel, serviceInstanceNum); result {
					glog.Infof("serviceInstanceNum=%d nodeLabel=%s currently runs %d pods", serviceInstanceNum, nodeLabel, numOfExistingPods)
					if numOfExistingPods < replicas {
						glog.Infof("serviceInstanceNum=%d Currently running %d pods is less than expected %d, scheduling pod %s on nodeLabel %s", serviceInstanceNum, numOfExistingPods, replicas, podGenerateName, nodeLabel)
						nodeLabelSplit := strings.Split(nodeLabel, "=")
						//glog.Infof("nodeLabelSplit=%v\n", nodeLabelSplit)
						nodeselectors[nodeLabelSplit[0]] = nodeLabelSplit[1]
						result = true
						return nodeselectors, result
					} else if numOfExistingPods == replicas {
						glog.Infof("serviceInstanceNum=%d Currently running %d pods is SAME as expected %d, ignoring the nodeLabel %s", serviceInstanceNum, numOfExistingPods, replicas, nodeLabel)
					} else {
						glog.Infof("serviceInstanceNum=%d Currently running %d pods is more than expected %d, NEED to delete few pods with nodeLabel %s", serviceInstanceNum, numOfExistingPods, replicas, nodeLabel)
					}

				} else {
					glog.Infof("serviceInstanceNum=%d GetNumOfExistingPods failed. Ignoring Custom scheduling for nodeLabel=%s", serviceInstanceNum, nodeLabel)
				}
			}
		} else {
			glog.Infof("serviceInstanceNum=%d Looks like Strategy declaration is wrong. Ignoring the custom scheduling. Pls fix and re-try", serviceInstanceNum)
		}
	}

	return nodeselectors, result
}

func GetPodsCustomSchedulingStrategyMap(Strategy string, numOfReplicas int, serviceInstanceNum int) (map[string]int, bool) {

	//DEBUG_ENABLED := false
	DEBUG_ENABLED := true

	result := true

	if DEBUG_ENABLED {
		glog.Infof("serviceInstanceNum=%d Strategy=%s numOfReplicas=%d\n", serviceInstanceNum, Strategy, numOfReplicas)
	}

	//podScheduleStrategy := CustomPodScheduleStrategy{}

	nodeLabelToReplicas := make(map[string]int)
	nodeLabelToWights := make(map[string]int)
	totalWeight := 0
	replicaCount := 0

	StrategyList := strings.Split(Strategy, ":")

	if DEBUG_ENABLED {
		fmt.Println("StrategyList=", StrategyList)
	}

	numOfBaseValues := 0

	baseNodeLabel := ""

	for _, nodeStrategy := range StrategyList {

		if DEBUG_ENABLED {
			fmt.Println("nodeStrategy: ", nodeStrategy)
		}

		nodeStrategyPartsList := strings.Split(nodeStrategy, ",")

		if DEBUG_ENABLED {
			fmt.Println("nodeStrategyPartsList: ", nodeStrategyPartsList)
			fmt.Println("nodeStrategyPartsList len: ", len(nodeStrategyPartsList))
		}

		base := 0
		weight := 0
		nodeLabel := ""
		var err error

		for _, nodeStrategyPart := range nodeStrategyPartsList {

			nodeStrategySubPartList := strings.Split(nodeStrategyPart, "=")
			if DEBUG_ENABLED {
				fmt.Println("nodeStrategyPart: ", nodeStrategyPart)
				fmt.Println("nodeStrategySubPartList: ", nodeStrategySubPartList)
				fmt.Println("nodeStrategySubPartList len: ", len(nodeStrategySubPartList))
			}

			if nodeStrategySubPartList[0] == "base" {

				if numOfBaseValues != 0 {
					fmt.Println("base value cannot be non-zero for more than node strategy")
					result = false
					//exit(1)
				} else {
					numOfBaseValues += 1
				}

				base, err = strconv.Atoi(nodeStrategySubPartList[1])
				if err != nil {
					// handle error
					fmt.Println(err)
					os.Exit(2)
				}

				if base > numOfReplicas {
					base = numOfReplicas
				}

				//replicaCount = base
				numOfReplicas = numOfReplicas - base

				if DEBUG_ENABLED {
					fmt.Println("base=", base)
				}

			} else if nodeStrategySubPartList[0] == "weight" {

				weight, err = strconv.Atoi(nodeStrategySubPartList[1])
				if err != nil {
					// handle error
					fmt.Println(err)
					os.Exit(2)
				}
				totalWeight += weight

				if DEBUG_ENABLED {
					fmt.Println("weight=", weight)
				}

			} else {
				nodeLabel = nodeStrategyPart
				if DEBUG_ENABLED {
					glog.Infof("label key=%s value=%s\n", nodeStrategySubPartList[0], nodeStrategySubPartList[1])
				}
			}
		}

		if numOfBaseValues == 1 {
			if baseNodeLabel == "" {
				baseNodeLabel = nodeLabel
			}
		}

		nodeLabelToWights[nodeLabel] = weight
		//podScheduleStrategy = append(podScheduleStrategy, )
		nodeLabelToReplicas[nodeLabel] = base

	}

	if DEBUG_ENABLED {
		glog.Infof("nodeLabelToReplicas=%v \n", nodeLabelToReplicas)
		glog.Infof("nodeLabelToWights=%v\n", nodeLabelToWights)
		glog.Infof("numOfBaseValues = %v totalWeight=%v  replicaCount=%v numOfReplicas=%v \n", numOfBaseValues, totalWeight, replicaCount, numOfReplicas)
		//glog.Infof("podScheduleStrategy = %v", podScheduleStrategy)
	}

	if numOfReplicas > 0 {
		weight := nodeLabelToWights[baseNodeLabel]
		baseReplicas := nodeLabelToReplicas[baseNodeLabel]
		weightReplicas := int(numOfReplicas * weight / totalWeight)
		baseReplicas = baseReplicas + weightReplicas
		replicaCount = weightReplicas
		nodeLabelToReplicas[baseNodeLabel] = baseReplicas
		//numOfReplicas = numOfReplicas - weightReplicas

		glog.Infof("baseNodeLabel=%s baseReplicas = %v replicaCount=%v numOfReplicas=%v \n", baseNodeLabel, baseReplicas, replicaCount, numOfReplicas)

		totalNumOfLables := len(nodeLabelToReplicas)
		labelNum := 1
		//weightReplicas := 0

		for key, replicas := range nodeLabelToReplicas {

			if key != baseNodeLabel {
				weight = nodeLabelToWights[key]
				if DEBUG_ENABLED {
					glog.Infof("labelNum=%v key: %v replicas=%v weight=%v, totalWeight=%v replicaCount=%v numOfReplicas=%v\n", labelNum, key, replicas, weight, totalWeight, replicaCount, numOfReplicas)
				}
				if labelNum == totalNumOfLables-1 {
					weightReplicas = numOfReplicas - replicaCount
				} else {
					//weightReplicas = math.RoundToEven(numOfReplicas * (weight / totalWeight))
					weightReplicas = int(numOfReplicas * weight / totalWeight)
				}

				replicas = replicas + weightReplicas
				replicaCount = replicaCount + weightReplicas
				nodeLabelToReplicas[key] = replicas

				//numOfReplicas -= weightReplicas
				if DEBUG_ENABLED {
					glog.Infof("labelNum=%v weightReplicas: %v replicas=%v,  replicaCount=%v, numOfReplicas=%v\n", labelNum, weightReplicas, replicas, replicaCount, numOfReplicas)
				}

				labelNum += 1
			}

		}

		if DEBUG_ENABLED {
			glog.Infof("nodeLabelToReplicas = %v\n", nodeLabelToReplicas)
			glog.Infof("numOfBaseValues = %v totalWeight=%v numOfReplicas=%v replicaCount=%v\n", numOfBaseValues, totalWeight, numOfReplicas, replicaCount)
		}

	}

	return nodeLabelToReplicas, result
}

func GetNumOfExistingPods(namespace string, podGenerateName string, nodeLabel string, serviceInstanceNum int) (int, bool) {
	result := true
	numOfExistingPods := 0

	glog.Infof("serviceInstanceNum=%d GetNumOfExistingPods namespace=%v podGenerateName=%v nodeLabel=%v\n", serviceInstanceNum, namespace, podGenerateName, nodeLabel)
	nodeLabelSplit := strings.Split(nodeLabel, "=")
	//glog.Infof("GetNumOfExistingPods nodeLabelSplit=%v\n", nodeLabelSplit)

	listOptions := metav1.ListOptions{}

	pods, err := api.Pods(namespace).List(context.Background(), listOptions)
	if err != nil {
		result = false
		log.Fatalln("failed to get pods:", err)
	}

	for i, pod := range pods.Items {

		if pod.GenerateName == podGenerateName {

			nodeSelectorMap := pod.Spec.NodeSelector
			glog.Infof("serviceInstanceNum=%d Existing pod i=%d Name=%v nodeSelectorMap=%v \n", serviceInstanceNum, i+1, pod.Name, nodeSelectorMap)
			for nodeLabelKey, nodeLabelValue := range nodeSelectorMap {
				if nodeLabelKey == nodeLabelSplit[0] && nodeLabelValue == nodeLabelSplit[1] {
					numOfExistingPods += 1
				}
			}

		}

	}

	return numOfExistingPods, result
}

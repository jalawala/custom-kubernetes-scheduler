package main

import (
	"context"
	"crypto/tls"
	"flag"
	"fmt"
	"github.com/golang/glog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
)

var (
	AppLogLevel              string
	BlockedNameSpaceList     []string
	ReconcilerIntervalPeriod int
)

/*
var (
	done chan bool
)
*/

func main() {
	var parameters WhSvrParameters

	// get command line parameters
	flag.IntVar(&parameters.port, "port", 8443, "Webhook server port.")
	flag.StringVar(&parameters.certFile, "tlsCertFile", "/etc/webhook/certs/cert.pem", "File containing the x509 Certificate for HTTPS.")
	flag.StringVar(&parameters.keyFile, "tlsKeyFile", "/etc/webhook/certs/key.pem", "File containing the x509 private key to --tlsCertFile.")
	flag.Parse()

	AppLogLevel = os.Getenv("LOG_LEVEL")
	ReconcilerIntervalPeriod, err := strconv.Atoi(os.Getenv("RECONCILER_PERIOD"))

	if err == nil {
		ReconcilerIntervalPeriod = 5
	}

	BlockedNameSpaceList = strings.Split(os.Getenv("BLOCKLISTED_NAMESPACE_LIST"), ",")

	glog.Infof("AppLogLevel=%s BlockedNameSpaceList=%v ReconcilerIntervalPeriod=%d", AppLogLevel, BlockedNameSpaceList, ReconcilerIntervalPeriod)

	pair, err := tls.LoadX509KeyPair(parameters.certFile, parameters.keyFile)
	if err != nil {
		glog.Errorf("Failed to load key pair: %v", err)
	}

	whsvr := &WebhookServer{

		server: &http.Server{
			Addr:      fmt.Sprintf(":%v", parameters.port),
			TLSConfig: &tls.Config{Certificates: []tls.Certificate{pair}},
		},
	}

	// define http server and server handler
	mux := http.NewServeMux()
	mux.HandleFunc("/mutate", whsvr.serve)
	whsvr.server.Handler = mux

	// start webhook server in new rountine
	go func() {

		if err := whsvr.server.ListenAndServeTLS("", ""); err != nil {
			glog.Errorf("Failed to listen and serve webhook server: %v", err)
		}
	}()

	go func() {
		RunBatchJobForPodsCleanup()
	}()

	// listening OS shutdown singal
	signalChan := make(chan os.Signal, 1)
	signal.Notify(signalChan, syscall.SIGINT, syscall.SIGTERM)
	<-signalChan

	glog.Infof("Got OS shutdown signal, shutting down webhook server gracefully...")
	whsvr.server.Shutdown(context.Background())
}

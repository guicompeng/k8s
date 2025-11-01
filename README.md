# k8s

## Pré-requisitos
- Ubuntu 24

### Instalar o multipass (ferramenta para gerenciar VMs)
```bash
$ sudo snap install multipass
```

### Instalar o kubectl (CLI para acessar o cluster Kubernetes)
```bash
$ snap install kubectl --classic
```

### Instalar o cluster Kubernetes (K8s)
```bash
$ chmod +x setup-k8s.sh
$ ./setup-k8s.sh
$ export KUBECONFIG=\$PWD/kubeconfig
```


### Instalar ArgoCD (Ferramenta GitOps - instala serviços no kubernetes pelo git)
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### Instalar todas as aplicações do cluster (Wordpress, Prometheus, K6)
```bash
kubectl apply -f https://raw.githubusercontent.com/guicompeng/k8s/main/root-app.yaml -n argocd
```

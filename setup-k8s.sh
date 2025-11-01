#!/bin/bash
set -e

# ================================
# Multipass + MicroK8s Cluster Setup
# ================================

# Configurações
NODES=("node1" "node2" "node3")
MEM="4G"
DISK="15G"

echo "Criando VMs com Multipass..."
for NODE in "${NODES[@]}"; do
  echo "Criando $NODE..."
  multipass launch --name "$NODE" --mem "$MEM"
done

echo "Todas as VMs criadas:"
multipass list

echo "Instalando MicroK8s no nó principal (node1)..."
multipass exec node1 -- bash -c "sudo snap install microk8s --classic"
multipass exec node1 -- bash -c "sudo usermod -aG microk8s ubuntu"
multipass exec node1 -- bash -c "sudo microk8s status --wait-ready"

echo "Gerando token de join..."
JOIN_CMD=$(multipass exec node1 -- microk8s add-node | grep 'microk8s join' | head -n 1)

echo "Instalando MicroK8s e unindo nós secundários..."
for NODE in "${NODES[@]:1}"; do
  echo "Configurando $NODE..."
  multipass exec "$NODE" -- bash -c "sudo snap install microk8s --classic"
  multipass exec "$NODE" -- bash -c "sudo usermod -aG microk8s ubuntu"
  multipass exec "$NODE" -- bash -c "$JOIN_CMD"
done

echo "Ativando add-ons úteis no cluster..."
multipass exec node1 -- bash -c "sudo microk8s enable dns storage ingress metrics-server dashboard"

echo "Aguardando o cluster ficar pronto..."
sleep 30
multipass exec node1 -- bash -c "sudo microk8s kubectl get nodes"

echo "Extraindo kubeconfig para o host..."
multipass exec node1 -- microk8s config > kubeconfig
echo "Arquivo 'kubeconfig' gerado. Use:"
echo "    export KUBECONFIG=\$PWD/kubeconfig"
echo "    kubectl get nodes"

echo "Cluster Kubernetes completo instalado!"


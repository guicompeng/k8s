import requests
import csv
import datetime
from datetime import timedelta

# Configurações
prometheus_url = "http://10.187.36.245:30082/api/v1/query_range"
metricas = [
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_load1",
    "node_network_receive_bytes_total"
]

# Intervalo desejado (pode ser grande)
params_base = {
    "start": "2025-10-10T00:00:00Z",
    "end": "2025-10-26T18:00:00Z",
    "step": "15s"
}

# Tamanho máximo de cada fatia (em horas)
FATIA_HORAS = 2  # ajuste conforme necessidade (2h = seguro p/ 15s step)

def iso_to_datetime(iso_str):
    return datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

def datetime_to_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

start_dt = iso_to_datetime(params_base["start"])
end_dt = iso_to_datetime(params_base["end"])

dados_metricas = {m: {} for m in metricas}

# Quebrar em fatias e buscar cada uma
fatias = []
t = start_dt
while t < end_dt:
    t_fim = min(t + timedelta(hours=FATIA_HORAS), end_dt)
    fatias.append((t, t_fim))
    t = t_fim

print(f"📆 Consultando em {len(fatias)} fatias de {FATIA_HORAS}h...")

for metrica in metricas:
    print(f"🔍 Baixando {metrica}...")
    for (inicio, fim) in fatias:
        params = {
            "query": metrica,
            "start": datetime_to_iso(inicio),
            "end": datetime_to_iso(fim),
            "step": params_base["step"]
        }
        resp = requests.get(prometheus_url, params=params).json()

        if resp.get("status") != "success" or not resp["data"]["result"]:
            print(f"⚠️ Erro ou sem dados: {metrica} ({inicio} -> {fim})")
            continue

        # Pode haver várias séries; use a primeira ou combine se quiser
        for serie in resp["data"]["result"]:
            for ts, val in serie["values"]:
                dados_metricas[metrica][float(ts)] = float(val)

# Construir tabela combinada
todos_tempos = sorted(set().union(*[d.keys() for d in dados_metricas.values()]))
csv_file = "dados_prometheus.csv"

with open(csv_file, "w", newline="") as f:
    writer = csv.writer(f, delimiter=';')
    header = ["tempo"] + metricas
    writer.writerow(header)

    for t in todos_tempos:
        linha = [datetime.datetime.utcfromtimestamp(t).isoformat()]
        for m in metricas:
            linha.append(dados_metricas[m].get(t, ""))
        writer.writerow(linha)

print(f"✅ Exportado para {csv_file}")

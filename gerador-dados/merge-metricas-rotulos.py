#!/usr/bin/env python3

import argparse
from pathlib import Path

import pandas as pd


def build_dataset(
	metrics_path: Path,
	labels_path: Path,
	output_path: Path,
	round_seconds: int = 10,
) -> None:
	metrics_df = pd.read_csv(metrics_path)
	labels_df = pd.read_csv(labels_path, sep=";")

	if "timestamp" not in metrics_df.columns:
		raise ValueError("metrics.csv precisa ter a coluna 'timestamp'.")
	if "timestamp" not in labels_df.columns or "healthy" not in labels_df.columns:
		raise ValueError("rotulos.csv precisa ter as colunas 'timestamp' e 'healthy'.")

	metrics_df["timestamp"] = pd.to_datetime(metrics_df["timestamp"], utc=True, errors="coerce")
	labels_df["timestamp"] = pd.to_datetime(labels_df["timestamp"], utc=True, errors="coerce")

	metrics_df = metrics_df.dropna(subset=["timestamp"]).copy()
	labels_df = labels_df.dropna(subset=["timestamp"]).copy()

	labels_df["healthy"] = (
		labels_df["healthy"].astype(str).str.strip().str.lower().map({"true": 1, "false": 0})
	)
	labels_df = labels_df.dropna(subset=["healthy"]).copy()
	labels_df["healthy"] = labels_df["healthy"].astype(int)

	# Considera somente o periodo em que existem rotulos.
	label_start = labels_df["timestamp"].min()
	label_end = labels_df["timestamp"].max()
	metrics_df = metrics_df[(metrics_df["timestamp"] >= label_start) & (metrics_df["timestamp"] <= label_end)].copy()

	round_freq = f"{int(round_seconds)}s"
	metrics_df["timestamp_rounded"] = metrics_df["timestamp"].dt.round(round_freq)
	labels_df["timestamp_rounded"] = labels_df["timestamp"].dt.round(round_freq)

	# Mantem um unico rotulo por instante arredondado (ultimo registro observado).
	labels_df = labels_df.sort_values("timestamp").drop_duplicates(
		subset=["timestamp_rounded"], keep="last"
	)

	dataset_df = metrics_df.merge(
		labels_df[["timestamp_rounded", "healthy"]],
		on="timestamp_rounded",
		how="left",
	)

	# Fallback: se ainda faltar rotulo apos arredondamento, usa vizinho mais proximo.
	missing_mask = dataset_df["healthy"].isna()
	if missing_mask.any():
		nearest = pd.merge_asof(
			dataset_df.loc[missing_mask, ["timestamp"]].sort_values("timestamp"),
			labels_df[["timestamp", "healthy"]].sort_values("timestamp"),
			on="timestamp",
			direction="nearest",
			tolerance=pd.Timedelta(seconds=round_seconds),
		)
		dataset_df.loc[missing_mask, "healthy"] = nearest["healthy"].to_numpy()

	# Remove amostras sem rotulo para manter somente dados rotulados no dataset final.
	dataset_df = dataset_df.dropna(subset=["healthy"]).copy()
	dataset_df["healthy"] = dataset_df["healthy"].astype(int)

	dataset_df = dataset_df.drop(columns=["timestamp_rounded"])
	dataset_df = dataset_df.rename(columns={"healthy": "label"})
	dataset_df = dataset_df.sort_values("timestamp")

	dataset_df.to_csv(output_path, index=False)

	print(f"Dataset gerado em: {output_path}")
	print(f"Linhas: {len(dataset_df)}")
	print(f"Labels (0): {(dataset_df['label'] == 0).sum()}")
	print(f"Labels (1): {(dataset_df['label'] == 1).sum()}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Mescla metrics.csv e rotulos.csv em dataset.csv com alinhamento temporal arredondado."
	)
	parser.add_argument(
		"--metrics",
		default="metrics.csv",
		help="Caminho do metrics.csv (padrao: metrics.csv)",
	)
	parser.add_argument(
		"--labels",
		default="../rotulador/rotulos.csv",
		help="Caminho do rotulos.csv (padrao: ../rotulador/rotulos.csv)",
	)
	parser.add_argument(
		"--output",
		default="dataset.csv",
		help="Caminho de saida do dataset.csv (padrao: dataset.csv)",
	)
	parser.add_argument(
		"--round-seconds",
		type=int,
		default=10,
		help="Janela de arredondamento em segundos (padrao: 10)",
	)
	return parser.parse_args()


if __name__ == "__main__":
	args = parse_args()
	build_dataset(
		metrics_path=Path(args.metrics),
		labels_path=Path(args.labels),
		output_path=Path(args.output),
		round_seconds=args.round_seconds,
	)

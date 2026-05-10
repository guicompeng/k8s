from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import sys # Import sys to access sys.argv

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt # Added for plotting
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight

try:
	import tensorflow as tf
except ImportError as exc:
	raise SystemExit("TensorFlow is required. Install with: pip install tensorflow") from exc


def parse_args() -> argparse.Namespace:
	# In a Colab environment, __file__ is not defined. We'll use a direct path.
	default_data = Path("/content/dataset.csv") # Corrected path for Colab
	parser = argparse.ArgumentParser(description="Train LSTM on time-series metrics")
	parser.add_argument("--data-path", type=Path, default=default_data)
	parser.add_argument("--target-col", type=str, default="target")
	parser.add_argument("--time-col", type=str, default="timestamp")
	parser.add_argument("--seq-len", type=int, default=6)
	parser.add_argument("--stride", type=int, default=1)
	parser.add_argument("--train-ratio", type=float, default=0.7)
	parser.add_argument("--val-ratio", type=float, default=0.15)
	parser.add_argument("--test-ratio", type=float, default=0.15)
	parser.add_argument("--batch-size", type=int, default=256)
	parser.add_argument("--epochs", type=int, default=30)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--threshold", type=float, default=None)
	parser.add_argument("--output-dir", type=Path, default=Path("lstm_artifacts"))

	return parser.parse_args(args=[])


def set_seed(seed: int) -> None:
	random.seed(seed)
	np.random.seed(seed)
	tf.random.set_seed(seed)


def load_dataframe(path: Path, target_col: str, time_col: str) -> pd.DataFrame:
	df = pd.read_csv(path)
	if target_col not in df.columns:
		if "label" in df.columns:
			df = df.rename(columns={"label": target_col})
		else:
			raise ValueError(f"Target column '{target_col}' not found")

	if time_col in df.columns:
		df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
		df = df.dropna(subset=[time_col])
		df = df.sort_values(time_col)
		df = df.drop_duplicates(subset=[time_col], keep="last")
	else:
		df = df.reset_index(drop=True)

	df = df.dropna(subset=[target_col])
	df = df.reset_index(drop=True)
	return df


def split_by_time(
	df: pd.DataFrame, train_ratio: float, val_ratio: float, test_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
	total = train_ratio + val_ratio + test_ratio
	if not np.isclose(total, 1.0):
		raise ValueError("Train/val/test ratios must sum to 1.0")

	n = len(df)
	train_end = int(n * train_ratio)
	val_end = train_end + int(n * val_ratio)
	train_df = df.iloc[:train_end].copy()
	val_df = df.iloc[train_end:val_end].copy()
	test_df = df.iloc[val_end:].copy()
	return train_df, val_df, test_df


def prepare_features(
	train_df: pd.DataFrame,
	val_df: pd.DataFrame,
	test_df: pd.DataFrame,
	target_col: str,
	time_col: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, StandardScaler]:
	drop_cols = [target_col]
	if time_col in train_df.columns:
		drop_cols.append(time_col)

	feature_cols = [c for c in train_df.columns if c not in drop_cols]
	if not feature_cols:
		raise ValueError("No feature columns found")

	def to_numeric(df: pd.DataFrame) -> pd.DataFrame:
		numeric_df = df[feature_cols].apply(pd.to_numeric, errors="coerce")
		numeric_df = numeric_df.replace([np.inf, -np.inf], np.nan)
		return numeric_df

	train_x = to_numeric(train_df)
	val_x = to_numeric(val_df)
	test_x = to_numeric(test_df)

	medians = train_x.median()
	train_x = train_x.fillna(medians)
	val_x = val_x.fillna(medians)
	test_x = test_x.fillna(medians)

	scaler = StandardScaler()
	train_x = scaler.fit_transform(train_x).astype(np.float32)
	val_x = scaler.transform(val_x).astype(np.float32)
	test_x = scaler.transform(test_x).astype(np.float32)

	train_y = train_df[target_col].astype(int).to_numpy()
	val_y = val_df[target_col].astype(int).to_numpy()
	test_y = test_df[target_col].astype(int).to_numpy()

	return train_x, val_x, test_x, train_y, val_y, test_y, scaler


def window_labels(y: np.ndarray, seq_len: int, stride: int) -> np.ndarray:
	if len(y) < seq_len:
		raise ValueError("Not enough rows to build a single sequence")
	indices = np.arange(seq_len - 1, len(y), stride)
	return y[indices]


def make_windowed_dataset(
	x: np.ndarray,
	y: np.ndarray,
	seq_len: int,
	stride: int,
	batch_size: int,
	shuffle: bool,
	seed: int,
) -> tf.data.Dataset:
	ds = tf.data.Dataset.from_tensor_slices((x, y))
	ds = ds.window(seq_len, shift=stride, drop_remainder=True)
	ds = ds.flat_map(
		lambda x_win, y_win: tf.data.Dataset.zip(
			(x_win.batch(seq_len), y_win.batch(seq_len))
		)
	)
	ds = ds.map(lambda x_win, y_win: (x_win, y_win[-1]), num_parallel_calls=tf.data.AUTOTUNE)
	if shuffle:
		num_windows = 1 + (len(x) - seq_len) // stride
		buffer_size = min(num_windows, 10000)
		ds = ds.shuffle(buffer_size=buffer_size, seed=seed, reshuffle_each_iteration=True)
	ds = ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
	return ds


def build_model(seq_len: int, n_features: int) -> tf.keras.Model:
	inputs = tf.keras.Input(shape=(seq_len, n_features))
	x = tf.keras.layers.LSTM(64, return_sequences=True)(inputs)
	x = tf.keras.layers.Dropout(0.2)(x)
	x = tf.keras.layers.LSTM(32)(x)
	x = tf.keras.layers.Dropout(0.2)(x)
	x = tf.keras.layers.Dense(32, activation="relu")(x)
	x = tf.keras.layers.Dropout(0.2)(x)
	outputs = tf.keras.layers.Dense(1, activation="sigmoid")(x)
	model = tf.keras.Model(inputs, outputs)
	model.compile(
		optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
		loss="binary_crossentropy",
		metrics=[tf.keras.metrics.AUC(name="auc"), tf.keras.metrics.BinaryAccuracy(name="acc")],
	)
	return model


def find_best_threshold(y_true: np.ndarray, probs: np.ndarray) -> tuple[float, float]:
	best_f1 = -1.0
	best_t = 0.5
	for t in np.linspace(0.1, 0.9, 17):
		preds = (probs >= t).astype(int)
		score = f1_score(y_true, preds, average="macro")
		if score > best_f1:
			best_f1 = score
			best_t = float(t)
	return best_t, best_f1


def compute_metrics(y_true: np.ndarray, probs: np.ndarray, threshold: float) -> dict[str, float | None]:
	preds = (probs >= threshold).astype(int)
	metrics = {
		"accuracy": accuracy_score(y_true, preds),
		"f1_macro": f1_score(y_true, preds, average="macro"),
	}
	try:
		metrics["roc_auc"] = roc_auc_score(y_true, probs)
	except ValueError:
		metrics["roc_auc"] = None
	return metrics

def plot_training_history(history):
    history_dict = history.history
    epochs = range(1, len(history_dict['loss']) + 1)

    plt.figure(figsize=(15, 10))

    # Plot Loss
    plt.subplot(2, 2, 1)
    plt.plot(epochs, history_dict['loss'], 'bo-', label='Training loss')
    if 'val_loss' in history_dict:
        plt.plot(epochs, history_dict['val_loss'], 'ro-', label='Validation loss')
    plt.title('Training and Validation Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()

    # Plot Accuracy
    plt.subplot(2, 2, 2)
    if 'acc' in history_dict:
        plt.plot(epochs, history_dict['acc'], 'bo-', label='Training Accuracy')
    if 'val_acc' in history_dict:
        plt.plot(epochs, history_dict['val_acc'], 'ro-', label='Validation Accuracy')
    plt.title('Training and Validation Accuracy')
    plt.xlabel('Epochs')
    plt.ylabel('Accuracy')
    plt.legend()

    # Plot AUC
    plt.subplot(2, 2, 3)
    if 'auc' in history_dict:
        plt.plot(epochs, history_dict['auc'], 'bo-', label='Training AUC')
    if 'val_auc' in history_dict:
        plt.plot(epochs, history_dict['val_auc'], 'ro-', label='Validation AUC')
    plt.title('Training and Validation AUC')
    plt.xlabel('Epochs')
    plt.ylabel('AUC')
    plt.legend()

    # Plot Learning Rate
    if 'lr' in history_dict:
        plt.subplot(2, 2, 4)
        plt.plot(epochs, history_dict['lr'], 'go-', label='Learning Rate')
        plt.title('Learning Rate')
        plt.xlabel('Epochs')
        plt.ylabel('LR')
        plt.legend()

    plt.tight_layout()
    plt.show()

def main() -> None:
	args = parse_args()
	set_seed(args.seed)

	df = load_dataframe(args.data_path, args.target_col, args.time_col)
	train_df, val_df, test_df = split_by_time(df, args.train_ratio, args.val_ratio, args.test_ratio)

	(
		train_x,
		val_x,
		test_x,
		train_y,
		val_y,
		test_y,
		scaler,
	) = prepare_features(train_df, val_df, test_df, args.target_col, args.time_col)

	train_y_seq = window_labels(train_y, args.seq_len, args.stride)
	val_y_seq = window_labels(val_y, args.seq_len, args.stride)
	test_y_seq = window_labels(test_y, args.seq_len, args.stride)

	print(f"Train rows: {len(train_x)} | Train sequences: {len(train_y_seq)}")
	print(f"Val rows: {len(val_x)} | Val sequences: {len(val_y_seq)}")
	print(f"Test rows: {len(test_x)} | Test sequences: {len(test_y_seq)}")
	print(f"Features: {train_x.shape[1]}")

	classes = np.unique(train_y_seq)
	if len(classes) == 1:
		class_weights = None
		print("Warning: only one class present in training sequences")
	else:
		weights = compute_class_weight(class_weight="balanced", classes=classes, y=train_y_seq)
		class_weights = {int(cls): float(w) for cls, w in zip(classes, weights)}

	train_ds = make_windowed_dataset(
		train_x, train_y, args.seq_len, args.stride, args.batch_size, True, args.seed
	)
	val_ds = make_windowed_dataset(
		val_x, val_y, args.seq_len, args.stride, args.batch_size, False, args.seed
	)
	test_ds = make_windowed_dataset(
		test_x, test_y, args.seq_len, args.stride, args.batch_size, False, args.seed
	)

	model = build_model(args.seq_len, train_x.shape[1])
	output_dir = args.output_dir
	output_dir.mkdir(parents=True, exist_ok=True)

	callbacks = [
		tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
		tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", patience=3, factor=0.5),
		tf.keras.callbacks.ModelCheckpoint(
			filepath=output_dir / "model.keras", monitor="val_loss", save_best_only=True
		),
	]

	history = model.fit( # Capture the history object
		train_ds,
		validation_data=val_ds,
		epochs=args.epochs,
		class_weight=class_weights,
		callbacks=callbacks,
		verbose=1,
	)

	plot_training_history(history) # Call the plotting function

	val_probs = model.predict(val_ds, verbose=0).reshape(-1)
	if args.threshold is None:
		threshold, val_f1 = find_best_threshold(val_y_seq, val_probs)
		print(f"Best threshold from val: {threshold:.2f} (macro F1={val_f1:.4f})")
	else:
		threshold = args.threshold

	test_probs = model.predict(test_ds, verbose=0).reshape(-1)

	val_metrics = compute_metrics(val_y_seq, val_probs, threshold)
	test_metrics = compute_metrics(test_y_seq, test_probs, threshold)

	print(
		"Val metrics | "
		f"acc={val_metrics['accuracy']:.4f} "
		f"f1_macro={val_metrics['f1_macro']:.4f} "
		f"roc_auc={val_metrics['roc_auc']}"
	)
	print(
		"Test metrics | "
		f"acc={test_metrics['accuracy']:.4f} "
		f"f1_macro={test_metrics['f1_macro']:.4f} "
		f"roc_auc={test_metrics['roc_auc']}"
	)

	joblib.dump(scaler, output_dir / "scaler.joblib")
	metrics_path = output_dir / "metrics.json"
	with metrics_path.open("w", encoding="utf-8") as f:
		json.dump(
			{
				"threshold": threshold,
				"val": val_metrics,
				"test": test_metrics,
				"seq_len": args.seq_len,
				"stride": args.stride,
				"batch_size": args.batch_size,
				"epochs": args.epochs,
			},
			f,
			indent=2,
		)


if __name__ == "__main__":
	main()
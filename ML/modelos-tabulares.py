
!pip install catboost

import warnings
warnings.simplefilter("ignore")


import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_score, GridSearchCV
from sklearn.ensemble import VotingClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier

## Carregamento de Dados (substitua com seu dataset)


# Substitua pelo carregamento do seu dataset
df = pd.read_csv('dataset-1m-relabel.csv')

# Remova a coluna 'timestamp'
if 'timestamp' in df.columns:
    df = df.drop('timestamp', axis=1)

X = df.drop('target', axis=1).values
y = df['target'].values


# from sklearn.datasets import load_breast_cancer
# data = load_breast_cancer()
# X = data.data
# y = data.target

## Inicializando os classificadores

xgb = XGBClassifier(verbosity=0)
lgb = LGBMClassifier(verbosity=-1)
cat = CatBoostClassifier(verbose=0)

## Avaliação com Validação Cruzada Manual (10 folds)

skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)

def avaliar_modelo(modelo, X, y, nome="Modelo"):
    f1_scores = []
    for train_idx, test_idx in skf.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        modelo.fit(X_train, y_train)
        preds = modelo.predict(X_test)
        f1_scores.append(f1_score(y_test, preds))
    print(f"{nome}: F1-score médio = {np.mean(f1_scores):.4f}, desvio padrão = {np.std(f1_scores):.4f}")

## Avaliação dos Modelos Individuais

avaliar_modelo(xgb, X, y, "XGBoost")
avaliar_modelo(lgb, X, y, "LightGBM")
avaliar_modelo(cat, X, y, "CatBoost")

## VotingClassifier (Hard e Soft)


voting_hard = VotingClassifier(estimators=[('xgb', xgb), ('lgb', lgb), ('cat', cat)], voting='hard')
voting_soft = VotingClassifier(estimators=[('xgb', xgb), ('lgb', lgb), ('cat', cat)], voting='soft')

avaliar_modelo(voting_hard, X, y, "VotingClassifier (Hard)")
avaliar_modelo(voting_soft, X, y, "VotingClassifier (Soft)")


## StackingClassifier


stacking = StackingClassifier(estimators=[('xgb', xgb), ('lgb', lgb), ('cat', cat)],
                              final_estimator=LogisticRegression(), cv=5)
avaliar_modelo(stacking, X, y, "StackingClassifier")


xgb_best = xgb

# Carregar o dataset de teste
try:
    test_df = pd.read_csv('dataset-1m-relabel.csv')
    if 'timestamp' in test_df.columns:
        test_df = test_df.drop('timestamp', axis=1)
    X_test_new = test_df.drop('target', axis=1).values
    y_test_new = test_df['target'].values
    print("\n--- Avaliando modelos no test.csv ---")

    # Re-definir o dicionário de modelos para garantir que as referências estejam corretas
    # e incluir o stacking com um final_estimator treinado no conjunto completo
    modelos = {
        "XGBoost Otimizado": xgb_best,
        "LightGBM": LGBMClassifier(verbosity=-1),
        "CatBoost": CatBoostClassifier(verbose=0),
        "Voting Soft": VotingClassifier(estimators=[
            ('xgb', xgb_best), ('lgb', LGBMClassifier(verbosity=-1)), ('cat', CatBoostClassifier(verbose=0))
        ], voting='soft'),
        "Stacking": StackingClassifier(estimators=[
            ('xgb', xgb_best), ('lgb', LGBMClassifier(verbosity=-1)), ('cat', CatBoostClassifier(verbose=0))
        ], final_estimator=LogisticRegression(), cv=5) # cv=5 é para a meta-classificador, não para a validação externa
    }

    for nome, modelo in modelos.items():
        # Treinar o modelo no dataset completo (X, y) antes de testar no novo conjunto
        print(f"Treinando {nome} no dataset completo...")
        modelo.fit(X, y)
        preds_new = modelo.predict(X_test_new)
        f1_new = f1_score(y_test_new, preds_new, average='macro')
        print(f"{nome} no test.csv: F1-score = {f1_new:.4f}")

except FileNotFoundError:
    print("Erro: O arquivo 'test.csv' não foi encontrado. Por favor, verifique o nome ou o caminho do arquivo.")
except KeyError:
    print("Erro: O arquivo 'test.csv' deve conter uma coluna 'target'.")
except Exception as e:
    print(f"Ocorreu um erro inesperado: {e}")


## Validação Cruzada Manual (10-Fold) para Modelos Otimizados


modelos = {
    "XGBoost Otimizado": xgb_best,
    "LightGBM": LGBMClassifier(),
    "CatBoost": CatBoostClassifier(verbose=0),
    "Voting Soft": VotingClassifier(estimators=[
        ('xgb', xgb_best), ('lgb', LGBMClassifier()), ('cat', CatBoostClassifier(verbose=0))
    ], voting='soft'),
    "Stacking": StackingClassifier(estimators=[
        ('xgb', xgb_best), ('lgb', LGBMClassifier()), ('cat', CatBoostClassifier(verbose=0))
    ], final_estimator=LogisticRegression(), cv=5)
}

for nome, modelo in modelos.items():
    f1_scores = []
    for train_idx, test_idx in skf.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        modelo.fit(X_train, y_train)
        preds = modelo.predict(X_test)
        f1_scores.append(f1_score(y_test, preds, average='macro'))
    print(f"{nome}: F1-score médio = {np.mean(f1_scores):.4f}, desvio padrão = {np.std(f1_scores):.4f}")

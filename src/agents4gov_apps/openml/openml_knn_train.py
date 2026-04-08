import json
import os
from typing import List, Optional

import numpy as np
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    def _determine_task_type(self, y) -> str:
        """
        Determine if the task is classification or regression.

        Args:
            y: Target variable

        Returns:
            'classification' or 'regression'
        """
        if y.dtype == 'object' or y.dtype.name == 'category':
            return 'classification'

        return 'regression'

    def train_knn_with_cv(
        self,
        data_path: str = Field(
            ...,
            description="Path to the dataset file (CSV, Parquet, or JSON) downloaded using openml_download.py"
        ),
        target_column: str = Field(
            ...,
            description="Name of the target column in the dataset"
        ),
        n_neighbors_range: List[int] = Field(
            default=[3, 5, 7, 9, 11],
            description="List of k values to test for KNN (default: [3, 5, 7, 9, 11])"
        ),
        cv_folds: int = Field(
            default=5,
            description="Number of cross-validation folds (default: 5)"
        ),
        random_state: int = Field(
            default=42,
            description="Random seed for reproducibility (default: 42)"
        ),
        metric: Optional[str] = Field(
            default=None,
            description="Distance metric for KNN (default: 'minkowski' for both tasks). Options: 'euclidean', 'manhattan', 'minkowski', 'chebyshev'"
        ),
        weights: str = Field(
            default='uniform',
            description="Weight function for KNN (default: 'uniform'). Options: 'uniform', 'distance'"
        ),
        save_model_path: Optional[str] = Field(
            default=None,
            description="Optional path to save the trained model using joblib"
        )
    ) -> str:
        """
        Train a KNN model with cross-validation and hyperparameter tuning.

        Returns a JSON string with the selected parameters, cross-validation metrics, and optional model persistence details.

        Args:
            data_path: Path to the dataset file
            target_column: Name of the target variable
            n_neighbors_range: List of k values to test
            cv_folds: Number of cross-validation folds
            random_state: Random seed
            metric: Distance metric for KNN
            weights: Weight function for KNN
            save_model_path: Path to save the model

        Returns:
            JSON string with cross-validation results, best parameters, and mean metrics
        """

        try:
            import joblib
            import pandas as pd
            from sklearn.model_selection import GridSearchCV, KFold, StratifiedKFold
            from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import LabelEncoder, StandardScaler

            if not os.path.exists(data_path):
                error_result = {
                    'status': 'error',
                    'error_type': 'file_not_found',
                    'message': f'Dataset file not found: {data_path}',
                    'data_path': data_path
                }
                return json.dumps(error_result, ensure_ascii=False, indent=2)

            try:
                if data_path.endswith('.csv'):
                    df = pd.read_csv(data_path)
                elif data_path.endswith('.parquet'):
                    df = pd.read_parquet(data_path)
                elif data_path.endswith('.json'):
                    df = pd.read_json(data_path)
                else:
                    error_result = {
                        'status': 'error',
                        'error_type': 'unsupported_format',
                        'message': f'Unsupported file format. Please use CSV, Parquet, or JSON.',
                        'data_path': data_path
                    }
                    return json.dumps(error_result, ensure_ascii=False, indent=2)

            except Exception as e:
                error_result = {
                    'status': 'error',
                    'error_type': 'load_error',
                    'message': f'Error loading dataset: {str(e)}',
                    'data_path': data_path
                }
                return json.dumps(error_result, ensure_ascii=False, indent=2)

            if target_column not in df.columns:
                error_result = {
                    'status': 'error',
                    'error_type': 'column_not_found',
                    'message': f'Target column "{target_column}" not found in dataset',
                    'available_columns': list(df.columns),
                    'data_path': data_path
                }
                return json.dumps(error_result, ensure_ascii=False, indent=2)

            X = df.drop(columns=[target_column])
            y = df[target_column]

            if X.isnull().any().any():
                for col in X.columns:
                    if np.issubdtype(X[col].dtype, np.number):
                        X[col].fillna(X[col].mean(), inplace=True)
                    else:
                        X[col].fillna(X[col].mode()[0] if not X[col].mode().empty else 'missing', inplace=True)

            if y.isnull().any():
                y.fillna(y.mode()[0] if not y.mode().empty else 0, inplace=True)

            label_encoders = {}
            for col in X.columns:
                if X[col].dtype == 'object' or X[col].dtype.name == 'category':
                    le = LabelEncoder()
                    X[col] = le.fit_transform(X[col].astype(str))
                    label_encoders[col] = le

            task_type = self._determine_task_type(y)

            target_encoder = None
            if task_type == 'classification':
                if y.dtype == 'object' or y.dtype.name == 'category':
                    target_encoder = LabelEncoder()
                    y = target_encoder.fit_transform(y.astype(str))

            if task_type == 'classification':
                cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
                model = KNeighborsClassifier()
                scoring = {
                    'accuracy': 'accuracy',
                    'precision': 'precision_weighted',
                    'recall': 'recall_weighted',
                    'f1': 'f1_weighted'
                }
                refit_metric = 'accuracy'
            else:
                cv = KFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
                model = KNeighborsRegressor()
                scoring = {
                    'neg_mse': 'neg_mean_squared_error',
                    'neg_mae': 'neg_mean_absolute_error',
                    'r2': 'r2'
                }
                refit_metric = 'neg_mse'

            pipeline = Pipeline([
                ('scaler', StandardScaler()),
                ('knn', model)
            ])

            param_grid = {
                'knn__n_neighbors': n_neighbors_range,
                'knn__weights': [weights]
            }

            if metric:
                param_grid['knn__metric'] = [metric]

            grid_search = GridSearchCV(
                estimator=pipeline,
                param_grid=param_grid,
                cv=cv,
                scoring=scoring,
                refit=refit_metric,
                n_jobs=-1,
                verbose=0,
                return_train_score=False
            )

            # Convert all data to numpy arrays
            X_array = X.values if hasattr(X, 'values') else X
            y_array = y.values if hasattr(y, 'values') else y

            grid_search.fit(X_array, y_array)

            best_pipeline = grid_search.best_estimator_
            best_params = grid_search.best_params_

            best_params_clean = {k.replace('knn__', ''): v for k, v in best_params.items()}

            best_index = grid_search.best_index_
            metrics = {}

            if task_type == 'classification':
                metrics['accuracy'] = {
                    'mean': float(grid_search.cv_results_[f'mean_test_accuracy'][best_index]),
                    'std': float(grid_search.cv_results_[f'std_test_accuracy'][best_index])
                }
                metrics['precision'] = {
                    'mean': float(grid_search.cv_results_[f'mean_test_precision'][best_index]),
                    'std': float(grid_search.cv_results_[f'std_test_precision'][best_index])
                }
                metrics['recall'] = {
                    'mean': float(grid_search.cv_results_[f'mean_test_recall'][best_index]),
                    'std': float(grid_search.cv_results_[f'std_test_recall'][best_index])
                }
                metrics['f1_score'] = {
                    'mean': float(grid_search.cv_results_[f'mean_test_f1'][best_index]),
                    'std': float(grid_search.cv_results_[f'std_test_f1'][best_index])
                }
            else:  # regression
                mse_mean = -float(grid_search.cv_results_[f'mean_test_neg_mse'][best_index])
                mse_std = float(grid_search.cv_results_[f'std_test_neg_mse'][best_index])
                mae_mean = -float(grid_search.cv_results_[f'mean_test_neg_mae'][best_index])
                mae_std = float(grid_search.cv_results_[f'std_test_neg_mae'][best_index])
                r2_mean = float(grid_search.cv_results_[f'mean_test_r2'][best_index])
                r2_std = float(grid_search.cv_results_[f'std_test_r2'][best_index])

                metrics['mse'] = {
                    'mean': mse_mean,
                    'std': mse_std
                }
                metrics['rmse'] = {
                    'mean': float(np.sqrt(mse_mean)),
                    'std': mse_std
                }
                metrics['mae'] = {
                    'mean': mae_mean,
                    'std': mae_std
                }
                metrics['r2_score'] = {
                    'mean': r2_mean,
                    'std': r2_std
                }

            cv_results = {
                'best_score': float(grid_search.best_score_),
                'all_params_scores': [
                    {
                        'params': {k.replace('knn__', ''): v for k, v in params.items()},
                        'mean_score': float(score),
                        'std_score': float(std)
                    }
                    for params, score, std in zip(
                        grid_search.cv_results_['params'],
                        grid_search.cv_results_[f'mean_test_{refit_metric}'],
                        grid_search.cv_results_[f'std_test_{refit_metric}']
                    )
                ]
            }

            model_info = {}
            if save_model_path:
                try:
                    os.makedirs(os.path.dirname(save_model_path) if os.path.dirname(save_model_path) else '.', exist_ok=True)
                    model_package = {
                        'pipeline': best_pipeline,
                        'label_encoders': label_encoders,
                        'target_encoder': target_encoder,
                        'task_type': task_type,
                        'feature_names': list(X.columns),
                        'best_params': best_params_clean
                    }

                    joblib.dump(model_package, save_model_path)

                    model_info['saved'] = True
                    model_info['save_path'] = save_model_path
                    model_info['file_size_bytes'] = os.path.getsize(save_model_path)

                except Exception as e:
                    model_info['save_error'] = str(e)

            result = {
                'status': 'success',
                'task_type': task_type,
                'dataset_info': {
                    'data_path': data_path,
                    'total_samples': len(df),
                    'num_features': X.shape[1],
                    'target_column': target_column,
                    'num_classes': int(len(np.unique(y))) if task_type == 'classification' else None,
                    'cv_folds': cv_folds
                },
                'best_parameters': best_params_clean,
                'hyperparameter_search': cv_results,
                'cross_validation_metrics': metrics,
                'model_info': model_info if model_info else None
            }

            return json.dumps(result, ensure_ascii=False, indent=2)

        except ImportError as e:
            error_result = {
                'status': 'error',
                'error_type': 'missing_dependency',
                'message': f'Required package not installed: {str(e)}. Please install with: pip install scikit-learn pandas joblib',
                'data_path': data_path
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)

        except Exception as e:
            error_result = {
                'status': 'error',
                'error_type': 'unexpected_error',
                'message': f'Unexpected error during training: {str(e)}',
                'data_path': data_path
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)

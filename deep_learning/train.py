"""
模型訓練腳本
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import matplotlib.pyplot as plt
import os
from datetime import datetime

from data.data_loader import load_stock_data, add_derived_features
from data.feature_engineering import generate_labels, prepare_features, normalize_features, create_sequences
from data.dataset import StockDataset
from models.lstm_model import StockLSTM
from config import *

class EarlyStopping:
    """Early Stopping機制"""
    
    def __init__(self, patience=10, min_delta=0, mode='min'):
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        
    def __call__(self, score):
        if self.best_score is None:
            self.best_score = score
        elif self._is_improvement(score):
            self.best_score = score
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        
        return self.early_stop
    
    def _is_improvement(self, score):
        if self.mode == 'min':
            return score < self.best_score - self.min_delta
        else:
            return score > self.best_score + self.min_delta

def train_epoch(model, dataloader, criterion, optimizer, device):
    """訓練一個epoch"""
    model.train()
    total_loss = 0
    all_preds = []
    all_labels = []
    
    for X_batch, y_batch in dataloader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device).unsqueeze(1)
        
        # Forward pass
        optimizer.zero_grad()
        outputs = model(X_batch)
        loss = criterion(outputs, y_batch)
        
        # Backward pass
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        
        # 收集預測結果
        preds = (outputs > 0.5).float()
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(y_batch.cpu().numpy())
    
    avg_loss = total_loss / len(dataloader)
    accuracy = accuracy_score(all_labels, all_preds)
    
    return avg_loss, accuracy

def validate(model, dataloader, criterion, device):
    """驗證"""
    model.eval()
    total_loss = 0
    all_preds = []
    all_probs = []
    all_labels = []
    
    with torch.no_grad():
        for X_batch, y_batch in dataloader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device).unsqueeze(1)
            
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            
            total_loss += loss.item()
            
            preds = (outputs > 0.5).float()
            all_preds.extend(preds.cpu().numpy())
            all_probs.extend(outputs.cpu().numpy())
            all_labels.extend(y_batch.cpu().numpy())
    
    avg_loss = total_loss / len(dataloader)
    
    # 計算指標
    accuracy = accuracy_score(all_labels, all_preds)
    precision = precision_score(all_labels, all_preds, zero_division=0)
    recall = recall_score(all_labels, all_preds, zero_division=0)
    f1 = f1_score(all_labels, all_preds, zero_division=0)
    
    # ROC-AUC
    try:
        roc_auc = roc_auc_score(all_labels, all_probs)
    except:
        roc_auc = 0.5
    
    metrics = {
        'loss': avg_loss,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'roc_auc': roc_auc
    }
    
    return metrics

def plot_training_history(history, save_path='training_history.png'):
    """繪製訓練歷史"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Loss
    axes[0, 0].plot(history['train_loss'], label='Train')
    axes[0, 0].plot(history['val_loss'], label='Validation')
    axes[0, 0].set_title('Loss')
    axes[0, 0].set_xlabel('Epoch')
    axes[0, 0].legend()
    axes[0, 0].grid(True)
    
    # Accuracy
    axes[0, 1].plot(history['train_acc'], label='Train')
    axes[0, 1].plot(history['val_acc'], label='Validation')
    axes[0, 1].set_title('Accuracy')
    axes[0, 1].set_xlabel('Epoch')
    axes[0, 1].legend()
    axes[0, 1].grid(True)
    
    # F1 Score
    axes[1, 0].plot(history['val_f1'], label='F1')
    axes[1, 0].plot(history['val_precision'], label='Precision')
    axes[1, 0].plot(history['val_recall'], label='Recall')
    axes[1, 0].set_title('Validation Metrics')
    axes[1, 0].set_xlabel('Epoch')
    axes[1, 0].legend()
    axes[1, 0].grid(True)
    
    # ROC-AUC
    axes[1, 1].plot(history['val_roc_auc'])
    axes[1, 1].set_title('Validation ROC-AUC')
    axes[1, 1].set_xlabel('Epoch')
    axes[1, 1].grid(True)
    
    plt.tight_layout()
    plt.savefig(save_path)
    print(f"Training history plot saved to {save_path}")
    plt.close()

def main():
    print("="*60)
    print("台積電深度學習交易系統 - 模型訓練")
    print("="*60)
    
    # 設定device
    device = torch.device('cuda' if torch.cuda.is_available() and TRAINING_CONFIG['device'] == 'cuda' else 'cpu')
    print(f"\nUsing device: {device}")
    
    # 1. 加載數據
    print("\n[1/6] Loading data...")
    train_df = load_stock_data(SYMBOL, TRAIN_START_DATE, TRAIN_END_DATE)
    train_df = add_derived_features(train_df)
    
    # 2. 生成標籤和特徵
    print("\n[2/6] Generating features and labels...")
    train_labels = generate_labels(train_df, **LABEL_CONFIG)
    train_features = prepare_features(train_df, FEATURES)
    
    # 標準化
    train_features_norm, scaler = normalize_features(train_features)
    
    # 保存scaler供後續使用
    import joblib
    os.makedirs('models/saved', exist_ok=True)
    joblib.dump(scaler, 'models/saved/scaler.pkl')
    print("Scaler saved to models/saved/scaler.pkl")
    
    # 3. 創建序列
    print("\n[3/6] Creating sequences...")
    X, y, indices = create_sequences(train_features_norm, train_labels, SEQUENCE_LENGTH)
    print(f"Total sequences: {len(X)}")
    print(f"Positive samples: {y.sum()} ({y.mean()*100:.1f}%)")
    
    # 4. 創建Dataset和DataLoader
    print("\n[4/6] Creating datasets...")
    dataset = StockDataset(X, y, indices)
    
    # 分割訓練集和驗證集 (80/20)
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=TRAINING_CONFIG['batch_size'], shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=TRAINING_CONFIG['batch_size'], shuffle=False)
    
    print(f"Train size: {train_size}, Validation size: {val_size}")
    
    # 5. 創建模型
    print("\n[5/6] Creating model...")
    input_size = len(FEATURES)
    model = StockLSTM(
        input_size=input_size,
        hidden_size=MODEL_CONFIG['hidden_size'],
        num_layers=MODEL_CONFIG['num_layers'],
        dropout=MODEL_CONFIG['dropout']
    ).to(device)
    
    print(model)
    print(f"Total parameters: {sum(p.numel() for p in model.parameters())}")
    
    # 損失函數和優化器
    criterion = nn.BCELoss()
    optimizer = optim.Adam(
        model.parameters(),
        lr=TRAINING_CONFIG['learning_rate'],
        weight_decay=TRAINING_CONFIG['weight_decay']
    )
    
    # Early stopping
    early_stopping = EarlyStopping(
        patience=TRAINING_CONFIG['early_stopping_patience'],
        mode='min'
    )
    
    # 6. 訓練
    print("\n[6/6] Training...")
    print("="*60)
    
    history = {
        'train_loss': [], 'train_acc': [],
        'val_loss': [], 'val_acc': [],
        'val_precision': [], 'val_recall': [],
        'val_f1': [], 'val_roc_auc': []
    }
    
    best_val_loss = float('inf')
    best_model_path = 'models/saved/best_model.pth'
    
    for epoch in range(TRAINING_CONFIG['epochs']):
        # 訓練
        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        
        # 驗證
        val_metrics = validate(model, val_loader, criterion, device)
        
        # 記錄歷史
        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)
        history['val_loss'].append(val_metrics['loss'])
        history['val_acc'].append(val_metrics['accuracy'])
        history['val_precision'].append(val_metrics['precision'])
        history['val_recall'].append(val_metrics['recall'])
        history['val_f1'].append(val_metrics['f1'])
        history['val_roc_auc'].append(val_metrics['roc_auc'])
        
        # 打印進度
        print(f"Epoch {epoch+1}/{TRAINING_CONFIG['epochs']}")
        print(f"  Train - Loss: {train_loss:.4f}, Acc: {train_acc:.4f}")
        print(f"  Val   - Loss: {val_metrics['loss']:.4f}, Acc: {val_metrics['accuracy']:.4f}, "
              f"F1: {val_metrics['f1']:.4f}, ROC-AUC: {val_metrics['roc_auc']:.4f}")
        
        # 保存最佳模型
        if val_metrics['loss'] < best_val_loss:
            best_val_loss = val_metrics['loss']
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_metrics['loss'],
                'val_metrics': val_metrics
            }, best_model_path)
            print(f"  → Best model saved!")
        
        # Early stopping
        if early_stopping(val_metrics['loss']):
            print(f"\nEarly stopping triggered at epoch {epoch+1}")
            break
    
    # 繪製訓練歷史
    plot_training_history(history, 'models/saved/training_history.png')
    
    # 保存歷史
    pd.DataFrame(history).to_csv('models/saved/training_history.csv', index=False)
    
    print("\n" + "="*60)
    print("Training completed!")
    print(f"Best model saved to: {best_model_path}")
    print("="*60)

if __name__ == "__main__":
    main()

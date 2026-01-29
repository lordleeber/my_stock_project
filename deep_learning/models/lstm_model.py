"""
LSTM模型定義
"""
import torch
import torch.nn as nn

class StockLSTM(nn.Module):
    """
    LSTM模型用於股票交易預測
    """
    
    def __init__(self, input_size, hidden_size=128, num_layers=2, dropout=0.3):
        """
        Args:
            input_size: 輸入特徵數量
            hidden_size: LSTM隱藏層大小
            num_layers: LSTM層數
            dropout: Dropout比率
        """
        super(StockLSTM, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM層
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Dropout層
        self.dropout = nn.Dropout(dropout)
        
        # 全連接層
        self.fc1 = nn.Linear(hidden_size, 64)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 1)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        """
        Args:
            x: (batch_size, sequence_length, input_size)
        
        Returns:
            output: (batch_size, 1) 持有機率
        """
        # LSTM
        lstm_out, (h_n, c_n) = self.lstm(x)
        
        # 取最後一個時間步的輸出
        last_output = lstm_out[:, -1, :]
        
        # Dropout
        out = self.dropout(last_output)
        
        # 全連接層
        out = self.fc1(out)
        out = self.relu(out)
        out = self.dropout(out)
        
        out = self.fc2(out)
        out = self.relu(out)
        out = self.dropout(out)
        
        out = self.fc3(out)
        out = self.sigmoid(out)
        
        return out

if __name__ == "__main__":
    # 測試模型
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import FEATURES, MODEL_CONFIG
    
    # 創建模型
    input_size = len(FEATURES)
    model = StockLSTM(
        input_size=input_size,
        hidden_size=MODEL_CONFIG['hidden_size'],
        num_layers=MODEL_CONFIG['num_layers'],
        dropout=MODEL_CONFIG['dropout']
    )
    
    print(model)
    print(f"\nTotal parameters: {sum(p.numel() for p in model.parameters())}")
    
    # 測試forward pass
    batch_size = 32
    seq_len = 20
    x = torch.randn(batch_size, seq_len, input_size)
    output = model(x)
    print(f"\nInput shape: {x.shape}")
    print(f"Output shape: {output.shape}")
    print(f"Output range: [{output.min().item():.4f}, {output.max().item():.4f}]")

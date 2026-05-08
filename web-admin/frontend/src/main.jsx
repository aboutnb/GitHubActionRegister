import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, theme } from 'antd';
import AppRouter from './router';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#2563eb',
          borderRadius: 8,
          colorBgLayout: '#f5f7fb',
        },
      }}
    >
      <AppRouter />
    </ConfigProvider>
  </React.StrictMode>,
);

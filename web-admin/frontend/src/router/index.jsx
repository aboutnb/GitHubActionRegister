import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Spin } from 'antd';
import { AuthProvider, useAuth } from '../context/AuthContext';
import AppLayout from '../layout/AppLayout';
import AuditLogsPage from '../pages/AuditLogsPage';
import BatchesPage from '../pages/BatchesPage';
import ClientsPage from '../pages/ClientsPage';
import DashboardPage from '../pages/DashboardPage';
import GitHubAccountsPage from '../pages/GitHubAccountsPage';
import LoginPage from '../pages/LoginPage';
import LogsPage from '../pages/LogsPage';
import MailAccountsPage from '../pages/MailAccountsPage';

function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  if (checking) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }
  return user ? children : <Navigate to="/login" replace />;
}

export default function AppRouter() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <AppLayout>
                  <DashboardPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/mail-accounts"
            element={
              <RequireAuth>
                <AppLayout>
                  <MailAccountsPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/github-accounts"
            element={
              <RequireAuth>
                <AppLayout>
                  <GitHubAccountsPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/clients"
            element={
              <RequireAuth>
                <AppLayout>
                  <ClientsPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/batches"
            element={
              <RequireAuth>
                <AppLayout>
                  <BatchesPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/logs"
            element={
              <RequireAuth>
                <AppLayout>
                  <LogsPage />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/audit-logs"
            element={
              <RequireAuth>
                <AppLayout>
                  <AuditLogsPage />
                </AppLayout>
              </RequireAuth>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

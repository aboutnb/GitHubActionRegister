import React from 'react';
import {
  ApiOutlined,
  BellOutlined,
  FileSearchOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  LogoutOutlined,
  MailOutlined,
  OrderedListOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Space, Tag } from 'antd';
import { ProLayout } from '@ant-design/pro-components';
import { useLocation, useNavigate } from 'react-router-dom';
import { BrandLockup } from '../components/BrandLogo';
import { logout } from '../services/api';
import { useAuth } from '../context/AuthContext';

const menuItems = [
  { path: '/', name: '仪表盘', icon: <DashboardOutlined /> },
  { path: '/mail-accounts', name: '邮箱资产', icon: <MailOutlined /> },
  { path: '/github-accounts', name: 'GitHub 账号库', icon: <DatabaseOutlined /> },
  { path: '/clients', name: '客户端密钥', icon: <ApiOutlined /> },
  { path: '/batches', name: '批次中心', icon: <OrderedListOutlined /> },
  { path: '/logs', name: '同步日志', icon: <SafetyCertificateOutlined /> },
  { path: '/audit-logs', name: '审计日志', icon: <FileSearchOutlined /> },
];

export default function AppLayout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, setUser } = useAuth();
  const role = user?.role || 'admin';

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setUser(null);
      window.location.href = '/login';
    }
  };

  return (
    <ProLayout
      className="asset-layout"
      title="GitHub Asset Center"
      logo={false}
      location={{ pathname: location.pathname }}
      route={{ path: '/', routes: menuItems }}
      menuItemRender={(item, dom) => (
        <div onClick={() => navigate(item.path)}>{dom}</div>
      )}
      layout="mix"
      navTheme="light"
      fixSiderbar
      fixedHeader
      siderWidth={248}
      headerTitleRender={() => (
        <BrandLockup size="md" title="Asset Center" subtitle="GitHub 资产中控台" onClick={() => navigate('/')} />
      )}
      avatarProps={{
        title: role.toUpperCase(),
        size: 'small',
        render: (_, dom) => (
          <div className="layout-avatar">
            <Avatar size={32} style={{ background: '#2563eb' }}>
              {role.slice(0, 1).toUpperCase()}
            </Avatar>
            {dom}
          </div>
        ),
      }}
      actionsRender={() => [
        <div className="layout-topbar" key="layout-topbar">
          <Tag color="blue">运营中</Tag>
          <Space size={8}>
            <Button type="text" shape="circle" icon={<BellOutlined />} />
            <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout}>
              退出
            </Button>
          </Space>
        </div>,
      ]}
      token={{
        pageContainer: {
          colorBgPageContainer: '#f5f7fb',
        },
      }}
    >
      {children}
    </ProLayout>
  );
}

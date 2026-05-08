import React, { useState } from 'react';
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography, message } from 'antd';
import { login } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const { refreshUser } = useAuth();

  const handleFinish = async (values) => {
    setLoading(true);
    try {
      await login(values);
      await refreshUser();
      window.location.href = '/';
    } catch (error) {
      message.error(error?.response?.data?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-shell__panel">
        <div className="login-shell__intro">
          <span className="login-shell__eyebrow">Asset Command</span>
          <Typography.Title level={2}>登录资产管理后台</Typography.Title>
          <Typography.Paragraph>
            统一管理邮箱资产、GitHub 成品账号、客户端密钥和批次审计，所有关键指标在同一处收口。
          </Typography.Paragraph>
          <div className="login-shell__feature-list">
            <div>
              <strong>邮箱 / GitHub</strong>
              <span>库存、状态、导出一屏串起来</span>
            </div>
            <div>
              <strong>同步监控</strong>
              <span>客户端在线、批次结果、吞吐趋势可视化</span>
            </div>
            <div>
              <strong>审计闭环</strong>
              <span>敏感操作留痕，方便回看问题与来源</span>
            </div>
          </div>
        </div>
        <Card className="login-card">
          <div className="login-card__badge">
            <SafetyCertificateOutlined />
            <span>安全访问</span>
          </div>
          <Typography.Title level={3}>账号登录</Typography.Title>
          <Typography.Paragraph>
            使用管理员账号进入资产中控台。
          </Typography.Paragraph>
          <Form layout="vertical" onFinish={handleFinish}>
            <Form.Item label="用户名" name="username" rules={[{ required: true }]}>
              <Input prefix={<UserOutlined />} placeholder="admin" />
            </Form.Item>
            <Form.Item label="密码" name="password" rules={[{ required: true }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录后台
            </Button>
          </Form>
        </Card>
      </div>
    </div>
  );
}
